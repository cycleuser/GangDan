"""
Real end-to-end generation tests with corrected models.
Uses gemma3:1b (chat) + nomic-embed-text:latest (embedding).
"""
import sys, os, json, time, requests

BASE = "http://127.0.0.1:5000"
SAVE = r'c:\Users\frede\Downloads\GangDan\test_screenshots'

def header(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}", flush=True)

def consume_sse(resp, max_seconds=180):
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
            etype = evt.get("type", "?")
            if etype == "content":
                c = evt.get("content", "")
                print(f"    SSE [content] +{len(c)} chars", flush=True)
            elif etype == "error":
                print(f"    SSE [error] {evt.get('message','')}", flush=True)
            else:
                msg = str(evt.get("message", ""))[:60]
                print(f"    SSE [{etype}] {msg}", flush=True)
        except json.JSONDecodeError:
            pass
    return events

# Use a real KB that has indexed docs
test_kb = ["tensorflow"]

# ---------------------------------------------------------------------------
# Test A: Question Generation
# ---------------------------------------------------------------------------
header("TEST A: Question Generation (2 questions, tensorflow)")
try:
    r = requests.post(f"{BASE}/api/learning/questions/generate", json={
        "kb_names": test_kb,
        "topic": "neural network basics",
        "num_questions": 2,
        "question_type": "choice",
        "difficulty": "easy",
        "web_search": False,
    }, stream=True, timeout=180)
    print(f"  HTTP status: {r.status_code}", flush=True)
    events = consume_sse(r, max_seconds=120)
    q_events = [e for e in events if e.get("type") == "question"]
    done = any(e.get("type") == "done" for e in events)
    errors = [e for e in events if e.get("type") == "error"]
    print(f"  Questions: {len(q_events)}  Done: {done}  Errors: {len(errors)}", flush=True)
    print(f"  [{'PASS' if len(q_events) >= 1 else 'FAIL'}] Question generation", flush=True)
except Exception as e:
    print(f"  [FAIL] {type(e).__name__}: {e}", flush=True)

# ---------------------------------------------------------------------------
# Test B: Lecture Generation
# ---------------------------------------------------------------------------
header("TEST B: Lecture Generation (tensorflow)")
try:
    r = requests.post(f"{BASE}/api/learning/lecture/generate", json={
        "topic": "TensorFlow basics",
        "kb_names": test_kb,
        "web_search": False,
    }, stream=True, timeout=300)
    print(f"  HTTP status: {r.status_code}", flush=True)
    events = consume_sse(r, max_seconds=240)
    phases = set(e.get("phase", "") for e in events if e.get("type") == "phase")
    has_content = any(e.get("type") == "content" for e in events)
    done = any(e.get("type") == "done" for e in events)
    errors = [e for e in events if e.get("type") == "error"]
    print(f"  Phases: {phases}  Content: {has_content}  Done: {done}  Errors: {len(errors)}", flush=True)
    if errors:
        print(f"  Error details: {errors[0].get('message','')[:100]}", flush=True)
    ok = done or (len(phases) >= 3 and has_content)
    print(f"  [{'PASS' if ok else 'FAIL'}] Lecture generation", flush=True)
except Exception as e:
    print(f"  [FAIL] {type(e).__name__}: {e}", flush=True)

# ---------------------------------------------------------------------------
# Test C: Exam Generation
# ---------------------------------------------------------------------------
header("TEST C: Exam Generation (tensorflow)")
try:
    r = requests.post(f"{BASE}/api/learning/exam/generate", json={
        "topic": "TensorFlow basics",
        "kb_names": test_kb,
        "difficulty": "easy",
        "web_search": False,
    }, stream=True, timeout=300)
    print(f"  HTTP status: {r.status_code}", flush=True)
    events = consume_sse(r, max_seconds=240)
    phases = set(e.get("phase", "") for e in events if e.get("type") == "phase")
    has_content = any(e.get("type") == "content" for e in events)
    done = any(e.get("type") == "done" for e in events)
    errors = [e for e in events if e.get("type") == "error"]
    print(f"  Phases: {phases}  Content: {has_content}  Done: {done}  Errors: {len(errors)}", flush=True)
    if errors:
        print(f"  Error details: {errors[0].get('message','')[:100]}", flush=True)
    ok = done or (len(phases) >= 3 and has_content)
    print(f"  [{'PASS' if ok else 'FAIL'}] Exam generation", flush=True)
except Exception as e:
    print(f"  [FAIL] {type(e).__name__}: {e}", flush=True)

# ---------------------------------------------------------------------------
# Saved items
# ---------------------------------------------------------------------------
header("TEST D: Saved items after generation")
r = requests.get(f"{BASE}/api/learning/lecture/list", timeout=10)
print(f"  Lectures: {json.dumps(r.json(), ensure_ascii=False)}", flush=True)
r = requests.get(f"{BASE}/api/learning/exam/list", timeout=10)
print(f"  Exams: {json.dumps(r.json(), ensure_ascii=False)}", flush=True)

print("\n  ALL GENERATION TESTS COMPLETE", flush=True)
