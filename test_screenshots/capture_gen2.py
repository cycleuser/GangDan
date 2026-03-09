"""
Capture generation screenshots with proper KB loading wait.
Uses page.evaluate to ensure KB checkboxes are loaded and checked.
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

def wait_and_check_kb(page, kb_name="numpy", timeout=15000):
    """Wait for KB checkboxes to load, then check the target KB."""
    try:
        # Wait for checkbox inputs to appear inside kbCheckList
        page.wait_for_selector('#kbCheckList input[type="checkbox"]', timeout=timeout)
        page.wait_for_timeout(500)
        
        # Try to check by value
        cb = page.query_selector(f'input[value="{kb_name}"]')
        if cb:
            cb.check()
            print(f"  Checked {kb_name} KB")
            return True
        
        # Fallback: check first available
        cbs = page.query_selector_all('#kbCheckList input[type="checkbox"]')
        if cbs:
            cbs[0].check()
            val = cbs[0].get_attribute("value")
            print(f"  Checked first KB: {val}")
            return True
    except Exception as e:
        print(f"  KB load timeout: {e}")
    
    # Last resort: inject via JS
    try:
        page.evaluate('''() => {
            const container = document.getElementById("kbCheckList");
            if (container) {
                container.innerHTML = `
                    <label class="kb-check-item">
                        <input type="checkbox" value="numpy" checked
                            onchange="toggleKbCommon(this, window._learningSelectedKbs)">
                        <span>NumPy <small style="color:var(--text-muted)">(3)</small></span>
                    </label>`;
                if (window._learningSelectedKbs) window._learningSelectedKbs.add("numpy");
            }
        }''')
        print("  Injected numpy KB via JS")
        return True
    except Exception as e:
        print(f"  JS inject failed: {e}")
        return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
    page = ctx.new_page()

    # ============================================================
    # Lecture Generation
    # ============================================================
    print("=== Lecture Generation ===")
    page.goto(f"{BASE}/learning/lecture?lang=en", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    
    wait_and_check_kb(page, "numpy")
    page.fill("#topicInput", "Python array basics with NumPy")
    print("  Filled topic")
    page.wait_for_timeout(500)
    save(page, "12_lecture_filled_en.png")
    
    # Click generate
    btn = page.query_selector("#startBtn")
    if btn:
        btn.click()
        print("  Clicked Generate Lecture")
        # Wait for phase indicator to appear
        try:
            page.wait_for_selector('#phaseSection', state='visible', timeout=10000)
        except:
            pass
        page.wait_for_timeout(20000)  # 20s into generation
        save(page, "13_lecture_generating_en.png")
        page.wait_for_timeout(40000)  # 40s more
        save(page, "14_lecture_result_en.png")
    else:
        print("  WARNING: startBtn not found")

    # ============================================================
    # Exam Generation
    # ============================================================
    print("\n=== Exam Generation ===")
    page.goto(f"{BASE}/learning/exam?lang=en", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    
    wait_and_check_kb(page, "numpy")
    page.fill("#topicInput", "Python array basics")
    # Set difficulty to easy
    sel = page.query_selector("#difficultySelect")
    if sel:
        page.select_option("#difficultySelect", "easy")
        print("  Set difficulty: easy")
    print("  Filled topic")
    page.wait_for_timeout(500)
    save(page, "15_exam_filled_en.png")
    
    btn = page.query_selector("#startBtn")
    if btn:
        btn.click()
        print("  Clicked Generate Exam")
        try:
            page.wait_for_selector('#phaseSection', state='visible', timeout=10000)
        except:
            pass
        page.wait_for_timeout(20000)
        save(page, "16_exam_generating_en.png")
        page.wait_for_timeout(60000)
        save(page, "17_exam_result_en.png")
    else:
        print("  WARNING: startBtn not found")

    # ============================================================
    # Question Generation
    # ============================================================
    print("\n=== Question Generation ===")
    page.goto(f"{BASE}/question?lang=en", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    
    wait_and_check_kb(page, "numpy")
    page.fill("#topicInput", "array operations")
    print("  Filled topic")
    page.wait_for_timeout(500)
    save(page, "18_question_filled_en.png")
    
    btn = page.query_selector("#generateBtn")
    if btn:
        btn.click()
        print("  Clicked Generate Questions")
        page.wait_for_timeout(50000)
        save(page, "19_question_result_en.png")
    else:
        print("  WARNING: generateBtn not found")

    browser.close()
    print("\n=== ALL DONE ===")
