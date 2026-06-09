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

# sessions[user_id] = { questions, current, correct, chat_id, nav_msg_id }
sessions: dict[int, dict] = {}

NEXT_CB = "next"
STOP_CB = "stop"


# ── keyboard ──────────────────────────────────────────────────────────────────

def _nav_keyboard(current: int, total: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"➡️  Keyingisi  ({current}/{total})", callback_data=NEXT_CB),
        InlineKeyboardButton("🛑 Tugatish", callback_data=STOP_CB),
    ]])


# ── core ──────────────────────────────────────────────────────────────────────

async def _send_question(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    session = sessions.get(user_id)
    if not session:
        return

    idx = session["current"]
    questions = session["questions"]
    chat_id = session["chat_id"]

    # Delete old nav message
    if session.get("nav_msg_id"):
        try:
            await context.bot.delete_message(chat_id, session["nav_msg_id"])
        except Exception:
            pass
        session["nav_msg_id"] = None

    if idx >= len(questions):
        await _finish_session(context, user_id)
        return

    q = questions[idx]
    options = [q["option_a"], q["option_b"], q["option_c"], q["option_d"]]
    # Drop placeholder options for Yes/No questions
    options = [o for o in options if o and o != "-"]
    correct_map = {"A": 0, "B": 1, "C": 2, "D": 3}
    correct_idx = correct_map[q["correct_answer"].upper()]
    if correct_idx >= len(options):
        # Data issue — skip question
        session["current"] += 1
        await _send_question(context, user_id)
        return

    poll_msg = await context.bot.send_poll(
        chat_id=chat_id,
        question=q["question"][:299],
        options=[o[:99] for o in options],
        type=Poll.QUIZ,
        correct_option_id=correct_idx,
        is_anonymous=True,
    )

    session["current"] += 1

    # Send navigation buttons as a separate message
    nav_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"👇 Javob bering, keyin davom eting.",
        reply_markup=_nav_keyboard(idx + 1, len(questions)),
    )
    session["nav_msg_id"] = nav_msg.message_id


async def _finish_session(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    session = sessions.pop(user_id, None)
    if not session:
        return

    chat_id = session["chat_id"]
    correct = session["correct"]
    total = session["current"]

    if session.get("nav_msg_id"):
        try:
            await context.bot.delete_message(chat_id, session["nav_msg_id"])
        except Exception:
            pass

    if total == 0:
        return

    db.update_stats(user_id, 0, total)

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"✅ <b>Test yakunlandi!</b>\n\n"
            f"📝 Ishlangan savollar: <b>{total}</b>\n\n"
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
        "/test — barcha savollar (cheksiz)\n"
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

    sessions[user_id] = {
        "questions": questions,
        "current": 0,
        "correct": 0,
        "chat_id": update.effective_chat.id,
        "nav_msg_id": None,
    }

    await update.message.reply_text(
        f"🚀 Test boshlanmoqda — <b>{len(questions)}</b> ta savol!\n"
        "Javob bering, so'ng <b>➡️ Keyingisi</b> tugmasini bosing.",
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
