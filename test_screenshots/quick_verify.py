"""Quick verify that embedding + generation work after config fix."""
import sys, json, time, requests

BASE = "http://127.0.0.1:5000"

# 1) Verify config loaded correctly
r = requests.get(f"{BASE}/api/kb/list", timeout=10)
kbs = r.json().get("kbs", [])
tf = [k for k in kbs if k["name"] == "tensorflow"]
print(f"tensorflow KB: {tf[0]['doc_count']} docs" if tf else "No tensorflow KB!", flush=True)

# 2) Quick question generation test
print("\n--- Question Generation ---", flush=True)
r = requests.post(f"{BASE}/api/learning/questions/generate", json={
    "kb_names": ["tensorflow"],
    "topic": "neural networks",
    "num_questions": 1,
    "question_type": "choice",
    "difficulty": "easy",
    "web_search": False,
}, stream=True, timeout=120)
print(f"HTTP: {r.status_code}", flush=True)
q_count = 0
for line in r.iter_lines(decode_unicode=True):
    if not line or not line.startswith("data: "): continue
    raw = line[6:]
    if raw == "[DONE]": break
    evt = json.loads(raw)
    etype = evt.get("type", "?")
    if etype == "question":
        q_count += 1
        print(f"  [question #{q_count}] {str(evt.get('question',''))[:60]}", flush=True)
    elif etype == "error":
        print(f"  [error] {evt.get('message','')}", flush=True)
    else:
        print(f"  [{etype}] {str(evt.get('message',''))[:60]}", flush=True)

print(f"\nResult: {q_count} questions generated", flush=True)
print("PASS" if q_count >= 1 else "FAIL", flush=True)
