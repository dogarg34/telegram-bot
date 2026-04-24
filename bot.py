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
FOUND_SMS_URL = None  # Store the working URL once found

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
    """Auto-detect the correct Live SMS URL"""
    global FOUND_SMS_URL
    
    # Extensive list of possible URLs to try
    possible_paths = [
        # Common panel paths
        '/live-test-sms',
        '/test-sms',
        '/live-sms',
        '/sms',
        '/messages',
        '/history',
        '/numbers',
        '/dashboard/live-sms',
        '/dashboard/test-sms',
        '/dashboard/sms',
        '/dashboard/messages',
        '/portal/live/test_sms',
        '/portal/test-sms',
        '/portal/live-sms',
        '/portal/sms',
        '/portal/messages',
        '/api/live-sms',
        '/api/test-sms',
        '/api/sms',
        '/api/messages',
        '/api/get-live-sms',
        '/api/get-sms',
        '/get-live-sms',
        '/get-sms',
        # With prefixes
        '/index.php?route=live-sms',
        '/?page=live-sms',
        '/?do=live-sms',
        '/live',
        '/test',
        '/recent',
        '/inbox',
        '/sms/list',
        '/sms/receive',
        '/otp/list',
        '/otp/recent',
    ]
    
    print("\n🔍 Auto-searching for Live SMS URL...")
    
    for path in possible_paths:
        url = f"{IVASMS_URL}{path}"
        try:
            r = requests.get(url, cookies=cookies_jar, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0',
                'X-Requested-With': 'XMLHttpRequest'
            })
            
            # Check if URL returns valid content (not 404, not login page)
            content_type = r.headers.get('Content-Type', '')
            content_length = len(r.text)
            
            # Skip 404 pages
            if r.status_code == 404:
                continue
            
            # Check if page contains SMS/OTP related content
            text_lower = r.text.lower()
            has_sms_keywords = any(keyword in text_lower for keyword in 
                ['sms', 'otp', 'message', 'phone', 'number', '+', 'verification', 'code'])
            
            # Skip login pages (usually small or have login form)
            has_login_keywords = any(keyword in text_lower for keyword in 
                ['login', 'sign in', 'email', 'password', 'remember me'])
            
            if has_sms_keywords and not has_login_keywords and content_length > 500:
                print(f"✅ Found working URL: {url}")
                print(f"   Status: {r.status_code}, Length: {content_length}, Type: {content_type}")
                FOUND_SMS_URL = url
                return url
                
        except Exception as e:
            continue
    
    # If no URL found, try to extract from dashboard
    print("\n⚠️ No direct URL found. Checking dashboard for links...")
    try:
        r = requests.get(f"{IVASMS_URL}/dashboard", cookies=cookies_jar, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            # Find all links that might point to SMS pages
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text().lower()
                if any(keyword in href.lower() or keyword in text for keyword in 
                       ['sms', 'otp', 'message', 'live', 'test']):
                    full_url = href if href.startswith('http') else f"{IVASMS_URL}{href}"
                    print(f"🔗 Found potential link: {full_url} ({text})")
                    if full_url not in possible_paths:
                        possible_paths.append(href)
    except Exception as e:
        print(f"Dashboard check error: {e}")
    
    print("\n❌ Could not find Live SMS URL automatically")
    return None

async def fetch_sms():
    """Fetch live SMS using auto-detected or manual URLs"""
    global cookies_jar, FOUND_SMS_URL
    
    if not cookies_jar:
        if not load_cookies():
            return []
    
    # If we already found a working URL, use it directly
    if FOUND_SMS_URL:
        urls_to_try = [FOUND_SMS_URL]
    else:
        # Try to find the URL first
        found_url = await find_exact_sms_url()
        if found_url:
            urls_to_try = [found_url]
        else:
            # Fallback to common URLs
            urls_to_try = [
                f'{IVASMS_URL}/live-test-sms',
                f'{IVASMS_URL}/test-sms',
                f'{IVASMS_URL}/dashboard/live-sms',
                f'{IVASMS_URL}/api/live-sms',
                f'{IVASMS_URL}/portal/live/test_sms',
            ]
    
    for url in urls_to_try:
        try:
            print(f"🌐 Fetching: {url}")
            r = requests.get(url, cookies=cookies_jar, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'X-Requested-With': 'XMLHttpRequest'
            })
            
            print(f"📡 Status: {r.status_code}, Size: {len(r.text)} bytes")
            
            if r.status_code == 200:
                if 'application/json' in r.headers.get('Content-Type', ''):
                    result = parse_json_response(r.json())
                else:
                    result = parse_html_response(r.text)
                
                if result:
                    print(f"✅ Found {len(result)} OTP(s) from {url}")
                    return result
                    
        except Exception as e:
            print(f"❌ Error with {url}: {e}")
            continue
    
    return []

def parse_json_response(data):
    """Parse JSON response for OTPs"""
    otps = []
    try:
        # Try different possible structures
        if isinstance(data, dict):
            # Check for data in various keys
            possible_keys = ['data', 'messages', 'sms', 'results', 'items', 'list', 'records', 'otps']
            items = []
            for key in possible_keys:
                if key in data:
                    items = data[key]
                    if items:
                        break
            
            if not items and isinstance(data, dict):
                # Maybe the whole dict is the item
                items = [data]
            
            for item in items:
                if isinstance(item, dict):
                    msg = str(item.get('message') or item.get('content') or item.get('text') or item.get('sms') or '')
                    otp = extract_otp(msg)
                    if otp:
                        otps.append({
                            'otp': otp,
                            'number': item.get('number') or item.get('phone') or item.get('mobile') or 'Unknown',
                            'service': item.get('service') or item.get('app') or item.get('application') or 'Unknown',
                            'message': msg[:500],
                            'time': time.strftime('%Y-%m-%d %H:%M:%S')
                        })
    except Exception as e:
        print(f"JSON parse error: {e}")
    
    return otps

def parse_html_response(html):
    """Parse HTML response for OTPs - FIXED for IVASMS table"""
    otps = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # METHOD 1: Find the live test SMS table
    # Look for table that contains OTP information
    tables = soup.find_all('table')
    
    for table in tables:
        # Check if this is the OTP table
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 3:
                # First cell contains country and phone number
                first_cell = cells[0].get_text(strip=True)
                # Second cell contains service name (SID)
                service = cells[1].get_text(strip=True)
                # Third cell contains message with OTP
                message = cells[2].get_text(strip=True)
                
                # Extract phone number from first cell
                phone_match = re.search(r'(\+\d{10,15})', first_cell)
                number = phone_match.group(1) if phone_match else first_cell
                
                # Extract OTP from message
                otp = extract_otp(message)
                
                if otp:
                    otps.append({
                        'otp': otp,
                        'number': number,
                        'service': service,
                        'message': message[:500],
                        'time': time.strftime('%H:%M:%S')
                    })
    
    # METHOD 2: If no table found, try div-based parsing
    if not otps:
        # Look for any content that looks like OTP messages
        lines = html.split('\n')
        for line in lines:
            otp = extract_otp(line)
            if otp:
                # Try to find phone number in same line/context
                phone_match = re.search(r'(\+\d{10,15})', line)
                number = phone_match.group(1) if phone_match else 'Unknown'
                
                # Try to find service
                service_match = re.search(r'(Facebook|TikTok|TINDER|SAMSUNG|Botim|YandexGo|Huawei)', line, re.I)
                service = service_match.group(1) if service_match else 'Unknown'
                
                otps.append({
                    'otp': otp,
                    'number': number,
                    'service': service,
                    'message': line[:500],
                    'time': time.strftime('%H:%M:%S')
                })
    
    # Remove duplicates based on OTP+number
    unique_otps = []
    seen = set()
    for otp in otps:
        key = f"{otp['otp']}_{otp['number']}"
        if key not in seen:
            seen.add(key)
            unique_otps.append(otp)
    
    return unique_otps
    # Method 3: Generic - find any numbers that look like OTP with context
    if not otps:
        # Look for patterns like "Your verification code is 123456"
        otp_pattern = r'(?:code|otp|verification).{0,20}(\d{4,6})'
        matches = re.finditer(otp_pattern, html, re.IGNORECASE)
        for match in matches:
            otp = match.group(1)
            # Get surrounding context (100 chars before and after)
            start = max(0, match.start() - 100)
            end = min(len(html), match.end() + 100)
            context = html[start:end]
            
            number = re.search(r'\+?\d{8,15}', context)
            number = number.group(0) if number else 'Unknown'
            
            service = re.search(r'(TikTok|Facebook|Microsoft|WhatsApp|Apple|Google)', context, re.I)
            service = service.group(0) if service else 'Unknown'
            
            otps.append({
                'otp': otp,
                'number': number,
                'service': service,
                'message': context[:500],
                'time': time.strftime('%Y-%m-%d %H:%M:%S')
            })
    
    return otps

def extract_otp(text):
    """Extract OTP code from text"""
    patterns = [
        r'\b\d{4}\b',
        r'\b\d{5}\b',
        r'\b\d{6}\b',
        r'code[:\s]*(\d{4,6})',
        r'OTP[:\s]*(\d{4,6})',
        r'verification[:\s]*(\d{4,6})',
        r'kode[:\s]*(\d{4,6})',
        r'is your verification code[:\s]*(\d{4,6})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if match.group(1):
                return match.group(1)
            return match.group(0)
    
    return None

async def send_to_telegram(otp_data):
    """Send OTP to Telegram"""
    message = f"🔐 *NEW OTP RECEIVED!*\n\n📱 *Number:* `{otp_data['number']}`\n🏷️ *Service:* {otp_data['service']}\n🔢 *OTP Code:* `{otp_data['otp']}`\n⏰ *Time:* {otp_data['time']}\n\n📝 *Message:*\n```\n{otp_data['message'][:300]}\n```"
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print(f"✅ Sent OTP: {otp_data['otp']}")
            return True
        else:
            print(f"❌ Telegram error: {r.status_code}")
            return False
    except Exception as e:
        print(f"❌ Send error: {e}")
        return False

async def keep_alive():
    """Health check for Railway"""
    app = Flask(__name__)
    
    @app.route('/')
    def health():
        return "✅ IVASMS OTP Bot is running!", 200
    
    @app.route('/stats')
    def stats():
        return {
            'status': 'running',
            'unique_otps': len(sent_otps),
            'sms_url': FOUND_SMS_URL or 'Not found yet',
            'cookies_valid': bool(cookies_jar),
            'last_check': time.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def run():
        app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)), debug=False)
    
    import threading
    threading.Thread(target=run, daemon=True).start()

async def main_loop():
    """Main monitoring loop"""
    print("🚀 IVASMS OTP Bot Starting...")
    print(f"📡 Panel URL: {IVASMS_URL}")
    print(f"⏱️ Check Interval: {CHECK_INTERVAL} seconds")
    print("-" * 50)
    
    if not load_cookies():
        print("❌ Failed to load cookies. Exiting.")
        return
    
    # Auto-find the SMS URL on startup
    await find_exact_sms_url()
    
    while True:
        try:
            sms_list = await fetch_sms()
            for sms in sms_list:
                key = f"{sms['number']}_{sms['otp']}"
                if key not in sent_otps:
                    if await send_to_telegram(sms):
                        sent_otps.add(key)
                        print(f"📤 New OTP sent: {sms['otp']}")
            
            if len(sent_otps) > 500:
                sent_otps.clear()
            
            print(f"📊 {time.strftime('%H:%M:%S')} → {len(sms_list)} OTPs found, Total unique: {len(sent_otps)}")
            
        except Exception as e:
            print(f"⚠️ Main loop error: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

async def main():
    await asyncio.gather(main_loop(), keep_alive())

if __name__ == "__main__":
    print("🚀 Starting IVASMS OTP Bot with Auto URL Finder...")
    
    required = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'COOKIES_JSON']
    missing = [v for v in required if not os.getenv(v)]
    
    if missing:
        print(f"❌ Missing environment variables: {missing}")
        print("\n📋 Required variables:")
        print("  - TELEGRAM_BOT_TOKEN: BotFather se lo")
        print("  - TELEGRAM_CHAT_ID: Group/User ID")
        print("  - COOKIES_JSON: Cookie-Editor se export karo")
    else:
        asyncio.run(main())
