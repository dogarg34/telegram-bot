import requests
import re
import time
import asyncio
import os
import json
from bs4 import BeautifulSoup
from flask import Flask

# ========== ENVIRONMENT VARIABLES ==========
IVASMS_URL = os.getenv('IVASMS_URL', 'https://ivasms.com')
COOKIES_JSON = os.getenv('COOKIES_JSON')  # JSON string of cookies
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '10'))

cookies_jar = {}
sent_otps = set()

# ========== COOKIES LOAD KARO ==========
def load_cookies():
    global cookies_jar
    if not COOKIES_JSON:
        print("❌ COOKIES_JSON environment variable is missing!")
        return False
    
    try:
        # Parse JSON string to dict
        cookies_dict = json.loads(COOKIES_JSON)
        cookies_jar = cookies_dict
        print(f"✅ Cookies loaded successfully! Found {len(cookies_jar)} cookies")
        print(f"📦 Cookies: {list(cookies_jar.keys())}")
        return True
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in COOKIES_JSON: {e}")
        return False
    except Exception as e:
        print(f"❌ Error loading cookies: {e}")
        return False

# ========== CHECK COOKIES VALID ==========
async def check_cookies_valid():
    """Check if cookies are still valid"""
    global cookies_jar
    if not cookies_jar:
        return False
    
    try:
        # Try to access dashboard with cookies
        r = requests.get(
            f"{IVASMS_URL}/dashboard",
            cookies=cookies_jar,
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        
        # If redirected to login page, cookies expired
        if 'login' in r.url or r.status_code == 401 or r.status_code == 403:
            print("⚠️ Cookies expired! Need new cookies")
            return False
        
        print("✅ Cookies are valid")
        return True
    except Exception as e:
        print(f"⚠️ Cookie check error: {e}")
        return False

# ========== FETCH SMS ==========
async def fetch_sms():
    global cookies_jar
    if not cookies_jar:
        if not load_cookies():
            return []
    
    # URLs to try (exact URLs from your screenshots)
    urls = [
        f'{IVASMS_URL}/live-test-sms',
        f'{IVASMS_URL}/test-sms',
        f'{IVASMS_URL}/dashboard/live-sms',
        f'{IVASMS_URL}/api/live-sms',
        f'{IVASMS_URL}/get-live-sms',
        f'{IVASMS_URL}/live-sms',
    ]
    
    for url in urls:
        try:
            r = requests.get(
                url, 
                cookies=cookies_jar,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                timeout=10
            )
            
            if r.status_code == 200:
                # Check if response is JSON
                if 'application/json' in r.headers.get('Content-Type', ''):
                    return parse_json_response(r.json())
                else:
                    return parse_html_response(r.text)
        except Exception as e:
            continue
    
    # If all URLs fail, cookies might be expired
    print("⚠️ Could not fetch SMS - cookies may be expired")
    return []

def parse_json_response(data):
    """Parse JSON response for OTPs"""
    otps = []
    try:
        # Try different possible structures
        items = data.get('data') or data.get('messages') or data.get('sms') or data.get('results') or []
        
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
    """Parse HTML response for OTPs"""
    otps = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all tables
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows[1:]:  # Skip header
            cols = row.find_all('td')
            if len(cols) >= 3:
                number = cols[0].get_text(strip=True)
                service = cols[1].get_text(strip=True)
                message = cols[2].get_text(strip=True)
                
                otp = extract_otp(message)
                if otp:
                    otps.append({
                        'otp': otp,
                        'number': number,
                        'service': service,
                        'message': message[:500],
                        'time': time.strftime('%Y-%m-%d %H:%M:%S')
                    })
    
    # If no table found, look for divs with sms/message class
    if not otps:
        sms_divs = soup.find_all('div', class_=re.compile('sms|message|otp|live', re.I))
        for div in sms_divs:
            text = div.get_text()
            otp = extract_otp(text)
            if otp:
                # Try to find number and service from nearby elements
                number = 'Unknown'
                service = 'Unknown'
                
                # Look for number pattern in text
                num_match = re.search(r'\+?\d{10,15}', text)
                if num_match:
                    number = num_match.group(0)
                
                otps.append({
                    'otp': otp,
                    'number': number,
                    'service': service,
                    'message': text[:500],
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
        r'verification code[:\s]*(\d{4,6})',
        r'Your.*?code[:\s]*(\d{4,6})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if match.group(1):
                return match.group(1)
            return match.group(0)
    
    return None

# ========== TELEGRAM SEND ==========
async def send_to_telegram(otp_data):
    """Send OTP to Telegram"""
    message = f"""🔐 *NEW OTP RECEIVED!*

📱 *Number:* `{otp_data['number']}`
🏷️ *Service:* {otp_data['service']}
🔢 *OTP Code:* `{otp_data['otp']}`
⏰ *Time:* {otp_data['time']}

📝 *Message:*
