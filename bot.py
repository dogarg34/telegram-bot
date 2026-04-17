import logging
import os
import sqlite3
import requests
from aiogram import Bot, Dispatcher, executor, types

# SAFE ENV
API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
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


# SAFE API FUNCTION 🔥
def get_api(cat):
    try:
        url = f"{PANEL_URL}?service={cat}&token={PANEL_TOKEN}"
        res = requests.get(url, timeout=10)

        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                return data
        return []
    except:
        return []


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


# SERVICE CLICK
@dp.callback_query_handler(lambda c: c.data in ["whatsapp","facebook","tiktok"])
async def show(call: types.CallbackQuery):

    nums = get_api(call.data)

    # API DATA
    if nums:
        kb = types.InlineKeyboardMarkup()
        for n in nums[:5]:
            kb.add(types.InlineKeyboardButton(n, callback_data=f"use_{n}"))
        return await call.message.answer("Choose number:", reply_markup=kb)

    # DB FALLBACK
    cursor.execute("SELECT id, number FROM numbers WHERE category=? AND used=0", (call.data,))
    row = cursor.fetchone()

    if not row:
        return await call.message.answer("❌ No numbers available")

    cursor.execute("UPDATE numbers SET used=1 WHERE id=?", (row[0],))
    conn.commit()

    await call.message.answer(f"📞 {row[1]}")


# USE NUMBER
@dp.callback_query_handler(lambda c: c.data.startswith("use_"))
async def use(call: types.CallbackQuery):
    num = call.data.split("_")[1]
    await call.message.answer(f"📞 Your Number:\n{num}")


# ADMIN PANEL 👑
@dp.message_handler(commands=['admin'])
async def admin(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return await msg.reply("❌ Access Denied")

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


# ADD NUMBER
@dp.callback_query_handler(lambda c: c.data=="add")
async def add(call: types.CallbackQuery):
    await call.message.answer("Send:\ncategory number\nExample:\nwhatsapp 923001234567")


@dp.message_handler(lambda m: m.text and m.text.split()[0] in ["whatsapp","facebook","tiktok"])
async def save_num(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return

    try:
        cat, num = msg.text.split()
        cursor.execute("INSERT INTO numbers (category, number) VALUES (?,?)", (cat, num))
        conn.commit()
        await msg.reply("✅ Added")
    except:
        await msg.reply("❌ Error format")


# DELETE
@dp.callback_query_handler(lambda c: c.data=="del")
async def delete(call: types.CallbackQuery):
    await call.message.answer("Send number to delete")


@dp.message_handler()
async def delete_num(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return

    cursor.execute("DELETE FROM numbers WHERE number=?", (msg.text,))
    conn.commit()
    await msg.reply("✅ Deleted if existed")


# LIST
@dp.callback_query_handler(lambda c: c.data=="list")
async def list_nums(call: types.CallbackQuery):
    cursor.execute("SELECT category, number, used FROM numbers")
    rows = cursor.fetchall()

    if not rows:
        return await call.message.answer("Empty")

    txt = "\n".join([f"{r[0]} - {r[1]} {'USED' if r[2] else 'FREE'}" for r in rows])
    await call.message.answer(txt)


# RESET
@dp.callback_query_handler(lambda c: c.data=="reset")
async def reset(call: types.CallbackQuery):
    cursor.execute("UPDATE numbers SET used=0")
    conn.commit()
    await call.message.answer("✅ Reset Done")


# USERS
@dp.callback_query_handler(lambda c: c.data=="m_users")
async def users(call: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*) FROM users")
    await call.message.answer(f"👥 Users: {cursor.fetchone()[0]}")


# STATS
@dp.callback_query_handler(lambda c: c.data=="m_stats")
async def stats(call: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*) FROM numbers")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM numbers WHERE used=1")
    used = cursor.fetchone()[0]

    await call.message.answer(f"📊 Total: {total}\nUsed: {used}")


# API CHECK
@dp.callback_query_handler(lambda c: c.data=="m_api")
async def api(call: types.CallbackQuery):
    test = get_api("whatsapp")
    await call.message.answer("✅ API Working" if test else "❌ API Down")


# BROADCAST
@dp.callback_query_handler(lambda c: c.data=="m_bc")
async def bc(call: types.CallbackQuery):
    await call.message.answer("Use /broadcast message")


@dp.message_handler(commands=['broadcast'])
async def send_all(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return

    users = cursor.execute("SELECT user_id FROM users").fetchall()

    for u in users:
        try:
            await bot.send_message(u[0], msg.get_args())
        except:
            pass


# DB
@dp.callback_query_handler(lambda c: c.data=="m_db")
async def db(call: types.CallbackQuery):
    await call.message.answer("💾 DB Active")


# SYSTEM
@dp.callback_query_handler(lambda c: c.data=="m_sys")
async def sys(call: types.CallbackQuery):
    await call.message.answer("⚙️ System Running")


# RUN
if __name__ == "__main__":
    executor.start_polling(dp)
