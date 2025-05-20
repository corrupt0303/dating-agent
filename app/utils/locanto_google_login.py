import asyncio
from playwright.async_api import async_playwright
import json

GOOGLE_EMAIL = "enteredafterdark@gmail.com"
GOOGLE_PASSWORD = "Pl@ywr1ght"
COOKIES_FILE = "locanto_cookies.json"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context()
        page = await context.new_page()
        print("[DEBUG] Navigating to Locanto login page...")
        await page.goto("https://www.locanto.co.za/g/my/?show=login", timeout=60000)
        # Wait for login form or input to appear
        print("[DEBUG] Waiting for login form or input...")
        try:
            await page.wait_for_selector('form, input[type="email"], input[type="text"]', timeout=10000)
        except Exception as e:
            print(f"[DEBUG] Login form/input not found: {e}")
        # Wait for Google sign-in iframe
        print("[DEBUG] Waiting for Google sign-in iframe...")
        try:
            await page.wait_for_selector('iframe[title="Sign in with Google Button"]', timeout=10000)
            iframe_elem = await page.query_selector('iframe[title="Sign in with Google Button"]')
            iframe = await iframe_elem.content_frame()
            print("[DEBUG] Found Google sign-in iframe. Attempting to click inside...")
            box = await iframe_elem.bounding_box()
            if box:
                await page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
            else:
                print("[DEBUG] Could not get bounding box for iframe.")
        except Exception as e:
            print(f"[DEBUG] Google sign-in iframe not found or could not click: {e}")
            html = await page.content()
            print('[DEBUG] Full page HTML follows:')
            print(html)
            await browser.close()
            return
        # Google login popup
        print("[DEBUG] Waiting for Google login popup...")
        popup = await context.wait_for_event("page")
        await popup.wait_for_load_state()
        print("[DEBUG] Filling Google email...")
        await popup.fill('input[type="email"]', GOOGLE_EMAIL)
        await popup.click('button:has-text("Next")')
        await popup.wait_for_timeout(2000)
        print("[DEBUG] Filling Google password...")
        await popup.fill('input[type="password"]', GOOGLE_PASSWORD)
        await popup.click('button:has-text("Next")')
        # Wait for popup to close
        await popup.wait_for_event("close")
        print("[DEBUG] Google login popup closed. Clicking Google sign-in iframe again...")
        # Click the Google sign-in iframe a second time
        await page.wait_for_timeout(2000)
        iframe_elem2 = await page.query_selector('iframe[title="Sign in with Google Button"]')
        box2 = await iframe_elem2.bounding_box()
        if box2:
            await page.mouse.click(box2['x'] + box2['width']/2, box2['y'] + box2['height']/2)
        else:
            print("[DEBUG] Could not get bounding box for iframe (second click).")
        # Wait for Google account selection dialog and select the account
        print("[DEBUG] Waiting for Google account selection dialog...")
        try:
            await page.wait_for_selector(f'text={GOOGLE_EMAIL}', timeout=10000)
            await page.click(f'text={GOOGLE_EMAIL}')
            print(f"[DEBUG] Selected Google account: {GOOGLE_EMAIL}")
        except Exception as e:
            print(f"[DEBUG] Could not select Google account: {e}")
        # Wait for Locanto to load after Google login
        print("[DEBUG] Waiting for Locanto to load after Google login...")
        await page.wait_for_load_state('networkidle', timeout=60000)
        await page.wait_for_timeout(5000)
        # Save cookies
        cookies = await context.cookies()
        with open(COOKIES_FILE, "w") as f:
            json.dump(cookies, f, indent=2)
        print(f"[DEBUG] Cookies saved to {COOKIES_FILE}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main()) 