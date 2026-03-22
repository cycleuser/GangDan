"""
Corrected comprehensive test with proper routes.
/learning/lecture and /learning/exam (not /lecture, /exam).
"""
import os, sys, json, time, requests

os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'

BASE = "http://127.0.0.1:5000"
RESULTS = {}

def header(msg):
    sep = "=" * 60
    print(f"\n{sep}\n  {msg}\n{sep}", flush=True)

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
                sys.stdout.write(f".")
                sys.stdout.flush()
            elif etype == "error":
                print(f"\n  ERROR: {evt.get('message','')}", flush=True)
            elif etype == "phase":
                print(f"\n  PHASE: {evt.get('phase','')}", flush=True)
            elif etype in ("outline", "plan", "section", "question"):
                msg = str(evt.get("message", evt.get("title", evt.get("question",{}).get("question",""))))[:80]
                print(f"\n  {etype.upper()}: {msg}", flush=True)
            elif etype == "done":
                print(f"\n  DONE event received", flush=True)
        except json.JSONDecodeError:
            pass
    print(f"\n  Total events: {len(events)}, elapsed: {time.time()-start:.1f}s", flush=True)
    return events

# =============================================
header("T0: Server Health Check")
r = requests.get(f"{BASE}/", timeout=10)
print(f"  Main page: HTTP {r.status_code}")
RESULTS["T0_health"] = "PASS" if r.status_code == 200 else "FAIL"

# =============================================
header("T1: Models API")
r = requests.get(f"{BASE}/api/models", timeout=10)
data = r.json()
print(f"  Chat models: {data.get('chat_models',[])}")
print(f"  Embedding models: {data.get('embedding_models',[])}")
print(f"  Current chat: {data.get('current_chat_model','?')}")
print(f"  Current embed: {data.get('current_embedding_model','?')}")
RESULTS["T1_models"] = "PASS"

# =============================================
header("T2: Knowledge Base List")
r = requests.get(f"{BASE}/api/kb/list", timeout=10)
kbs = r.json().get("kbs", [])
print(f"  KB count: {len(kbs)}")
total_docs = sum(kb['doc_count'] for kb in kbs)
print(f"  Total docs: {total_docs}")
RESULTS["T2_kb"] = "PASS" if total_docs > 0 else "FAIL"

# =============================================
header("T3: Page Load Tests (correct routes)")
pages = [
    ("/", "Main"),
    ("/question", "Question"),
    ("/guide", "Guide"),
    ("/research", "Research"),
    ("/learning/lecture", "Lecture"),
    ("/learning/exam", "Exam"),
    ("/?lang=zh", "Main ZH"),
    ("/learning/lecture?lang=zh", "Lecture ZH"),
    ("/learning/exam?lang=zh", "Exam ZH"),
    ("/question?lang=en", "Question EN"),
]
page_pass = 0
for path, name in pages:
    r = requests.get(f"{BASE}{path}", timeout=10)
    ok = r.status_code == 200
    if ok: page_pass += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: HTTP {r.status_code}, {len(r.text)} bytes")
RESULTS["T3_pages"] = "PASS" if page_pass == len(pages) else f"PARTIAL ({page_pass}/{len(pages)})"

# =============================================
header("T4: F1 - Vector DB Backend (ChromaDB)")
with open(r'c:\Users\frede\Downloads\GangDan\data\gangdan_config.json') as f:
    cfg = json.load(f)
print(f"  vector_db_type: {cfg.get('vector_db_type', 'not set')}")
print(f"  embedding_model: {cfg.get('embedding_model', 'not set')}")
print(f"  chat_model: {cfg.get('chat_model', 'not set')}")
RESULTS["T4_vector_db"] = "PASS" if cfg.get('vector_db_type') == 'chroma' else "FAIL"

# =============================================
header("T5: F2 - Web Search Toggle")
ws_count = 0
for path in ["/question", "/learning/lecture", "/learning/exam"]:
    r = requests.get(f"{BASE}{path}", timeout=10)
    has = "web_search" in r.text or "web-search" in r.text or "webSearch" in r.text
    print(f"  {path}: web_search={has}")
    if has: ws_count += 1
RESULTS["T5_web_search"] = "PASS" if ws_count >= 3 else f"PARTIAL ({ws_count}/3)"

# =============================================
header("T6: F3 - Lecture Generation (numpy, Python basics)")
try:
    r = requests.post(f"{BASE}/api/learning/lecture/generate", json={
        "topic": "Python basics",
        "kb_names": ["numpy"],
        "web_search": False,
    }, stream=True, timeout=300)
    print(f"  HTTP: {r.status_code}")
    events = consume_sse(r, max_seconds=300)
    phases = set(e.get("phase","") for e in events if e.get("type")=="phase")
    content_n = sum(1 for e in events if e.get("type")=="content")
    done = any(e.get("type")=="done" for e in events)
    errs = [e.get("message","") for e in events if e.get("type")=="error"]
    print(f"  Phases: {phases}, Content chunks: {content_n}, Done: {done}")
    if errs:
        print(f"  Errors: {errs}")
    ok = (len(phases)>=2 and content_n>0) or done
    RESULTS["T6_lecture"] = "PASS" if ok else "FAIL"
    RESULTS["T6_detail"] = {"phases": list(phases), "chunks": content_n, "done": done, "errors": errs}
except Exception as e:
    print(f"  FAIL: {e}")
    RESULTS["T6_lecture"] = "FAIL"

# =============================================
header("T7: F4 - Exam Generation (numpy, easy)")
try:
    r = requests.post(f"{BASE}/api/learning/exam/generate", json={
        "topic": "Python basics",
        "kb_names": ["numpy"],
        "difficulty": "easy",
        "web_search": False,
    }, stream=True, timeout=300)
    print(f"  HTTP: {r.status_code}")
    events = consume_sse(r, max_seconds=300)
    phases = set(e.get("phase","") for e in events if e.get("type")=="phase")
    content_n = sum(1 for e in events if e.get("type")=="content")
    done = any(e.get("type")=="done" for e in events)
    errs = [e.get("message","") for e in events if e.get("type")=="error"]
    print(f"  Phases: {phases}, Content chunks: {content_n}, Done: {done}")
    if errs:
        print(f"  Errors: {errs}")
    ok = (len(phases)>=2 and content_n>0) or done
    RESULTS["T7_exam"] = "PASS" if ok else "FAIL"
    RESULTS["T7_detail"] = {"phases": list(phases), "chunks": content_n, "done": done, "errors": errs}
except Exception as e:
    print(f"  FAIL: {e}")
    RESULTS["T7_exam"] = "FAIL"

# =============================================
header("T8: Question Generation (numpy)")
try:
    r = requests.post(f"{BASE}/api/learning/questions/generate", json={
        "kb_names": ["numpy"],
        "topic": "array operations",
        "num_questions": 2,
        "question_type": "choice",
        "difficulty": "easy",
        "web_search": False,
    }, stream=True, timeout=300)
    print(f"  HTTP: {r.status_code}")
    events = consume_sse(r, max_seconds=180)
    q_events = [e for e in events if e.get("type")=="question"]
    done = any(e.get("type")=="done" for e in events)
    errs = [e.get("message","") for e in events if e.get("type")=="error"]
    print(f"  Questions: {len(q_events)}, Done: {done}, Errors: {len(errs)}")
    ok = len(q_events)>=1 or done
    RESULTS["T8_questions"] = "PASS" if ok else "FAIL"
except Exception as e:
    print(f"  FAIL: {e}")
    RESULTS["T8_questions"] = "FAIL"

# =============================================
header("T9: i18n Check")
r_zh = requests.get(f"{BASE}/learning/lecture?lang=zh", timeout=10)
r_en = requests.get(f"{BASE}/learning/lecture?lang=en", timeout=10)
has_cjk = any(ord(c) > 0x4e00 for c in r_zh.text[:3000])
has_en = "Lecture" in r_en.text
print(f"  ZH page CJK chars: {has_cjk}")
print(f"  EN page 'Lecture' text: {has_en}")
RESULTS["T9_i18n"] = "PASS" if has_cjk and has_en else "PARTIAL"

# =============================================
header("T10: Saved Items")
r1 = requests.get(f"{BASE}/api/learning/lecture/list", timeout=10)
r2 = requests.get(f"{BASE}/api/learning/exam/list", timeout=10)
lects = r1.json().get("lectures", [])
exams = r2.json().get("exams", [])
print(f"  Lectures saved: {len(lects)}")
print(f"  Exams saved: {len(exams)}")
RESULTS["T10_saved"] = "PASS" if r1.status_code==200 and r2.status_code==200 else "FAIL"

# =============================================
header("SUMMARY")
test_items = {k:v for k,v in RESULTS.items() if not isinstance(v, dict)}
passed = sum(1 for v in test_items.values() if v == "PASS")
total = len(test_items)
for k, v in sorted(test_items.items()):
    mark = "[OK]" if v == "PASS" else "[!!]"
    print(f"  {mark} {k}: {v}")
print(f"\n  PASSED: {passed}/{total}")

with open(r'c:\Users\frede\Downloads\GangDan\test_screenshots\test_results.json', 'w', encoding='utf-8') as f:
    json.dump(RESULTS, f, indent=2, ensure_ascii=False)
print("  Results saved.")
