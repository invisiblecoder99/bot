import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.environ["BOT_TOKEN"]

ADMIN_ID = int(os.environ.get("ADMIN_ID", "6656836923"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "streaminghelpadmin").lstrip("@")

# Map: admin_message_id -> user_id (in-memory)
MESSAGE_MAP: dict[int, int] = {}

# --- tiny web server for Railway health ---
app = Flask(__name__)

@app.get("/")
def home():
    return "OK", 200

def run_http():
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

# --- bot handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! Send your message here. Admin will reply.\n"
        "Use /contact to DM admin directly."
    )

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Contact admin: @{ADMIN_USERNAME}\nhttps://t.me/{ADMIN_USERNAME}",
        disable_web_page_preview=True
    )

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message

    text = msg.text or ""
    header = (
        "📩 New message\n"
        f"👤 {user.first_name or ''} @{(user.username or 'no_username')}\n"
        f"🆔 {user.id}\n\n"
    )

    # Send to admin
    sent = await context.bot.send_message(chat_id=ADMIN_ID, text=header + text)

    # Store mapping so admin reply can route back
    MESSAGE_MAP[sent.message_id] = user.id

    await msg.reply_text("✅ Sent to admin. Please wait for reply.")

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.from_user.id != ADMIN_ID:
        return

    # Must be a reply to the bot's admin message
    if not msg.reply_to_message:
        return

    replied_to_id = msg.reply_to_message.message_id
    user_id = MESSAGE_MAP.get(replied_to_id)
    if not user_id:
        return

    await context.bot.send_message(
        chat_id=user_id,
        text=f"💬 Admin reply:\n\n{msg.text}",
        disable_web_page_preview=True
    )

def main():
    # Start HTTP server in background thread
    threading.Thread(target=run_http, daemon=True).start()

    # Start Telegram polling
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("contact", contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
    application.add_handler(MessageHandler(filters.REPLY & filters.TEXT, handle_admin_reply))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
