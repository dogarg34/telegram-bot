import requests
import json
import re
import time
import asyncio
import os
from bs4 import BeautifulSoup
from telegram import Bot
from telegram.ext import Application

# ============== RAILWAY VARIABLES SE READ ==============
IVASMS_URL = os.getenv('IVASMS_URL', 'https://ivasms.com')
IVASMS_EMAIL = os.getenv('IVASMS_EMAIL')
IVASMS_PASSWORD = os.getenv('IVASMS_PASSWORD')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '10'))  # seconds

# Cookies store karne ke liye
cookies_jar = {}
bheje_hue_otps = set()
last_cookies_time = 0

# ===============================================

async def login_to_ivasms():
    """IVASMS panel me login karega aur cookies save karega"""
    global cookies_jar, last_cookies_time
    
    print(f"🔄 Logging into IVASMS...")
    
    login_url = f"{IVASMS_URL}/login"  # Exact login URL adjust karna
    
    # Pehle GET request for CSRF token
    session = requests.Session()
    try:
        get_response = session.get(login_url, timeout=10)
        soup = BeautifulSoup(get_response.text, 'html.parser')
        
        # CSRF token find karo
        csrf_token = None
        csrf_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
        if csrf_input:
            csrf_token = csrf_input.get('value')
        
        # Login data
        login_data = {
            'email': IVASMS_EMAIL,
            'password': IVASMS_PASSWORD,
        }
        if csrf_token:
            login_data['csrfmiddlewaretoken'] = csrf_token
        
        # Login POST request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': login_url,
        }
        
        if csrf_token:
            headers['X-CSRFToken'] = csrf_token
        
        post_response = session.post(login_url, data=login_data, headers=headers, timeout=15)
        
        # Check login success
        if 'dashboard' in post_response.url or post_response.status_code == 200:
            cookies_jar = session.cookies.get_dict()
            last_cookies_time = time.time()
            print(f"✅ IVASMS Login Successful!")
            print(f"📦 Cookies: {list(cookies_jar.keys())}")
            return True
        else:
            print(f"❌ Login Failed: {post_response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Login Error: {e}")
        return False

async def get_live_sms():
    """Live test SMS page se OTP fetch karega"""
    global cookies_jar
    
    if not cookies_jar:
        await login_to_ivasms()
    
    # URLs to try (exact URL capture karna padega from network tab)
    urls_to_try = [
        f'{IVASMS_URL}/live-test-sms',
        f'{IVASMS_URL}/test-sms',
        f'{IVASMS_URL}/dashboard/live-sms',
        f'{IVASMS_URL}/api/live-sms',
        f'{IVASMS_URL}/get-live-sms',
    ]
    
    for url in urls_to_try:
        try:
            response = requests.get(
                url, 
                cookies=cookies_jar,
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=10
            )
            
            if response.status_code == 200:
                # Check if JSON response
                if 'application/json' in response.headers.get('Content-Type', ''):
                    return parse_json_response(response.json())
                else:
                    return parse_html_response(response.text)
                    
        except Exception as e:
            print(f"⚠️ URL failed {url}: {e}")
            continue
    
    # Agar sab fail ho jaye to login refresh karo
    await login_to_ivasms()
    return []

def parse_json_response(data):
    """JSON response se OTP nikalega"""
    otps = []
    
    try:
        # Different possible response structures
        sms_list = data.get('data', []) or data.get('messages', []) or data.get('sms', [])
        
        for sms in sms_list:
            if isinstance(sms, dict):
                number = sms.get('number', sms.get('phone', 'Unknown'))
                service = sms.get('service', sms.get('app', 'Unknown'))
                message = sms.get('message', sms.get('content', sms.get('text', '')))
                
                otp = extract_otp(message)
                if otp:
                    otps.append({
                        'otp': otp,
                        'number': number,
                        'service': service,
                        'message': message,
                        'time': time.strftime('%Y-%m-%d %H:%M:%S')
                    })
    except Exception as e:
        print(f"JSON parse error: {e}")
    
    return otps

def parse_html_response(html):
    """HTML page se OTP nikalega"""
    otps = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find table - jaise screenshot me dikh raha hai
    table = soup.find('table')
    if table:
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
                        'message': message,
                        'time': time.strftime('%Y-%m-%d %H:%M:%S')
                    })
    
    # Agar table nahi mila to divs me dhundho
    if not otps:
        sms_divs = soup.find_all('div', class_=re.compile('sms|message|otp', re.I))
        for div in sms_divs:
            text = div.get_text()
            otp = extract_otp(text)
            if otp:
                otps.append({
                    'otp': otp,
                    'number': 'Unknown',
                    'service': 'Unknown',
                    'message': text[:200],
                    'time': time.strftime('%Y-%m-%d %H:%M:%S')
                })
    
    return otps

def extract_otp(text):
    """Text se OTP code nikalega"""
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
    """OTP ko Telegram par bhejega"""
    
    message = f"""
🔐 **NEW OTP RECEIVED!**

📱 **Number:** `{otp_data['number']}`
🏷️ **Service:** {otp_data['service']}
🔢 **OTP Code:** `{otp_data['otp']}`
⏰ **Time:** {otp_data['time']}

📝 **Full Message:**
