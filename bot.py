import requests
import re
import time
import asyncio
import os
import json
from bs4 import BeautifulSoup
from flask import Flask

IVASMS_URL = os.getenv('IVASMS_URL', 'https://www.ivasms.com')
COOKIES_JSON = os.getenv('COOKIES_JSON')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '10'))

cookies_jar = {}
sent_otps = set()
FOUND_SMS_URL = None

def load_cookies():
    global cookies_jar
    if not COOKIES_JSON:
        print("❌ COOKIES_JSON missing")
        return False
    try:
        cookies_jar = json.loads(COOKIES_JSON)
        print(f"✅ Cookies loaded: {list(cookies_jar.keys())}")
        return True
    except Exception as e:
        print(f"❌ Invalid JSON: {e}")
        return False

async def find_exact_sms_url():
    global FOUND_SMS_URL
    
    # FORCE USE CORRECT URL FIRST
    manual_url = f"{IVASMS_URL}/index.php?route=live-sms"
    print(f"📍 Trying manual URL first: {manual_url}")
    
    try:
        r = requests.get(manual_url, cookies=cookies_jar, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0',
            'X-Requested-With': 'XMLHttpRequest'
        })
        if r.status_code == 200:
            print(f"✅ Manual URL working! Status: {r.status_code}")
            FOUND_SMS_URL = manual_url
            return manual_url
    except Exception as e:
        print(f"Manual URL test failed: {e}")
    
    # Auto-search as fallback
    print("\n🔍 Auto-searching for Live SMS URL...")
    possible_paths = [
        '/index.php?route=live-sms',
        '/live-test-sms',
        '/test-sms',
        '/live-sms',
        '/dashboard/live-sms',
        '/portal/live/test_sms',
        '/api/live-sms',
    ]
    
    for path in possible_paths:
        url = f"{IVASMS_URL}{path}"
        try:
            r = requests.get(url, cookies=cookies_jar, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0',
                'X-Requested-With': 'XMLHttpRequest'
            })
            if r.status_code == 200:
                text_lower = r.text.lower()
                if len(r.text) > 500 and 'login' not in text_lower:
                    print(f"✅ Found working URL: {url}")
                    FOUND_SMS_URL = url
                    return url
        except:
            continue
    
    print("❌ No working URL found")
    return None

async def fetch_sms():
    global cookies_jar, FOUND_SMS_URL
    
    if not cookies_jar:
        if not load_cookies():
            return []
    
    if not FOUND_SMS_URL:
        await find_exact_sms_url()
        if not FOUND_SMS_URL:
            return []
    
    try:
        print(f"🌐 Fetching: {FOUND_SMS_URL}")
        r = requests.get(FOUND_SMS_URL, cookies=cookies_jar, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        print(f"📡 Status: {r.status_code}, Size: {len(r.text)} bytes")
        
        if r.status_code == 200:
            return parse_html_response(r.text)
        else:
            print(f"⚠️ Status {r.status_code}, trying fallback...")
            return []
            
    except Exception as e:
        print(f"❌ Fetch error: {e}")
        return []

def parse_html_response(html):
    otps = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find OTP table
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 3:
                first_cell = cells[0].get_text(strip=True)
                service = cells[1].get_text(strip=True)
                message = cells[2].get_text(strip=True)
                
                phone_match = re.search(r'(\+\d{8,15})', first_cell)
                number = phone_match.group(1) if phone_match else first_cell
                otp = extract_otp(message)
                
                if otp:
                    otps.append({
                        'otp': otp,
                        'number': number,
                        'service': service,
                        'message': message[:500],
                        'time': time.strftime('%H:%M:%S')
                    })
    
    # Remove duplicates
    unique_otps = []
    seen = set()
    for otp in otps:
        key = f"{otp['otp']}_{otp['number']}"
        if key not in seen:
            seen.add(key)
            unique_otps.append(otp)
    
    return unique_otps

def extract_otp(text):
    patterns = [
        r'\b\d{4}\b',
        r'\b\d{5}\b',
        r'\b\d{6}\b',
        r'code[:\s]*(\d{4,6})',
        r'OTP[:\s]*(\d{4,6})',
        r'verification[:\s]*(\d{4,6})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1) if match.group(1) else match.group(0)
    return None

async def send_to_telegram(otp_data):
    message = f"🔐 *NEW OTP RECEIVED!*\n\n📱 *Number:* `{otp_data['number']}`\n🏷️ *Service:* {otp_data['service']}\n🔢 *OTP Code:* `{otp_data['otp']}`\n⏰ *Time:* {otp_data['time']}"
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
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
    def health():
        return "✅ Bot running", 200
    def run():
        app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)), debug=False)
    import threading
    threading.Thread(target=run, daemon=True).start()

async def main_loop():
    print("🚀 IVASMS OTP Bot Starting...")
    print(f"📡 Panel URL: {IVASMS_URL}")
    
    if not load_cookies():
        print("❌ Failed to load cookies")
        return
    
    await find_exact_sms_url()
    
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
        print(f"❌ Missing: {missing}")
    else:
        asyncio.run(main())
