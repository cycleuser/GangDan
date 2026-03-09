"""
Capture all feature screenshots using Playwright.
Covers: main page, question, guide, research, lecture, exam (EN + ZH),
plus generation results for lecture and exam.
"""
import os, json, time
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
SAVE = r'c:\Users\frede\Downloads\GangDan\test_screenshots'

def screenshot(page, url, filename, wait_ms=2000):
    path = os.path.join(SAVE, filename)
    page.goto(url, wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(wait_ms)
    page.screenshot(path=path, full_page=True)
    print(f"  [OK] {filename} ({url})")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
    page = ctx.new_page()

    # ---- English Pages ----
    print("=== English Pages ===")
    screenshot(page, f"{BASE}/", "01_main_page_en.png")
    screenshot(page, f"{BASE}/question?lang=en", "02_question_en.png")
    screenshot(page, f"{BASE}/guide?lang=en", "03_guide_en.png")
    screenshot(page, f"{BASE}/research?lang=en", "04_research_en.png")
    screenshot(page, f"{BASE}/learning/lecture?lang=en", "05_lecture_en.png")
    screenshot(page, f"{BASE}/learning/exam?lang=en", "06_exam_en.png")

    # ---- Chinese Pages ----
    print("\n=== Chinese Pages ===")
    screenshot(page, f"{BASE}/?lang=zh", "07_main_page_zh.png")
    screenshot(page, f"{BASE}/question?lang=zh", "08_question_zh.png")
    screenshot(page, f"{BASE}/learning/lecture?lang=zh", "09_lecture_zh.png")
    screenshot(page, f"{BASE}/learning/exam?lang=zh", "10_exam_zh.png")

    # ---- Lecture Generation (trigger + wait for content) ----
    print("\n=== Lecture Generation ===")
    page.goto(f"{BASE}/learning/lecture?lang=en", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(1500)
    # Select numpy KB
    cb = page.query_selector('input[value="numpy"]')
    if cb:
        cb.check()
        print("  Checked numpy KB")
    # Type topic
    topic_input = page.query_selector('input[name="topic"], input#topic, input[placeholder*="topic"], input[placeholder*="Topic"]')
    if not topic_input:
        topic_input = page.query_selector('input[type="text"]')
    if topic_input:
        topic_input.fill("Python array basics")
        print("  Filled topic")
    page.screenshot(path=os.path.join(SAVE, "11_lecture_filled_en.png"), full_page=True)
    print("  [OK] 11_lecture_filled_en.png")

    # Click generate
    gen_btn = page.query_selector('button#generateBtn, button:has-text("Generate"), button:has-text("generate")')
    if gen_btn:
        gen_btn.click()
        print("  Clicked generate")
        # Wait for content to appear (up to 60s)
        try:
            page.wait_for_selector('.phase-indicator, .content-area, #lectureContent, .lecture-content, [class*="content"]', timeout=10000)
        except:
            pass
        page.wait_for_timeout(30000)  # Wait 30s for generation
        page.screenshot(path=os.path.join(SAVE, "12_lecture_generating_en.png"), full_page=True)
        print("  [OK] 12_lecture_generating_en.png")
        page.wait_for_timeout(30000)  # Wait another 30s
        page.screenshot(path=os.path.join(SAVE, "13_lecture_result_en.png"), full_page=True)
        print("  [OK] 13_lecture_result_en.png")

    # ---- Exam Generation ----
    print("\n=== Exam Generation ===")
    page.goto(f"{BASE}/learning/exam?lang=en", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(1500)
    cb = page.query_selector('input[value="numpy"]')
    if cb:
        cb.check()
        print("  Checked numpy KB")
    topic_input = page.query_selector('input[name="topic"], input#topic, input[placeholder*="topic"], input[placeholder*="Topic"]')
    if not topic_input:
        topic_input = page.query_selector('input[type="text"]')
    if topic_input:
        topic_input.fill("Python array basics")
        print("  Filled topic")
    page.screenshot(path=os.path.join(SAVE, "14_exam_filled_en.png"), full_page=True)
    print("  [OK] 14_exam_filled_en.png")

    gen_btn = page.query_selector('button#generateBtn, button:has-text("Generate"), button:has-text("generate")')
    if gen_btn:
        gen_btn.click()
        print("  Clicked generate")
        try:
            page.wait_for_selector('.phase-indicator, .content-area, #examContent, .exam-content, [class*="content"]', timeout=10000)
        except:
            pass
        page.wait_for_timeout(30000)
        page.screenshot(path=os.path.join(SAVE, "15_exam_generating_en.png"), full_page=True)
        print("  [OK] 15_exam_generating_en.png")
        page.wait_for_timeout(45000)
        page.screenshot(path=os.path.join(SAVE, "16_exam_result_en.png"), full_page=True)
        print("  [OK] 16_exam_result_en.png")

    # ---- Question Generation ----
    print("\n=== Question Generation ===")
    page.goto(f"{BASE}/question?lang=en", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(1500)
    cb = page.query_selector('input[value="numpy"]')
    if cb:
        cb.check()
        print("  Checked numpy KB")
    topic_input = page.query_selector('input[name="topic"], input#topic, input[placeholder*="topic"], input[placeholder*="Topic"]')
    if not topic_input:
        topic_input = page.query_selector('input[type="text"]')
    if topic_input:
        topic_input.fill("array operations")
        print("  Filled topic")
    page.screenshot(path=os.path.join(SAVE, "17_question_filled_en.png"), full_page=True)
    print("  [OK] 17_question_filled_en.png")

    gen_btn = page.query_selector('button#generateBtn, button:has-text("Generate"), button:has-text("generate")')
    if gen_btn:
        gen_btn.click()
        print("  Clicked generate")
        page.wait_for_timeout(45000)
        page.screenshot(path=os.path.join(SAVE, "18_question_result_en.png"), full_page=True)
        print("  [OK] 18_question_result_en.png")

    # ---- Settings page (main page has settings) ----
    print("\n=== Settings / Config ===")
    page.goto(f"{BASE}/?lang=en", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(2000)
    # Try to open settings panel
    settings_btn = page.query_selector('button:has-text("Settings"), button:has-text("settings"), a:has-text("Settings"), #settingsBtn, [onclick*="settings"]')
    if settings_btn:
        settings_btn.click()
        page.wait_for_timeout(1500)
    page.screenshot(path=os.path.join(SAVE, "19_settings_en.png"), full_page=True)
    print("  [OK] 19_settings_en.png")

    browser.close()
    print("\n=== ALL SCREENSHOTS CAPTURED ===")
