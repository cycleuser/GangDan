"""
Real end-to-end generation tests:
 - Question generation (F2 web search toggle)
 - Lecture generation (F3)
 - Exam generation (F4)

Each test uses SSE streaming and captures output.
"""
import sys, os, json, time, requests

BASE = "http://127.0.0.1:5000"
SAVE = r'c:\Users\frede\Downloads\GangDan\test_screenshots'

def header(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}", flush=True)

def consume_sse(resp, max_seconds=120):
    """Read SSE stream, return collected events."""
    events = []
    start = time.time()
    for line in resp.iter_lines(decode_unicode=True):
        if time.time() - start > max_seconds:
            print("  [TIMEOUT]", flush=True)
            break
        if not line or not line.startswith("data: "):
            continue
        raw = line[6:]
        if raw == "[DONE]":
            break
        try:
            evt = json.loads(raw)
            events.append(evt)
            etype = evt.get("type", evt.get("event", "?"))
            msg = evt.get("message", evt.get("content", ""))[:80] if isinstance(evt.get("message", evt.get("content", "")), str) else ""
            print(f"    SSE [{etype}] {msg}", flush=True)
        except json.JSONDecodeError:
            pass
    return events

# ---------------------------------------------------------------------------
# Find a valid KB to use
# ---------------------------------------------------------------------------
r = requests.get(f"{BASE}/api/kb/list", timeout=10)
kb_data = r.json()
if isinstance(kb_data, dict) and "collections" in kb_data:
    kb_names = [c["name"] for c in kb_data["collections"] if c.get("count", 0) > 0]
elif isinstance(kb_data, list):
    kb_names = [c["name"] for c in kb_data if c.get("count", 0) > 0]
else:
    kb_names = []

print(f"Available KBs with docs: {kb_names}", flush=True)
if not kb_names:
    print("WARNING: No KB with documents found. Using first available.", flush=True)
    if isinstance(kb_data, dict) and "collections" in kb_data:
        kb_names = [c["name"] for c in kb_data["collections"][:1]]
    elif isinstance(kb_data, list):
        kb_names = [c["name"] for c in kb_data[:1]]

test_kb = kb_names[:1] if kb_names else ["tensorflow"]
print(f"Using KB: {test_kb}", flush=True)

# ---------------------------------------------------------------------------
# Test A: Question Generation (with web_search=false)
# ---------------------------------------------------------------------------
header("TEST A: Question Generation")
try:
    r = requests.post(f"{BASE}/api/learning/questions/generate", json={
        "kb_names": test_kb,
        "topic": "basic concepts",
        "num_questions": 2,
        "question_type": "choice",
        "difficulty": "easy",
        "web_search": False,
    }, stream=True, timeout=180)
    print(f"  Status: {r.status_code}", flush=True)
    events = consume_sse(r, max_seconds=120)
    q_events = [e for e in events if e.get("type") == "question"]
    print(f"  Questions received: {len(q_events)}", flush=True)
    print(f"  [{'PASS' if len(q_events) >= 1 else 'FAIL'}] Question generation", flush=True)
except Exception as e:
    print(f"  [FAIL] {e}", flush=True)

# ---------------------------------------------------------------------------
# Test B: Lecture Generation
# ---------------------------------------------------------------------------
header("TEST B: Lecture Generation")
try:
    r = requests.post(f"{BASE}/api/learning/lecture/generate", json={
        "topic": "introduction to machine learning",
        "kb_names": test_kb,
        "web_search": False,
    }, stream=True, timeout=300)
    print(f"  Status: {r.status_code}", flush=True)
    events = consume_sse(r, max_seconds=240)
    phases_seen = set(e.get("phase", "") for e in events if e.get("type") == "phase")
    has_content = any(e.get("type") == "content" for e in events)
    done = any(e.get("type") == "done" for e in events)
    print(f"  Phases seen: {phases_seen}", flush=True)
    print(f"  Has content: {has_content}", flush=True)
    print(f"  Done: {done}", flush=True)
    ok = len(phases_seen) >= 2 and has_content
    print(f"  [{'PASS' if ok else 'FAIL'}] Lecture generation", flush=True)
except Exception as e:
    print(f"  [FAIL] {e}", flush=True)

# ---------------------------------------------------------------------------
# Test C: Exam Generation
# ---------------------------------------------------------------------------
header("TEST C: Exam Generation")
try:
    r = requests.post(f"{BASE}/api/learning/exam/generate", json={
        "topic": "basic programming",
        "kb_names": test_kb,
        "difficulty": "easy",
        "web_search": False,
    }, stream=True, timeout=300)
    print(f"  Status: {r.status_code}", flush=True)
    events = consume_sse(r, max_seconds=240)
    phases_seen = set(e.get("phase", "") for e in events if e.get("type") == "phase")
    has_content = any(e.get("type") == "content" for e in events)
    done = any(e.get("type") == "done" for e in events)
    print(f"  Phases seen: {phases_seen}", flush=True)
    print(f"  Has content: {has_content}", flush=True)
    print(f"  Done: {done}", flush=True)
    ok = len(phases_seen) >= 2 and has_content
    print(f"  [{'PASS' if ok else 'FAIL'}] Exam generation", flush=True)
except Exception as e:
    print(f"  [FAIL] {e}", flush=True)

# ---------------------------------------------------------------------------
# Test D: Check saved lectures/exams
# ---------------------------------------------------------------------------
header("TEST D: Saved items list")
r = requests.get(f"{BASE}/api/learning/lecture/list", timeout=10)
data = r.json()
print(f"  Lectures: {data}", flush=True)

r = requests.get(f"{BASE}/api/learning/exam/list", timeout=10)
data = r.json()
print(f"  Exams: {data}", flush=True)

print("\n  ALL GENERATION TESTS COMPLETE", flush=True)
