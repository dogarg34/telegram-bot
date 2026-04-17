import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, executor, types

API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

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
CREATE TABLE IF NOT EXISTS countries (
id INTEGER PRIMARY KEY,
service TEXT,
name TEXT
)
""")

conn.commit()

# ================= DEFAULT COUNTRIES =================
def load_default():
    for s in ["whatsapp", "facebook", "tiktok"]:
        cursor.execute("SELECT * FROM countries WHERE service=?", (s,))
        if not cursor.fetchall():
            for c in ["USA", "UK", "UAE", "PK", "INDIA"]:
                cursor.execute("INSERT INTO countries (service,name) VALUES (?,?)", (s, c))
    conn.commit()

load_default()

# ================= STATE =================
user_mode = {}
user_service = {}
user_country = {}

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
        types.InlineKeyboardButton("✏️ Edit Country", callback_data="edit_country"),
        types.InlineKeyboardButton("📋 List", callback_data="list"),
    )
    await msg.answer("👑 Admin Panel", reply_markup=kb)

# ================= SELECT SERVICE =================
@dp.callback_query_handler(lambda c: c.data=="add_main")
async def add_main(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("WhatsApp", callback_data="svc_whatsapp"),
        types.InlineKeyboardButton("Facebook", callback_data="svc_facebook"),
        types.InlineKeyboardButton("TikTok", callback_data="svc_tiktok")
    )
    await call.message.answer("Select Service:", reply_markup=kb)

# ================= SHOW COUNTRIES =================
@dp.callback_query_handler(lambda c: c.data.startswith("svc_"))
async def show_country(call: types.CallbackQuery):
    service = call.data.split("_")[1]
    user_service[call.from_user.id] = service

    cursor.execute("SELECT name FROM countries WHERE service=?", (service,))
    rows = cursor.fetchall()

    kb = types.InlineKeyboardMarkup()
    for r in rows:
        kb.add(types.InlineKeyboardButton(r[0], callback_data=f"addcountry_{r[0]}"))

    await call.message.answer("Select Country:", reply_markup=kb)

# ================= SELECT COUNTRY =================
@dp.callback_query_handler(lambda c: c.data.startswith("addcountry_"))
async def select_country(call: types.CallbackQuery):
    country = call.data.split("_")[1]

    user_mode[call.from_user.id] = "add"
    user_country[call.from_user.id] = country

    await call.message.answer(f"Send numbers for {country}\n\nExample:\n923001234567")

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

        for num in lines:
            cursor.execute(
                "INSERT INTO numbers (service,country,number) VALUES (?,?,?)",
                (service, country, num)
            )

        conn.commit()
        await msg.reply("✅ Numbers Added")

# ================= EDIT COUNTRY =================
@dp.callback_query_handler(lambda c: c.data=="edit_country")
async def edit_country(call: types.CallbackQuery):
    await call.message.answer("Send like:\nwhatsapp|USA|Pakistan")

@dp.message_handler(lambda m: "|" in m.text)
async def update_country(msg: types.Message):
    try:
        service, old, new = msg.text.split("|")
        cursor.execute("UPDATE countries SET name=? WHERE service=? AND name=?", (new, service, old))
        conn.commit()
        await msg.reply("✅ Updated")
    except:
        pass

# ================= USER FLOW =================
@dp.callback_query_handler(lambda c: c.data.startswith("service_"))
async def choose_service(call: types.CallbackQuery):
    service = call.data.split("_")[1]
    user_service[call.from_user.id] = service

    cursor.execute("SELECT DISTINCT country FROM numbers WHERE service=? AND used=0", (service,))
    countries = cursor.fetchall()

    kb = types.InlineKeyboardMarkup()
    for ctry in countries:
        kb.add(types.InlineKeyboardButton(ctry[0], callback_data=f"country_{ctry[0]}"))

    await call.message.answer("Select Country:", reply_markup=kb)

# ================= SHOW NUMBERS (UPDATED UI) =================
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

    # HEADER
    await call.message.answer(f"✅ Order Successful\n🌍 Range: {country}")

    text = ""

    for r in rows:
        text += f"📋 ⭐ +{r[1]}\n\n"
        cursor.execute("UPDATE numbers SET used=1 WHERE id=?", (r[0],))

    conn.commit()

    # BUTTONS
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🔄 Change Number", callback_data=f"country_{country}"),
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
