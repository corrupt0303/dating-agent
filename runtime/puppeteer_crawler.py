import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def crawl_page(url, wait_selector=None, timeout=30000, user_agent=None, extra_headers=None, extract_text=True):
    """
    Fetches and optionally extracts readable content from any web page using Playwright (Puppeteer-like).
    If the URL is a Locanto listing, returns structured data: title, location, category, description, contact_info, listing_url, images.
    Args:
        url (str): The URL to crawl.
        wait_selector (str, optional): CSS selector to wait for before extracting content.
        timeout (int): Max timeout for page load (ms).
        user_agent (str, optional): Custom user agent string.
        extra_headers (dict, optional): Additional HTTP headers.
        extract_text (bool): If True, returns visible text, else returns raw HTML.
    Returns:
        str or dict: Extracted text/HTML or structured dict for Locanto listings.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context_args = {}
        if user_agent:
            context_args['user_agent'] = user_agent
        if extra_headers:
            context_args['extra_http_headers'] = extra_headers
        context = await browser.new_context(**context_args)
        page = await context.new_page()
        await page.goto(url, timeout=timeout)
        if wait_selector:
            await page.wait_for_selector(wait_selector, timeout=timeout)
        # Attempt to bypass cookie/consent popups
        try:
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

    # --- Locanto structured extraction ---
    from urllib.parse import urlparse, parse_qs
    import re
    if 'locanto.co.za' in url:
        soup = BeautifulSoup(html, 'html.parser')
        # Detect if this is a tag/category/search page (listings) or detail page
        is_listing_collection = False
        # Locanto listing links: broaden match to '/ID_' or '/\d+.html' or '/\d+/'
        # Locanto: Extract all <article class="posting_listing"> as listings
        articles = soup.find_all('article', class_='posting_listing')
        if articles:
            from urllib.parse import urljoin
            listings = []
            for art in articles:
                # Listing URL
                a = art.find('a', class_='posting_listing__title')
                if not a or not a.get('href'): continue
                listing_url = urljoin(url, a['href'])
                # Title
                title_div = a.find('div', class_='h3')
                title = title_div.get_text(strip=True) if title_div else a.get_text(strip=True)
                # Location
                loc_span = art.find('span', class_='posting_listing__city')
                location = loc_span.get_text(strip=True) if loc_span else None
                # Age
                age_span = art.find('span', class_='posting_listing__age')
                age = age_span.get_text(strip=True) if age_span else None
                # Category
                cat_span = art.find('span', class_='posting_listing__category')
                category = cat_span.get_text(strip=True) if cat_span else None
                # Description snippet
                desc_div = art.find('div', class_='posting_listing__description')
                description = desc_div.get_text(strip=True) if desc_div else None
                listings.append({
                    'listing_url': listing_url,
                    'title': title,
                    'location': location,
                    'age': age,
                    'category': category,
                    'description_snippet': description
                })
            # For each listing, crawl and extract full details
            import asyncio
            async def extract_all():
                results = []
                sem = asyncio.Semaphore(3)
                async def fetch_listing(listing):
                    async with sem:
                        try:
                            details = await crawl_page(listing['listing_url'], extract_text=True)
                            listing.update({'details': details})
                            return listing
                        except Exception:
                            listing['details'] = {'error': 'Failed to extract'}
                            return listing
                tasks = [fetch_listing(l) for l in listings]
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    results.append(result)
                return results
            return await extract_all()
        # Fallback: previous logic
        # DEBUG: Print all anchor hrefs and their text
        print('DEBUG: All anchors (href, text) on page:')
        all_anchors = [(a['href'], a.get_text(strip=True)) for a in soup.find_all('a', href=True)]
        for href, text in all_anchors[:50]:  # print first 50 only
            print(f"{href} | {text}")
        listing_links = []
        print('DEBUG: Matched listing links:')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if re.search(r'(/ID_\d+/|/ID_\d+\.html|/\d+\.html|/\d+/)', href):
                abs_url = urljoin(url, href)
                listing_links.append(abs_url)
                print(abs_url)
        listing_links = list(dict.fromkeys(listing_links))
        if listing_links:
            is_listing_collection = True
        if is_listing_collection:
            import asyncio
            async def extract_all():
                results = []
                sem = asyncio.Semaphore(3)
                async def fetch_listing(listing_url):
                    async with sem:
                        try:
                            return await crawl_page(listing_url, extract_text=True)
                        except Exception:
                            return {'listing_url': listing_url, 'error': 'Failed to extract'}
                tasks = [fetch_listing(l) for l in listing_links]
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    results.append(result)
                return results
            return await extract_all()
        # --- Otherwise, treat as detail page ---
        # Title
        title_tag = soup.find('h1') or soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else None
        # Location
        location = None
        loc_tag = soup.find('span', class_=re.compile(r'location|area', re.I))
        if loc_tag:
            location = loc_tag.get_text(strip=True)
        # Category
        category = None
        breadcrumb = soup.find('ul', class_=re.compile(r'breadcrumb', re.I))
        if breadcrumb:
            cats = [li.get_text(strip=True) for li in breadcrumb.find_all('li')]
            if cats:
                category = ' > '.join(cats)
        # Description
        desc_tag = soup.find('div', class_=re.compile(r'description|adDesc|text', re.I))
        description = desc_tag.get_text(strip=True) if desc_tag else None
        # Contact info (look for phone/email in visible text)
        contact_info = None
        body_text = soup.get_text(separator=' ', strip=True)
        phone_match = re.search(r'(\+?\d[\d\s\-]{7,}\d)', body_text)
        email_match = re.search(r'([\w\.-]+@[\w\.-]+)', body_text)
        if phone_match:
            contact_info = phone_match.group(1)
        elif email_match:
            contact_info = email_match.group(1)
        # Images
        images = []
        for img in soup.find_all('img'):
            src = img.get('src')
            if src and ('locanto' in src or src.startswith('http')) and not src.endswith('.svg'):
                images.append(src)
        images = list(dict.fromkeys(images))
        return {
            'title': title,
            'location': location,
            'category': category,
            'description': description,
            'contact_info': contact_info,
            'listing_url': url,
            'images': images
        }
    # --- Fallback: plain text extraction ---
    if extract_text:
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()
        text = ' '.join(soup.stripped_strings)
        return text
    else:
        return html

# Example usage:
# asyncio.run(crawl_page('https://example.com'))
