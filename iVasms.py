import cloudscraper
import json
import concurrent.futures
from datetime import datetime

class iVasmsPanel:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = cloudscraper.create_scraper()
        self.cookies = None
        self.logged_in = False
        self.active_countries = {}
        self.all_numbers = {}
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
    
    def set_cookies(self, cookies_str):
        """Manually set cookies from browser"""
        try:
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
            print(f"Cookie error: {e}")
            return False
    
    def login(self):
        """Login to iVasms with email/password"""
        try:
            login_url = "https://ivasms.com/api/login"
            data = {
                'email': self.email,
                'password': self.password
            }
            response = self.session.post(login_url, json=data)
            if response.status_code == 200:
                self.logged_in = True
                return True
            return False
        except:
            return False
    
    def check_whatsapp_status(self):
        """Check which countries have working WhatsApp OTP"""
        try:
            api_url = "https://ivasms.com/api/whatsapp-status"
            response = self.session.get(api_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Expected format: {"countries": [{"name": "Pakistan", "code": "+92", "status": "active"}, ...]}
                countries = data.get('countries', [])
                self.active_countries = {}
                for country in countries:
                    if country.get('status') == 'active':
                        self.active_countries[country.get('name')] = country.get('code')
                return self.active_countries
            return self._fallback_country_check()
        except:
            return self._fallback_country_check()
    
    def _fallback_country_check(self):
        """Fallback: Check available numbers for each common country"""
        common_countries = {
            "Pakistan": "+92",
            "Egypt": "+20",
            "Lebanon": "+961",
            "Nigeria": "+234",
            "Indonesia": "+62",
            "Bangladesh": "+880",
            "India": "+91",
            "Brazil": "+55"
        }
        
        active = {}
        for name, code in common_countries.items():
            numbers = self.get_numbers_for_country(code, limit=5)
            if len(numbers) > 0:
                active[name] = code
        return active
    
    def get_numbers_for_country(self, country_code, limit=100):
        """Get numbers for a specific country"""
        try:
            api_url = "https://ivasms.com/api/get-numbers"
            params = {
                'country': country_code,
                'service': 'whatsapp',
                'limit': limit
            }
            response = self.session.get(api_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                numbers = data.get('numbers', [])
                # Format numbers properly
                formatted_numbers = []
                for num in numbers:
                    formatted_numbers.append({
                        'id': num.get('id'),
                        'number': num.get('number'),
                        'country_code': country_code,
                        'status': 'active'
                    })
                return formatted_numbers
            return []
        except Exception as e:
            print(f"Error fetching {country_code}: {e}")
            return []
    
    def refresh_all_countries(self, limit=100):
        """Refresh numbers for all active countries in parallel"""
        if not self.active_countries:
            self.check_whatsapp_status()
        
        results = {}
        
        def fetch(country_name, country_code):
            numbers = self.get_numbers_for_country(country_code, limit)
            return country_name, country_code, numbers
        
        futures = []
        for name, code in self.active_countries.items():
            future = self.executor.submit(fetch, name, code)
            futures.append(future)
        
        for future in concurrent.futures.as_completed(futures):
            name, code, numbers = future.result()
            results[name] = {
                'code': code,
                'numbers': numbers,
                'count': len(numbers)
            }
        
        self.all_numbers = results
        return results
    
    def get_total_numbers(self):
        """Get total count of all numbers"""
        total = 0
        for country in self.all_numbers.values():
            total += country.get('count', 0)
        return total
    
    def get_country_list(self):
        """Get list of available countries with counts"""
        country_list = []
        for name, data in self.all_numbers.items():
            country_list.append({
                'name': name,
                'code': data['code'],
                'count': data['count']
            })
        return country_list
    
    def get_numbers_by_country(self, country_name):
        """Get all numbers for a specific country"""
        if country_name in self.all_numbers:
            return self.all_numbers[country_name]['numbers']
        return []
    
    def claim_number(self, country_name):
        """Claim a number for user (remove from pool)"""
        if country_name in self.all_numbers:
            numbers = self.all_numbers[country_name]['numbers']
            if numbers:
                claimed = numbers.pop(0)
                self.all_numbers[country_name]['count'] = len(numbers)
                return claimed.get('number')
        return None
