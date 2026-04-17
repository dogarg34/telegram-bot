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
        sorted_data = sorted(data, key=lambda x: x['count'], reverse=True)
        return sorted_data[:5]
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
    service = call.data
    countries = get_trending_countries(service)

    if not countries:
        return await call.message.answer("No country data")

    kb = types.InlineKeyboardMarkup()
    for c in countries:
        name = c["country"]
        kb.add(types.InlineKeyboardButton(f"{get_flag(name)} {name}", callback_data=f"{service}_{name}"))

    await call.message.answer("Select Country:", reply_markup=kb)

# COUNTRY → NUMBER
@dp.callback_query_handler(lambda c: "_" in c.data)
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

    except:
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

# NUMBERS MENU
@dp.callback_query_handler(lambda c: c.data=="m_numbers")
async def numbers_menu(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Add", callback_data="add"),
        types.InlineKeyboardButton("❌ Delete", callback_data="del"),
        types.InlineKeyboardButton("📋 List", callback_data="list"),
        types.InlineKeyboardButton("♻️ Reset", callback_data="reset")
    )
    await call.message.answer("Numbers Menu", reply_markup=kb)

# ADD / DELETE
@dp.callback_query_handler(lambda c: c.data=="add")
async def add_guide(call: types.CallbackQuery):
    await call.message.answer("Use:\n/add whatsapp 92300xxxx")

@dp.callback_query_handler(lambda c: c.data=="del")
async def del_guide(call: types.CallbackQuery):
    await call.message.answer("Use:\n/delete 92300xxxx")

@dp.message_handler(commands=['add'])
async def add_number(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    try:
        _, cat, num = msg.text.split()
        cursor.execute("INSERT INTO numbers (category, number) VALUES (?,?)",(cat,num))
        conn.commit()
        await msg.reply("Added ✅")
    except:
        await msg.reply("Usage: /add whatsapp 92300")

@dp.message_handler(commands=['delete'])
async def delete_number(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    try:
        _, num = msg.text.split()
        cursor.execute("DELETE FROM numbers WHERE number=?",(num,))
        conn.commit()
        await msg.reply("Deleted ❌")
    except:
        await msg.reply("Usage: /delete 92300")

# LIST + RESET
@dp.callback_query_handler(lambda c: c.data=="list")
async def list_nums(call: types.CallbackQuery):
    rows = cursor.execute("SELECT category, number, used FROM numbers").fetchall()
    txt = "\n".join([f"{r[0]}-{r[1]} {'USED' if r[2] else 'FREE'}" for r in rows]) or "Empty"
    await call.message.answer(txt)

@dp.callback_query_handler(lambda c: c.data=="reset")
async def reset_nums(call: types.CallbackQuery):
    cursor.execute("UPDATE numbers SET used=0")
    conn.commit()
    await call.message.answer("Reset Done")

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

# BROADCAST
@dp.callback_query_handler(lambda c: c.data=="m_bc")
async def bc(call: types.CallbackQuery):
    await call.message.answer("Use /broadcast message")

@dp.message_handler(commands=['broadcast'])
async def send_all(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    users = cursor.execute("SELECT user_id FROM users").fetchall()
    for u in users:
        try:
            await bot.send_message(u[0], msg.get_args())
        except: pass

# DB TOOLS
@dp.callback_query_handler(lambda c: c.data=="m_db")
async def db_tools(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🧹 Clear DB", callback_data="clear_db"),
        types.InlineKeyboardButton("♻️ Reset Used", callback_data="reset_db")
    )
    await call.message.answer("DB Tools:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data=="clear_db")
async def clear_db(call: types.CallbackQuery):
    cursor.execute("DELETE FROM numbers")
    conn.commit()
    await call.message.answer("Database Cleared")

@dp.callback_query_handler(lambda c: c.data=="reset_db")
async def reset_db(call: types.CallbackQuery):
    cursor.execute("UPDATE numbers SET used=0")
    conn.commit()
    await call.message.answer("Reset Done")

# SYSTEM INFO
@dp.callback_query_handler(lambda c: c.data=="m_sys")
async def system(call: types.CallbackQuery):
    users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    nums = cursor.execute("SELECT COUNT(*) FROM numbers").fetchone()[0]

    await call.message.answer(f"""
⚙️ SYSTEM INFO

👥 Users: {users}
📦 Numbers: {nums}
🌐 API: Active
🟢 Bot: Running
""")

if __name__ == "__main__":
    executor.start_polling(dp)
