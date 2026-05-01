"""Screenshot capture script for GangDan testing - Playwright + Edge."""
import sys
import os
import time

SAVE_DIR = r'c:\Users\frede\Downloads\GangDan\test_screenshots'
os.makedirs(SAVE_DIR, exist_ok=True)

from playwright.sync_api import sync_playwright

pages = [
    ('http://127.0.0.1:5000/',                       '01_main_page.png'),
    ('http://127.0.0.1:5000/question',                '02_question_en.png'),
    ('http://127.0.0.1:5000/guide',                   '03_guide_en.png'),
    ('http://127.0.0.1:5000/research',                '04_research_en.png'),
    ('http://127.0.0.1:5000/learning/lecture',         '05_lecture_en.png'),
    ('http://127.0.0.1:5000/learning/exam',            '06_exam_en.png'),
    ('http://127.0.0.1:5000/learning/lecture?lang=zh', '07_lecture_zh.png'),
    ('http://127.0.0.1:5000/learning/exam?lang=zh',    '08_exam_zh.png'),
    ('http://127.0.0.1:5000/question?lang=zh',         '09_question_zh.png'),
]

with sync_playwright() as p:
    # Use locally installed Edge instead of playwright's bundled chromium
    browser = p.chromium.launch(headless=True, channel="msedge")
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()
    print("Browser launched OK (Edge)", flush=True)

    for url, filename in pages:
        print(f"Loading {url} ...", flush=True)
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1500)
        filepath = os.path.join(SAVE_DIR, filename)
        page.screenshot(path=filepath, full_page=True)
        size = os.path.getsize(filepath)
        print(f"  -> {filename}  size={size}  title={page.title()}", flush=True)

    browser.close()
    print("\nALL SCREENSHOTS DONE", flush=True)
