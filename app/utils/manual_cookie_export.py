import asyncio
from playwright.async_api import async_playwright
import json

COOKIES_FILE = "locanto_cookies.json"

IOS_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
IOS_VIEWPORT = {"width": 430, "height": 932}
IOS_DEVICE_SCALE_FACTOR = 3
IOS_IS_MOBILE = True
IOS_HAS_TOUCH = True
IOS_LANGUAGE = "en-US"
IOS_LANGUAGES = ["en-US", "en"]
IOS_TIMEZONE = "Africa/Johannesburg"

FINGERPRINT_SCRIPT = """
Object.defineProperty(navigator, 'platform', {get: () => 'iPhone'});
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 5});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'language', {get: () => 'en-US'});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 4});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 4});
Object.defineProperty(navigator, 'vendor', {get: () => 'Apple Computer, Inc.'});
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
window.screen.orientation = {type: 'portrait-primary', angle: 0};
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context(
            user_agent=IOS_USER_AGENT,
            viewport=IOS_VIEWPORT,
            device_scale_factor=IOS_DEVICE_SCALE_FACTOR,
            is_mobile=IOS_IS_MOBILE,
            has_touch=IOS_HAS_TOUCH,
            locale=IOS_LANGUAGE,
            timezone_id=IOS_TIMEZONE,
        )
        await context.add_init_script(FINGERPRINT_SCRIPT)
        page = await context.new_page()
        print("[MANUAL] Navigating to Locanto via web proxy. Please log in and solve any Cloudflare challenge in the browser window.")
        await page.goto("https://please.untaint.us/?url=locanto.co.za", timeout=60000)
        input("[MANUAL] When you are fully logged in and can browse Locanto (via the proxy), press Enter here to save cookies...")
        cookies = await context.cookies()
        with open(COOKIES_FILE, "w") as f:
            json.dump(cookies, f, indent=2)
        print(f"[MANUAL] Cookies saved to {COOKIES_FILE}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main()) 