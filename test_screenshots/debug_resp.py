"""Check all responses for 404 and verify no JS errors."""
import os
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:5000"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    all_resp = []
    page.on("response", lambda r: all_resp.append((r.status, r.url)))
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.goto(f"{BASE}/learning/lecture?lang=en", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(5000)
    print("=== All Responses ===")
    for status, url in all_resp:
        marker = " <-- 404!" if status == 404 else ""
        if status >= 400 or "favicon" in url:
            print(f"  {status} {url}{marker}")
    print(f"\n=== JS Errors ({len(errors)}) ===")
    for e in errors:
        print(f"  {e}")
    # Check KB loaded
    kb_html = page.evaluate('document.getElementById("kbCheckList").innerHTML')
    has_cb = 'type="checkbox"' in kb_html
    print(f"\n=== KB loaded: {has_cb}, HTML length: {len(kb_html)} ===")
    if has_cb:
        print(f"  Preview: {kb_html[:300]}")
    browser.close()
