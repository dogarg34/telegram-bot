import logging
import sqlite3
import requests
import os
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS numbers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    number TEXT
)
""")
conn.commit()

# START
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("WhatsApp", callback_data="whatsapp"))
    kb.add(types.InlineKeyboardButton("Facebook", callback_data="facebook"))
    kb.add(types.InlineKeyboardButton("TikTok", callback_data="tiktok"))

    await message.answer("Select Service:", reply_markup=kb)

# SHOW NUMBERS
@dp.callback_query_handler(lambda c: c.data in ["whatsapp", "facebook", "tiktok"])
async def show_numbers(callback_query: types.CallbackQuery):
    category = callback_query.data

    cursor.execute("SELECT number FROM numbers WHERE category=?", (category,))
    rows = cursor.fetchall()

    if not rows:
        await callback_query.message.answer("No numbers available")
        return

    kb = types.InlineKeyboardMarkup()

    for row in rows:
        num = row[0]
        kb.add(types.InlineKeyboardButton(f"+{num}", callback_data=f"otp_{num}"))

    await callback_query.message.answer("Select Number:", reply_markup=kb)

# OTP
@dp.callback_query_handler(lambda c: c.data.startswith("otp_"))
async def send_otp(callback_query: types.CallbackQuery):
    number = callback_query.data.split("_")[1]

    try:
        url = f"{PANEL_URL}/get-otp?number={number}&token={PANEL_TOKEN}"
        res = requests.get(url)
        otp = res.text
    except:
        otp = "Error getting OTP"

    await callback_query.message.answer(f"OTP for +{number}:\n{otp}")

# ADMIN
@dp.message_handler(commands=['admin'])
async def admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Add WhatsApp", "Add Facebook")
    kb.add("Add TikTok")

    await message.answer("Admin Panel:", reply_markup=kb)

# ADD NUMBERS
@dp.message_handler(lambda m: m.text.startswith("Add"))
async def add_prompt(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    category = message.text.split(" ")[1].lower()

    await message.answer(f"Send numbers for {category} (comma separated):")

    dp.register_message_handler(lambda m: save_numbers(m, category), state="*")

async def save_numbers(message, category):
    nums = message.text.split(",")

    for num in nums:
        num = num.strip()
        cursor.execute("INSERT INTO numbers (category, number) VALUES (?, ?)", (category, num))

    conn.commit()

    await message.answer("Numbers Added ✅")

# RUN
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
