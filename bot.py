import requests
import re
import time
import asyncio
import os
import json
from bs4 import BeautifulSoup
from flask import Flask

IVASMS_URL = os.getenv('IVASMS_URL', 'https://ivasms.com')
COOKIES_JSON = os.getenv('COOKIES_JSON')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '10'))

cookies_jar = {}
sent_otps = set()

def load_cookies():
    global cookies_jar
    if not COOKIES_JSON:
        print("❌ COOKIES_JSON missing")
        return False
    try:
        cookies_jar = json.loads(COOKIES_JSON)
        print(f"✅ Cookies loaded: {list(cookies_jar.keys())}")
        return True
    except:
        print("❌ Invalid JSON")
        return False

async def check_cookies_valid():
    global cookies_jar
    if not cookies_jar:
        return False
    try:
        r = requests.get(f"{IVASMS_URL}/dashboard", cookies=cookies_jar, timeout=10)
        if 'login' in r.url or r.status_code in [401,403]:
            print("⚠️ Cookies expired")
            return False
        return True
    except:
        return False

async def fetch_sms():
    global cookies_jar
    if not cookies_jar:
        if not load_cookies():
            return []
    urls = [
        f'{IVASMS_URL}/live-test-sms',
        f'{IVASMS_URL}/test-sms',
        f'{IVASMS_URL}/dashboard/live-sms',
        f'{IVASMS_URL}/api/live-sms'
    ]
    for url in urls:
        try:
            r = requests.get(url, cookies=cookies_jar, timeout=10)
            if r.status_code == 200:
                if 'json' in r.headers.get('Content-Type',''):
                    return parse_json(r.json())
                else:
                    return parse_html(r.text)
        except:
            continue
    return []

def parse_json(data):
    otps = []
    items = data.get('data') or data.get('messages') or data.get('sms') or []
    for item in items:
        msg = str(item.get('message') or item.get('content') or item.get('text') or '')
        otp = extract_otp(msg)
        if otp:
            otps.append({
                'otp': otp,
                'number': item.get('number') or item.get('phone') or 'Unknown',
                'service': item.get('service') or item.get('app') or 'Unknown',
                'message': msg[:300],
                'time': time.strftime('%H:%M:%S')
            })
    return otps

def parse_html(html):
    otps = []
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr')
    for row in rows[1:]:
        cols = row.find_all('td')
        if len(cols) >= 3:
            num = cols[0].get_text(strip=True)
            svc = cols[1].get_text(strip=True)
            msg = cols[2].get_text(strip=True)
            otp = extract_otp(msg)
            if otp:
                otps.append({
                    'otp': otp,
                    'number': num,
                    'service': svc,
                    'message': msg[:300],
                    'time': time.strftime('%H:%M:%S')
                })
    return otps

def extract_otp(text):
    patterns = [r'\b\d{4,6}\b', r'code[:\s]*(\d{4,6})', r'OTP[:\s]*(\d{4,6})']
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(1) if m.group(1) else m.group(0)
    return None

async def send_to_telegram(otp_data):
    # FIXED: Single line string, no triple quotes issue
    message = f"🔐 NEW OTP RECEIVED!\n\n📱 Number: {otp_data['number']}\n🏷️ Service: {otp_data['service']}\n🔢 OTP Code: {otp_data['otp']}\n⏰ Time: {otp_data['time']}\n\n📝 Message:\n{otp_data['message']}"
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print(f"✅ Sent OTP: {otp_data['otp']}")
            return True
        return False
    except Exception as e:
        print(f"❌ Send error: {e}")
        return False

async def keep_alive():
    app = Flask(__name__)
    @app.route('/')
    def home():
        return "✅ Bot running", 200
    def run():
        app.run(host='0.0.0.0', port=int(os.getenv('PORT',8080)))
    import threading
    threading.Thread(target=run, daemon=True).start()

async def main_loop():
    print("🚀 Bot started. Monitoring OTPs...")
    await load_cookies()
    while True:
        try:
            sms_list = await fetch_sms()
            for sms in sms_list:
                key = f"{sms['number']}_{sms['otp']}"
                if key not in sent_otps:
                    if await send_to_telegram(sms):
                        sent_otps.add(key)
            if len(sent_otps) > 500:
                sent_otps.clear()
            print(f"📊 {time.strftime('%H:%M:%S')} → {len(sms_list)} OTPs found")
        except Exception as e:
            print(f"⚠️ Error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

async def main():
    await asyncio.gather(main_loop(), keep_alive())

if __name__ == "__main__":
    required = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'COOKIES_JSON']
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print(f"❌ Missing env: {missing}")
    else:
        asyncio.run(main())
