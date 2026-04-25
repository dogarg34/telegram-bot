import requests
import time
import os
import hashlib
from bs4 import BeautifulSoup
from datetime import datetime

# ========== RAILWAY KE VARIABLES SE SAB LEGA ==========
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')  # Group ka chat ID
PANEL_URL = os.environ.get('PANEL_URL')
COOKIE_NAME = os.environ.get('COOKIE_NAME', 'sessionid')
COOKIE_VALUE = os.environ.get('COOKIE_VALUE')

# Cookie set karo
cookies = {COOKIE_NAME: COOKIE_VALUE}

# Already bheje gaye messages track karne ke liye
sent_sms_ids = set()

def get_sms_unique_id(sms_data):
    """Har SMS ka unique ID banane ke liye (duplicate na bheje)"""
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
            print(f"✅ Sent: {message[:50]}...")
        else:
            print(f"❌ Error: {r.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")

def fetch_live_sms():
    """Panel se Live Test SMS fetch karo"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(PANEL_URL, cookies=cookies, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"⚠️ Panel error: Status {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Tumhari screenshot ke hisaab se table rows find karo
        # Try different selectors
        rows = soup.select('table tbody tr')
        
        if not rows:
            rows = soup.select('tr')
        
        if not rows:
            print("⚠️ No table found. Check selector.")
            return []
        
        messages = []
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 3:
                country_cell = cols[0].get_text(strip=True)
                service_cell = cols[1].get_text(strip=True)
                msg_cell = cols[2].get_text(strip=True)
                
                # Clean and format message
                sms_data = {
                    'country': country_cell,
                    'service': service_cell,
                    'message': msg_cell,
                    'time': datetime.now().strftime('%H:%M:%S %d-%m-%Y')
                }
                
                # Format karke message banana
                formatted_msg = f"""
📱 <b>⚠️ NEW LIVE SMS DETECTED ⚠️</b>
━━━━━━━━━━━━━━━━━━━━━━
🌍 <b>Country / Number:</b>
<code>{sms_data['country']}</code>

🏷️ <b>Service:</b> {sms_data['service']}

💬 <b>Message:</b>
<code>{sms_data['message']}</code>

⏰ <b>Time:</b> {sms_data['time']}
━━━━━━━━━━━━━━━━━━━━━━
✅ <b>Forwarded by IVASMS Bot</b>
"""
                
                messages.append({
                    'unique_id': get_sms_unique_id(sms_data),
                    'formatted_msg': formatted_msg,
                    'raw': sms_data
                })
        
        return messages
    
    except Exception as e:
        print(f"⚠️ Fetch error: {e}")
        return []

def save_sent_ids():
    """Bheje gaye message IDs save karo (Railway disk me)"""
    try:
        with open('sent_ids.txt', 'w') as f:
            for uid in sent_sms_ids:
                f.write(uid + '\n')
    except:
        pass  # Railway read-only ho sakta hai, ignore

def load_sent_ids():
    """Previous sent IDs load karo"""
    try:
        with open('sent_ids.txt', 'r') as f:
            for line in f:
                sent_sms_ids.add(line.strip())
        print(f"📚 Loaded {len(sent_sms_ids)} previously sent messages")
    except:
        print("📚 No previous data, starting fresh")

def monitor_sms():
    """Main monitoring function"""
    print(f"🤖 Bot Started Successfully!")
    print(f"📡 Monitoring: {PANEL_URL}")
    print(f"💬 Sending to Chat ID: {CHAT_ID}")
    print(f"🍪 Cookie Name: {COOKIE_NAME}")
    print("⏳ Waiting for new SMS...\n" + "="*50)
    
    while True:
        try:
            # Fetch new SMS from panel
            new_sms_list = fetch_live_sms()
            
            # Check for new messages
            for sms in new_sms_list:
                if sms['unique_id'] not in sent_sms_ids:
                    # Naya SMS mila! Send to Telegram
                    send_to_telegram(sms['formatted_msg'])
                    sent_sms_ids.add(sms['unique_id'])
                    save_sent_ids()
                    print(f"📤 New SMS Sent! Total sent: {len(sent_sms_ids)}")
            
            # Wait before next check
            time.sleep(5)  # Har 5 second mein check karega
            
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped by user")
            break
        except Exception as e:
            print(f"⚠️ Main loop error: {e}")
            time.sleep(30)

# ========== BOT START ==========
if __name__ == "__main__":
    # Check if all required variables are set
    required_vars = ['BOT_TOKEN', 'CHAT_ID', 'PANEL_URL', 'COOKIE_VALUE']
    missing = [var for var in required_vars if not os.environ.get(var)]
    
    if missing:
        print(f"❌ ERROR: Missing Railway variables: {', '.join(missing)}")
        print("Please add them in Railway dashboard → Variables tab")
        exit(1)
    
    # Load previously sent messages
    load_sent_ids()
    
    # Start monitoring
    monitor_sms()
