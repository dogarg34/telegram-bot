import logging, os, sqlite3, asyncio, re, aiohttp, phonenumbers
from aiogram import Bot, Dispatcher, executor, types

API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PANEL_URL = os.getenv("PANEL_URL")
PANEL_TOKEN = os.getenv("PANEL_TOKEN")

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

# ===== GLOBAL =====
active_orders = {}
flag_cache = {}

# ===== DB =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS countries(service TEXT, name TEXT)")
conn.commit()

# ===== FLAG =====
def get_flag(num):
    if num in flag_cache:
        return flag_cache[num]
    try:
        p = phonenumbers.parse("+"+num)
        cc = phonenumbers.region_code_for_number(p)
        flag = ''.join(chr(ord(c)+127397) for c in cc)
    except:
        flag = "🌍"
    flag_cache[num] = flag
    return flag

# ===== PANEL FETCH =====
async def fetch_panel(service):
    try:
        url = f"{PANEL_URL}/numbers?service={service}&token={PANEL_TOKEN}"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=10) as r:
                data = await r.json()
                return data.get("numbers", [])
    except:
        return []

# ===== COUNTRY DETECT =====
def get_country(num):
    try:
        p = phonenumbers.parse("+"+num)
        return phonenumbers.region_code_for_number(p)
    except:
        return "UNK"

# ===== AUTO COUNTRY SYNC =====
async def auto_country_sync():
    while True:
        try:
            for service in ["whatsapp","facebook","tiktok"]:
                nums = await fetch_panel(service)

                for n in nums[:50]:
                    c = get_country(n)
                    cursor.execute("SELECT 1 FROM countries WHERE service=? AND name=?", (service,c))
                    if not cursor.fetchone():
                        cursor.execute("INSERT INTO countries VALUES(?,?)",(service,c))

            conn.commit()
            logging.info("🌍 Countries synced")

        except Exception as e:
            logging.error(e)

        await asyncio.sleep(10800)

# ===== KEYBOARD =====
def number_kb(numbers, service, country):
    kb = types.InlineKeyboardMarkup(row_width=1)

    for n in numbers:
        kb.add(types.InlineKeyboardButton(
            text=f"📋 {get_flag(n)} +{n}",
            callback_data=f"copy_{n}"
        ))

    kb.row(
        types.InlineKeyboardButton("🔄 Change Number", callback_data=f"refresh_{service}_{country}"),
        types.InlineKeyboardButton("⬅️ Back", callback_data=f"srv_{service}")
    )

    return kb

# ===== START =====
@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("📱 WhatsApp",callback_data="srv_whatsapp"),
        types.InlineKeyboardButton("📘 Facebook",callback_data="srv_facebook"),
        types.InlineKeyboardButton("🎵 TikTok",callback_data="srv_tiktok")
    )
    await msg.answer("Select Service:", reply_markup=kb)

# ===== SERVICE =====
@dp.callback_query_handler(lambda c: c.data.startswith("srv_"))
async def srv(call):
    service = call.data.split("_")[1]

    cursor.execute("SELECT name FROM countries WHERE service=?", (service,))
    rows = cursor.fetchall()

    kb = types.InlineKeyboardMarkup()
    for r in rows:
        kb.add(types.InlineKeyboardButton(r[0], callback_data=f"get_{service}_{r[0]}"))

    await call.message.answer("Select Country:", reply_markup=kb)

# ===== GET NUMBERS =====
@dp.callback_query_handler(lambda c: c.data.startswith("get_"))
async def get(call):
    _,service,country = call.data.split("_")

    nums = await fetch_panel(service)

    filtered = [n for n in nums if get_country(n) == country]

    if not filtered:
        return await call.message.answer("❌ No numbers")

    show = []

    for n in filtered:
        if n in active_orders:
            continue
        active_orders[n] = call.from_user.id
        show.append(n)
        if len(show) >= 5:
            break

    if not show:
        return await call.message.answer("⚠️ All numbers busy")

    await call.message.answer(
        f"✅ {service.upper()}\n🌍 {country}",
        reply_markup=number_kb(show, service, country)
    )

# ===== COPY =====
@dp.callback_query_handler(lambda c: c.data.startswith("copy_"))
async def copy_number(call):
    num = call.data.split("_")[1]

    await call.answer("📋 Copied!")

    await call.message.answer(
        f"📋 <b>Number:</b>\n<code>+{num}</code>"
    )

# ===== REFRESH =====
@dp.callback_query_handler(lambda c: c.data.startswith("refresh_"))
async def refresh(call):
    _,service,country = call.data.split("_")

    await call.answer("🔄 Refreshing...")

    class Fake:
        data = f"get_{service}_{country}"
        from_user = call.from_user
        message = call.message

    await get(Fake)

# ===== OTP =====
def extract_code(msg):
    m = re.search(r"\d{4,8}", msg or "")
    return m.group(0) if m else msg

async def otp_poller():
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{PANEL_URL}/viewstats?token={PANEL_TOKEN}", timeout=10) as r:
                    data = await r.json()

                    for i in data.get("data", []):
                        num = str(i.get("num") or i.get("number"))
                        sms = i.get("message") or i.get("sms")

                        if num in active_orders:
                            uid = active_orders[num]
                            await bot.send_message(uid, f"📩 OTP\n+{num}\n🔑 {extract_code(sms)}")
                            del active_orders[num]

        except Exception as e:
            logging.error(e)

        await asyncio.sleep(4)

# ===== STARTUP =====
async def on_startup(dp):
    asyncio.create_task(otp_poller())
    asyncio.create_task(auto_country_sync())

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)
