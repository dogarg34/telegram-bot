import logging
import os
import sqlite3
import requests
import asyncio
from aiogram import Bot, Dispatcher, executor, types

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
order_id TEXT,
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

# ================= OTP FETCH =================
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
    for i in range(12):
        otp = get_otp(order_id)

        if otp:
            # 🔒 CHECK: OTP sirf usi user ko jaye
            cursor.execute("SELECT user_id FROM orders WHERE order_id=?", (order_id,))
            row = cursor.fetchone()

            if row and row[0] == user_id:
                await bot.send_message(user_id, f"✅ OTP:\n{otp}")
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
    )

    await msg.answer("👑 Admin Panel", reply_markup=kb)

# ================= ADD =================
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
    await call.message.answer(f"Send:\ncountry|number|order_id")

    dp.current_state(user=call.from_user.id).set_data({"service": service})

@dp.message_handler()
async def add_numbers(msg: types.Message):
    data = await dp.current_state(user=msg.from_user.id).get_data()

    if not data:
        return

    service = data.get("service")

    lines = msg.text.split("\n")

    for line in lines:
        try:
            country, number, order_id = line.split("|")

            cursor.execute(
                "INSERT INTO numbers (service,country,number,order_id) VALUES (?,?,?,?)",
                (service, country, number, order_id)
            )
        except:
            continue

    conn.commit()
    await msg.reply("✅ Numbers Added")

# ================= USER FLOW =================
@dp.callback_query_handler(lambda c: c.data.startswith("service_"))
async def choose_service(call: types.CallbackQuery):
    service = call.data.split("_")[1]

    cursor.execute("SELECT DISTINCT country FROM numbers WHERE service=? AND used=0", (service,))
    countries = cursor.fetchall()

    kb = types.InlineKeyboardMarkup()
    for c in countries:
        kb.add(types.InlineKeyboardButton(c[0], callback_data=f"country_{c[0]}_{service}"))

    await call.message.answer("Select Country:", reply_markup=kb)

# ================= GET NUMBERS =================
@dp.callback_query_handler(lambda c: c.data.startswith("country_"))
async def show_numbers(call: types.CallbackQuery):
    _, country, service = call.data.split("_")

    cursor.execute("""
    SELECT id, number, order_id FROM numbers
    WHERE service=? AND country=? AND used=0
    LIMIT 3
    """, (service, country))

    rows = cursor.fetchall()

    if not rows:
        return await call.message.answer("❌ No numbers")

    await call.message.answer(f"✅ Order Successful\n🌍 Range: {country}")

    text = ""

    for r in rows:
        db_id, number, order_id = r

        text += f"📋 ⭐ +{number}\n\n"

        cursor.execute("UPDATE numbers SET used=1 WHERE id=?", (db_id,))

        # 🔒 SAVE USER ↔ ORDER LINK
        cursor.execute(
            "INSERT INTO orders (user_id, number, order_id) VALUES (?,?,?)",
            (call.from_user.id, number, order_id)
        )

        # 🔄 AUTO OTP START
        asyncio.create_task(auto_otp(call.from_user.id, order_id))

    conn.commit()

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🔄 Change Number", callback_data=f"country_{country}_{service}"),
        types.InlineKeyboardButton("⬅️ Back", callback_data=f"service_{service}")
    )

    await call.message.answer(text, reply_markup=kb)

# ================= LIST =================
@dp.callback_query_handler(lambda c: c.data=="list")
async def list_data(call: types.CallbackQuery):
    cursor.execute("SELECT service,country,number FROM numbers WHERE used=0 LIMIT 50")
    rows = cursor.fetchall()

    txt = "\n".join([f"{r[0]} | {r[1]} | {r[2]}" for r in rows]) or "Empty"
    await call.message.answer(txt)

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp)
