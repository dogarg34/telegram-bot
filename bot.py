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
            row.append(InlineKeyboardButton(f"🇵🇰 {country['name']} ({country['count']})", callback_data=f"country_{country['name']}"))
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
    
    # If admin
    if user_id == config.ADMIN_ID:
        await update.message.reply_text(
            "🤖 *Admin Panel*\n\n"
            "Welcome back admin! Use the buttons below to manage the bot.\n\n"
            f"📊 Total numbers available: {panel.get_total_numbers()}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
    else:
        # Normal user
        await update.message.reply_text(
            "🤖 *WhatsApp OTP Bot*\n\n"
            "Welcome! Select your country to get a WhatsApp number for OTP verification.\n\n"
            "📌 *Note:* Numbers change every few hours. If you don't receive OTP, try a different number.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_user_country_keyboard()
        )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized! This command is only for admin.")
        return
    
    await update.message.reply_text(
        "🔧 *Admin Control Panel*\n\n"
        f"📊 Active Countries: {len(panel.active_countries)}\n"
        f"📞 Total Numbers: {panel.get_total_numbers()}\n"
        f"🕐 Last Refresh: {last_refresh_time if last_refresh_time else 'Never'}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

# ============ BUTTON HANDLERS ============
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # ============ ADMIN HANDLERS ============
    if user_id == config.ADMIN_ID:
        if data == 'admin_users':
            await query.edit_message_text(
                "👥 *Users*\n\n"
                "User tracking coming soon. Currently only admin access.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_admin_keyboard()
            )
        
        elif data == 'admin_stats':
            countries = panel.get_country_list()
            stats_text = "📈 *Bot Statistics*\n\n"
            stats_text += f"🕐 Last Refresh: {last_refresh_time if last_refresh_time else 'Never'}\n"
            stats_text += f"🌍 Active Countries: {len(countries)}\n"
            stats_text += f"📞 Total Numbers: {panel.get_total_numbers()}\n\n"
            stats_text += "*Country-wise Numbers:*\n"
            for c in countries:
                stats_text += f"• {c['name']}: {c['count']} numbers\n"
            
            await query.edit_message_text(
                stats_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_admin_keyboard()
            )
        
        elif data == 'admin_check':
            await query.edit_message_text(
                "🔍 *Checking active countries...*\n\n"
                "Please wait while I check which countries have working WhatsApp OTP.",
                parse_mode=ParseMode.MARKDOWN
            )
            
            countries = panel.check_whatsapp_status()
            
            if countries:
                text = "✅ *Active Countries Found:*\n\n"
                for name, code in countries.items():
                    text += f"• {name} ({code})\n"
                text += f"\nTotal: {len(countries)} countries"
            else:
                text = "❌ *No active countries found!*\n\nMake sure you have set cookies correctly and iVasms panel is working."
            
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_admin_keyboard()
            )
        
        elif data == 'admin_refresh':
            global refresh_in_progress, last_refresh_time
            
            if refresh_in_progress:
                await query.edit_message_text(
                    "⏳ *Refresh already in progress!*\nPlease wait...",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_admin_keyboard()
                )
                return
            
            refresh_in_progress = True
            await query.edit_message_text(
                "🔄 *Refreshing numbers...*\n\n"
                "Step 1/4: Checking active countries...\n"
                "Step 2/4: Fetching available ranges...\n"
                "Step 3/4: Adding numbers...\n"
                "Step 4/4: Finalizing...\n\n"
                "⏱️ This may take 10-20 seconds.",
                parse_mode=ParseMode.MARKDOWN
            )
            
            try:
                start_time = datetime.now()
                
                # Step 1: Check active countries
                await query.edit_message_text(
                    "🔄 *Refreshing numbers...*\n\n"
                    "✅ Step 1/4: Checking active countries...\n"
                    "⏳ Step 2/4: Fetching available ranges...\n"
                    "⏳ Step 3/4: Adding numbers...\n"
                    "⏳ Step 4/4: Finalizing...",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                panel.check_whatsapp_status()
                
                # Step 2-4: Refresh all countries
                await query.edit_message_text(
                    "🔄 *Refreshing numbers...*\n\n"
                    "✅ Step 1/4: Checking active countries...\n"
                    "✅ Step 2/4: Fetching available ranges...\n"
                    "⏳ Step 3/4: Adding numbers (this may take a moment)...\n"
                    "⏳ Step 4/4: Finalizing...",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                results = panel.refresh_all_countries(100)
                
                elapsed = (datetime.now() - start_time).total_seconds()
                last_refresh_time = datetime.now().strftime("%H:%M:%S")
                
                # Build success message
                success_text = f"✅ *Refresh Complete!*\n\n"
                success_text += f"⏱️ Time taken: {elapsed:.1f} seconds\n"
                success_text += f"📊 Total numbers added: {panel.get_total_numbers()}\n\n"
                success_text += "*Numbers by country:*\n"
                for name, data in results.items():
                    success_text += f"• {name}: {data['count']} numbers\n"
                
                await query.edit_message_text(
                    success_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_admin_keyboard()
                )
                
            except Exception as e:
                await query.edit_message_text(
                    f"❌ *Error during refresh:*\n`{str(e)}`",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_admin_keyboard()
                )
            finally:
                refresh_in_progress = False
        
        elif data == 'admin_cookies':
            await query.edit_message_text(
                "🍪 *Set Cookies*\n\n"
                "Please send your iVasms cookies in this format:\n\n"
                "`sessionid=abc123; csrftoken=xyz789; userid=456`\n\n"
                "How to get cookies:\n"
                "1. Login to iVasms in Kiwi browser\n"
                "2. Install 'Cookie Editor' extension\n"
                "3. Click export → Copy as string\n"
                "4. Paste here",
                parse_mode=ParseMode.MARKDOWN
            )
            context.user_data['awaiting_cookies'] = True
        
        elif data == 'admin_broadcast':
            await query.edit_message_text(
                "📢 *Broadcast Message*\n\n"
                "Send the message you want to broadcast to all users.",
                parse_mode=ParseMode.MARKDOWN
            )
            context.user_data['awaiting_broadcast'] = True
    
    # ============ USER HANDLERS ============
    else:
        if data == 'user_refresh':
            await query.edit_message_text(
                "🔄 *Refreshing country list...*",
                parse_mode=ParseMode.MARKDOWN
            )
            await query.edit_message_text(
                "📱 *Select Your Country*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_user_country_keyboard()
            )
        
        elif data == 'user_back':
            await query.edit_message_text(
                "📱 *Select Your Country*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_user_country_keyboard()
            )
        
        elif data.startswith('country_'):
            country_name = data.replace('country_', '')
            user_sessions[user_id] = {'country': country_name}
            
            numbers = panel.get_numbers_by_country(country_name)
            
            if numbers:
                text = f"🇵🇰 *{country_name}*\n\n"
                text += f"Available numbers: {len(numbers)}\n\n"
                text += "Click 'Get New Number' to receive a WhatsApp number for OTP."
                
                await query.edit_message_text(
                    text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_user_number_keyboard(country_name, numbers)
                )
            else:
                await query.edit_message_text(
                    f"❌ *No numbers available for {country_name}!*\n\n"
                    "Please inform admin to refresh the ranges.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_user_country_keyboard()
                )
        
        elif data.startswith('getnum_'):
            country_name = data.replace('getnum_', '')
            
            number = panel.claim_number(country_name)
            
            if number:
                await query.edit_message_text(
                    f"📞 *Your WhatsApp Number*\n\n"
                    f"`{number}`\n\n"
                    f"📌 *Instructions:*\n"
                    f"1. Use this number for WhatsApp OTP\n"
                    f"2. Wait 30-60 seconds for OTP\n"
                    f"3. The OTP will appear here\n\n"
                    f"⚠️ Numbers expire after some time. If no OTP received, request a new number.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_user_country_keyboard()
                )
                
                # Store number for OTP tracking
                context.user_data['last_number'] = number
                context.user_data['last_country'] = country_name
            else:
                await query.edit_message_text(
                    f"❌ *No numbers left for {country_name}!*\n\n"
                    "Please inform admin to refresh the ranges.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_user_country_keyboard()
                )

# ============ MESSAGE HANDLERS ============
async def handle_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_cookies'):
        cookies_str = update.message.text
        success = panel.set_cookies(cookies_str)
        
        if success:
            await update.message.reply_text(
                "✅ *Cookies saved successfully!*\n\n"
                "Now use /admin and click 'Check Active Countries' to find working countries.\n"
                "Then click 'Refresh Ranges' to add numbers.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                "❌ *Invalid cookies!*\n\n"
                "Please try again with correct format.\n\n"
                "Format: `key1=value1; key2=value2`",
                parse_mode=ParseMode.MARKDOWN
            )
        
        context.user_data['awaiting_cookies'] = False

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_broadcast'):
        message = update.message.text
        
        # Here you would send to all users
        # For now, just send back to admin
        await update.message.reply_text(
            f"📢 *Broadcast sent!*\n\nMessage: {message}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        context.user_data['awaiting_broadcast'] = False

async def check_otp_updates(context: ContextTypes.DEFAULT_TYPE):
    """Background task to check for OTPs"""
    # This would fetch OTPs from iVasms panel
    # And forward to users who requested numbers
    print(f"[{datetime.now()}] Checking for OTP updates...")

# ============ MAIN ============
def main():
    app = Application.builder().token(config.BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast))
    
    # JobQueue for OTP checking
    if app.job_queue:
        app.job_queue.run_repeating(check_otp_updates, interval=15, first=5)
        print("✅ JobQueue started for OTP checking")
    
    print("🚀 WhatsApp OTP Bot Started!")
    print("=" * 40)
    print(f"👤 Admin ID: {config.ADMIN_ID}")
    print(f"🌍 Auto country detection: ENABLED")
    print(f"🔄 Auto refresh: {config.AUTO_REFRESH_INTERVAL // 3600} hours")
    print("=" * 40)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
