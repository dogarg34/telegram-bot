import logging
import os
import sqlite3
import asyncio
import re
import aiohttp
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

PANEL_URL = os.getenv("PANEL_URL")
PANEL_TOKEN = os.getenv("PANEL_TOKEN")

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

# ================= GLOBAL OTP =================
active_orders = {}

def extract_code(msg):
    m = re.search(r"\b\d{4,8}\b", msg or "")
    return m.group(0) if m else msg

async def otp_poller():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{PANEL_URL}/viewstats?token={PANEL_TOKEN}") as r:
                    data = await r.json()
                    for item in data.get("data", []):
                        num = str(item.get("num") or item.get("number"))
                        sms = item.get("message") or item.get("sms")

                        if num in active_orders:
                            uid = active_orders[num]
                            code = extract_code(sms)

                            await bot.send_message(uid, f"📩 OTP\n📱 +{num}\n🔑 {code}")
                            del active_orders[num]

        except Exception as e:
            print("OTP ERROR:", e)

        await asyncio.sleep(2)

# ================= MENU =================
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Get Number"), KeyboardButton("👤 Profile"))
    kb.add(KeyboardButton("💰 Balances"), KeyboardButton("💸 Withdraw"))
    kb.add(KeyboardButton("❤️ Invite"), KeyboardButton("💬 Support"))
    return kb

# ================= DB =================
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS numbers (
id INTEGER PRIMARY KEY,
service TEXT,
country TEXT,
number TEXT UNIQUE,
used INTEGER DEFAULT 0)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS users (
user_id INTEGER PRIMARY KEY)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS orders (
id INTEGER PRIMARY KEY,
user_id INTEGER,
number TEXT)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS countries (
id INTEGER PRIMARY KEY,
service TEXT,
name TEXT)""")

conn.commit()

# ================= DEFAULT =================
def load_default():
    for s in ["whatsapp","facebook","tiktok"]:
        cursor.execute("SELECT * FROM countries WHERE service=?", (s,))
        if not cursor.fetchall():
            for c in ["USA","BJ","USA2","NISHA","UK"]:
                cursor.execute("INSERT INTO countries (service,name) VALUES (?,?)",(s,c))
    conn.commit()

load_default()

# ================= START =================
@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)",(msg.from_user.id,))
    conn.commit()

    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("📱 WhatsApp",callback_data="service_whatsapp"),
        types.InlineKeyboardButton("📘 Facebook",callback_data="service_facebook"),
        types.InlineKeyboardButton("🎵 TikTok",callback_data="service_tiktok")
    )

    await msg.answer("Select Service:", reply_markup=kb)
    await msg.answer("Main Menu 👇", reply_markup=main_menu())

# ================= BUTTONS =================
@dp.message_handler(lambda m: m.text == "📱 Get Number")
async def btn_get(msg: types.Message):
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("📱 WhatsApp",callback_data="service_whatsapp"),
        types.InlineKeyboardButton("📘 Facebook",callback_data="service_facebook"),
        types.InlineKeyboardButton("🎵 TikTok",callback_data="service_tiktok")
    )
    await msg.answer("Select Service:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "👤 Profile")
async def profile(msg: types.Message):
    await msg.answer(f"👤 ID: {msg.from_user.id}")

@dp.message_handler(lambda m: m.text == "💰 Balances")
async def balance(msg: types.Message):
    await msg.answer("💰 Balance: 0")

@dp.message_handler(lambda m: m.text == "💸 Withdraw")
async def withdraw(msg: types.Message):
    await msg.answer("Withdraw coming soon")

@dp.message_handler(lambda m: m.text == "❤️ Invite")
async def invite(msg: types.Message):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={msg.from_user.id}"
    await msg.answer(f"🔗 {link}")

@dp.message_handler(lambda m: m.text == "💬 Support")
async def support(msg: types.Message):
    await msg.answer("Contact admin")

# ================= ADMIN =================
@dp.message_handler(commands=['admin'])
async def admin(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return await msg.reply("Denied")

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Add Number",callback_data="add"),
        types.InlineKeyboardButton("✏️ Edit Country",callback_data="edit"),
        types.InlineKeyboardButton("📂 Used",callback_data="used")
    )
    await msg.answer("Admin Panel", reply_markup=kb)

# ================= ADD (NEW SYSTEM) =================
user_state = {}

# STEP 1 → service select
@dp.callback_query_handler(lambda c: c.data=="add")
async def add(call):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("📱 WhatsApp", callback_data="addservice_whatsapp"),
        types.InlineKeyboardButton("📘 Facebook", callback_data="addservice_facebook"),
        types.InlineKeyboardButton("🎵 TikTok", callback_data="addservice_tiktok"),
    )
    await call.message.answer("Select Service:", reply_markup=kb)


# STEP 2 → country select
@dp.callback_query_handler(lambda c: c.data.startswith("addservice_"))
async def add_service(call):
    service = call.data.split("_")[1]
    user_state[call.from_user.id] = {"service": service}

    cursor.execute("SELECT name FROM countries WHERE service=?", (service,))
    rows = cursor.fetchall()

    kb = types.InlineKeyboardMarkup()
    for r in rows:
        kb.add(types.InlineKeyboardButton(r[0], callback_data=f"addcountry_{r[0]}"))

    await call.message.answer("Select Country:", reply_markup=kb)


# STEP 3 → number input
@dp.callback_query_handler(lambda c: c.data.startswith("addcountry_"))
async def add_country(call):
    country = call.data.split("_")[1]

    if call.from_user.id in user_state:
        user_state[call.from_user.id]["country"] = country

    await call.message.answer("📲 Send numbers only:\n(one per line)")


# STEP 4 → save
@dp.message_handler(lambda m: m.from_user.id in user_state and "country" in user_state[m.from_user.id])
async def save_numbers(msg):
    try:
        data = user_state[msg.from_user.id]
        service = data["service"]
        country = data["country"]

        lines = msg.text.splitlines()
        added = 0

        for num in lines:
            num = num.strip()
            if not num:
                continue

            cursor.execute(
                "INSERT OR IGNORE INTO numbers VALUES (NULL,?,?,?,0)",
                (service, country, num)
            )
            added += 1

        conn.commit()
        user_state.pop(msg.from_user.id)

        await msg.answer(f"✅ {added} Numbers Added\n🌍 {country}\n📱 {service}")

    except Exception as e:
        await msg.answer("Error adding numbers")
        print(e)

# ================= EDIT COUNTRY =================
@dp.callback_query_handler(lambda c: c.data=="edit")
async def edit(call):
    await call.message.answer("service|old|new")

@dp.message_handler(lambda m: "|" in m.text and m.from_user.id==ADMIN_ID)
async def edit_country(msg):
    try:
        s,o,n = msg.text.split("|")
        cursor.execute("UPDATE countries SET name=? WHERE service=? AND name=?",(n,s,o))
        cursor.execute("UPDATE numbers SET country=? WHERE service=? AND country=?",(n,s,o))
        conn.commit()
        await msg.answer("Updated")
    except:
        await msg.answer("Error")

# ======== GET ========
@dp.callback_query_handler(lambda c: c.data.startswith("get_"))
async def get(call):
    await call.answer()  # ✅ loading fix

    _, country, service = call.data.split("_")

    cursor.execute(
        "SELECT id, number FROM numbers WHERE service=? AND country=? AND used=0 LIMIT 3",
        (service, country)
    )
    rows = cursor.fetchall()

    if not rows:
        return await call.message.answer("❌ No numbers")

    text = ""

for r in rows:
    id, num = r

    active_orders[num] = call.from_user.id
    cursor.execute("UPDATE numbers SET used=1 WHERE id=?", (id,))

    text += f"📋 <code>{num}</code>\n\n"

conn.commit()

kb = types.InlineKeyboardMarkup(row_width=1)
kb.add(
    types.InlineKeyboardButton("🔁 Change Number", callback_data=f"get_{country}_{service}"),
    types.InlineKeyboardButton("⬅ Back", callback_data=f"service_{service}")
)

await call.message.edit_text(
    f"✅ Order Successful\n🌍 Range: {country}\n\n📱 Your Numbers 👇\n\n{text}",
    parse_mode="HTML",
    reply_markup=kb
)


# ================= START =================
async def on_startup(dp):
    asyncio.create_task(otp_poller())

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)
