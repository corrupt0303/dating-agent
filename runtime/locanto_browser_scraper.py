"""
LocantoBrowserScraper: Async, Playwright-powered scraper for locanto.co.za

Usage:
    from locanto_browser_scraper import LocantoBrowserScraper
    listings = await LocantoBrowserScraper().search_listings("dating", "Cape Town", max_pages=2)
    details = await LocantoBrowserScraper().get_listing_details(listings[0]['url'])

Requirements:
    pip install playwright
    playwright install
"""
import asyncio
from typing import List, Dict, Optional
from urllib.parse import urljoin
from playwright.async_api import async_playwright
# Optional import for agent integration
try:
    from livekit.agents import function_tool, RunContext
except ImportError:
    function_tool = None
    RunContext = None

from playwright_stealth import stealth_async
import os
import json
import urllib.parse
import re
from .agent_utils import speak_chunks
import logging
from .locanto_constants import LOCANTO_CATEGORY_SLUGS, LOCANTO_LOCATION_SLUGS, LOCANTO_SECTION_IDS

PROXY_PREFIX = "https://please.untaint.us/?url="
BASE_URL = "https://www.locanto.co.za"

# Constants
MAX_ARTICLES_PER_PAGE = 10
PAGE_TIMEOUT = 30000
WAIT_AFTER_NAV = 2000
SELECTOR_TIMEOUT = 8000
MAX_RETRIES = 3

# Setup logging
logging.basicConfig(level=logging.INFO)

def is_valid_locanto_location(location):
    if not location:
        return False
    return location.lower().replace(' ', '-') in LOCANTO_LOCATION_SLUGS

# --- Selectors for robust extraction ---
LISTING_SELECTORS = {
    'container': [
        'article.posting_listing',
    ],
    'url': [
        'a.posting_listing__title.js-result_title.js-ad_link',
        'a.posting_listing__title',
    ],
    'title': [
        'a.posting_listing__title.js-result_title.js-ad_link div.h3.js-result_title',
        'div.h3.js-result_title',
    ],
    'location': [
        'span.js-result_location.posting_listing__city',
        'span.js-result_location',
        'span.posting_listing__city',
    ],
    'description': [
        'div.posting_listing__description.js-description_snippet',
        '.js-description_snippet',
        'div.posting_listing__description',
    ],
    'age': [
        'span.posting_listing__age',
    ],
    'category': [
        # Not directly present, can be left as is or inferred from context
    ],
}
DETAIL_SELECTORS = {
    'title': [
        'h1.app_title',
        'h1',
        '.vap_header__title',
    ],
    'description': [
        '.vap__description',
        '.vap_user_content__description',
        '.js-description_snippet',
        '.posting_listing__description',
        'div[class*="description"]',
        'div[class*="content"]',
    ],
    'price': [
        'div.price',
        'span.price',
        'div[class*="price"]',
        'span[class*="price"]',
    ],
    'location': [
        'span[itemprop="addressLocality"]',
        '.vap_posting_details__address',
        '.js-result_location',
        'div[class*="location"]',
        'span[class*="location"]',
    ],
    'date_posted': [
        'meta[name="dcterms.date"]',
        '.vap_user_content__date',
        'time[datetime]',
    ],
    'images': [
        '.user_images__img',
        'img[src*="locanto"]',
        'img.posting_listing__image',
    ],
    'contact_info': [
        '.vap__description',
        '.contact_buttons__button--call',
        'div[class*="contact"]',
        'div[class*="phone"]',
        'a[href^="tel:"]',
    ],
    'age': [
        '.header-age',
        '.vap_user_content__feature_value',
        'span.posting_listing__age',
        'span[class*="age"]',
    ],
}

def clean_url(u: str) -> str:
    """Clean and normalize Locanto URLs, removing proxy prefixes and decoding repeatedly."""
    import urllib.parse, re
    # Decode repeatedly until stable
    prev = None
    while prev != u:
        prev = u
        u = urllib.parse.unquote(u)
    # Substitute double-proxy pattern with single proxy
    u = re.sub(r'https://please\.untaint\.us/\?url=https://please\.untaint\.us\?','https://please.untaint.us/?url=', u)
    # Remove all proxy prefixes (encoded or not), even if nested
    proxy_pattern = re.escape(PROXY_PREFIX)
    u = re.sub(rf'({proxy_pattern})+', '', u)
    # Remove any ?url= or &url= at the start or after a proxy
    u = re.sub(r'([&?])url=', r'\1', u)
    # Remove any leading ? or & left over
    u = re.sub(r'^[?&]+', '', u)
    # Remove double slashes after https:
    u = re.sub(r'https:\/\/+', 'https://', u)
    # Remove any whitespace
    u = u.strip()
    return u

def build_locanto_url(query=None, location=None, category=None, tag=None, section=None):
    base = "https://www.locanto.co.za"
    if tag:
        return f"{base}/g/tag/{tag}/"
    # Only use /<location>/ if location is a valid slug
    if location and is_valid_locanto_location(location):
        if category:
            return f"{base}/{location}/{category}/?query={query.replace(' ', '+') if query else ''}"
        if section:
            return f"{base}/{location}/{section}/?query={query.replace(' ', '+') if query else ''}"
        return f"{base}/{location}/?query={query.replace(' ', '+') if query else ''}"
    # Otherwise, use generic search
    if query:
        return f"{base}/g/q/?query={query.replace(' ', '+')}"
    return base

class LocantoBrowserScraper:
    def __init__(self, cookies_path: str = None, detail_fetch_concurrency: int = 4):
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self.cookies_path = cookies_path
        self.detail_fetch_concurrency = detail_fetch_concurrency

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        # Load cookies if provided
        if self.cookies_path and os.path.exists(self.cookies_path):
            logging.info(f"[DEBUG] Loading cookies from {self.cookies_path}")
            with open(self.cookies_path, "r") as f:
                cookies = json.load(f)
            await self.context.add_cookies(cookies)
        await stealth_async(self.context)
        self.page = await self.context.new_page()

    async def close(self):
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def try_selectors_playwright(self, element, selectors, attr=None):
        for sel in selectors:
            try:
                if attr:
                    found = await element.query_selector(sel)
                    if found:
                        val = await found.get_attribute(attr)
                        if val:
                            logging.info(f"[DEBUG] Selector '{sel}' succeeded for attr '{attr}'")
                            return val, sel
                else:
                    found = await element.query_selector(sel)
                    if found:
                        val = await found.inner_text()
                        if val:
                            logging.info(f"[DEBUG] Selector '{sel}' succeeded for text")
                            return val, sel
            except Exception as e:
                continue
        return None, None

    async def search_listings(self, query: str = None, location: str = None, max_pages: int = 1, tag: str = None, category: str = None, section: str = None, url: str = None, age_min: int = None, age_max: int = None, query_description: bool = None, dist: int = None, sort: str = None) -> List[Dict]:
        """Search Locanto listings by tag, category, section, generic query, or direct URL. Always includes all required parameters in the URL. Enhanced with robust pagination and contact info extraction."""
        results = []
        page_num = 1
        debug_info = {}
        if query_description is None:
            query_description = True
        if sort is None:
            sort = "date"
        if age_min is None:
            age_min = 18
        if age_max is None:
            age_max = 40
        if dist is None:
            dist = 30
        while page_num <= max_pages:
            if url:
                search_url = clean_url(url)
                from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, parse_qsl
                parsed = urlparse(search_url)
                query_params = dict(parse_qsl(parsed.query))
                query_params.setdefault('query', query or '')
                query_params['query_description'] = '1'
                query_params['sort'] = sort
                query_params['age[min]'] = str(age_min)
                query_params['age[max]'] = str(age_max)
                query_params['dist'] = str(dist)
                new_query = urlencode(query_params, doseq=True)
                search_url = urlunparse(parsed._replace(query=new_query))
                if not search_url.startswith("http"):
                    search_url = BASE_URL + search_url if search_url.startswith("/") else BASE_URL + "/" + search_url
            else:
                search_url = build_locanto_url(query=query, location=location, category=category, tag=tag, section=section)
                params = [
                    f"query={query or ''}",
                    "query_description=1",
                    f"sort={sort}",
                    f"age[min]={age_min}",
                    f"age[max]={age_max}",
                    f"dist={dist}"
                ]
                if '?' in search_url:
                    search_url += '&' + '&'.join(params)
                else:
                    search_url += '?' + '&'.join(params)
                if page_num > 1:
                    search_url += f"&page={page_num}"
            proxied_url = f"{PROXY_PREFIX}{search_url}"
            if page_num == 1:
                debug_info['_debug_url'] = search_url
                debug_info['_debug_proxied_url'] = proxied_url
            logging.info(f"[DEBUG] Navigating to: {proxied_url}")
            if not self.page:
                await self.start()
            try:
                await self.page.goto(proxied_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            except Exception as e:
                logging.error(f"[DEBUG] Navigation timeout or error: {e}")
                break
            await self.page.wait_for_timeout(WAIT_AFTER_NAV)
            html = await self.page.content()
            logging.info('[DEBUG] First 2000 chars of page HTML:')
            logging.info(html[:2000])
            if (
                "<title>Locanto Error page</title>" in html
                or ("captcha" in html.lower() and "Please verify you are a human" in html)
                or "cf-challenge" in html
            ):
                logging.info("[DEBUG] Blocked by Cloudflare, captcha, or similar detected! Aborting.")
                return [debug_info | {"error": "Blocked by Cloudflare or captcha. Try again later or with different proxy/cookies."}]
            try:
                await self.page.wait_for_selector(','.join(LISTING_SELECTORS['container']), timeout=SELECTOR_TIMEOUT)
            except Exception as e:
                logging.error(f"[DEBUG] Selector not found: {e}")
                debug_path = f"locanto_debug_page_{page_num}.html"
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(html)
                logging.info(f"[DEBUG] Wrote full HTML to {debug_path} for inspection.")
                break
            articles = []
            for sel in LISTING_SELECTORS['container']:
                found = await self.page.query_selector_all(sel)
                if found:
                    articles.extend(found)
            logging.info(f"[DEBUG] Found {len(articles)} listing elements on page {page_num} (using multiple selectors)")
            articles = articles[:MAX_ARTICLES_PER_PAGE]
            if not articles:
                logging.info('[DEBUG] No articles found. Dumping first 2000 chars of HTML:')
                logging.info(html[:2000])
            for art in articles:
                try:
                    anchor = await art.query_selector('a.posting_listing__title.js-result_title.js-ad_link')
                    url_val = None
                    title = None
                    if anchor:
                        url_val = await anchor.get_attribute('href')
                        title_elem = await anchor.query_selector('div.h3.js-result_title')
                        if title_elem:
                            title = await title_elem.inner_text()
                    if not url_val:
                        url_val, _ = await self.try_selectors_playwright(art, LISTING_SELECTORS['url'], attr='href')
                    url_val = clean_url(url_val)
                    if url_val and not url_val.startswith(PROXY_PREFIX):
                        if url_val.startswith("/"):
                            url_val = BASE_URL + url_val
                        if url_val.startswith(BASE_URL):
                            url_val = PROXY_PREFIX + url_val
                        elif url_val.startswith('http'):
                            url_val = PROXY_PREFIX + url_val
                    location_val, _ = await self.try_selectors_playwright(art, LISTING_SELECTORS['location'])
                    description, _ = await self.try_selectors_playwright(art, LISTING_SELECTORS['description'])
                    age, _ = await self.try_selectors_playwright(art, LISTING_SELECTORS['age'])
                    category_val = None
                    # Prepare listing dict (contact_info to be filled in batch)
                    results.append({
                        'title': title,
                        'url': url_val,
                        'location': location_val,
                        'description': description,
                        'age': age,
                        'category': category_val,
                        'contact_info': None
                    })
                except Exception as e:
                    logging.error(f"[DEBUG] Error parsing article: {e}")
            # Batch fetch contact info for all listings in parallel (with concurrency limit)
            async def fetch_contact_info(listing, sem):
                async with sem:
                    contact_info = None
                    try:
                        detail_url = listing['url']
                        if detail_url and detail_url.startswith(PROXY_PREFIX):
                            detail = await self.get_listing_details(detail_url)
                            contact_info = detail.get('contact_info')
                    except Exception as e:
                        logging.error(f"[DEBUG] Error fetching contact info for {listing.get('url')}: {e}")
                    listing['contact_info'] = contact_info
            sem = asyncio.Semaphore(self.detail_fetch_concurrency)
            await asyncio.gather(*(fetch_contact_info(listing, sem) for listing in results[-len(articles):]))
            page_num += 1
        if results and debug_info:
            results[0].update(debug_info)
        elif debug_info:
            results.append(debug_info)
        return results

    async def get_listing_details(self, url: str) -> Dict:
        """Get detailed info from a Locanto listing page using the same browser context. Extracts only relevant content. Retries on failure."""
        url = clean_url(url)
        if not url.startswith(PROXY_PREFIX):
            if url.startswith("/"):
                url = BASE_URL + url
            if url.startswith(BASE_URL):
                url = PROXY_PREFIX + url
            elif url.startswith('http'):
                url = PROXY_PREFIX + url
        logging.info(f"[DEBUG] Navigating to detail page: {url}")
        details = {}
        if not self.page:
            await self.start()
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                await asyncio.sleep(2)
                html = await self.page.content()
                # Title
                title, title_sel = await self.try_selectors_playwright(self.page, DETAIL_SELECTORS['title'])
                details['title'] = title or ""
                # Description
                description, desc_sel = await self.try_selectors_playwright(self.page, DETAIL_SELECTORS['description'])
                details['description'] = description or ""
                # Price
                price, price_sel = await self.try_selectors_playwright(self.page, DETAIL_SELECTORS['price'])
                details['price'] = price or ""
                # Location
                location, loc_sel = await self.try_selectors_playwright(self.page, DETAIL_SELECTORS['location'])
                details['location'] = location or ""
                # Date posted
                date_posted, date_sel = await self.try_selectors_playwright(self.page, DETAIL_SELECTORS['date_posted'])
                details['date_posted'] = date_posted or ""
                # Images
                img_urls = []
                for sel in DETAIL_SELECTORS['images']:
                    imgs = await self.page.query_selector_all(sel)
                    for img in imgs:
                        src = await img.get_attribute('src')
                        if src:
                            img_urls.append(src)
                details['images'] = img_urls
                # Contact info
                contact, contact_sel = await self.try_selectors_playwright(self.page, DETAIL_SELECTORS['contact_info'])
                details['contact_info'] = contact or ""
                # Age
                age, age_sel = await self.try_selectors_playwright(self.page, DETAIL_SELECTORS['age'])
                if age:
                    age_match = re.search(r'(\d{2})', age)
                    details['age'] = age_match.group(1) if age_match else age
                else:
                    details['age'] = ""
                # Ad ID
                id_match = re.search(r'ID_(\d+)', url)
                if not id_match:
                    id_match = re.search(r'ID_(\d+)', html)
                details['ad_id'] = id_match.group(1) if id_match else ""
                logging.info(f"[DEBUG] Details extracted: {details}")
                return details
            except Exception as e:
                logging.error(f"[DEBUG] Error fetching details (attempt {attempt}): {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2)
                else:
                    details['error'] = f"Failed to fetch details after {MAX_RETRIES} attempts: {e}"
                    return details

    async def recursive_map_site(self, start_url: str = None, max_depth: int = 2, visited=None, depth=0, save_html=False):
        """
        Recursively map Locanto site structure for fine-tuning selectors.
        - start_url: The URL to start mapping from (default: Locanto search page).
        - max_depth: How deep to recurse (default: 2).
        - visited: Set of visited URLs to avoid loops.
        - save_html: If True, saves each page's HTML for manual inspection.
        """
        if visited is None:
            visited = set()
        if not start_url:
            start_url = f"{PROXY_PREFIX}{BASE_URL}/g/q/?query=dating"
        if start_url in visited or depth > max_depth:
            return
        visited.add(start_url)
        logging.info(f"[MAP] Visiting (depth={depth}): {start_url}")
        if not self.page:
            await self.start()
        try:
            await self.page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
            await self.page.wait_for_timeout(2000)
            html = await self.page.content()
            if save_html:
                fname = f"map_debug_depth{depth}_{re.sub(r'[^a-zA-Z0-9]', '_', start_url)[:50]}.html"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(html)
            # Find all listing containers
            articles = await self.page.query_selector_all('article.posting_listing, li.listing, div.listing')
            logging.info(f"[MAP] Found {len(articles)} listing elements at depth {depth}")
            # Find all category links (sidebars, navs, etc.)
            cat_links = await self.page.query_selector_all('a[href*="/g/"], a[href*="/personals/"], a[href*="/dating/"]')
            next_links = await self.page.query_selector_all('a[rel="next"], a.js-pagination-next')
            # Print found category and next links
            for a in cat_links + next_links:
                href = await a.get_attribute('href')
                if href and not href.startswith('http'):
                    href = BASE_URL + href
                if href and not href.startswith(PROXY_PREFIX):
                    href = PROXY_PREFIX + href
                if href and href not in visited:
                    logging.info(f"[MAP] Queuing: {href}")
                    await self.recursive_map_site(href, max_depth, visited, depth+1, save_html)
        except Exception as e:
            logging.error(f"[MAP] Error at {start_url}: {e}")

@function_tool
async def search_locanto_browser(context: RunContext, query: str = "dating", location: str = "Cape Town", max_pages: int = 1, tag: str = None, category: str = None, section: str = None, url: str = None) -> str:
    """Search Locanto.co.za for listings by tag, category, section, generic query, or direct URL. Uses Playwright browser and proxy. Supports tag, category, section, and direct URLs."""
    try:
        scraper = LocantoBrowserScraper()
        listings = await scraper.search_listings(query=query, location=location, max_pages=max_pages, tag=tag, category=category, section=section, url=url)
        if not listings:
            return f"No Locanto listings found for '{query}' in '{location}'."
        # If the first result is an error dict, return the error message
        if isinstance(listings[0], dict) and 'error' in listings[0]:
            debug_url = listings[0].get('_debug_url')
            debug_proxied_url = listings[0].get('_debug_proxied_url')
            debug_msg = f"\n[DEBUG] Search URL: {debug_url}" if debug_url else ""
            debug_msg += f"\n[DEBUG] Proxied URL: {debug_proxied_url}" if debug_proxied_url else ""
            return f"Error: {listings[0]['error']}{debug_msg}"
        summary = f"Found {len(listings)} Locanto listings for '{query}' in '{location}':\n\n"
        for i, listing in enumerate(listings[:5], 1):
            if not isinstance(listing, dict) or 'title' not in listing:
                continue
            summary += f"{i}. {listing['title']}\n"
            if listing.get('age'):
                summary += f"   Age: {listing['age']}\n"
            if listing.get('location'):
                summary += f"   Location: {listing['location']}\n"
            if listing.get('description'):
                desc = listing['description'][:120] + ('...' if len(listing['description']) > 120 else '')
                summary += f"   Description: {desc}\n"
            # Do NOT include the URL in the summary
            summary += "\n"
        return summary
    except Exception as e:
        return f"Error searching Locanto with Playwright: {e}" 