import cloudscraper
import asyncio
import concurrent.futures

class iVasmsPanel:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = cloudscraper.create_scraper()
        self.cookies = None
        self.logged_in = False
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
    
    def set_cookies(self, cookies_str):
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
        except:
            return False
    
    def refresh_range_fast(self):
        """Fast refresh - parallel requests"""
        try:
            refresh_url = "https://ivasms.com/api/refresh-range"
            response = self.session.post(refresh_url, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_numbers_for_country(self, country_code, limit=100):
        """Get numbers for single country"""
        try:
            api_url = "https://ivasms.com/api/get-numbers"
            params = {
                'country': country_code,
                'service': 'whatsapp',
                'limit': limit
            }
            response = self.session.get(api_url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get('numbers', [])
            return []
        except:
            return []
    
    def get_all_countries_numbers_parallel(self, countries, limit=100):
        """Parallel fetch for all countries"""
        results = {}
        
        def fetch(country_name, country_code):
            numbers = self.get_numbers_for_country(country_code, limit)
            return country_name, numbers
        
        # Parallel execution
        futures = []
        for country_name, country_code in countries.items():
            future = self.executor.submit(fetch, country_name, country_code)
            futures.append(future)
        
        # Collect results
        for future in concurrent.futures.as_completed(futures):
            country_name, numbers = future.result()
            results[country_name] = numbers
        
        return results
