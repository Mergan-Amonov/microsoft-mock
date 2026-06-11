import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    ContextTypes,
)

import database as db
from parser import parse_file

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DOCS_DIR = Path(__file__).parent / "docs"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING,
)
logger = logging.getLogger(__name__)

# sessions[user_id] = {
#   all_questions, chunk_start, current, correct, wrong,
#   saved_correct, saved_answered, db_session_counted,
#   chat_id, nav_msg_id, poll_ids
# }
sessions: dict[int, dict] = {}

# poll_registry[poll_id] = { "user_id": int, "correct_id": int }
poll_registry: dict[str, dict] = {}

CHUNK_SIZE = 50
NEXT_CB = "next"
STOP_CB = "stop"
NEXT_CHUNK_CB = "next_chunk"
COUNT_PREFIX = "count_"  # count_10 / count_20 / count_50 / count_all


# ── keyboards ─────────────────────────────────────────────────────────────────

def _count_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 10 ta", callback_data=f"{COUNT_PREFIX}10"),
            InlineKeyboardButton("📝 20 ta", callback_data=f"{COUNT_PREFIX}20"),
            InlineKeyboardButton("📝 50 ta", callback_data=f"{COUNT_PREFIX}50"),
        ],
        [InlineKeyboardButton("📚 Hammasi", callback_data=f"{COUNT_PREFIX}all")],
    ])


def _nav_keyboard(current: int, total: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"➡️  Keyingisi  ({current}/{total})", callback_data=NEXT_CB),
        InlineKeyboardButton("🛑 Tugatish", callback_data=STOP_CB),
    ]])


def _chunk_keyboard(next_count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"▶️ Keyingi {next_count} ta savol", callback_data=NEXT_CHUNK_CB),
        InlineKeyboardButton("🛑 Tugatish", callback_data=STOP_CB),
    ]])


# ── stats helpers ───────────────────────────────────────────────────────────--

def _summary(session: dict) -> str:
    correct = session["correct"]
    wrong = session["wrong"]
    answered = correct + wrong
    skipped = session["current"] - answered
    pct = round(correct / answered * 100) if answered else 0

    lines = [
        f"✅ To'g'ri: <b>{correct}</b>",
        f"❌ Noto'g'ri: <b>{wrong}</b>",
    ]
    if skipped > 0:
        lines.append(f"⏭ Javobsiz: <b>{skipped}</b>")
    lines.append(f"🎯 Natija: <b>{pct}%</b>")
    return "\n".join(lines)


def _persist(user_id: int, session: dict):
    """Write the not-yet-saved correct/answered delta to the DB."""
    answered = session["correct"] + session["wrong"]
    delta_answered = answered - session["saved_answered"]
    delta_correct = session["correct"] - session["saved_correct"]

    if delta_answered <= 0 and session["db_session_counted"]:
        return

    inc_session = 0 if session["db_session_counted"] else 1
    db.update_stats(user_id, delta_correct, delta_answered, inc_session)

    session["saved_correct"] = session["correct"]
    session["saved_answered"] = answered
    session["db_session_counted"] = True


def _cleanup_polls(session: dict):
    for pid in session.get("poll_ids", []):
        poll_registry.pop(pid, None)
    session["poll_ids"] = []


# ── core ──────────────────────────────────────────────────────────────────────

async def _start_test(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int, n: int):
    total_available = db.count_questions()
    if total_available == 0:
        await context.bot.send_message(chat_id, "❌ Bazada savollar yo'q.")
        return

    n = max(1, min(n, total_available))
    questions = db.get_random_questions(n)

    # Cancel any active session (and free its poll registry entries)
    old = sessions.pop(user_id, None)
    if old:
        _cleanup_polls(old)

    sessions[user_id] = {
        "all_questions": questions,
        "chunk_start": 0,
        "current": 0,
        "correct": 0,
        "wrong": 0,
        "saved_correct": 0,
        "saved_answered": 0,
        "db_session_counted": False,
        "chat_id": chat_id,
        "nav_msg_id": None,
        "poll_ids": [],
    }

    first_chunk = min(CHUNK_SIZE, len(questions))
    extra = (
        f"Har safar <b>{CHUNK_SIZE}</b> tadan beriladi.\n"
        if len(questions) > CHUNK_SIZE else ""
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🚀 Test boshlanmoqda — jami <b>{len(questions)}</b> ta savol!\n"
            f"{extra}\nBirinchi qism: <b>{first_chunk}</b> ta savol"
        ),
        parse_mode="HTML",
    )
    await _send_question(context, user_id)


async def _send_question(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    session = sessions.get(user_id)
    if not session:
        return

    idx = session["current"]
    all_questions = session["all_questions"]
    chunk_start = session["chunk_start"]
    chunk_end = min(chunk_start + CHUNK_SIZE, len(all_questions))
    chat_id = session["chat_id"]

    # Delete old nav message
    if session.get("nav_msg_id"):
        try:
            await context.bot.delete_message(chat_id, session["nav_msg_id"])
        except Exception:
            pass
        session["nav_msg_id"] = None

    # Current chunk finished
    if idx >= chunk_end:
        await _finish_chunk(context, user_id)
        return

    q = all_questions[idx]
    options = [q["option_a"], q["option_b"], q["option_c"], q["option_d"]]
    options = [o for o in options if o and o != "-"]
    correct_map = {"A": 0, "B": 1, "C": 2, "D": 3}
    correct_idx = correct_map[q["correct_answer"].upper()]
    if correct_idx >= len(options):
        session["current"] += 1
        await _send_question(context, user_id)
        return

    poll_msg = await context.bot.send_poll(
        chat_id=chat_id,
        question=q["question"][:299],
        options=[o[:99] for o in options],
        type=Poll.QUIZ,
        correct_option_id=correct_idx,
        is_anonymous=False,
    )

    # Register the poll so we can score the answer later
    poll_registry[poll_msg.poll.id] = {"user_id": user_id, "correct_id": correct_idx}
    session["poll_ids"].append(poll_msg.poll.id)

    session["current"] += 1

    chunk_pos = idx - chunk_start + 1
    chunk_total = chunk_end - chunk_start

    nav_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="👇 Javob bering, keyin davom eting.",
        reply_markup=_nav_keyboard(chunk_pos, chunk_total),
    )
    session["nav_msg_id"] = nav_msg.message_id


async def _finish_chunk(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    session = sessions.get(user_id)
    if not session:
        return

    all_questions = session["all_questions"]
    chunk_start = session["chunk_start"]
    chunk_end = min(chunk_start + CHUNK_SIZE, len(all_questions))
    chat_id = session["chat_id"]
    chunk_num = chunk_start // CHUNK_SIZE + 1

    if session.get("nav_msg_id"):
        try:
            await context.bot.delete_message(chat_id, session["nav_msg_id"])
        except Exception:
            pass
        session["nav_msg_id"] = None

    _persist(user_id, session)

    has_more = chunk_end < len(all_questions)

    if has_more:
        remaining = len(all_questions) - chunk_end
        next_count = min(CHUNK_SIZE, remaining)
        text = (
            f"✅ <b>{chunk_num}-qism yakunlandi!</b>\n\n"
            f"📊 Umumiy progress: <b>{chunk_end} / {len(all_questions)}</b>\n\n"
            f"{_summary(session)}\n\n"
            f"Keyingi qismda <b>{next_count}</b> ta savol bor."
        )
        nav_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=_chunk_keyboard(next_count),
        )
        session["chunk_start"] = chunk_end
        session["nav_msg_id"] = nav_msg.message_id
    else:
        # All questions done
        summary = _summary(session)
        total = len(all_questions)
        _cleanup_polls(session)
        sessions.pop(user_id, None)
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🏁 <b>Test to'liq yakunlandi!</b>\n\n"
                f"📝 Jami savollar: <b>{total}</b>\n"
                f"{summary}\n\n"
                "Qayta boshlash uchun /test ni yuboring."
            ),
            parse_mode="HTML",
        )


async def _finish_session(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    session = sessions.pop(user_id, None)
    if not session:
        return

    chat_id = session["chat_id"]

    if session.get("nav_msg_id"):
        try:
            await context.bot.delete_message(chat_id, session["nav_msg_id"])
        except Exception:
            pass

    _persist(user_id, session)
    _cleanup_polls(session)

    if session["current"] == 0:
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🛑 <b>Test to'xtatildi.</b>\n\n"
            f"📝 Ishlangan savollar: <b>{session['current']}</b> / {len(session['all_questions'])}\n"
            f"{_summary(session)}\n\n"
            "Qayta boshlash uchun /test ni yuboring."
        ),
        parse_mode="HTML",
    )


# ── handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = db.count_questions()
    await update.message.reply_text(
        "👋 <b>Test Simulyatori</b>ga xush kelibsiz!\n\n"
        f"📦 Bazada <b>{total}</b> ta savol mavjud.\n\n"
        "Nechta savol yechmoqchisiz? 👇",
        parse_mode="HTML",
        reply_markup=_count_keyboard(),
    )


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Power-user shortcut: /test 30
    if context.args:
        try:
            n = int(context.args[0])
            await _start_test(context, user_id, chat_id, n)
            return
        except ValueError:
            pass

    await update.message.reply_text(
        "Nechta savol yechmoqchisiz? 👇",
        reply_markup=_count_keyboard(),
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in sessions:
        await update.message.reply_text("Hozir aktiv test yo'q.")
        return
    await _finish_session(context, user_id)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = db.get_stats(user_id)
    if not stats or stats["total_answered"] == 0:
        await update.message.reply_text("📊 Hali statistika yo'q. /test bilan boshlang!")
        return

    correct = stats["total_correct"]
    answered = stats["total_answered"]
    wrong = answered - correct
    pct = round(correct / answered * 100) if answered else 0
    await update.message.reply_text(
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"🔁 Testlar: <b>{stats['total_sessions']}</b>\n"
        f"✅ To'g'ri: <b>{correct}</b>\n"
        f"❌ Noto'g'ri: <b>{wrong}</b>\n"
        f"📝 Jami javoblar: <b>{answered}</b>\n"
        f"🎯 O'rtacha: <b>{pct}%</b>",
        parse_mode="HTML",
    )


async def cmd_load(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Sizda ruxsat yo'q.")
        return

    DOCS_DIR.mkdir(exist_ok=True)
    files = list(DOCS_DIR.glob("*.docx")) + list(DOCS_DIR.glob("*.pdf"))
    if not files:
        await update.message.reply_text(
            "📂 <code>docs/</code> papkasi bo'sh. DOCX/PDF qo'yib qayta /load bering.",
            parse_mode="HTML",
        )
        return

    report_lines = []
    for f in files:
        try:
            questions = parse_file(f)
            if not questions:
                report_lines.append(f"⚠️ {f.name} — savol topilmadi")
                continue
            saved = db.save_questions(questions, f.name)
            report_lines.append(f"✅ {f.name} — {saved} ta savol")
        except Exception as e:
            report_lines.append(f"❌ {f.name} — {e}")

    await update.message.reply_text(
        f"📥 <b>Yuklash yakunlandi</b>\n\n" + "\n".join(report_lines) +
        f"\n\n📦 Jami: <b>{db.count_questions()}</b> ta savol",
        parse_mode="HTML",
    )


async def cmd_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        f"📦 Bazada <b>{db.count_questions()}</b> ta savol.", parse_mode="HTML"
    )


async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    info = poll_registry.pop(answer.poll_id, None)
    if not info:
        return

    session = sessions.get(info["user_id"])
    if not session:
        return

    if not answer.option_ids:  # vote retracted (not possible for quiz, but guard)
        return

    if answer.option_ids[0] == info["correct_id"]:
        session["correct"] += 1
    else:
        session["wrong"] += 1


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    data = query.data

    # Count selection → start a test
    if data.startswith(COUNT_PREFIX):
        choice = data[len(COUNT_PREFIX):]
        n = db.count_questions() if choice == "all" else int(choice)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await _start_test(context, user_id, query.message.chat.id, n)
        return

    if data == STOP_CB:
        await _finish_session(context, user_id)
        return

    if data in (NEXT_CB, NEXT_CHUNK_CB):
        if user_id not in sessions:
            try:
                await query.edit_message_text("⚠️ Aktiv sessiya topilmadi. /test bosing.")
            except Exception:
                pass
            return
        await _send_question(context, user_id)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    db.init_db()
    DOCS_DIR.mkdir(exist_ok=True)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("load", cmd_load))
    app.add_handler(CommandHandler("count", cmd_count))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(PollAnswerHandler(poll_answer_handler))

    logger.warning("Bot ishga tushdi...")
    app.run_polling(allowed_updates=["message", "callback_query", "poll_answer"])


if __name__ == "__main__":
    main()
