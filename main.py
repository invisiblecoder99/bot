import os
import threading
from datetime import timezone
from flask import Flask
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================
BOT_TOKEN = os.environ["BOT_TOKEN"]

ADMIN_ID = int(os.environ.get("ADMIN_ID", "6656836923"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "streaminghelpadmin").lstrip("@")

# Map: admin_message_id -> target chat/user
MESSAGE_MAP: dict[int, dict] = {}

# ================= RAILWAY HTTP =================
app = Flask(__name__)

@app.get("/")
def home():
    return "OK", 200

def run_http():
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Send your message here and admin will reply.\n"
        "Use /contact for direct admin contact."
    )

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📞 Contact admin: @{ADMIN_USERNAME}\nhttps://t.me/{ADMIN_USERNAME}",
        disable_web_page_preview=True
    )

# ================= HELPERS =================
def fmt_dt(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if dt else "unknown"

async def build_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    user = update.effective_user
    chat = update.effective_chat
    msg = update.effective_message

    # Profile photos count (best effort)
    photos_count = "unknown"
    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
        photos_count = str(photos.total_count)
    except Exception:
        pass

    username = f"@{user.username}" if user.username else "no_username"
    full_name = user.full_name or ""
    lang = user.language_code or "unknown"
    is_premium = getattr(user, "is_premium", None)
    premium = "unknown" if is_premium is None else str(is_premium)

    chat_type = chat.type
    chat_title = getattr(chat, "title", "") or "n/a"
    chat_username = f"@{chat.username}" if getattr(chat, "username", None) else "n/a"

    text = msg.text or msg.caption or "(no text)"

    return (
        "🧷 <b>REPLY TO THIS MESSAGE TO REPLY TO USER</b>\n"
        "──────────────────────────────\n"
        "📩 <b>New message</b>\n"
        f"🕒 <b>Date:</b> {fmt_dt(msg.date)}\n\n"
        f"👤 <b>Name:</b> {full_name}\n"
        f"🔗 <b>Username:</b> {username}\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
        f"🌐 <b>Language:</b> <code>{lang}</code>\n"
        f"⭐ <b>Premium:</b> <code>{premium}</code>\n"
        f"🖼️ <b>Profile photos:</b> <code>{photos_count}</code>\n\n"
        f"💬 <b>Chat type:</b> <code>{chat_type}</code>\n"
        f"🏷️ <b>Chat title:</b> {chat_title}\n"
        f"🔗 <b>Chat username:</b> {chat_username}\n"
        f"🆔 <b>Chat ID:</b> <code>{chat.id}</code>\n"
        f"🧾 <b>Message ID:</b> <code>{msg.message_id}</code>\n\n"
        f"📝 <b>Message:</b>\n{text}"
    )

# ================= HANDLERS =================
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    chat = update.effective_chat

    # Ignore admin sending messages
    if user and user.id == ADMIN_ID:
        return

    details = await build_details(update, context)

    sent = await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=details,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

    MESSAGE_MAP[sent.message_id] = {
        "chat_id": chat.id,
        "user_id": user.id,
    }

    await msg.reply_text("✅ Message sent to admin. Please wait for reply.")

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    if not msg or not msg.from_user or msg.from_user.id != ADMIN_ID:
        return

    if not msg.reply_to_message:
        return

    # Walk reply chain to find original details message
    cur = msg.reply_to_message
    target = None

    for _ in range(8):
        target = MESSAGE_MAP.get(cur.message_id)
        if target:
            break
        if not cur.reply_to_message:
            break
        cur = cur.reply_to_message

    if not target:
        await msg.reply_text("⚠️ Cannot find original user (bot restart or old message).")
        return

    reply_text = msg.text or msg.caption
    if not reply_text:
        await msg.reply_text("⚠️ Only text replies supported.")
        return

    await context.bot.send_message(
        chat_id=target["chat_id"],
        text=f"💬 <b>Admin reply</b>:\n\n{reply_text}",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

# ================= MAIN =================
def main():
    threading.Thread(target=run_http, daemon=True).start()

    app_bot = Application.builder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("contact", contact))

    # IMPORTANT: admin reply FIRST
    app_bot.add_handler(MessageHandler(filters.REPLY & (filters.TEXT | filters.CAPTION), handle_admin_reply))
    app_bot.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_user_message))

    app_bot.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
