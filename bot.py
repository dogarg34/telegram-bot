import asyncio
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

import config
from iVasms import iVasmsPanel

# Initialize panel
panel = iVasmsPanel(config.IVASMS_EMAIL, config.IVASMS_PASSWORD)

# Store user sessions
user_sessions = {}

# ✅ FIX: Variables ko function ke BAHAR define karo
refresh_in_progress = False
last_refresh_time = None

# ============ ADMIN KEYBOARD ============
def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 Users", callback_data='admin_users')],
        [InlineKeyboardButton("📈 Stats", callback_data='admin_stats')],
        [InlineKeyboardButton("🔄 Refresh Ranges", callback_data='admin_refresh')],
        [InlineKeyboardButton("🌍 Check Active Countries", callback_data='admin_check')],
        [InlineKeyboardButton("🍪 Set Cookies", callback_data='admin_cookies')],
        [InlineKeyboardButton("📢 Broadcast", callback_data='admin_broadcast')],
    ]
    return InlineKeyboardMarkup(keyboard)

# ============ USER KEYBOARD ============
def get_user_country_keyboard():
    countries = panel.get_country_list()
    if not countries:
        keyboard = [[InlineKeyboardButton("🔄 No countries, ask admin to refresh", callback_data='user_refresh')]]
    else:
        keyboard = []
        row = []
        for i, country in enumerate(countries):
            row.append(InlineKeyboardButton(f"📱 {country['name']} ({country['count']})", callback_data=f"country_{country['name']}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔄 Refresh List", callback_data='user_refresh')])
    return InlineKeyboardMarkup(keyboard)

def get_user_number_keyboard(country_name, numbers):
    keyboard = [
        [InlineKeyboardButton("📞 Get New Number", callback_data=f"getnum_{country_name}")],
        [InlineKeyboardButton("🔙 Back to Countries", callback_data="user_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ============ COMMANDS ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id == config.ADMIN_ID:
        await update.message.reply_text(
            "🤖 *Admin Panel*\n\n"
            "Welcome back admin!\n\n"
            f"📊 Total numbers: {panel.get_total_numbers()}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
    else:
        await update.message.reply_text(
            "🤖 *WhatsApp OTP Bot*\n\n"
            "Select your country to get a number:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_user_country_keyboard()
        )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    await update.message.reply_text(
        "🔧 *Admin Panel*\n\n"
        f"📊 Numbers: {panel.get_total_numbers()}\n"
        f"🕐 Last Refresh: {last_refresh_time if last_refresh_time else 'Never'}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

# ============ BUTTON HANDLERS ============
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global refresh_in_progress, last_refresh_time  # ✅ Now this works because variables are defined above
    
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # ============ ADMIN HANDLERS ============
    if user_id == config.ADMIN_ID:
        if data == 'admin_users':
            await query.edit_message_text("👥 *Users*\n\nAdmin only currently.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        
        elif data == 'admin_stats':
            countries = panel.get_country_list()
            stats = f"📈 *Stats*\n\nNumbers: {panel.get_total_numbers()}\nCountries: {len(countries)}"
            await query.edit_message_text(stats, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        
        elif data == 'admin_check':
            await query.edit_message_text("🔍 Checking active countries...", parse_mode=ParseMode.MARKDOWN)
            countries = panel.check_whatsapp_status()
            if countries:
                text = "✅ *Active Countries:*\n\n"
                for name, code in countries.items():
                    text += f"• {name} ({code})\n"
            else:
                text = "❌ No active countries found!"
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        
        elif data == 'admin_refresh':
            if refresh_in_progress:
                await query.edit_message_text("⏳ Refresh already in progress!", reply_markup=get_admin_keyboard())
                return
            
            refresh_in_progress = True
            await query.edit_message_text("🔄 Refreshing numbers...\n⏱️ Please wait 10-20 seconds...", parse_mode=ParseMode.MARKDOWN)
            
            try:
                start_time = datetime.now()
                panel.check_whatsapp_status()
                results = panel.refresh_all_countries(100)
                elapsed = (datetime.now() - start_time).total_seconds()
                last_refresh_time = datetime.now().strftime("%H:%M:%S")
                
                success_text = f"✅ *Refresh Complete!*\n\n⏱️ Time: {elapsed:.1f}s\n📊 Total: {panel.get_total_numbers()} numbers"
                await query.edit_message_text(success_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
            except Exception as e:
                await query.edit_message_text(f"❌ Error: {str(e)}", reply_markup=get_admin_keyboard())
            finally:
                refresh_in_progress = False
        
        elif data == 'admin_cookies':
            await query.edit_message_text("🍪 *Send cookies*\n\nFormat: `key1=value1; key2=value2`", parse_mode=ParseMode.MARKDOWN)
            context.user_data['awaiting_cookies'] = True
        
        elif data == 'admin_broadcast':
            await query.edit_message_text("📢 *Send broadcast message:*", parse_mode=ParseMode.MARKDOWN)
            context.user_data['awaiting_broadcast'] = True
    
    # ============ USER HANDLERS ============
    else:
        if data == 'user_refresh':
            await query.edit_message_text("🔄 Refreshing...", reply_markup=get_user_country_keyboard())
        
        elif data == 'user_back':
            await query.edit_message_text("📱 *Select Country*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_country_keyboard())
        
        elif data.startswith('country_'):
            country_name = data.replace('country_', '')
            user_sessions[user_id] = {'country': country_name}
            numbers = panel.get_numbers_by_country(country_name)
            
            if numbers:
                text = f"📱 *{country_name}*\n\nNumbers: {len(numbers)}\n\nClick below to get a number:"
                await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_number_keyboard(country_name, numbers))
            else:
                await query.edit_message_text(f"❌ No numbers for {country_name}!", reply_markup=get_user_country_keyboard())
        
        elif data.startswith('getnum_'):
            country_name = data.replace('getnum_', '')
            number = panel.claim_number(country_name)
            
            if number:
                await query.edit_message_text(
                    f"📞 *Your Number*\n\n`{number}`\n\nUse this for WhatsApp OTP.\nOTP will appear here.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_user_country_keyboard()
                )
            else:
                await query.edit_message_text(f"❌ No numbers left for {country_name}!", reply_markup=get_user_country_keyboard())

# ============ MESSAGE HANDLERS ============
async def handle_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_cookies'):
        cookies_str = update.message.text
        success = panel.set_cookies(cookies_str)
        if success:
            await update.message.reply_text("✅ Cookies saved! Use /admin to refresh.")
        else:
            await update.message.reply_text("❌ Invalid cookies format! Try again.")
        context.user_data['awaiting_cookies'] = False

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_broadcast'):
        await update.message.reply_text("✅ Broadcast sent!")
        context.user_data['awaiting_broadcast'] = False

async def check_otp_updates(context: ContextTypes.DEFAULT_TYPE):
    print(f"[{datetime.now()}] Checking OTP...")

# ============ MAIN ============
def main():
    app = Application.builder().token(config.BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast))
    
    if app.job_queue:
        app.job_queue.run_repeating(check_otp_updates, interval=30, first=10)
    
    print("🚀 Bot Started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
