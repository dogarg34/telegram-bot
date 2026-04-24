import requests
import cloudscraper
from bs4 import BeautifulSoup
import json
import time

class iVasmsPanel:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = cloudscraper.create_scraper()
        self.cookies = None
        self.logged_in = False
        
    def login(self):
        """Login to iVasms and get cookies"""
        try:
            # First get login page for CSRF token
            login_url = "https://ivasms.com/login"  # Update URL if different
            
            response = self.session.get(login_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Get CSRF token if exists
            csrf_token = None
            token_input = soup.find('input', {'name': '_token'})
            if token_input:
                csrf_token = token_input.get('value')
            
            # Login data
            login_data = {
                'email': self.email,
                'password': self.password,
            }
            if csrf_token:
                login_data['_token'] = csrf_token
            
            # Post login
            login_response = self.session.post(login_url, data=login_data)
            
            if login_response.status_code == 200:
                self.cookies = self.session.cookies.get_dict()
                self.logged_in = True
                return True
            return False
            
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    def set_cookies(self, cookies_str):
        """Manually set cookies from browser"""
        try:
            # Parse cookies string (format: "name1=value1; name2=value2")
            cookies_dict = {}
            for item in cookies_str.split(';'):
                item = item.strip()
                if '=' in item:
                    key, value = item.split('=', 1)
                    cookies_dict[key] = value
            
            self.session.cookies.update(cookies_dict)
            self.cookies = cookies_dict
            self.logged_in = True
            return True
        except Exception as e:
            print(f"Cookie parse error: {e}")
            return False
    
    def get_available_numbers(self, country_code, limit=100):
        """Get available numbers for a country"""
        try:
            # API endpoint (adjust based on actual iVasms API)
            api_url = "https://ivasms.com/api/get-numbers"
            
            params = {
                'country': country_code,
                'service': 'whatsapp',
                'limit': limit
            }
            
            response = self.session.get(api_url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('numbers', [])
            return []
            
        except Exception as e:
            print(f"Get numbers error: {e}")
            return []
    
    def get_otp_messages(self):
        """Fetch OTP messages"""
        try:
            # API to get messages
            api_url = "https://ivasms.com/api/get-messages"
            
            response = self.session.get(api_url)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('messages', [])
            return []
            
        except Exception as e:
            print(f"Get OTP error: {e}")
            return []
    
    def refresh_range(self):
        """Manual range refresh"""
        try:
            refresh_url = "https://ivasms.com/api/refresh-range"
            
            response = self.session.post(refresh_url)
            
            if response.status_code == 200:
                return response.json().get('status', False)
            return False
            
        except Exception as e:
            print(f"Refresh error: {e}")
            return False
