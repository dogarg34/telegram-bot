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
        [InlineKeyboardButton("➕ Add Channel", callback_data='add_channel')],
        [InlineKeyboardButton("❌ Del Channel", callback_data='del_channel')],
        [InlineKeyboardButton("📢 Broadcast", callback_data='broadcast')],
        [InlineKeyboardButton("🍪 Set Cookies", callback_data='set_cookies')],
    ]
    return InlineKeyboardMarkup(keyboard)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized! Only admin can use this bot.")
        return
    
    welcome_text = """
🤖 *OTP Bot Started!*

✅ Bot is active and ready.
📱 iVasms panel connected.

*Current Status:*
• Auto Range: ON
• Countries: {countries}
• Active Numbers: {numbers}

Use /admin to open control panel.
    """.format(
        countries=len(config.COUNTRIES),
        numbers=len(active_numbers)
    )
    
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

# Admin command
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

# Callback handler for buttons
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id != config.ADMIN_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    data = query.data
    
    if data == 'users':
        await show_users(query)
    elif data == 'stats':
        await show_stats(query)
    elif data == 'manual_refresh':
        await manual_range_refresh(query)
    elif data == 'add_numbers':
        await add_numbers(query)
    elif data == 'list_ranges':
        await list_ranges(query)
    elif data == 'set_cookies':
        await ask_cookies(query)
    elif data == 'toggle_auto':
        await toggle_auto(query)
    else:
        await query.edit_message_text("⏳ Coming soon!")

async def show_users(query):
    # Track users who have interacted
    users_list = "📊 *Users List*\n\n"
    users_list += "Total users: 1\n"
    users_list += f"Admin: {config.ADMIN_ID}\n"
    
    await query.edit_message_text(users_list, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

async def show_stats(query):
    stats_text = f"""
📈 *Bot Statistics*

• Total Numbers Added: {len(active_numbers)}
• Countries Active: {len(config.COUNTRIES)}
• OTPs Received: {len(otp_cache)}
• Uptime: Active

*Country-wise Numbers:*
"""
    for country, code in config.COUNTRIES.items():
        count = len([n for n in active_numbers.values() if n.get('country') == country])
        stats_text += f"• {country}: {count} numbers\n"
    
    await query.edit_message_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

async def manual_range_refresh(query):
    await query.edit_message_text("🔄 *Refreshing ranges...*", parse_mode=ParseMode.MARKDOWN)
    
    try:
        success = panel.refresh_range()
        if success:
            await add_all_country_numbers()
            await query.edit_message_text(
                "✅ *Range refreshed successfully!*\n\nNumbers have been updated.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_admin_keyboard()
            )
        else:
            await query.edit_message_text(
                "❌ *Refresh failed!*\nPlease check cookies or login.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_admin_keyboard()
            )
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}", reply_markup=get_admin_keyboard())

async def add_numbers(query):
    await query.edit_message_text("🌍 *Adding numbers for all countries...*\n⏳ Please wait...", parse_mode=ParseMode.MARKDOWN)
    
    await add_all_country_numbers()
    
    await query.edit_message_text(
        f"✅ *Numbers added successfully!*\n\nTotal numbers: {len(active_numbers)}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

async def add_all_country_numbers():
    """Add 100 numbers for each country"""
    total_added = 0
    
    for country_name, country_code in config.COUNTRIES.items():
        numbers = panel.get_available_numbers(country_code, limit=100)
        
        for num in numbers:
            num_id = str(num.get('id', num.get('number', total_added)))
            active_numbers[num_id] = {
                'number': num.get('number'),
                'country': country_name,
                'code': country_code,
                'added_at': datetime.now().isoformat()
            }
            total_added += 1
        
        await asyncio.sleep(2)  # Avoid rate limiting
    
    return total_added

async def list_ranges(query):
    if not active_numbers:
        await query.edit_message_text("📭 *No numbers added yet!*\n\nUse 'Add Numbers' first.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        return
    
    ranges_text = "📋 *Active Number Ranges*\n\n"
    
    country_count = {}
    for num_data in active_numbers.values():
        country = num_data['country']
        country_count[country] = country_count.get(country, 0) + 1
    
    for country, count in country_count.items():
        ranges_text += f"• {country}: {count} numbers\n"
    
    await query.edit_message_text(ranges_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

async def ask_cookies(query):
    await query.edit_message_text(
        "🍪 *Set Cookies*\n\n"
        "Please send your iVasms cookies in this format:\n\n"
        "`session=abc123; token=xyz789; user_id=123`\n\n"
        "How to get cookies:\n"
        "1. Login to iVasms in Kiwi browser\n"
        "2. Install Cookie Editor extension\n"
        "3. Export cookies as string\n"
        "4. Paste here",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Set a flag to expect cookies
    context.user_data['awaiting_cookies'] = True

async def handle_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_cookies'):
        cookies_str = update.message.text
        
        try:
            success = panel.set_cookies(cookies_str)
            if success:
                await update.message.reply_text("✅ Cookies saved successfully!\n\nUse /admin to refresh ranges.")
            else:
                await update.message.reply_text("❌ Invalid cookies format! Please try again with /admin")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        
        context.user_data['awaiting_cookies'] = False

async def toggle_auto(query):
    global auto_refresh_task
    
    if auto_refresh_task and not auto_refresh_task.done():
        auto_refresh_task.cancel()
        status_text = "OFF"
        button_text = "🔘 Auto Range: OFF"
    else:
        auto_refresh_task = asyncio.create_task(auto_refresh_loop())
        status_text = "ON"
        button_text = "🔘 Auto Range: ON"
    
    # Update button
    keyboard = get_admin_keyboard()
    for row in keyboard:
        for btn in row:
            if btn.callback_data == 'toggle_auto':
                btn.text = button_text
    
    await query.edit_message_text(
        f"✅ Auto Range turned {status_text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def auto_refresh_loop():
    while True:
        await asyncio.sleep(config.AUTO_REFRESH_INTERVAL)
        try:
            panel.refresh_range()
            await add_all_country_numbers()
            print(f"[{datetime.now()}] Auto refresh completed")
        except Exception as e:
            print(f"Auto refresh error: {e}")

async def check_otp_updates(context: ContextTypes.DEFAULT_TYPE):
    """Background task to check for new OTPs"""
    messages = panel.get_otp_messages()
    
    for msg in messages:
        msg_id = msg.get('id')
        if msg_id not in otp_cache:
            otp_cache[msg_id] = msg
            # Forward OTP to admin
            otp_text = f"🔐 *New OTP Received!*\n\n📱 Number: {msg.get('number')}\n🔑 OTP: `{msg.get('otp')}`\n📨 Message: {msg.get('text')}"
            
            try:
                await context.bot.send_message(
                    chat_id=config.ADMIN_ID,
                    text=otp_text,
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass

async def error_handler(update, context):
    print(f"Error: {context.error}")

def main():
    # Create application
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies))
    application.add_error_handler(error_handler)
    
    # Start background OTP checker
    job_queue = application.job_queue
    job_queue.run_repeating(check_otp_updates, interval=5, first=10)
    
    # Start bot
    print("🤖 Bot started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
