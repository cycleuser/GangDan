"""
Capture generation screenshots with correct selectors.
KB checkboxes are dynamically loaded, button IDs differ per page.
"""
import os, time
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
SAVE = r'c:\Users\frede\Downloads\GangDan\test_screenshots'

def save(page, name, full=True):
    path = os.path.join(SAVE, name)
    page.screenshot(path=path, full_page=full)
    print(f"  [OK] {name}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
    page = ctx.new_page()

    # ============================================================
    # Static pages (EN + ZH)
    # ============================================================
    print("=== Static Pages ===")
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
        page.wait_for_timeout(2000)
        save(page, name)

    # ============================================================
    # Settings page (main page with settings open)
    # ============================================================
    print("\n=== Settings ===")
    page.goto(f"{BASE}/?lang=en", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(1500)
    # Try various settings triggers
    for sel in ['#settingsBtn', 'button:has-text("Settings")', 'a:has-text("Settings")', '.settings-btn', '[data-i18n="settings"]']:
        el = page.query_selector(sel)
        if el:
            el.click()
            page.wait_for_timeout(1000)
            break
    save(page, "11_settings_en.png")

    # ============================================================
    # Lecture Generation
    # ============================================================
    print("\n=== Lecture Generation ===")
    page.goto(f"{BASE}/learning/lecture?lang=en", wait_until="networkidle", timeout=15000)
    # Wait for KB list to load dynamically
    page.wait_for_timeout(3000)
    
    # Check numpy KB checkbox (dynamically loaded)
    kb_checked = False
    for sel in ['input[value="numpy"]', '#kbCheckList input[type="checkbox"]']:
        cbs = page.query_selector_all(sel)
        if cbs:
            cbs[0].check()
            kb_checked = True
            print(f"  Checked KB via: {sel} ({len(cbs)} found)")
            break
    if not kb_checked:
        # Try clicking by label text
        labels = page.query_selector_all('#kbCheckList label')
        for lbl in labels[:1]:
            lbl.click()
            kb_checked = True
            print(f"  Checked KB via label click")
            break
    
    # Fill topic
    page.fill("#topicInput", "Python array basics with NumPy")
    print("  Filled topic")
    save(page, "12_lecture_filled_en.png")
    
    # Click generate (startBtn for lecture)
    btn = page.query_selector("#startBtn")
    if btn:
        btn.click()
        print("  Clicked startBtn")
        page.wait_for_timeout(15000)  # 15s - should see phase indicator
        save(page, "13_lecture_generating_en.png")
        page.wait_for_timeout(45000)  # 45s more - should have content
        save(page, "14_lecture_result_en.png")
    else:
        print("  WARNING: startBtn not found!")

    # ============================================================
    # Exam Generation
    # ============================================================
    print("\n=== Exam Generation ===")
    page.goto(f"{BASE}/learning/exam?lang=en", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(3000)
    
    kb_checked = False
    for sel in ['input[value="numpy"]', '#kbCheckList input[type="checkbox"]']:
        cbs = page.query_selector_all(sel)
        if cbs:
            cbs[0].check()
            kb_checked = True
            print(f"  Checked KB via: {sel}")
            break
    if not kb_checked:
        labels = page.query_selector_all('#kbCheckList label')
        for lbl in labels[:1]:
            lbl.click()
            kb_checked = True
            print(f"  Checked KB via label")
            break
    
    page.fill("#topicInput", "Python array basics")
    print("  Filled topic")
    save(page, "15_exam_filled_en.png")
    
    btn = page.query_selector("#startBtn")
    if btn:
        btn.click()
        print("  Clicked startBtn")
        page.wait_for_timeout(15000)
        save(page, "16_exam_generating_en.png")
        page.wait_for_timeout(60000)
        save(page, "17_exam_result_en.png")
    else:
        print("  WARNING: startBtn not found!")

    # ============================================================
    # Question Generation
    # ============================================================
    print("\n=== Question Generation ===")
    page.goto(f"{BASE}/question?lang=en", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(3000)
    
    kb_checked = False
    for sel in ['input[value="numpy"]', '#kbCheckList input[type="checkbox"]']:
        cbs = page.query_selector_all(sel)
        if cbs:
            cbs[0].check()
            kb_checked = True
            print(f"  Checked KB via: {sel}")
            break
    if not kb_checked:
        labels = page.query_selector_all('#kbCheckList label')
        for lbl in labels[:1]:
            lbl.click()
            kb_checked = True
            print(f"  Checked KB via label")
            break
    
    page.fill("#topicInput", "array operations")
    print("  Filled topic")
    save(page, "18_question_filled_en.png")
    
    btn = page.query_selector("#generateBtn")
    if btn:
        btn.click()
        print("  Clicked generateBtn")
        page.wait_for_timeout(50000)  # 50s for question gen
        save(page, "19_question_result_en.png")
    else:
        print("  WARNING: generateBtn not found!")

    browser.close()
    print("\n=== ALL DONE ===")
