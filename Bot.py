import asyncio
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

import config
from iVasms import iVasmsPanel

# Initialize iVasms panel
panel = iVasmsPanel(config.IVASMS_EMAIL, config.IVASMS_PASSWORD)

# Store active numbers and OTPs
active_numbers = {}
otp_cache = {}
auto_refresh_task = None

# Admin keyboard
def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 Users", callback_data='users')],
        [InlineKeyboardButton("📈 Stats", callback_data='stats')],
        [InlineKeyboardButton("🔄 Manual Range Refresh", callback_data='manual_refresh')],
        [InlineKeyboardButton("🌍 Add Numbers", callback_data='add_numbers')],
        [InlineKeyboardButton("🔘 Auto Range: ON", callback_data='toggle_auto')],
        [InlineKeyboardButton("📝 List Ranges", callback_data='list_ranges')],
        [InlineKeyboardButton("🍪 Set Cookies", callback_data='set_cookies')],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized! Only admin can use this bot.")
        return
    
    welcome_text = f"""
🤖 *OTP Bot Started!*

✅ Bot is active and ready.
📱 iVasms panel connected.

*Current Status:*
• Countries: {len(config.COUNTRIES)}
• Active Numbers: {len(active_numbers)}

Use /admin to open control panel.
    """
    
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    await update.message.reply_text(
        "🔧 *Admin Control Panel*\n\nSelect an option:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id != config.ADMIN_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    data = query.data
    
    if data == 'users':
        await query.edit_message_text("📊 *Users*\n\nAdmin only. Total: 1 user", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    elif data == 'stats':
        stats_text = f"📈 *Statistics*\n\n• Total Numbers: {len(active_numbers)}\n• Countries: {len(config.COUNTRIES)}"
        await query.edit_message_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    elif data == 'manual_refresh':
        await query.edit_message_text("🔄 *Refreshing ranges...*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    elif data == 'add_numbers':
        await query.edit_message_text("🌍 *Adding numbers...*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    elif data == 'list_ranges':
        ranges_text = "📋 *Active Ranges*\n\n"
        for country in config.COUNTRIES:
            ranges_text += f"• {country}\n"
        await query.edit_message_text(ranges_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    elif data == 'set_cookies':
        await query.edit_message_text("🍪 *Send Cookies*\n\nSend cookies in format: `name1=value1; name2=value2`", parse_mode=ParseMode.MARKDOWN)
        context.user_data['awaiting_cookies'] = True
    elif data == 'toggle_auto':
        await query.edit_message_text("🔘 *Auto Range Toggled*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    else:
        await query.edit_message_text("⏳ Coming soon!", reply_markup=get_admin_keyboard())

async def handle_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_cookies'):
        cookies_str = update.message.text
        success = panel.set_cookies(cookies_str)
        if success:
            await update.message.reply_text("✅ Cookies saved successfully!")
        else:
            await update.message.reply_text("❌ Failed to save cookies. Check format.")
        context.user_data['awaiting_cookies'] = False

async def check_otp_updates(context: ContextTypes.DEFAULT_TYPE):
    print(f"[{datetime.now()}] Checking for OTP updates...")
    messages = panel.get_otp_messages()
    for msg in messages:
        msg_id = msg.get('id')
        if msg_id not in otp_cache:
            otp_cache[msg_id] = msg
            try:
                await context.bot.send_message(
                    chat_id=config.ADMIN_ID,
                    text=f"🔐 *New OTP!*\n\n📱 {msg.get('number')}\n🔑 `{msg.get('otp')}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass

async def error_handler(update, context):
    print(f"Error: {context.error}")

def main():
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies))
    application.add_error_handler(error_handler)
    
    # JobQueue for OTP checking
    if application.job_queue:
        application.job_queue.run_repeating(check_otp_updates, interval=10, first=5)
        print("✅ JobQueue started")
    else:
        print("⚠️ JobQueue not available")
    
    print("🤖 Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
