from curl_cffi import requests

class NetworkEngine:
    def __init__(self, proxy=None):
        self.session = requests.Session(impersonate="chrome120")
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    def fetch_static(self, url):
        """High-speed fetch with browser-grade TLS fingerprinting."""
        try:
            response = self.session.get(url, timeout=10)
            return response.text if response.status_code == 200 else None
        except Exception as e:
            print(f"[!] Network Error: {e}")
            return None