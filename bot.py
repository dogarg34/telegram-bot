import requests
import time
import os
import hashlib
from bs4 import BeautifulSoup
from datetime import datetime

# ========== RAILWAY KE VARIABLES ==========
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
PANEL_URL = os.environ.get('PANEL_URL')

# 🔑 SIRF EK VARIABLE - COOKIE_STRING
COOKIE_STRING = os.environ.get('COOKIE_STRING')

# Headers with cookie
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Cookie": COOKIE_STRING
}

# Already sent messages track karne ke liye
sent_sms_ids = set()

def get_sms_unique_id(sms_data):
    """Har SMS ka unique ID banane ke liye"""
    unique_string = f"{sms_data['country']}|{sms_data['service']}|{sms_data['message']}"
    return hashlib.md5(unique_string.encode()).hexdigest()

def send_to_telegram(message):
    """Telegram group mein message bhej"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print(f"✅ Sent to Telegram")
        else:
            print(f"❌ Error: {r.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")

def fetch_live_sms():
    """Panel se Live Test SMS fetch karo"""
    try:
        response = requests.get(PANEL_URL, headers=headers, timeout=30)
        print(f"📡 Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"⚠️ Panel error: Status {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Table rows find karo
        rows = soup.select('table tbody tr')
        
        if not rows:
            rows = soup.select('tr')
        
        if not rows:
            print("⚠️ No table found")
            return []
        
        messages = []
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 3:
                sms_data = {
                    'country': cols[0].get_text(strip=True),
                    'service': cols[1].get_text(strip=True),
                    'message': cols[2].get_text(strip=True),
                    'time': datetime.now().strftime('%H:%M:%S %d-%m-%Y')
                }
                
                formatted_msg = f"""
📱 <b>⚠️ NEW LIVE SMS</b>
━━━━━━━━━━━━━━━━
🌍 <b>Country/Number:</b>
<code>{sms_data['country']}</code>

🏷️ <b>Service:</b> {sms_data['service']}

💬 <b>Message:</b>
<code>{sms_data['message']}</code>

⏰ <b>Time:</b> {sms_data['time']}
━━━━━━━━━━━━━━━━
✅ Forwarded by IVASMS Bot
"""
                messages.append({
                    'unique_id': get_sms_unique_id(sms_data),
                    'formatted_msg': formatted_msg
                })
        
        print(f"📊 Found {len(messages)} SMS entries")
        return messages
    
    except Exception as e:
        print(f"⚠️ Fetch error: {e}")
        return []

def monitor_sms():
    """Main monitoring function"""
    print("="*50)
    print(f"🤖 IVASMS Bot Started!")
    print(f"📡 Monitoring: {PANEL_URL}")
    print(f"💬 Sending to Chat ID: {CHAT_ID}")
    print(f"🍪 Cookie length: {len(COOKIE_STRING)} characters")
    print("⏳ Waiting for new SMS...")
    print("="*50)
    
    while True:
        try:
            new_sms_list = fetch_live_sms()
            
            for sms in new_sms_list:
                if sms['unique_id'] not in sent_sms_ids:
                    send_to_telegram(sms['formatted_msg'])
                    sent_sms_ids.add(sms['unique_id'])
                    print(f"📤 New SMS sent! Total sent: {len(sent_sms_ids)}")
            
            time.sleep(10)  # Har 10 second mein check
            
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped")
            break
        except Exception as e:
            print(f"⚠️ Main loop error: {e}")
            time.sleep(30)

# ========== BOT START ==========
if __name__ == "__main__":
    # Check if all required variables are set
    required_vars = ['BOT_TOKEN', 'CHAT_ID', 'PANEL_URL', 'COOKIE_STRING']
    missing = [var for var in required_vars if not os.environ.get(var)]
    
    if missing:
        print(f"❌ ERROR: Missing Railway variables: {', '.join(missing)}")
        print("Please add them in Railway dashboard → Variables tab")
        exit(1)
    
    if not COOKIE_STRING:
        print("❌ ERROR: COOKIE_STRING is empty!")
        exit(1)
    
    monitor_sms()
