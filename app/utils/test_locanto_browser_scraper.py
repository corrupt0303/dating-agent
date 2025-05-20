import asyncio
from locanto_browser_scraper import LocantoBrowserScraper
import urllib.parse
import re

PROXY_PREFIX = "https://please.untaint.us/?url="

def clean_url(u):
    if not u:
        return None
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

async def main():
    print("Testing LocantoBrowserScraper with Playwright (authenticated)...")
    scraper = LocantoBrowserScraper(cookies_path="locanto_cookies.json")
    try:
        await scraper.start()
        query = "single white girl"
        location = "South Africa"
        print(f"\nSearching for '{query}' in '{location}' (max_pages=1)...")
        listings = await scraper.search_listings(query, location, max_pages=1)
        print(f"Found {len(listings)} listings.")
        if listings and isinstance(listings[0], dict) and 'error' in listings[0]:
            print(f"[ERROR] {listings[0]['error']}")
            return
        if not listings:
            print("No listings found to test details.")
            return
        for i, listing in enumerate(listings[:5], 1):
            print(f"\nListing {i}:")
            for k, v in listing.items():
                print(f"  {k}: {v}")
            print(f"  [DEBUG] Proxied URL: {listing.get('url')}")
        if listings:
            print("\nTesting get_listing_details on the first result...")
            clean_listing_url = clean_url(listings[0]['url'])
            if clean_listing_url and not clean_listing_url.startswith(PROXY_PREFIX):
                if clean_listing_url.startswith("/"):
                    clean_listing_url = "https://www.locanto.co.za" + clean_listing_url
                if clean_listing_url.startswith("https://www.locanto.co.za"):
                    clean_listing_url = PROXY_PREFIX + clean_listing_url
                elif clean_listing_url.startswith('http'):
                    clean_listing_url = PROXY_PREFIX + clean_listing_url
            print(f"  [DEBUG] Cleaned URL for details: {clean_listing_url}")
            details = await scraper.get_listing_details(clean_listing_url)
            print("\nDetails for first listing:")
            for k, v in details.items():
                if isinstance(v, list):
                    print(f"  {k}: {len(v)} images")
                else:
                    print(f"  {k}: {v}")

        # --- Test direct URL search (new feature) ---
        direct_url = "https://www.locanto.co.za/randburg/Personals/P/"
        print(f"\nTesting direct URL search: {direct_url}")
        listings_url = await scraper.search_listings(url=direct_url, max_pages=1)
        print(f"Found {len(listings_url)} listings from direct URL.")
        if listings_url and isinstance(listings_url[0], dict) and 'error' in listings_url[0]:
            print(f"[ERROR] {listings_url[0]['error']}")
        for i, listing in enumerate(listings_url[:5], 1):
            print(f"\n[URL] Listing {i}:")
            for k, v in listing.items():
                print(f"  {k}: {v}")
            print(f"  [DEBUG] Proxied URL: {listing.get('url')}")
        if listings_url:
            print("\nTesting get_listing_details on the first result from direct URL...")
            clean_listing_url2 = clean_url(listings_url[0]['url'])
            if clean_listing_url2 and not clean_listing_url2.startswith(PROXY_PREFIX):
                if clean_listing_url2.startswith("/"):
                    clean_listing_url2 = "https://www.locanto.co.za" + clean_listing_url2
                if clean_listing_url2.startswith("https://www.locanto.co.za"):
                    clean_listing_url2 = PROXY_PREFIX + clean_listing_url2
                elif clean_listing_url2.startswith('http'):
                    clean_listing_url2 = PROXY_PREFIX + clean_listing_url2
            print(f"  [DEBUG] Cleaned URL for details: {clean_listing_url2}")
            details2 = await scraper.get_listing_details(clean_listing_url2)
            print("\nDetails for first listing from direct URL:")
            for k, v in details2.items():
                if isinstance(v, list):
                    print(f"  {k}: {len(v)} images")
                else:
                    print(f"  {k}: {v}")

        # --- Test another direct URL (Women-Seeking-Men in Roodepoort) ---
        direct_url2 = "https://www.locanto.co.za/roodepoort/Women-Seeking-Men/202/"
        print(f"\nTesting direct URL search: {direct_url2}")
        listings_url2 = await scraper.search_listings(url=direct_url2, max_pages=1)
        print(f"Found {len(listings_url2)} listings from direct URL.")
        if listings_url2 and isinstance(listings_url2[0], dict) and 'error' in listings_url2[0]:
            print(f"[ERROR] {listings_url2[0]['error']}")
        for i, listing in enumerate(listings_url2[:5], 1):
            print(f"\n[URL2] Listing {i}:")
            for k, v in listing.items():
                print(f"  {k}: {v}")
            print(f"  [DEBUG] Proxied URL: {listing.get('url')}")
        if listings_url2:
            print("\nTesting get_listing_details on the first result from direct URL 2...")
            clean_listing_url3 = clean_url(listings_url2[0]['url'])
            if clean_listing_url3 and not clean_listing_url3.startswith(PROXY_PREFIX):
                if clean_listing_url3.startswith("/"):
                    clean_listing_url3 = "https://www.locanto.co.za" + clean_listing_url3
                if clean_listing_url3.startswith("https://www.locanto.co.za"):
                    clean_listing_url3 = PROXY_PREFIX + clean_listing_url3
                elif clean_listing_url3.startswith('http'):
                    clean_listing_url3 = PROXY_PREFIX + clean_listing_url3
            print(f"  [DEBUG] Cleaned URL for details: {clean_listing_url3}")
            details3 = await scraper.get_listing_details(clean_listing_url3)
            print("\nDetails for first listing from direct URL 2:")
            for k, v in details3.items():
                if isinstance(v, list):
                    print(f"  {k}: {len(v)} images")
                else:
                    print(f"  {k}: {v}")
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        await scraper.close()

if __name__ == "__main__":
    asyncio.run(main()) 