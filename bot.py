import logging
import os
import sqlite3
import requests
import asyncio
from aiogram import Bot, Dispatcher, executor, types

# ================= CONFIG =================
API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

PANEL_URL = os.getenv("PANEL_URL")
PANEL_TOKEN = os.getenv("PANEL_TOKEN")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

# ================= DB =================
conn = sqlite3.connect("data.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS numbers (
id INTEGER PRIMARY KEY,
service TEXT,
country TEXT,
number TEXT,
used INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
user_id INTEGER PRIMARY KEY
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
id INTEGER PRIMARY KEY,
user_id INTEGER,
number TEXT,
order_id TEXT
)
""")

conn.commit()

# ================= STATE =================
user_mode = {}
user_service = {}

# ================= OTP FUNCTION =================
def get_otp(order_id):
    try:
        url = f"{PANEL_URL}/get_sms?id={order_id}&token={PANEL_TOKEN}"
        res = requests.get(url, timeout=10)

        if res.status_code == 200:
            data = res.json()
            if "sms" in data:
                return data["sms"]
        return None
    except:
        return None

# ================= AUTO OTP =================
async def auto_otp(user_id, order_id):
    for i in range(10):
        otp = get_otp(order_id)

        if otp:
            try:
                await bot.send_message(user_id, f"✅ OTP:\n{otp}")
            except:
                pass
            return

        await asyncio.sleep(5)

# ================= START =================
@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)", (msg.from_user.id,))
    conn.commit()

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("📱 WhatsApp", callback_data="service_whatsapp"),
        types.InlineKeyboardButton("📘 Facebook", callback_data="service_facebook"),
        types.InlineKeyboardButton("🎵 TikTok", callback_data="service_tiktok")
    )

    await msg.answer("Select Service:", reply_markup=kb)

# ================= ADMIN =================
@dp.message_handler(commands=['admin'])
async def admin(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return await msg.reply("Denied")

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Add Number", callback_data="add_main"),
        types.InlineKeyboardButton("📋 List", callback_data="list"),
        types.InlineKeyboardButton("📊 Users", callback_data="users"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="bc")
    )

    await msg.answer("👑 Admin Panel", reply_markup=kb)

# ================= ADD FLOW =================
@dp.callback_query_handler(lambda c: c.data=="add_main")
async def add_main(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("WhatsApp", callback_data="add_whatsapp"),
        types.InlineKeyboardButton("Facebook", callback_data="add_facebook"),
        types.InlineKeyboardButton("TikTok", callback_data="add_tiktok")
    )
    await call.message.answer("Select Service", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("add_"))
async def select_service(call: types.CallbackQuery):
    service = call.data.split("_")[1]
    user_mode[call.from_user.id] = "add"
    user_service[call.from_user.id] = service

    await call.message.answer(
        "Send data like:\ncountry|number\n\nExample:\nPakistan|923001234567"
    )

# ================= ADD HANDLER =================
@dp.message_handler()
async def handle(msg: types.Message):
    uid = msg.from_user.id

    if uid not in user_mode:
        return

    if user_mode[uid] == "add":
        service = user_service[uid]
        lines = msg.text.split("\n")

        for line in lines:
            try:
                country, number = line.split("|")
                cursor.execute(
                    "INSERT INTO numbers (service,country,number) VALUES (?,?,?)",
                    (service, country, number)
                )
            except:
                continue

        conn.commit()
        await msg.reply("✅ Numbers Added")

# ================= USER FLOW =================
@dp.callback_query_handler(lambda c: c.data.startswith("service_"))
async def choose_service(call: types.CallbackQuery):
    service = call.data.split("_")[1]
    user_service[call.from_user.id] = service

    cursor.execute("SELECT DISTINCT country FROM numbers WHERE service=? AND used=0", (service,))
    countries = cursor.fetchall()

    kb = types.InlineKeyboardMarkup()
    for ctry in countries[:5]:
        kb.add(types.InlineKeyboardButton(ctry[0], callback_data=f"country_{ctry[0]}"))

    await call.message.answer("Select Country:", reply_markup=kb)

# ================= SHOW NUMBERS (AUTO OTP) =================
@dp.callback_query_handler(lambda c: c.data.startswith("country_"))
async def show_numbers(call: types.CallbackQuery):
    country = call.data.split("_")[1]
    service = user_service[call.from_user.id]

    cursor.execute("""
    SELECT id, number FROM numbers
    WHERE service=? AND country=? AND used=0
    LIMIT 3
    """, (service, country))

    rows = cursor.fetchall()

    if not rows:
        return await call.message.answer("❌ No numbers")

    text = ""

    for r in rows:
        number = r[1]
        db_id = r[0]

        text += f"⭐ +{number}\n"

        cursor.execute("UPDATE numbers SET used=1 WHERE id=?", (db_id,))

        order_id = str(db_id)

        cursor.execute(
            "INSERT INTO orders (user_id, number, order_id) VALUES (?,?,?)",
            (call.from_user.id, number, order_id)
        )

        asyncio.create_task(auto_otp(call.from_user.id, order_id))

    conn.commit()

    await call.message.answer(text)

# ================= LIST =================
@dp.callback_query_handler(lambda c: c.data=="list")
async def list_data(call: types.CallbackQuery):
    cursor.execute("SELECT service,country,number FROM numbers WHERE used=0 LIMIT 50")
    rows = cursor.fetchall()

    txt = "\n".join([f"{r[0]} | {r[1]} | {r[2]}" for r in rows]) or "Empty"
    await call.message.answer(txt)

# ================= USERS =================
@dp.callback_query_handler(lambda c: c.data=="users")
async def users(call: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*) FROM users")
    await call.message.answer(f"Users: {cursor.fetchone()[0]}")

# ================= BROADCAST =================
@dp.callback_query_handler(lambda c: c.data=="bc")
async def bc(call: types.CallbackQuery):
    await call.message.answer("Use /broadcast msg")

@dp.message_handler(commands=['broadcast'])
async def broadcast(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return

    users = cursor.execute("SELECT user_id FROM users").fetchall()

    for u in users:
        try:
            await bot.send_message(u[0], msg.get_args())
        except:
            pass

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp)
