import logging
import os
import sqlite3
import requests
import asyncio
from aiogram import Bot, Dispatcher, executor, types

API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PANEL_URL = os.getenv("PANEL_URL")
PANEL_TOKEN = os.getenv("PANEL_TOKEN")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# DATABASE
conn = sqlite3.connect("data.db")
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS numbers (id INTEGER PRIMARY KEY, category TEXT, number TEXT, used INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
conn.commit()

def is_admin(uid):
    return uid == ADMIN_ID

# FLAGS
def get_flag(country):
    flags = {
        "Pakistan": "🇵🇰",
        "India": "🇮🇳",
        "USA": "🇺🇸",
        "UK": "🇬🇧",
        "Indonesia": "🇮🇩"
    }
    return flags.get(country, "🌍")

# TRENDING COUNTRIES
def get_trending_countries(service):
    try:
        url = f"{PANEL_URL}/stats?service={service}&token={PANEL_TOKEN}"
        data = requests.get(url).json()
        return sorted(data, key=lambda x: x['count'], reverse=True)[:5]
    except:
        return []

# OTP SYSTEM
async def wait_for_otp(user_id, number):
    for _ in range(30):
        try:
            url = f"{PANEL_URL}/get-otp?number={number}&token={PANEL_TOKEN}"
            data = requests.get(url).json()
            if data.get("otp"):
                await bot.send_message(user_id, f"🔐 OTP: {data['otp']}")
                return
        except:
            pass
        await asyncio.sleep(10)
    await bot.send_message(user_id, "❌ OTP not received")

# START
@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (msg.from_user.id,))
    conn.commit()

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("WhatsApp", callback_data="whatsapp"))
    kb.add(types.InlineKeyboardButton("Facebook", callback_data="facebook"))
    kb.add(types.InlineKeyboardButton("TikTok", callback_data="tiktok"))

    await msg.answer("Select Service:", reply_markup=kb)

# SERVICE → COUNTRIES
@dp.callback_query_handler(lambda c: c.data in ["whatsapp","facebook","tiktok"])
async def show_countries(call: types.CallbackQuery):
    countries = get_trending_countries(call.data)

    if not countries:
        return await call.message.answer("No country data")

    kb = types.InlineKeyboardMarkup()
    for c in countries:
        name = c["country"]
        kb.add(types.InlineKeyboardButton(f"{get_flag(name)} {name}", callback_data=f"{call.data}_{name}"))

    await call.message.answer("Select Country:", reply_markup=kb)

# ✅ FIXED HANDLER (IMPORTANT)
@dp.callback_query_handler(lambda c: c.data.count("_") == 1 and c.data.split("_")[0] in ["whatsapp","facebook","tiktok"])
async def get_number(call: types.CallbackQuery):
    service, country = call.data.split("_")

    try:
        url = f"{PANEL_URL}/get-number?service={service}&country={country}&token={PANEL_TOKEN}"
        data = requests.get(url).json()

        number = data.get("number")
        if not number:
            return await call.message.answer("No number available")

        await call.message.answer(f"📞 {number}\n⏳ Waiting for OTP...")
        asyncio.create_task(wait_for_otp(call.from_user.id, number))

    except Exception as e:
        await call.message.answer("Error getting number")

# 👑 ADMIN PANEL
@dp.message_handler(commands=['admin'])
async def admin(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return await msg.reply("Denied")

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📦 Numbers", callback_data="m_numbers"),
        types.InlineKeyboardButton("👥 Users", callback_data="m_users"),
        types.InlineKeyboardButton("📊 Stats", callback_data="m_stats"),
        types.InlineKeyboardButton("🌐 API", callback_data="m_api"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="m_bc"),
        types.InlineKeyboardButton("💾 DB Tools", callback_data="m_db"),
        types.InlineKeyboardButton("⚙️ System", callback_data="m_sys")
    )
    await msg.answer("👑 Admin Panel", reply_markup=kb)

# USERS
@dp.callback_query_handler(lambda c: c.data=="m_users")
async def users(call: types.CallbackQuery):
    count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    await call.message.answer(f"Users: {count}")

# STATS
@dp.callback_query_handler(lambda c: c.data=="m_stats")
async def stats(call: types.CallbackQuery):
    total = cursor.execute("SELECT COUNT(*) FROM numbers").fetchone()[0]
    used = cursor.execute("SELECT COUNT(*) FROM numbers WHERE used=1").fetchone()[0]
    await call.message.answer(f"Total: {total}\nUsed: {used}")

# API CHECK
@dp.callback_query_handler(lambda c: c.data=="m_api")
async def api_check(call: types.CallbackQuery):
    test = get_trending_countries("whatsapp")
    await call.message.answer("✅ API Working" if test else "❌ API Down")

# SYSTEM
@dp.callback_query_handler(lambda c: c.data=="m_sys")
async def system(call: types.CallbackQuery):
    await call.message.answer("System Running")

if __name__ == "__main__":
    executor.start_polling(dp)
