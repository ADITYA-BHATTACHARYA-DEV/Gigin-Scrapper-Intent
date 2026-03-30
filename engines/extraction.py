import os
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from utils.ua_manager import get_random_ua

class ExtractionEngine:
    async def to_markdown(self, url):
        """
        Uses Crawl4AI to convert a webpage into clean Markdown text.
        Optimized for StackOverflow and GitHub deep crawling.
        """
        # 1. Defensive Proxy Setup
        proxy_raw = os.getenv("PROXY_URL", "").strip()
        proxy = None
        
        # Avoid using the placeholder string if it's still in the .env
        if proxy_raw and "host:port" not in proxy_raw.lower() and len(proxy_raw) > 10:
            proxy = proxy_raw

        # 2. Browser Configuration
        # These 'extra_args' are crucial for Windows stability
        b_config = BrowserConfig(
            headless=True,
            proxy=proxy,
            user_agent=get_random_ua(),
            extra_args=[
                "--disable-gpu", 
                "--no-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-software-rasterizer"
            ]
        )
        
        # 3. Content Filtering
        # Strips out menus and footers so the AI only sees the important technical content
        r_config = CrawlerRunConfig(
            cache_mode="BYPASS",
            excluded_tags=['nav', 'footer', 'header', 'aside', 'script', 'style'],
            remove_overlay_elements=True,
            word_count_threshold=10
        )

        try:
            print(f"   [🕷️] Deep Crawling: {url}")
            async with AsyncWebCrawler(config=b_config) as crawler:
                result = await crawler.arun(url=url, config=r_config)
                
                if result.success:
                    # We only need the first 4000 characters for a solid AI analysis
                    return result.markdown[:4000]
                else:
                    print(f"   [!] Extraction failed for {url}: {result.error_message}")
                    return None
                    
        except Exception as e:
            print(f"   [!] Extraction Engine Error: {e}")
            return None