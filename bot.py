import asyncio
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

import config
from iVasms import iVasmsPanel

panel = iVasmsPanel(config.IVASMS_EMAIL, config.IVASMS_PASSWORD)
active_numbers = {}
otp_cache = {}
refresh_in_progress = False

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
        await update.message.reply_text("❌ Unauthorized!")
        return
    await update.message.reply_text("🤖 Fast OTP Bot Started!\nUse /admin", parse_mode=ParseMode.MARKDOWN)

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    await update.message.reply_text("🔧 Admin Panel (Fast Mode 🚀)", reply_markup=get_admin_keyboard())

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global refresh_in_progress
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id != config.ADMIN_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    data = query.data
    
    if data == 'users':
        await query.edit_message_text("📊 *Users*\n\n👤 Admin only", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    
    elif data == 'stats':
        stats_text = f"📈 *Statistics (Fast Mode)*\n\n• Numbers: {len(active_numbers)}\n• Countries: {len(config.COUNTRIES)}\n• OTPs: {len(otp_cache)}"
        await query.edit_message_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    
    elif data == 'manual_refresh':
        if refresh_in_progress:
            await query.edit_message_text("⏳ Refresh already in progress...", reply_markup=get_admin_keyboard())
            return
        
        refresh_in_progress = True
        status_msg = await query.edit_message_text("🔄 *Refreshing ranges (Fast Mode)*...\n⏱️ Should take 5-10 seconds", parse_mode=ParseMode.MARKDOWN)
        
        try:
            # Fast parallel refresh
            start_time = datetime.now()
            
            # Step 1: Refresh range
            panel.refresh_range_fast()
            
            # Step 2: Parallel fetch all countries
            results = panel.get_all_countries_numbers_parallel(config.COUNTRIES, 100)
            
            # Step 3: Update active numbers
            active_numbers.clear()
            total = 0
            for country_name, numbers in results.items():
                for num in numbers:
                    num_id = str(num.get('id', total))
                    active_numbers[num_id] = {
                        'number': num.get('number'),
                        'country': country_name,
                        'added_at': datetime.now().isoformat()
                    }
                    total += 1
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            await status_msg.edit_text(
                f"✅ *Refresh Complete!*\n\n"
                f"• Numbers added: {total}\n"
                f"• Time taken: {elapsed:.1f} seconds\n"
                f"• Countries: {len(config.COUNTRIES)}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_admin_keyboard()
            )
        except Exception as e:
            await status_msg.edit_text(f"❌ Error: {str(e)}", reply_markup=get_admin_keyboard())
        finally:
            refresh_in_progress = False
    
    elif data == 'add_numbers':
        await query.edit_message_text("🌍 *Adding numbers...*\nUse Manual Range Refresh instead", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    
    elif data == 'list_ranges':
        if not active_numbers:
            await query.edit_message_text("📭 No numbers yet! Do Manual Range Refresh first.", reply_markup=get_admin_keyboard())
            return
        
        ranges_text = "📋 *Active Numbers*\n\n"
        country_count = {}
        for num_data in active_numbers.values():
            country = num_data['country']
            country_count[country] = country_count.get(country, 0) + 1
        
        for country, count in country_count.items():
            ranges_text += f"• {country}: {count} numbers\n"
        
        await query.edit_message_text(ranges_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    
    elif data == 'set_cookies':
        await query.edit_message_text("🍪 *Send Cookies*\n\nSend cookies from Kiwi browser:", parse_mode=ParseMode.MARKDOWN)
        context.user_data['awaiting_cookies'] = True
    
    elif data == 'toggle_auto':
        await query.edit_message_text("🔘 Auto refresh feature coming soon!", reply_markup=get_admin_keyboard())

async def handle_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_cookies'):
        cookies_str = update.message.text
        success = panel.set_cookies(cookies_str)
        if success:
            await update.message.reply_text("✅ Cookies saved successfully!\nNow use /admin → Manual Range Refresh")
        else:
            await update.message.reply_text("❌ Failed to save cookies. Try again.")
        context.user_data['awaiting_cookies'] = False

async def check_otp_updates(context: ContextTypes.DEFAULT_TYPE):
    print(f"[{datetime.now()}] Checking OTP...")

def main():
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies))
    
    if app.job_queue:
        app.job_queue.run_repeating(check_otp_updates, interval=30, first=10)
    
    print("🚀 Fast OTP Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
