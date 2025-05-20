import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


import re

async def scrape_bing(query, num_results=10):
    # --- AI logic for Bing parameters ---
    safesearch = "Strict"
    mkt = "en-US"
    setlang = "EN"
    freshness = None
    response_filter = None

    # Lowercase query for checks
    q_lower = query.lower()

    # If query looks like news/time-sensitive, add freshness
    if any(word in q_lower for word in ["news", "today", "latest", "breaking", "update", "recent"]):
        freshness = "Week"

    # If query looks like it needs images/videos, add response filter
    if any(word in q_lower for word in ["image", "photo", "picture", "video"]):
        response_filter = "Images"
    elif any(word in q_lower for word in ["video", "clip", "movie"]):
        response_filter = "Videos"
    else:
        response_filter = "Webpages"

    # If query contains explicit language, relax safesearch
    if re.search(r"\b(sex|porn|adult|xxx|nude|nsfw)\b", q_lower):
        safesearch = "Off"

    # TODO: Enhance language/market detection if needed

    # Build Bing URL with smart parameters
    url = f"https://www.bing.com/search?q={query}&count={num_results}&safesearch={safesearch}&mkt={mkt}&setlang={setlang}"
    if freshness:
        url += f"&freshness={freshness}"
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Referer": "https://www.bing.com/"
            }
        )
        page = await context.new_page()
        await page.goto(url, timeout=30000)
        # Attempt to bypass cookie/consent popups
        try:
            # Look for consent/cookie button and click if present
            consent_selectors = [
                'button[aria-label*="accept"]',
                'button[title*="Accept"]',
                'button[aria-label*="Agree"]',
                'button[title*="Agree"]',
                'button:has-text("Accept")',
                'button:has-text("Agree")'
            ]
            for selector in consent_selectors:
                if await page.query_selector(selector):
                    await page.click(selector)
                    break
        except Exception:
            pass
        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all('li', {'class': 'b_algo'})
    for item in items[:num_results]:
        title_elem = item.find('h2')
        link_elem = item.find('a')
        snippet_elem = item.find('p')
        if title_elem and link_elem and link_elem.has_attr('href'):
            title = title_elem.get_text(strip=True)
            link = link_elem['href']
            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
            results.append({
                "title": title,
                "link": link,
                "snippet": snippet
            })

    return results