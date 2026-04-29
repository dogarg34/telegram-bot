import requests
import json
import time
import re
import html
import unicodedata
import queue
import threading
import os
from typing import Optional, Tuple
import pycountry
import phonenumbers
from flask import Flask, Response

# ===== CONFIG =====
API_TOKEN = "QlNTRzRSQl99i5dpWFR3RmBneYqKinZCYoBYhn9ndoJHaIlfcpaQ"
BASE_URL = "http://147.135.212.197/crapi/time/viewstats"

BOT_TOKEN = "8701599744:AAH4pNNBV7XcohSj9YhhBKTW7OCXHKks8Ng"
CHAT_IDS = ["-1003964811702"]
CHANNEL_LINK = "https://t.me/superfaster13w"
DEVELOPER = "t.me/Saraquuen21"

SEEN_FILE = "seen_messages.json"
message_queue = queue.Queue()

# ===== ADMIN + NUMBER SYSTEM =====
ADMINS = {6997695956}  # apna Telegram user ID

NUMBERS_FILE = "numbers.txt"

# ========= PERSISTENT SEEN MESSAGES =========
def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen(seen: set):
    try:
        data = list(seen)
        if len(data) > 5000:
            data = data[-5000:]
        with open(SEEN_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[ERROR] Could not save seen_messages: {e}")

seen_messages = load_seen()
print(f"[INFO] Loaded {len(seen_messages)} seen messages from disk")

# ========= TELEGRAM HELPERS =========
def make_keyboard(buttons: list) -> dict:
    return {"inline_keyboard": buttons}

AUTO_DELETE_SECONDS = 300  # 5 minutes

def delete_message_later(chat_id, message_id, delay):
    time.sleep(delay)
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
        r = requests.post(url, data={"chat_id": chat_id, "message_id": message_id}, timeout=10)
        if r.status_code == 200:
            print(f"[INFO] Auto-deleted message {message_id} from {chat_id}")
        else:
            print(f"[WARN] Could not delete message {message_id}: {r.text[:100]}")
    except Exception as e:
        print(f"[ERROR] Delete failed: {e}")

def send_to_telegram(msg: str, keyboard: dict = None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    success = False
    for chat_id in CHAT_IDS:
        payload = {
            "chat_id": chat_id,
            "text": msg[:3900],
            "parse_mode": "HTML"
        }
        if keyboard:
            payload["reply_markup"] = json.dumps(keyboard)

        for attempt in range(3):
            try:
                r = requests.post(url, data=payload, timeout=10)
                if r.status_code == 200:
                    success = True
                    data = r.json()
                    message_id = data.get("result", {}).get("message_id")
                    if message_id:
                        threading.Thread(
                            target=delete_message_later,
                            args=(chat_id, message_id, AUTO_DELETE_SECONDS),
                            daemon=True
                        ).start()
                    break
                else:
                    print(f"[ERROR] Telegram ({chat_id}): {r.status_code} - {r.text[:200]}")
            except Exception as e:
                print(f"[ERROR] Telegram Exception ({chat_id}): {e}")
            time.sleep(1)
    return success

# ========= QUEUE WORKER =========
def sender_worker():
    while True:
        msg, kb = message_queue.get()
        send_to_telegram(msg, kb)
        print("[INFO] Message sent from queue")
        time.sleep(0.5)
        message_queue.task_done()

# ========= API HELPERS =========
def safe_request(url, params):
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            print(f"[ERROR] API HTTP {response.status_code} for {url}")
            return None
        return response.json()
    except requests.exceptions.ConnectionError as e:
        print(f"[ERROR] API Connection failed: {e}")
        return None
    except requests.exceptions.Timeout:
        print(f"[ERROR] API Timeout: {url}")
        return None
    except Exception as e:
        print(f"[ERROR] API Exception: {e}")
        return None

def view_stats(fromdate, todate, records=200):
    params = {
        "token": API_TOKEN,
        "fromdate": fromdate,
        "todate": todate,
        "records": records,
        "searchnumber": "",
        "searchcli": ""
    }
    return safe_request(BASE_URL, params)

def save_numbers(numbers):
    with open(NUMBERS_FILE, "a") as f:
        for num in numbers:
            f.write(num + "\n")

def load_numbers():
    if not os.path.exists(NUMBERS_FILE):
        return []
    with open(NUMBERS_FILE, "r") as f:
        return [x.strip() for x in f.readlines()]
      
# ========= OTP + NUMBER HELPERS =========
def extract_otp(message: str) -> Optional[str]:
    message = unicodedata.normalize("NFKD", message)
    message = re.sub(r"[\u200f\u200e\u202a-\u202e]", "", message)

    keyword_regex = re.search(r"(otp|code|pin|password)[^\d]{0,10}(\d[\d\-]{3,8})", message, re.I)
    if keyword_regex:
        return re.sub(r"\D", "", keyword_regex.group(2))

    reverse_regex = re.search(r"(\d[\d\-]{3,8})[^\w]{0,10}(otp|code|pin|password)", message, re.I)
    if reverse_regex:
        return re.sub(r"\D", "", reverse_regex.group(1))

    generic_regex = re.findall(r"\d{2,4}[-]?\d{2,4}", message)
    if generic_regex:
        return re.sub(r"\D", "", generic_regex[0])

    return None

def mask_number(number: str) -> str:
    if len(number) <= 4:
        return number
    mid = len(number) // 2
    return number[:mid - 1] + "**" + number[mid + 1:]

def country_from_number(number: str) -> Tuple[str, str]:
    try:
        parsed = phonenumbers.parse("+" + number)
        region = phonenumbers.region_code_for_number(parsed)
        if not region:
            return "Unknown", "🌍"
        country_obj = pycountry.countries.get(alpha_2=region)
        if not country_obj:
            return "Unknown", "🌍"
        country = country_obj.name
        flag = "".join([chr(127397 + ord(c)) for c in region])
        return country, flag
    except Exception:
        return "Unknown", "🌍"

# ========= FORMAT OTP MESSAGE =========
def format_message(record):
    current_time = record.get("datetime")
    number = record.get("number") or "Unknown"
    sender = record.get("cli") or "Unknown"
    message = record.get("message") or ""

    country, flag = country_from_number(number)
    otp = extract_otp(message)

    e_time    = '<tg-emoji emoji-id="5368666745852678313">🕰</tg-emoji>'
    e_country = '<tg-emoji emoji-id="5260293700088511294">🌍</tg-emoji>'
    e_service = '<tg-emoji emoji-id="5461117441612462242">📱</tg-emoji>'
    e_number  = '<tg-emoji emoji-id="5224607267797606837">📞</tg-emoji>'
    e_otp     = '<tg-emoji emoji-id="5456140674028019486">🔑</tg-emoji>'
    e_msg     = '<tg-emoji emoji-id="5240241223632954241">✉️</tg-emoji>'
    e_star    = '<tg-emoji emoji-id="5274099962655816924">⭐</tg-emoji>'

    otp_line = f"<blockquote>{e_otp} <b>OTP:</b> <code>{html.escape(otp)}</code></blockquote>\n" if otp else ""

    text = (
        f"{flag} {e_star} <b>New {html.escape(sender)} OTP Received</b>\n\n"
        f"<blockquote>{e_time} <b>Time:</b> <b>{html.escape(str(current_time))}</b></blockquote>\n"
        f"<blockquote>{e_country} <b>Country:</b> <b>{html.escape(country)} {flag}</b></blockquote>\n"
        f"<blockquote>{e_service} <b>Service:</b> <b>{html.escape(sender)}</b></blockquote>\n"
        f"<blockquote>{e_number} <b>Number:</b> <b>{html.escape(mask_number(number))}</b></blockquote>\n"
        f"{otp_line}"
        f"<blockquote>{e_msg} <b>Full Message:</b></blockquote>\n"
        f"<blockquote><code>{html.escape(message)}</code></blockquote>\n"
    )

    keyboard = make_keyboard([
        [
            {
                "text": "🚀 Panel",
                "url": CHANNEL_LINK,
                "style": "primary",
                "icon_custom_emoji_id": "5287472412051388029"
            },
            {
                "text": "📢 Channel",
                "url": DEVELOPER,
                "style": "success",
                "icon_custom_emoji_id": "5289934755456889065"
            }
        ]
    ])

    return text, keyboard

# ========= /START COMMAND HANDLER =========
last_update_id = 0

def handle_updates():
    global last_update_id
    tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    print("[INFO] /start command handler activated")

    while True:
        try:
            params = {"offset": last_update_id + 1, "timeout": 10}
            r = requests.get(tg_url, params=params, timeout=20)
            if r.status_code == 200:
                data = r.json()
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    chat_id = msg.get("chat", {}).get("id")
                    if text.startswith("/start") and chat_id:
                        reply_text = "🤖 <b>Bot is Active</b>"
                        kb = make_keyboard([
                            [
                                {
                                    "text": "🤖 Number Bot",
                                    "url": "https://t.me/OPXNmoptbot",
                                    "style": "primary",
                                    "icon_custom_emoji_id": "5287472412051388029"
                                },
                                {
                                    "text": "📢 Channel",
                                    "url": CHANNEL_LINK,
                                    "style": "success",
                                    "icon_custom_emoji_id": "5289934755456889065"
                                }
                            ]
                        ])
                        requests.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                            data={
                                "chat_id": chat_id,
                                "text": reply_text,
                                "parse_mode": "HTML",
                                "reply_markup": json.dumps(kb)
                            }, timeout=10)
        except Exception as e:
            print(f"[ERROR] Update polling: {e}")
        time.sleep(0.5)

# ========= MAIN OTP FETCHER =========
def main_loop():
    global seen_messages
    print("[INFO] OTP Monitor Started...")
    api_error_count = 0

    while True:
        stats = view_stats("1970-01-01 00:00:00", "2099-12-31 23:59:59", records=200) or {}

        if stats.get("status") == "Success":
            api_error_count = 0
            new_count = 0
            for record in stats.get("data", []):
                uid = f"{record.get('datetime')}_{record.get('number')}_{record.get('message')}"
                if uid not in seen_messages:
                    seen_messages.add(uid)
                    msg, kb = format_message(record)
                    message_queue.put((msg, kb))
                    print(f"[NEW OTP] {record.get('cli')} | {record.get('number')} | {record.get('message', '')[:50]}")
                    new_count += 1
            if new_count > 0:
                save_seen(seen_messages)
        else:
            api_error_count += 1
            if api_error_count == 1 or api_error_count % 100 == 0:
                print(f"[WARN] API status: {stats.get('status', 'no response')} (attempt {api_error_count})")

        time.sleep(0.2)

# ========= FLASK HEALTH CHECK =========
app = Flask(__name__)

@app.route("/health")
def health():
    return Response("OK", status=200)

# ========= /START + COMMAND HANDLER =========
last_update_id = 0

def handle_updates():
    global last_update_id
    tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    print("[INFO] Command handler activated")

    while True:
        try:
            params = {"offset": last_update_id + 1, "timeout": 10}
            r = requests.get(tg_url, params=params, timeout=20)

            if r.status_code == 200:
                data = r.json()

                for update in data.get("result", []):
                    last_update_id = update["update_id"]

                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    chat_id = msg.get("chat", {}).get("id")
                    user_id = msg.get("from", {}).get("id")

                    # ===== FILE UPLOAD =====
                    if "document" in msg:
                        if user_id not in ADMINS:
                            continue

                        file_id = msg["document"]["file_id"]

                        r = requests.get(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
                            params={"file_id": file_id}
                        )
                        file_path = r.json()["result"]["file_path"]

                        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                        file_data = requests.get(file_url).text

                        nums = file_data.splitlines()
                        clean = [re.sub(r"\D", "", n) for n in nums if len(n) >= 8]

                        save_numbers(clean)

                        send_to_telegram(f"📂 File uploaded\n✅ {len(clean)} numbers added")
                        continue

                    # ===== COMMANDS =====
                    if text.startswith("/start") and chat_id:
                        reply_text = "🤖 <b>Bot is Active</b>"
                        send_to_telegram(reply_text)

                    elif text.startswith("/addnum"):
                        if user_id not in ADMINS:
                            continue

                        nums = text.replace("/addnum", "").strip().split()
                        clean = [re.sub(r"\D", "", n) for n in nums if len(n) >= 8]

                        save_numbers(clean)
                        send_to_telegram(f"✅ Added {len(clean)} numbers")

                    elif text.startswith("/numbers"):
                        if user_id not in ADMINS:
                            continue

                        nums = load_numbers()
                        if not nums:
                            send_to_telegram("📭 No numbers saved")
                        else:
                            show = "\n".join(nums[:50])
                            send_to_telegram(f"📱 <b>Saved Numbers:</b>\n<code>{show}</code>")

                    elif text.startswith("/clearnum"):
                        if user_id not in ADMINS:
                            continue

                        open(NUMBERS_FILE, "w").close()
                        send_to_telegram("🗑 Numbers cleared")

        except Exception as e:
            print(f"[ERROR] Update polling: {e}")

        time.sleep(0.5)
    else:
        show = "\n".join(nums[:50])
        send_to_telegram(f"📱 <b>Saved Numbers:</b>\n<code>{show}</code>")

elif text.startswith("/clearnum"):
    if user_id not in ADMINS:
        continue

    open(NUMBERS_FILE, "w").close()
    send_to_telegram("🗑 Numbers cleared")
  if "document" in msg:
    if user_id not in ADMINS:
        continue

    file_id = msg["document"]["file_id"]

    r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile", params={"file_id": file_id})
    file_path = r.json()["result"]["file_path"]

    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    file_data = requests.get(file_url).text

    nums = file_data.splitlines()
    clean = [re.sub(r"\D", "", n) for n in nums if len(n) >= 8]

    save_numbers(clean)

    send_to_telegram(f"📂 File uploaded\n✅ {len(clean)} numbers added")
    
