"""Screenshot capture script for GangDan testing - using Edge."""
import sys
import os
import time

SAVE_DIR = r'c:\Users\frede\Downloads\GangDan\test_screenshots'
os.makedirs(SAVE_DIR, exist_ok=True)

print(f"Save dir: {SAVE_DIR}", flush=True)

from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

print("Selenium imported OK", flush=True)

opts = EdgeOptions()
opts.add_argument('--headless=new')
opts.add_argument('--window-size=1400,900')
opts.add_argument('--force-device-scale-factor=1')
opts.add_argument('--disable-gpu')
opts.add_argument('--no-sandbox')
opts.binary_location = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

print("Creating Edge driver...", flush=True)
driver = webdriver.Edge(options=opts)
print("Edge driver created OK", flush=True)

driver.implicitly_wait(3)

pages = [
    ('http://127.0.0.1:5000/', '01_main_page.png'),
    ('http://127.0.0.1:5000/question', '02_question_en.png'),
    ('http://127.0.0.1:5000/guide', '03_guide_en.png'),
    ('http://127.0.0.1:5000/research', '04_research_en.png'),
    ('http://127.0.0.1:5000/learning/lecture', '05_lecture_en.png'),
    ('http://127.0.0.1:5000/learning/exam', '06_exam_en.png'),
    ('http://127.0.0.1:5000/learning/lecture?lang=zh', '07_lecture_zh.png'),
    ('http://127.0.0.1:5000/learning/exam?lang=zh', '08_exam_zh.png'),
    ('http://127.0.0.1:5000/question?lang=zh', '09_question_zh.png'),
]

try:
    for url, filename in pages:
        print(f"Loading {url} ...", flush=True)
        driver.get(url)
        time.sleep(2)
        filepath = os.path.join(SAVE_DIR, filename)
        result = driver.save_screenshot(filepath)
        size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        print(f"  -> {filename}  saved={result}  size={size}  title={driver.title}", flush=True)

    print("\nALL SCREENSHOTS DONE", flush=True)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"Error: {e}", flush=True)
finally:
    driver.quit()
    print("Driver closed", flush=True)
