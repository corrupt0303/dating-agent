import asyncio
from runtime.locanto_browser_scraper import LocantoBrowserScraper

async def main():
    scraper = LocantoBrowserScraper(cookies_path='locanto_cookies.json')
    await scraper.start()
    # Use the proxy and search for 'single white girl' in Randburg
    search_url = 'https://please.untaint.us/?url=https://www.locanto.co.za/g/q/?query=single+white+girl&location=Randburg'
    await scraper.recursive_map_site(start_url=search_url, max_depth=1, save_html=True)
    await scraper.close()

if __name__ == '__main__':
    asyncio.run(main()) 