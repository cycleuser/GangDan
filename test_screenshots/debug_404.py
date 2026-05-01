"""Quick debug: check which resources 404 on the lecture page."""
import os
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    
    failed_requests = []
    page.on("requestfailed", lambda req: failed_requests.append(f"FAIL: {req.url} - {req.failure}"))
    
    responses_404 = []
    def on_response(resp):
        if resp.status >= 400:
            responses_404.append(f"HTTP {resp.status}: {resp.url}")
    page.on("response", on_response)
    
    page.on("console", lambda msg: print(f"  [CONSOLE {msg.type}] {msg.text}") if msg.type in ("error","warning") else None)
    page.on("pageerror", lambda err: print(f"  [PAGE ERROR] {err}"))
    
    page.goto(f"{BASE}/learning/lecture?lang=en", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)
    
    print("=== Failed Requests ===")
    for f in failed_requests:
        print(f"  {f}")
    print(f"=== HTTP 4xx/5xx Responses ({len(responses_404)}) ===")
    for r in responses_404:
        print(f"  {r}")
    
    # Also check question page for comparison
    failed_requests.clear()
    responses_404.clear()
    page.goto(f"{BASE}/question?lang=en", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)
    
    print("\n=== Question page - Failed Requests ===")
    for f in failed_requests:
        print(f"  {f}")
    print(f"=== Question page - HTTP 4xx/5xx ({len(responses_404)}) ===")
    for r in responses_404:
        print(f"  {r}")
    
    browser.close()
