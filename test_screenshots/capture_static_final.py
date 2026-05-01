"""Quick re-capture of static pages after JS fix."""
import os
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:5000"
SAVE = r'c:\Users\frede\Downloads\GangDan\test_screenshots'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
    page = ctx.new_page()
    for url, name in [
        (f"{BASE}/", "01_main_page_en.png"),
        (f"{BASE}/question?lang=en", "02_question_en.png"),
        (f"{BASE}/guide?lang=en", "03_guide_en.png"),
        (f"{BASE}/research?lang=en", "04_research_en.png"),
        (f"{BASE}/learning/lecture?lang=en", "05_lecture_en.png"),
        (f"{BASE}/learning/exam?lang=en", "06_exam_en.png"),
        (f"{BASE}/?lang=zh", "07_main_page_zh.png"),
        (f"{BASE}/question?lang=zh", "08_question_zh.png"),
        (f"{BASE}/learning/lecture?lang=zh", "09_lecture_zh.png"),
        (f"{BASE}/learning/exam?lang=zh", "10_exam_zh.png"),
    ]:
        page.goto(url, wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.join(SAVE, name), full_page=True)
        print(f"  [OK] {name}")
    
    # Settings
    page.goto(f"{BASE}/?lang=en", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(1500)
    for sel in ['#settingsBtn', 'button:has-text("Settings")', '.settings-btn', '[onclick*="toggleSettings"]']:
        el = page.query_selector(sel)
        if el:
            el.click()
            page.wait_for_timeout(1000)
            print(f"  Opened settings via: {sel}")
            break
    page.screenshot(path=os.path.join(SAVE, "11_settings_en.png"), full_page=True)
    print("  [OK] 11_settings_en.png")
    browser.close()
    print("Done")
