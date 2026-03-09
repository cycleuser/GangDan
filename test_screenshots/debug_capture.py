"""
Debug capture: check JS state and manually trigger generation.
"""
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
    
    # Capture console messages
    page.on("console", lambda msg: print(f"  [CONSOLE {msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: print(f"  [PAGE ERROR] {err}"))
    
    print("=== Lecture Debug ===")
    page.goto(f"{BASE}/learning/lecture?lang=en", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(5000)
    
    # Check what's in the KB list
    kb_html = page.evaluate('document.getElementById("kbCheckList").innerHTML')
    print(f"  KB list HTML length: {len(kb_html)}")
    print(f"  KB list preview: {kb_html[:200]}")
    
    # Inject KB + topic
    page.evaluate('''() => {
        // Ensure the Set exists and has numpy
        if (!window._learningSelectedKbs) window._learningSelectedKbs = new Set();
        window._learningSelectedKbs.add("numpy");
        
        // Also update the local ref in lecture.js scope
        // The variable `selectedKbs` in lecture.js is a reference to the same Set
        
        // Set the topic
        document.getElementById("topicInput").value = "Python array basics";
        
        // Update KB display
        const container = document.getElementById("kbCheckList");
        container.innerHTML = '<label class="kb-check-item"><input type="checkbox" value="numpy" checked><span>NumPy (3)</span></label>';
    }''')
    
    # Verify state
    size = page.evaluate('window._learningSelectedKbs.size')
    has_numpy = page.evaluate('window._learningSelectedKbs.has("numpy")')
    print(f"  Selected KBs size: {size}, has numpy: {has_numpy}")
    
    page.screenshot(path=os.path.join(SAVE, "debug_lecture_before.png"), full_page=True)
    
    # Click the button
    page.click("#startBtn")
    print("  Clicked startBtn")
    
    page.wait_for_timeout(5000)
    
    # Check content area
    content_html = page.evaluate('document.getElementById("lectureContent").innerHTML')
    status_html = page.evaluate('document.getElementById("statusMsg").innerHTML')
    phase_visible = page.evaluate('document.getElementById("phaseSection").style.display')
    print(f"  Content HTML length: {len(content_html)}")
    print(f"  Status msg: {status_html[:200] if status_html else 'empty'}")
    print(f"  Phase section display: {phase_visible}")
    
    page.screenshot(path=os.path.join(SAVE, "debug_lecture_5s.png"), full_page=True)
    print("  [OK] debug_lecture_5s.png")
    
    page.wait_for_timeout(25000)
    
    content_html = page.evaluate('document.getElementById("lectureContent").innerHTML')
    print(f"  Content HTML length after 30s: {len(content_html)}")
    print(f"  Content preview: {content_html[:300]}")
    
    page.screenshot(path=os.path.join(SAVE, "debug_lecture_30s.png"), full_page=True)
    print("  [OK] debug_lecture_30s.png")
    
    browser.close()
    print("\nDone")
