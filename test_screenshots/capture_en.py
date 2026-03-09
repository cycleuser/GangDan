"""Take English screenshots + run API functional tests."""
import sys, os, time, json

SAVE_DIR = r'c:\Users\frede\Downloads\GangDan\test_screenshots'
os.makedirs(SAVE_DIR, exist_ok=True)

from playwright.sync_api import sync_playwright

en_pages = [
    ('http://127.0.0.1:5000/question?lang=en',          '10_question_en.png'),
    ('http://127.0.0.1:5000/guide?lang=en',              '11_guide_en.png'),
    ('http://127.0.0.1:5000/research?lang=en',           '12_research_en.png'),
    ('http://127.0.0.1:5000/learning/lecture?lang=en',    '13_lecture_en.png'),
    ('http://127.0.0.1:5000/learning/exam?lang=en',       '14_exam_en.png'),
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()
    print("Browser launched OK (Edge)", flush=True)

    for url, filename in en_pages:
        print(f"Loading {url} ...", flush=True)
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1500)
        filepath = os.path.join(SAVE_DIR, filename)
        page.screenshot(path=filepath, full_page=True)
        size = os.path.getsize(filepath)
        print(f"  -> {filename}  size={size}  title={page.title()}", flush=True)

    browser.close()
    print("\nALL EN SCREENSHOTS DONE", flush=True)
