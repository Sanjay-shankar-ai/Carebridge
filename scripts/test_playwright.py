"""
CareBridge Demo Quick Test
Run with: python scripts/test_playwright.py
"""
import sys
print("Starting Playwright test...", flush=True)

try:
    from playwright.sync_api import sync_playwright
    print("Playwright imported OK", flush=True)
    
    with sync_playwright() as pw:
        print("sync_playwright context OK", flush=True)
        browser = pw.chromium.launch(headless=False, args=["--no-sandbox"])
        print("Browser launched", flush=True)
        
        page = browser.new_page()
        print("Page created", flush=True)
        
        page.goto("http://localhost:3000/login", wait_until="domcontentloaded")
        print(f"Navigated to login: {page.title()}", flush=True)
        
        import time
        time.sleep(2)
        
        page.screenshot(path="c:/CareBridge/demo_assets/screenshots/test_login_page.png")
        print("Screenshot saved!", flush=True)
        
        browser.close()
        print("Browser closed. Test PASSED.", flush=True)
        
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)
