import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
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

# sessions[user_id] = { all_questions, chunk_start, current, total_answered, chat_id, nav_msg_id }
sessions: dict[int, dict] = {}

CHUNK_SIZE = 50
NEXT_CB = "next"
STOP_CB = "stop"
NEXT_CHUNK_CB = "next_chunk"


# ── keyboards ─────────────────────────────────────────────────────────────────

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


# ── core ──────────────────────────────────────────────────────────────────────

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

    await context.bot.send_poll(
        chat_id=chat_id,
        question=q["question"][:299],
        options=[o[:99] for o in options],
        type=Poll.QUIZ,
        correct_option_id=correct_idx,
        is_anonymous=True,
    )

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
    chunk_count = chunk_end - chunk_start
    chat_id = session["chat_id"]
    chunk_num = chunk_start // CHUNK_SIZE + 1

    if session.get("nav_msg_id"):
        try:
            await context.bot.delete_message(chat_id, session["nav_msg_id"])
        except Exception:
            pass
        session["nav_msg_id"] = None

    db.update_stats(user_id, 0, chunk_count)
    session["total_answered"] += chunk_count

    has_more = chunk_end < len(all_questions)

    if has_more:
        remaining = len(all_questions) - chunk_end
        next_count = min(CHUNK_SIZE, remaining)
        text = (
            f"✅ <b>{chunk_num}-qism yakunlandi!</b>\n\n"
            f"📝 Bu qismda: <b>{chunk_count}</b> ta savol\n"
            f"📊 Umumiy progress: <b>{chunk_end} / {len(all_questions)}</b>\n\n"
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
        total = session["total_answered"]
        sessions.pop(user_id, None)
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🏁 <b>Test to'liq yakunlandi!</b>\n\n"
                f"📝 Jami ishlangan savollar: <b>{total}</b> / {len(all_questions)}\n\n"
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

    # Save progress for the current partial chunk
    unsaved = session["current"] - session["total_answered"]
    if unsaved > 0:
        db.update_stats(user_id, 0, unsaved)

    total = session["current"]
    if total == 0:
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🛑 <b>Test to'xtatildi.</b>\n\n"
            f"📝 Ishlangan savollar: <b>{total}</b> / {len(session['all_questions'])}\n\n"
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
        "📋 <b>Komandalar:</b>\n"
        "/test — 50 tadan savollar (barcha savollar)\n"
        "/stop — testni to'xtatish",
        parse_mode="HTML",
    )


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # How many questions
    total_available = db.count_questions()
    if context.args:
        try:
            n = max(1, min(int(context.args[0]), total_available))
        except ValueError:
            n = total_available
    else:
        n = total_available  # cheksiz — barcha savollar

    questions = db.get_random_questions(n)
    if not questions:
        await update.message.reply_text("❌ Bazada savollar yo'q.")
        return

    # Cancel any active session
    if user_id in sessions:
        sessions.pop(user_id)

    first_chunk = min(CHUNK_SIZE, len(questions))
    sessions[user_id] = {
        "all_questions": questions,
        "chunk_start": 0,
        "current": 0,
        "total_answered": 0,
        "chat_id": update.effective_chat.id,
        "nav_msg_id": None,
    }

    await update.message.reply_text(
        f"🚀 Test boshlanmoqda — jami <b>{len(questions)}</b> ta savol!\n"
        f"Har safar <b>{CHUNK_SIZE}</b> tadan beriladi.\n\n"
        f"Birinchi qism: <b>{first_chunk}</b> ta savol",
        parse_mode="HTML",
    )
    await _send_question(context, user_id)


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

    pct = round(stats["total_correct"] / stats["total_answered"] * 100)
    await update.message.reply_text(
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"🔁 Sessiyalar: <b>{stats['total_sessions']}</b>\n"
        f"✔️ To'g'ri: <b>{stats['total_correct']}</b> / {stats['total_answered']}\n"
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


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == STOP_CB:
        await _finish_session(context, user_id)
        return

    if query.data == NEXT_CB:
        if user_id not in sessions:
            try:
                await query.edit_message_text("⚠️ Aktiv sessiya topilmadi. /test bosing.")
            except Exception:
                pass
            return
        await _send_question(context, user_id)

    if query.data == NEXT_CHUNK_CB:
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

    logger.warning("Bot ishga tushdi...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
