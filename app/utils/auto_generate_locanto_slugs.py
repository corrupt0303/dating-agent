import asyncio
from bs4 import BeautifulSoup
import re
import time
from playwright.async_api import async_playwright

PROXY_PREFIX = "https://please.untaint.us/?url="
BASE_URL = "https://www.locanto.co.za"

async def fetch_playwright(url, page):
    proxied_url = PROXY_PREFIX + url
    await page.goto(proxied_url, wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(2)  # Let JS render
    html = await page.content()
    return html

def extract_slugs_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    location_slugs = set()
    category_slugs = set()
    section_ids = set()
    tag_slugs = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # /<location>/<category>/<section>/
        m = re.match(r"https://www\\.locanto\\.co\\.za/([a-zA-Z0-9\\-]+)/([a-zA-Z0-9\\-]+)/([a-zA-Z0-9]+)/", href)
        if m:
            location_slugs.add(m.group(1))
            category_slugs.add(m.group(2))
            section_ids.add(m.group(3))
        # /g/<category>/
        m2 = re.match(r"https://www\\.locanto\\.co\\.za/g/([a-zA-Z0-9\\-]+)/", href)
        if m2:
            category_slugs.add(m2.group(1))
        # /<location>/
        m3 = re.match(r"https://www\\.locanto\\.co\\.za/([a-zA-Z0-9\\-]+)/$", href)
        if m3:
            location_slugs.add(m3.group(1))
        # /g/tag/<tag>/
        m4 = re.match(r"https://www\\.locanto\\.co\\.za/g/tag/([a-zA-Z0-9\\-]+)/", href)
        if m4:
            tag_slugs.add(m4.group(1))
    return location_slugs, category_slugs, section_ids, tag_slugs

async def crawl(start_urls, max_depth=2, delay=1.0):
    visited = set()
    all_location_slugs = set()
    all_category_slugs = set()
    all_section_ids = set()
    all_tag_slugs = set()
    queue = [(url, 0) for url in start_urls]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        page = await context.new_page()
        while queue:
            url, depth = queue.pop(0)
            if url in visited or depth > max_depth:
                continue
            visited.add(url)
            try:
                html = await fetch_playwright(url, page)
            except Exception as e:
                print(f"[WARN] Failed to fetch {url}: {e}")
                continue
            locs, cats, secs, tags = extract_slugs_from_html(html)
            all_location_slugs.update(locs)
            all_category_slugs.update(cats)
            all_section_ids.update(secs)
            all_tag_slugs.update(tags)
            # Find more category/tag pages to crawl
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("https://www.locanto.co.za/") and href not in visited:
                    # Only crawl category/tag/section pages
                    if re.search(r"/(g/|personals|services|jobs|community|for-sale|real-estate|events|classes|automotive|dating|tag)/", href):
                        queue.append((href, depth + 1))
            await asyncio.sleep(delay)
        await browser.close()
    return all_location_slugs, all_category_slugs, all_section_ids, all_tag_slugs

async def main():
    print("[INFO] Fetching Locanto homepage with Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        page = await context.new_page()
        html = await fetch_playwright(BASE_URL, page)
        print("[DEBUG] First 1000 chars of homepage HTML:")
        print(html[:1000])
        locs, cats, secs, tags = extract_slugs_from_html(html)
        # Start URLs: homepage + all category/tag links found on homepage
        soup = BeautifulSoup(html, "html.parser")
        start_urls = set([BASE_URL])
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("https://www.locanto.co.za/"):
                if re.search(r"/(g/|personals|services|jobs|community|for-sale|real-estate|events|classes|automotive|dating|tag)/", href):
                    start_urls.add(href)
        await browser.close()
    print(f"[INFO] Crawling {len(start_urls)} start URLs up to depth 2 with Playwright...")
    all_locs, all_cats, all_secs, all_tags = await crawl(list(start_urls), max_depth=2)
    # Merge with homepage results
    all_locs.update(locs)
    all_cats.update(cats)
    all_secs.update(secs)
    all_tags.update(tags)
    print("\n# LOCANTO_LOCATION_SLUGS = set([");
    for slug in sorted(all_locs):
        print(f"    '{slug}',")
    print("])")
    print("\n# LOCANTO_CATEGORY_SLUGS = set([");
    for slug in sorted(all_cats):
        print(f"    '{slug}',")
    print("])")
    print("\n# LOCANTO_SECTION_IDS = set([");
    for sid in sorted(all_secs):
        print(f"    '{sid}',")
    print("])")
    print("\n# LOCANTO_TAG_SLUGS = set([");
    for tag in sorted(all_tags):
        print(f"    '{tag}',")
    print("])")

if __name__ == '__main__':
    asyncio.run(main()) 