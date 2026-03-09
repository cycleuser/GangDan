"""
Comprehensive test script for all GangDan features.
Tests F1 (Vector DB), F2 (Web Search), F3 (Lecture), F4 (Exam).
Captures results for documentation.
"""
import os
import sys
import json
import time
import requests

os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

BASE = "http://127.0.0.1:5000"
RESULTS = {}

def header(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}", flush=True)

def consume_sse(resp, max_seconds=300):
    events = []
    start = time.time()
    for line in resp.iter_lines(decode_unicode=True):
        elapsed = time.time() - start
        if elapsed > max_seconds:
            print(f"  [TIMEOUT after {int(elapsed)}s]", flush=True)
            break
        if not line or not line.startswith("data: "):
            continue
        raw = line[6:]
        if raw == "[DONE]":
            print("  [DONE received]", flush=True)
            break
        try:
            evt = json.loads(raw)
            events.append(evt)
            etype = evt.get("type", "?")
            if etype == "content":
                c = evt.get("content", "")
                print(f"    chunk +{len(c)} chars", end="", flush=True)
            elif etype == "error":
                print(f"\n    ERROR: {evt.get('message','')}", flush=True)
            elif etype == "phase":
                print(f"\n    PHASE: {evt.get('phase','')}", flush=True)
            elif etype in ("outline", "plan", "section"):
                msg = str(evt.get("message", evt.get("title", "")))[:60]
                print(f"\n    {etype.upper()}: {msg}", flush=True)
            elif etype == "question":
                q = evt.get("question", {})
                print(f"\n    QUESTION: {str(q.get('question',''))[:60]}", flush=True)
            elif etype == "done":
                print(f"\n    DONE event received", flush=True)
        except json.JSONDecodeError:
            pass
    print(f"\n  Total events: {len(events)}, elapsed: {time.time()-start:.1f}s", flush=True)
    return events

# =============================================
# T0: Server Health
# =============================================
header("T0: Server Health Check")
try:
    r = requests.get(f"{BASE}/", timeout=10)
    print(f"  Main page: HTTP {r.status_code}, len={len(r.text)}")
    RESULTS["T0_health"] = "PASS" if r.status_code == 200 else "FAIL"
except Exception as e:
    print(f"  FAIL: {e}")
    RESULTS["T0_health"] = "FAIL"
    print("Server not running. Aborting.")
    sys.exit(1)

# =============================================
# T1: Settings / Config API
# =============================================
header("T1: Settings API")
try:
    r = requests.get(f"{BASE}/api/models", timeout=10)
    models = r.json()
    print(f"  Models endpoint: HTTP {r.status_code}")
    print(f"  Chat models: {len(models.get('chat_models',[]))}")
    print(f"  Embedding models: {len(models.get('embedding_models',[]))}")
    print(f"  Current chat: {models.get('current_chat_model','?')}")
    print(f"  Current embed: {models.get('current_embedding_model','?')}")
    RESULTS["T1_models"] = "PASS" if r.status_code == 200 else "FAIL"
except Exception as e:
    print(f"  FAIL: {e}")
    RESULTS["T1_models"] = "FAIL"

# =============================================
# T2: KB List
# =============================================
header("T2: Knowledge Base List")
try:
    r = requests.get(f"{BASE}/api/kb/list", timeout=10)
    kbs = r.json().get("kbs", [])
    print(f"  KB list: HTTP {r.status_code}, count={len(kbs)}")
    for kb in kbs[:5]:
        print(f"    - {kb['name']}: {kb['doc_count']} docs ({kb['type']})")
    if len(kbs) > 5:
        print(f"    ... and {len(kbs)-5} more")
    has_tf = any(kb['name'] == 'tensorflow' for kb in kbs)
    print(f"  TensorFlow KB present: {has_tf}")
    RESULTS["T2_kb_list"] = "PASS" if has_tf else "FAIL"
except Exception as e:
    print(f"  FAIL: {e}")
    RESULTS["T2_kb_list"] = "FAIL"

# =============================================
# T3: Page Load Tests
# =============================================
header("T3: Page Load Tests")
pages = [
    ("/", "Main"),
    ("/question", "Question (EN)"),
    ("/guide", "Guide (EN)"),
    ("/research", "Research (EN)"),
    ("/lecture", "Lecture (EN)"),
    ("/exam", "Exam (EN)"),
    ("/?lang=zh", "Main (ZH)"),
    ("/lecture?lang=zh", "Lecture (ZH)"),
    ("/exam?lang=zh", "Exam (ZH)"),
]
page_results = []
for path, name in pages:
    try:
        r = requests.get(f"{BASE}{path}", timeout=10)
        ok = r.status_code == 200
        page_results.append(ok)
        print(f"  [{('PASS' if ok else 'FAIL')}] {name}: HTTP {r.status_code}")
    except Exception as e:
        page_results.append(False)
        print(f"  [FAIL] {name}: {e}")
RESULTS["T3_pages"] = "PASS" if all(page_results) else "FAIL"

# =============================================
# T4: F1 - Vector DB Backend Switching
# =============================================
header("T4: F1 - Vector DB Backend (ChromaDB)")
try:
    # Check current config
    r = requests.get(f"{BASE}/api/models", timeout=10)
    data = r.json()
    print(f"  Current vector_db_type from config file...")
    # Read config
    with open(r'c:\Users\frede\Downloads\GangDan\data\gangdan_config.json') as f:
        cfg = json.load(f)
    print(f"  vector_db_type: {cfg.get('vector_db_type', 'not set')}")
    
    # Test ChromaDB collections
    r = requests.get(f"{BASE}/api/kb/list", timeout=10)
    kbs = r.json().get("kbs", [])
    total_docs = sum(kb['doc_count'] for kb in kbs)
    print(f"  Total KBs: {len(kbs)}, Total docs: {total_docs}")
    RESULTS["T4_vector_db"] = "PASS" if total_docs > 0 else "FAIL"
except Exception as e:
    print(f"  FAIL: {e}")
    RESULTS["T4_vector_db"] = "FAIL"

# =============================================
# T5: F2 - Web Search Toggle Present
# =============================================
header("T5: F2 - Web Search Integration Check")
try:
    ws_found = 0
    for path in ["/question", "/lecture", "/exam"]:
        r = requests.get(f"{BASE}{path}", timeout=10)
        html = r.text
        has_ws = "web_search" in html or "web-search" in html or "webSearch" in html
        print(f"  {path}: web_search element = {has_ws}")
        if has_ws:
            ws_found += 1
    RESULTS["T5_web_search"] = "PASS" if ws_found >= 3 else "FAIL"
except Exception as e:
    print(f"  FAIL: {e}")
    RESULTS["T5_web_search"] = "FAIL"

# =============================================
# T6: F3 - Lecture Generation (streaming)
# =============================================
header("T6: F3 - Lecture Generation")
try:
    r = requests.post(f"{BASE}/api/learning/lecture/generate", json={
        "topic": "Python basics",
        "kb_names": ["numpy"],
        "web_search": False,
    }, stream=True, timeout=300)
    print(f"  HTTP status: {r.status_code}")
    events = consume_sse(r, max_seconds=300)
    
    phases = set()
    content_chunks = 0
    has_done = False
    errors = []
    for e in events:
        t = e.get("type", "")
        if t == "phase":
            phases.add(e.get("phase", ""))
        elif t == "content":
            content_chunks += 1
        elif t == "done":
            has_done = True
        elif t == "error":
            errors.append(e.get("message", ""))
    
    print(f"  Phases seen: {phases}")
    print(f"  Content chunks: {content_chunks}")
    print(f"  Done: {has_done}, Errors: {len(errors)}")
    
    ok = (len(phases) >= 2 and content_chunks > 0) or has_done
    RESULTS["T6_lecture"] = "PASS" if ok else "FAIL"
    RESULTS["T6_detail"] = {
        "phases": list(phases),
        "content_chunks": content_chunks,
        "done": has_done,
        "errors": errors
    }
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    RESULTS["T6_lecture"] = "FAIL"

# =============================================
# T7: F4 - Exam Generation (streaming)
# =============================================
header("T7: F4 - Exam Generation")
try:
    r = requests.post(f"{BASE}/api/learning/exam/generate", json={
        "topic": "Python basics",
        "kb_names": ["numpy"],
        "difficulty": "easy",
        "web_search": False,
    }, stream=True, timeout=300)
    print(f"  HTTP status: {r.status_code}")
    events = consume_sse(r, max_seconds=300)
    
    phases = set()
    content_chunks = 0
    has_done = False
    errors = []
    for e in events:
        t = e.get("type", "")
        if t == "phase":
            phases.add(e.get("phase", ""))
        elif t == "content":
            content_chunks += 1
        elif t == "done":
            has_done = True
        elif t == "error":
            errors.append(e.get("message", ""))
    
    print(f"  Phases seen: {phases}")
    print(f"  Content chunks: {content_chunks}")
    print(f"  Done: {has_done}, Errors: {len(errors)}")
    
    ok = (len(phases) >= 2 and content_chunks > 0) or has_done
    RESULTS["T7_exam"] = "PASS" if ok else "FAIL"
    RESULTS["T7_detail"] = {
        "phases": list(phases),
        "content_chunks": content_chunks,
        "done": has_done,
        "errors": errors
    }
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    RESULTS["T7_exam"] = "FAIL"

# =============================================
# T8: Question Generation (streaming)
# =============================================
header("T8: Question Generation")
try:
    r = requests.post(f"{BASE}/api/learning/questions/generate", json={
        "kb_names": ["numpy"],
        "topic": "array operations",
        "num_questions": 2,
        "question_type": "choice",
        "difficulty": "easy",
        "web_search": False,
    }, stream=True, timeout=300)
    print(f"  HTTP status: {r.status_code}")
    events = consume_sse(r, max_seconds=180)
    
    q_events = [e for e in events if e.get("type") == "question"]
    has_done = any(e.get("type") == "done" for e in events)
    errors = [e for e in events if e.get("type") == "error"]
    
    print(f"  Questions: {len(q_events)}, Done: {has_done}, Errors: {len(errors)}")
    
    ok = len(q_events) >= 1 or has_done
    RESULTS["T8_questions"] = "PASS" if ok else "FAIL"
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    RESULTS["T8_questions"] = "FAIL"

# =============================================
# T9: Translation / i18n Check
# =============================================
header("T9: i18n / Language Switching")
try:
    r_zh = requests.get(f"{BASE}/lecture?lang=zh", timeout=10)
    r_en = requests.get(f"{BASE}/lecture?lang=en", timeout=10)
    
    zh_keys = ["lecture_maker" in r_zh.text or "\\u8bfe\\u7a0b" in r_zh.text]
    en_keys = ["Lecture Maker" in r_en.text or "lecture_maker" in r_en.text]
    
    # Check for key Chinese characters or English text
    has_zh = any(ord(c) > 0x4e00 for c in r_zh.text[:2000])
    has_en = "Lecture" in r_en.text or "lecture" in r_en.text.lower()
    
    print(f"  Chinese page has CJK chars: {has_zh}")
    print(f"  English page has English text: {has_en}")
    RESULTS["T9_i18n"] = "PASS" if has_zh and has_en else "PARTIAL"
except Exception as e:
    print(f"  FAIL: {e}")
    RESULTS["T9_i18n"] = "FAIL"

# =============================================
# T10: Saved Items (Lecture/Exam lists)
# =============================================
header("T10: Saved Items APIs")
try:
    r1 = requests.get(f"{BASE}/api/learning/lecture/list", timeout=10)
    r2 = requests.get(f"{BASE}/api/learning/exam/list", timeout=10)
    print(f"  Lecture list: HTTP {r1.status_code}, data: {r1.text[:200]}")
    print(f"  Exam list: HTTP {r2.status_code}, data: {r2.text[:200]}")
    RESULTS["T10_saved"] = "PASS" if r1.status_code == 200 and r2.status_code == 200 else "FAIL"
except Exception as e:
    print(f"  FAIL: {e}")
    RESULTS["T10_saved"] = "FAIL"

# =============================================
# Summary
# =============================================
header("TEST SUMMARY")
total = len(RESULTS)
passed = sum(1 for v in RESULTS.values() if v == "PASS" or (isinstance(v, dict)))
# Only count non-dict items
test_items = {k:v for k,v in RESULTS.items() if not isinstance(v, dict)}
passed = sum(1 for v in test_items.values() if v == "PASS")
total = len(test_items)
for k, v in sorted(test_items.items()):
    print(f"  {k}: {v}")
print(f"\n  Total: {passed}/{total} PASSED")

# Save results to file
with open(r'c:\Users\frede\Downloads\GangDan\test_screenshots\test_results.json', 'w', encoding='utf-8') as f:
    json.dump(RESULTS, f, indent=2, ensure_ascii=False)
print(f"\n  Results saved to test_results.json")
