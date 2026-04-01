
"""
discovery.py — Lead discovery engine (rectified)
================================================
Fixes:
  1. SSL cert error → verify=False on curl_cffi calls when proxy is active
  2. Bing DOM changes → expanded selectors, flexible anchor extraction
  3. Added fallback to DuckDuckGo/Google CSE if Bing fails
  4. Reddit SSL error → verify=False fix
"""

import os
import re
import asyncio
import random
import urllib.parse
from curl_cffi import requests as curl_requests
from utils.ua_manager import get_random_ua
from utils.intent_router import normalize_query_for_platform

# ── UA Pool ────────────────────────────────────────────────────────────────
_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

def _random_ua() -> str:
    return random.choice(_UA_POOL)

def _build_proxies():
    proxy_raw = os.getenv("PROXY_URL", "").strip()
    if proxy_raw and "host:port" not in proxy_raw and len(proxy_raw) > 10:
        return {"http": proxy_raw, "https": proxy_raw}
    return None

def _proxy_for_playwright():
    proxy_raw = os.getenv("PROXY_URL", "").strip()
    if not proxy_raw or "host:port" in proxy_raw:
        return None
    try:
        parsed = urllib.parse.urlparse(proxy_raw)
        pw = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
        if parsed.username:
            pw["username"] = urllib.parse.unquote(parsed.username)
        if parsed.password:
            pw["password"] = urllib.parse.unquote(parsed.password)
        return pw
    except Exception:
        return None

def _use_proxy() -> bool:
    proxy_raw = os.getenv("PROXY_URL", "").strip()
    return bool(proxy_raw and "host:port" not in proxy_raw and len(proxy_raw) > 10)


# ── Helpers ────────────────────────────────────────────────────────────────
_SKIP_SEGMENTS = {
    "search","about","login","policies","help","legal","signup","register",
    "feed","notifications","messaging","learning","events","404","terms",
    "privacy","tos","safety","contactus","cookies",
}

def _is_valid_profile_url(url: str, platform: str) -> bool:
    if not url or f"{platform}.com" not in url:
        return False
    path = urllib.parse.urlparse(url).path.lower()

    # Allow LinkedIn profiles, Pulse articles, and company pages
    if platform == "linkedin":
        return (
            "/in/" in path or
            "/pulse/" in path or
            "/company/" in path
        )

    # For other platforms, keep existing logic
    path_parts = [p for p in path.split("/") if p]
    if not path_parts:
        return False
    if any(seg in _SKIP_SEGMENTS for seg in path_parts):
        return False
    return True


def _strip_tags(html: str) -> str:
    return re.sub(r'<[^>]+>', '', html).strip()

def _html_decode(text: str) -> str:
    return (text.replace("&amp;", "&").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&quot;", '"')
                .replace("&#39;", "'").replace("&nbsp;", " "))

def _decode_ddg_href(raw: str):
    href = _html_decode(raw)
    m = re.search(r'uddg=([^&"\']+)', href)
    if m:
        return urllib.parse.unquote(m.group(1))
    if href.startswith("//"):
        return "https:" + href
    return href if href.startswith("http") else None

def _curl_get(url, headers=None, proxies=None, timeout=20):
    kwargs = dict(headers=headers or {}, proxies=proxies,
                  impersonate="chrome120", timeout=timeout)
    if _use_proxy():
        kwargs["verify"] = False
    return curl_requests.get(url, **kwargs)


# ── Public Entry Point ─────────────────────────────────────────────────────
async def find_platform_leads_from_search(platform: str, query: str) -> list:
    clean_query = re.sub(rf'site:{re.escape(platform)}\.com\s*', '', query, flags=re.IGNORECASE).strip()
    print(f"\n[*] Discovery: Finding {platform.upper()} leads → \"{clean_query}\"")

    proxies = _build_proxies()
    normalized_query = await normalize_query_for_platform(platform, clean_query)
    router = {
        "linkedin":      _search_linkedin,
        "reddit":        _search_reddit,
        "github":        _search_github,
        "stackoverflow": _search_ddg,
        "x":             _search_x,
    }
    handler = router.get(platform.lower(), _search_ddg)
    results = await handler(platform, normalized_query, proxies)

    seen = {}
    for r in results:
        seen.setdefault(r["url"], r)
        #This for the the number of results to be displayed and saved in the database
    final = list(seen.values())[:10]

    print(f"[+] Returning {len(final)} leads for {platform}\n")
    return final


# ── Bing via Playwright ─────────────────────────────────────────────────────
_BING_RESULT_SELECTORS = [
    "li.b_algo","div.b_algo","div.b_title","div[class*='b_algo']",
    "div[class*='b_title']","#b_results li","#b_results div",
]

_BING_LINK_SELECTORS = [
    "h2 a","h3 a","div.b_title a","a.tilk","cite + a","a[href^='http']",
]

async def _playwright_bing_search(search_query: str, platform: str, url_filter=None) -> list:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("    [!] Run: pip install playwright && playwright install chromium")
        return []

    ua = _random_ua()
    pw_proxy = _proxy_for_playwright()
    results = []

    print(f"    [Browser] UA: {ua[:65]}...")

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-blink-features=AutomationControlled",
                      "--disable-dev-shm-usage","--disable-gpu","--window-size=1280,900",
                      "--ignore-certificate-errors"],
                proxy=pw_proxy,
            )
            context = await browser.new_context(
                user_agent=ua, viewport={"width":1280,"height":900},
                locale="en-US", timezone_id="America/New_York",
                ignore_https_errors=True,
                extra_http_headers={"Accept-Language":"en-US,en;q=0.9","DNT":"1"},
            )
            await context.route(re.compile(r"\.(png|jpg|jpeg|gif|svg|woff2?|ttf|mp4|webp)(\?.*)?$"),
                                lambda route: route.abort())
            page = await context.new_page()
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
            """)
            print("    [Browser] Opening bing.com...")
            await page.goto("https://www.bing.com", wait_until="domcontentloaded", timeout=30000)
            search_input = await page.wait_for_selector('#sb_form_q, input[name="q"], input[type="search"]', timeout=10000)
            await search_input.click()
            for char in search_query:
                await search_input.type(char, delay=random.randint(45,130))
            await page.keyboard.press("Enter")

            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                await asyncio.sleep(3)

            found_selector = None
            for sel in _BING_RESULT_SELECTORS:
                try:
                    await page.wait_for_selector(sel, timeout=5000)
                    count = len(await page.query_selector_all(sel))
                    if count > 0:
                        found_selector = sel
                        print(f"    [Browser] Results found with selector: '{sel}' ({count} items)")
                        break
                except Exception:
                    continue

            debug_html_path = f"debug_bing_{platform}.html"
            debug_png_path  = f"debug_bing_{platform}.png"
            try:
                page_html = await page.content()
                with open(debug_html_path, "w", encoding="utf-8") as f:
                    f.write(page_html)
                    print(f"    [debug] HTML saved → {debug_html_path} ({len(page_html)} chars)")
            except Exception:
                pass

            try:
                await page.screenshot(path=debug_png_path, full_page=False)
                print(f"    [debug] Screenshot → {debug_png_path}")
            except Exception:
                pass

            if not found_selector:
                print(f"    [!] No result selector matched. Check {debug_html_path} and {debug_png_path}")
                await browser.close()
                return []

            # ── Extract results ───────────────────────────────────────────────
            result_items = await page.query_selector_all(found_selector)
            for item in result_items:
                try:
                    anchor = None
                    for link_sel in _BING_LINK_SELECTORS:
                        anchor = await item.query_selector(link_sel)
                        if anchor:
                            break
                    if not anchor:
                        continue

                    href  = (await anchor.get_attribute("href") or "").strip()
                    title = (await anchor.inner_text() or "").strip()
                    if not href.startswith("http") or "bing.com" in href or "microsoft.com" in href:
                        continue

                    snip_el = await item.query_selector('.b_caption p, .b_algoSlug, p')
                    snippet = (await snip_el.inner_text() if snip_el else "").strip()

                    if url_filter and not url_filter(href):
                        continue

                    results.append({
                        "url": href,
                        "title": title[:120],
                        "snippet": snippet[:200],
                        "source": "playwright_bing",
                    })
                except Exception:
                    continue

            await browser.close()
        print(f"    [✓] Browser: {len(results)} results for {platform}")

    except Exception as e:
        print(f"    [!] Playwright error: {e}")

    return results


# ── LinkedIn Search with DDG → BotRight → Crawlee ─────────────────────────────
async def _search_linkedin(platform: str, query: str, proxies) -> list:
    # Primary: Google CSE (if configured)
    results = await _google_cse_search(platform, query, proxies)
    if results:
        print(f"    [✓] Google CSE: {len(results)} results")
        return results

    # Fallback 1: DuckDuckGo
    print("    [→] Launching DuckDuckGo for LinkedIn...")
    ddg_results = await _search_ddg(platform, query, proxies)
    if ddg_results:
        print(f"    [✓] DuckDuckGo: {len(ddg_results)} results")
        return ddg_results

    # Fallback 2: BotRight (stealth browser automation)
    print("[→] DDG empty — trying BotRight...")
    botright_results = await _botright_ddg_search(platform, query)
    if botright_results:
        print(f"    [✓] BotRight: {len(botright_results)} results")
        return botright_results

    # Fallback 3: Crawlee microservice
    print("[→] BotRight failed — trying Crawlee service...")
    crawlee_results = await _crawlee_service_search(platform, query)
    if crawlee_results:
        print(f"    [✓] Crawlee: {len(crawlee_results)} results")
        return crawlee_results

    # If all fail, return empty
    print("    [!] No results found for LinkedIn")
    return []



# ── Reddit ──────────────────────────────────────────────────────────────────
async def _search_reddit(platform: str, query: str, proxies) -> list:
    # Primary: Reddit JSON API
    results = await _reddit_json_api(query, proxies)
    if results:
        print(f"    [✓] Reddit API: {len(results)} results")
        return results

    # Fallback 1: DuckDuckGo
    print("    [→] Reddit API empty — trying DuckDuckGo...")
    ddg_results = await _search_ddg(platform, query, proxies)
    if ddg_results:
        print(f"    [✓] DuckDuckGo: {len(ddg_results)} results")
        return ddg_results

    # Fallback 2: BotRight (stealth browser automation)
    print("[→] DDG empty — trying BotRight...")
    botright_results = await _botright_ddg_search(platform, query)
    if botright_results:
        print(f"    [✓] BotRight: {len(botright_results)} results")
        return botright_results

    # Fallback 3: Crawlee microservice
    print("[→] BotRight failed — trying Crawlee service...")
    crawlee_results = await _crawlee_service_search(platform, query)
    if crawlee_results:
        print(f"    [✓] Crawlee: {len(crawlee_results)} results")
        return crawlee_results

    # Final fallback: Google CSE (if configured)
    print("[→] Crawlee empty — trying Google CSE...")
    gcs_results = await _google_cse_search(platform, query, proxies)
    if gcs_results:
        print(f"    [✓] Google CSE: {len(gcs_results)} results")
        return gcs_results

    # If all fail
    print("    [!] No results found for Reddit")
    return []



async def _reddit_json_api(query: str, proxies) -> list:
    params = urllib.parse.urlencode({"q": query, "sort": "relevance", "t": "month", "limit": 10, "type": "link"})
    headers = {"User-Agent": "LeadDiscoveryBot/1.0", "Accept": "application/json"}
    print(f"    [Reddit API] {query[:60]}")
    await asyncio.sleep(random.uniform(1, 2))

    try:
        resp = _curl_get(f"https://www.reddit.com/search.json?{params}", headers=headers, proxies=proxies, timeout=15)
        if resp.status_code == 429:
            print("    [!] Reddit rate limited — waiting 10s")
            await asyncio.sleep(10)
            resp = _curl_get(f"https://www.reddit.com/search.json?{params}", headers=headers, proxies=proxies, timeout=15)
        if resp.status_code != 200:
            print(f"    [!] Reddit API HTTP {resp.status_code}")
            return []

        results = []
        for post in resp.json().get("data", {}).get("children", []):
            pd = post.get("data", {})
            permalink = "https://www.reddit.com" + pd.get("permalink", "")
            title     = pd.get("title", "Reddit Post")
            selftext  = pd.get("selftext", "")[:200]
            sub       = pd.get("subreddit_name_prefixed", "")
            results.append({
                "url": permalink,
                "title": f"[{sub}] {title}"[:120],
                "snippet": selftext,
                "source": "reddit_api",
            })
        print(f"    [✓] Reddit API: {len(results)} posts")
        return results
    except Exception as e:
        print(f"    [!] Reddit API error: {e}")
        return []


# ── GitHub REST API ─────────────────────────────────────────────────────────
async def _search_github(platform: str, query: str, proxies) -> list:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "LeadDiscoveryBot/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    results = []
    for endpoint, label in [
        (f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=updated&per_page=5", "repos"),
        (f"https://api.github.com/search/users?q={urllib.parse.quote(query + ' type:user')}&per_page=5", "users"),
    ]:
        try:
            await asyncio.sleep(random.uniform(0.5, 1.5))
            resp = _curl_get(endpoint, headers=headers, proxies=proxies, timeout=15)
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    results.append({
                        "url": item.get("html_url", ""),
                        "title": item.get("full_name") or item.get("login", "GitHub"),
                        "snippet": (item.get("description") or "")[:200],
                        "source": f"github_api_{label}",
                    })
            elif resp.status_code == 403:
                print("    [!] GitHub rate limited — add GITHUB_TOKEN to .env")
                break
        except Exception as e:
            print(f"    [!] GitHub {label} error: {e}")
    print(f"    [✓] GitHub: {len(results)} results")
    return results

# ── X / Twitter ──────────────────────────────────────────────────────────────
async def _search_x(platform: str, query: str, proxies) -> list:
    # Normalize platform name
    normalized_platform = "twitter"

    # Primary: DuckDuckGo
    print("    [→] Launching DuckDuckGo for X...")
    ddg_results = await _search_ddg(normalized_platform, query, proxies)
    if ddg_results:
        print(f"    [✓] DuckDuckGo: {len(ddg_results)} results")
        return ddg_results

    # Fallback 1: BotRight (stealth browser automation)
    print("[→] DDG empty — trying BotRight...")
    botright_results = await _botright_ddg_search(normalized_platform, query)
    if botright_results:
        print(f"    [✓] BotRight: {len(botright_results)} results")
        return botright_results

    # Fallback 2: Crawlee microservice (scalable scraping)
    print("[→] BotRight failed — trying Crawlee service...")
    crawlee_results = await _crawlee_service_search(normalized_platform, query)
    if crawlee_results:
        print(f"    [✓] Crawlee: {len(crawlee_results)} results")
        return crawlee_results

    # Final fallback: Google CSE (if configured)
    print("[→] Crawlee empty — trying Google CSE...")
    return await _google_cse_search(normalized_platform, query, proxies)



# ── Playwright + BotRight Proxy Fallback for StackOverflow ───────────────────
async def _playwright_stackoverflow(url: str) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("    [!] Run: pip install playwright && playwright install chromium")
        return ""

    proxy = _proxy_for_playwright()
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                proxy=proxy
            )
            context = await browser.new_context(
                user_agent=_random_ua(),
                ignore_https_errors=True
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            content = await page.content()
            await browser.close()
            return content
    except Exception as e:
        print(f"    [!] Playwright error: {e}")
        print("    [→] Falling back to BotRight...")

        # BotRight fallback
        try:
            from botright.async_api import async_botright
        except ImportError:
            print("    [!] Run: pip install botright")
            return ""

        async with async_botright() as br:
            browser = await br.chromium.launch(
                headless=True,
                proxy=proxy,
                human_like=True
            )
            context = await browser.new_context(
                user_agent=_random_ua(),
                ignore_https_errors=True
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            content = await page.content()
            await browser.close()
            return content

    


# ── BotRight DuckDuckGo Fallback ─────────────────────────────────────────────
async def _botright_ddg_search(platform: str, query: str) -> list:
    # Proper existence check — ImportError alone doesn't catch playwright
    # browser missing or sub-dependency failures
    try:
        from botright.async_api import async_botright as _br_cls
    except Exception as e:
        print(f"    [!] BotRight unavailable: {e}")
        print("    [!] Run: pip install botright && playwright install chromium")
        return []

    results = []
    try:
        async with _br_cls() as br:
            browser = await br.chromium.launch(
                headless=True,
                proxy=_proxy_for_playwright(),
                human_like=True,
            )
            context = await browser.new_context(
                user_agent=_random_ua(),
                ignore_https_errors=True,
            )
            page = await context.new_page()
            await page.goto("https://duckduckgo.com", wait_until="domcontentloaded", timeout=30000)

            for char in query:
                await page.type("input[name='q']", char, delay=random.randint(50, 120))
            await page.keyboard.press("Enter")
            await page.wait_for_load_state("networkidle", timeout=20000)

            anchors = await page.query_selector_all("a.result__a")
            check_platform = "twitter" if platform == "x" else platform
            for a in anchors:
                href  = await a.get_attribute("href") or ""
                title = (await a.inner_text() or "").strip()
                if href.startswith("http") and _is_valid_profile_url(href, check_platform):
                    results.append({
                        "url": href,
                        "title": title[:120],
                        "snippet": "",
                        "source": "botright_ddg",
                    })

            await browser.close()
    except Exception as e:
        print(f"    [!] BotRight runtime error: {e}")

    print(f"    [✓] BotRight DDG: {len(results)} results for {platform}")
    return results

# ── BotRight Bing Search (fallback) ────────────────────────────────
async def _botright_bing_search(search_query: str, platform: str, url_filter=None) -> list:
    try:
        from botright.async_api import async_botright
    except ImportError:
        print("    [!] Run: pip install botright")
        return []

    results = []
    async with async_botright() as br:
        browser = await br.chromium.launch(
            headless=True,
            proxy=_proxy_for_playwright(),
            human_like=True  # BotRight option
        )
        context = await browser.new_context(user_agent=_random_ua())
        page = await context.new_page()
        await page.goto("https://www.bing.com", wait_until="domcontentloaded", timeout=30000)

        # Human-like typing
        for char in search_query:
            await page.type("#sb_form_q", char, delay=random.randint(50,120))
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle", timeout=20000)

        # Extract results (similar to Playwright logic)
        anchors = await page.query_selector_all("h2 a, h3 a")
        for a in anchors:
            href = await a.get_attribute("href")
            title = await a.inner_text()
            if href and href.startswith("http") and url_filter and url_filter(href):
                results.append({"url": href, "title": title[:120], "snippet": "", "source": "botright_bing"})

        await browser.close()
    print(f"    [✓] BotRight: {len(results)} results for {platform}")
    return results
import httpx

async def _crawlee_service_search(platform: str, query: str) -> list:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post("http://localhost:4000/scrape", json={"platform": platform, "query": query})
            if resp.status_code == 200:
                return resp.json().get("results", [])
    except Exception as e:
        print(f"    [!] Crawlee service error: {e}")
    return []

# ── DuckDuckGo HTML (StackOverflow fallback) ────────────────────────────────
# ── DuckDuckGo HTML ─────────────────────────────────────────────────────────
async def _search_ddg(platform: str, query: str, proxies) -> list:
    # The query from normalize_query_for_platform already contains site:
    # Only prepend if it somehow slipped through without one
    _platform_hint = "twitter" if platform == "x" else platform
    if "site:" in query:
        full_query = query
    else:
        full_query = f"site:{platform}.com {query}"

    print(f"    [DDG] Final query: {full_query}")
    params = urllib.parse.urlencode({"q": full_query, "kl": "us-en"})
    headers = {
        "User-Agent": _random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://duckduckgo.com/",
        "DNT": "1",
    }
    await asyncio.sleep(random.uniform(1.5, 3.0))
    try:
        resp = _curl_get(
            f"https://html.duckduckgo.com/html/?{params}",
            headers=headers, proxies=proxies, timeout=20,
        )

        # Retry once if DDG throttles with 202
        if resp.status_code == 202:
            print("    [!] DDG throttled — retrying after 8s")
            await asyncio.sleep(8)
            resp = _curl_get(
                f"https://html.duckduckgo.com/html/?{params}",
                headers=headers, proxies=proxies, timeout=20,
            )

        if resp.status_code != 200:
            print(f"    [!] DDG HTTP {resp.status_code}")
            return []

        html = resp.text
        with open(f"debug_ddg_{platform}.html", "w", encoding="utf-8") as f:
            f.write(html)

        # ── Split into result blocks ──────────────────────────────────────
        # DDG uses both "web-result" and plain "result" class names across versions
        blocks_web    = re.split(r'<div[^>]+\bweb-result\b[^>]*>', html)
        blocks_result = re.split(r'<div[^>]+class=["\'][^"\']*\bresult\b[^"\']*["\'][^>]*>', html)
        blocks = blocks_web if len(blocks_web) >= len(blocks_result) else blocks_result
        print(f"    [debug] result blocks: {len(blocks) - 1}")

        # ── If still only 1 block, try a relaxed query without site: ─────
        # This catches cases where DDG has no index for the site: combo
        if len(blocks) <= 1:
            print("    [!] DDG returned 0 blocks — retrying without site: restriction")
            relaxed = re.sub(r'site:\S+\s*', '', full_query).strip()
            # Add platform name as a keyword instead so results are still relevant
            relaxed = f"{relaxed} linkedin" if platform == "linkedin" else f"{relaxed} {platform}"
            params2 = urllib.parse.urlencode({"q": relaxed, "kl": "us-en"})
            await asyncio.sleep(random.uniform(2.0, 4.0))
            resp2 = _curl_get(
                f"https://html.duckduckgo.com/html/?{params2}",
                headers=headers, proxies=proxies, timeout=20,
            )
            if resp2.status_code == 200:
                html = resp2.text
                with open(f"debug_ddg_{platform}_relaxed.html", "w", encoding="utf-8") as f:
                    f.write(html)
                blocks_web2    = re.split(r'<div[^>]+\bweb-result\b[^>]*>', html)
                blocks_result2 = re.split(r'<div[^>]+class=["\'][^"\']*\bresult\b[^"\']*["\'][^>]*>', html)
                blocks = blocks_web2 if len(blocks_web2) >= len(blocks_result2) else blocks_result2
                print(f"    [debug] relaxed result blocks: {len(blocks) - 1}")

        results = []
        for block in blocks[1:]:
            # ── Extract href — try multiple DDG anchor patterns ───────────
            href_raw = None
            for pattern in [
                r'class="result__a"[^>]+href=["\']([^"\']+)["\']',
                r'href=["\']([^"\']+)["\'][^>]*class="result__a"',
                r'class="[^"]*result__url[^"]*"[^>]*href=["\']([^"\']+)["\']',
                r'href=["\'](/l/\?[^"\']+)["\']',
                r'href=["\']([^"\']*uddg=[^"\']+)["\']',
            ]:
                m = re.search(pattern, block)
                if m:
                    href_raw = m.group(1)
                    break

            if not href_raw:
                continue

            real_url = _decode_ddg_href(href_raw)
            if not real_url:
                continue

            # ── Validate: must belong to target platform ──────────────────
            check_platform = "twitter" if platform == "x" else platform
            valid = _is_valid_profile_url(real_url, check_platform)
            if not valid and platform == "x":
                valid = _is_valid_profile_url(real_url, "x")
            if not valid:
                print(f"    [debug] Discarded: {real_url}")
                continue

            # ── Title ─────────────────────────────────────────────────────
            title = "Lead"
            for pat in [
                r'class="result__a"[^>]*>(.*?)</a>',
                r'class="[^"]*result__title[^"]*"[^>]*>(.*?)</(?:a|span|div)>',
            ]:
                tm = re.search(pat, block, re.DOTALL)
                if tm:
                    t = _strip_tags(_html_decode(tm.group(1))).strip()
                    if t:
                        title = t
                        break

            # ── Snippet ───────────────────────────────────────────────────
            snippet = ""
            for pat in [
                r'class="result__snippet"[^>]*>(.*?)</(?:a|span|div)>',
                r'class="[^"]*result__snip[^"]*"[^>]*>(.*?)</(?:a|span|div)>',
                r'class="[^"]*snippet[^"]*"[^>]*>(.*?)</(?:a|span|div)>',
            ]:
                sm = re.search(pat, block, re.DOTALL)
                if sm:
                    s = _strip_tags(_html_decode(sm.group(1))).strip()
                    if s:
                        snippet = s
                        break

            results.append({
                "url": real_url,
                "title": title[:120],
                "snippet": snippet[:200],
                "source": "ddg",
            })

        print(f"    [✓] DDG: {len(results)} results for {platform}")
        return results

    except Exception as e:
        print(f"    [!] DDG error: {e}")
        return []

# ── Google CSE (optional) ─────────────────────────────────────────────────────
async def _google_cse_search(platform: str, query: str, proxies) -> list:
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    cse_id  = os.getenv("GOOGLE_CSE_ID", "").strip()
    if not api_key or not cse_id:
        return []

    params = urllib.parse.urlencode({
        "key": api_key,
        "cx": cse_id,
        "q": f"site:{platform}.com {query}",
        "num": 10,
    })
    try:
        resp = _curl_get(
            f"https://www.googleapis.com/customsearch/v1?{params}",
            proxies=proxies,
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"    [!] Google CSE HTTP {resp.status_code}")
            return []

        results = []
        for item in resp.json().get("items", []):
            link = item.get("link", "")
            if _is_valid_profile_url(link, platform):
                results.append({
                    "url": link,
                    "title": item.get("title", "")[:120],
                    "snippet": item.get("snippet", "")[:200],
                    "source": "google_cse",
                })
        print(f"    [✓] Google CSE: {len(results)} results")
        return results

    except Exception as e:
        print(f"    [!] Google CSE error: {e}")
        return []