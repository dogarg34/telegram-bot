import logging
import os
import sqlite3
import requests
import asyncio
import re
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS countries (
id INTEGER PRIMARY KEY,
service TEXT,
name TEXT
)
""")

conn.commit()

# ================= DEFAULT COUNTRIES =================
def load_default():
    for s in ["whatsapp","facebook","tiktok"]:
        cursor.execute("SELECT * FROM countries WHERE service=?", (s,))
        if not cursor.fetchall():
            for c in ["USA","BJ","USA2","NISHA","UK"]:
                cursor.execute("INSERT INTO countries (service,name) VALUES (?,?)",(s,c))
    conn.commit()

load_default()

# ================= OTP NEW SYSTEM =================
def get_all_otps():
    try:
        url = f"{PANEL_URL}/viewstats?token={PANEL_TOKEN}"
        r = requests.get(url)
        data = r.json()
        return data.get("data", [])
    except:
        return []

def extract_code(msg):
    m = re.search(r"\b\d{4,8}\b", msg)
    return m.group(0) if m else msg

async def auto_otp(user_id, number):
    for i in range(20):
        data = get_all_otps()

        for item in data:
            panel_number = str(item.get("num") or item.get("number"))
            sms = item.get("message") or item.get("sms")

            if panel_number == str(number):  # ✅ FULL MATCH
                code = extract_code(sms)

                await bot.send_message(
                    user_id,
                    f"📩 OTP Received\n📱 +{number}\n🔑 Code: {code}"
                )
                return

        await asyncio.sleep(5)

# ================= STATE =================
user_service = {}
user_country = {}
user_mode = {}

# ================= START =================
@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)",(msg.from_user.id,))
    conn.commit()

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("📱 WhatsApp",callback_data="service_whatsapp"),
        types.InlineKeyboardButton("📘 Facebook",callback_data="service_facebook"),
        types.InlineKeyboardButton("🎵 TikTok",callback_data="service_tiktok")
    )
    await msg.answer("Select Service:",reply_markup=kb)

# ================= ADMIN =================
@dp.message_handler(commands=['admin'])
async def admin(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return await msg.reply("Denied")

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Add Number",callback_data="add_main"),
        types.InlineKeyboardButton("✏️ Edit Country",callback_data="edit_country"),
        types.InlineKeyboardButton("📂 Used Numbers",callback_data="used_list")
    )
    await msg.answer("👑 Admin Panel",reply_markup=kb)

# ================= ADD FLOW =================
@dp.callback_query_handler(lambda c: c.data=="add_main")
async def add_main(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("WhatsApp",callback_data="svc_whatsapp"),
        types.InlineKeyboardButton("Facebook",callback_data="svc_facebook"),
        types.InlineKeyboardButton("TikTok",callback_data="svc_tiktok")
    )
    await call.message.answer("Select Service:",reply_markup=kb)

# ================= SERVICE → COUNTRIES =================
@dp.callback_query_handler(lambda c: c.data.startswith("svc_"))
async def svc(call: types.CallbackQuery):
    service = call.data.split("_")[1]
    user_service[call.from_user.id] = service

    cursor.execute("SELECT name FROM countries WHERE service=?", (service,))
    rows = cursor.fetchall()

    kb = types.InlineKeyboardMarkup()
    for r in rows:
        kb.add(types.InlineKeyboardButton(r[0],callback_data=f"countryadd_{r[0]}"))

    await call.message.answer("Select Country:",reply_markup=kb)

# ================= SELECT COUNTRY =================
@dp.callback_query_handler(lambda c: c.data.startswith("countryadd_"))
async def country_add(call: types.CallbackQuery):
    country = call.data.split("_")[1]
    user_country[call.from_user.id] = country
    user_mode[call.from_user.id] = "add"

    await call.message.answer(f"Send numbers for {country}\nFormat:\nnumber|order_id")

# ================= ADD NUMBERS =================
@dp.message_handler()
async def add_numbers(msg: types.Message):
    uid = msg.from_user.id

    if uid not in user_mode:
        return

    if user_mode[uid] == "add":
        service = user_service[uid]
        country = user_country[uid]

        lines = msg.text.split("\n")

        for line in lines:
            try:
                number, order_id = line.split("|")
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
async def choose(call: types.CallbackQuery):
    service = call.data.split("_")[1]
    user_service[call.from_user.id] = service

    cursor.execute("SELECT DISTINCT country FROM numbers WHERE service=? AND used=0",(service,))
    rows = cursor.fetchall()

    kb = types.InlineKeyboardMarkup()
    for r in rows:
        kb.add(types.InlineKeyboardButton(r[0],callback_data=f"get_{r[0]}_{service}"))

    await call.message.answer("Select Country:",reply_markup=kb)

# ================= GET NUMBERS =================
@dp.callback_query_handler(lambda c: c.data.startswith("get_"))
async def get_num(call: types.CallbackQuery):
    _, country, service = call.data.split("_")

    cursor.execute("SELECT id,number FROM numbers WHERE service=? AND country=? AND used=0 LIMIT 3",(service,country))
    rows = cursor.fetchall()

    if not rows:
        return await call.message.answer("❌ No numbers")

    await call.message.answer(f"✅ Order Successful\n🌍 {country}")

    text=""
    for r in rows:
        id, num = r
        text += f"⭐ +{num}\n\n"

        cursor.execute("UPDATE numbers SET used=1 WHERE id=?",(id,))

        # ✅ NEW OTP SYSTEM CALL
        asyncio.create_task(auto_otp(call.from_user.id, num))

    conn.commit()

    await call.message.answer(text)

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp)
