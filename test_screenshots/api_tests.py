"""Functional API tests for all 4 features."""
import sys, os, json, time, requests

BASE = "http://127.0.0.1:5000"

def header(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}", flush=True)

def check(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}  {detail}", flush=True)
    return ok

results = []

# ---------------------------------------------------------------------------
# Test 1: All pages return HTTP 200
# ---------------------------------------------------------------------------
header("TEST 1: Page load (HTTP 200)")
pages = [
    ("/", "Main"),
    ("/question", "Question"),
    ("/guide", "Guide"),
    ("/research", "Research"),
    ("/learning/lecture", "Lecture"),
    ("/learning/exam", "Exam"),
    ("/learning/lecture?lang=en", "Lecture EN"),
    ("/learning/exam?lang=en", "Exam EN"),
]
for path, name in pages:
    r = requests.get(f"{BASE}{path}", timeout=10)
    results.append(check(f"{name} page ({path})", r.status_code == 200, f"status={r.status_code}"))

# ---------------------------------------------------------------------------
# Test 2: New nav links present in all learning pages
# ---------------------------------------------------------------------------
header("TEST 2: Navigation links on learning pages")
nav_pages = ["/question", "/guide", "/research", "/learning/lecture", "/learning/exam"]
for path in nav_pages:
    r = requests.get(f"{BASE}{path}", timeout=10)
    html = r.text
    has_lecture = "/learning/lecture" in html
    has_exam = "/learning/exam" in html
    results.append(check(f"{path} has lecture link", has_lecture))
    results.append(check(f"{path} has exam link", has_exam))

# Main page check
r = requests.get(f"{BASE}/", timeout=10)
html = r.text
results.append(check("Main page has lecture link", "/learning/lecture" in html))
results.append(check("Main page has exam link", "/learning/exam" in html))

# ---------------------------------------------------------------------------
# Test 3: Web search checkbox in question/guide pages
# ---------------------------------------------------------------------------
header("TEST 3: Web search checkbox present")
for path in ["/question", "/guide"]:
    r = requests.get(f"{BASE}{path}", timeout=10)
    has_ws = "webSearchToggle" in r.text
    results.append(check(f"{path} has webSearchToggle", has_ws))

# Also in lecture and exam
for path in ["/learning/lecture", "/learning/exam"]:
    r = requests.get(f"{BASE}{path}", timeout=10)
    has_ws = "webSearchToggle" in r.text
    results.append(check(f"{path} has webSearchToggle", has_ws))

# ---------------------------------------------------------------------------
# Test 4: Lecture page has correct form elements
# ---------------------------------------------------------------------------
header("TEST 4: Lecture page UI elements")
r = requests.get(f"{BASE}/learning/lecture", timeout=10)
html = r.text
for elem_id, label in [
    ("kbCheckList", "KB checklist"),
    ("topicInput", "Topic input"),
    ("webSearchToggle", "Web search toggle"),
    ("startBtn", "Start button"),
    ("phaseSection", "Phase indicator"),
    ("lectureContent", "Content area"),
    ("lectureList", "History list"),
]:
    results.append(check(f"Lecture has #{elem_id} ({label})", elem_id in html))

# Phase steps
for phase in ["phase-analyzing", "phase-outlining", "phase-writing", "phase-summarizing"]:
    results.append(check(f"Lecture has {phase}", phase in html))

# ---------------------------------------------------------------------------
# Test 5: Exam page has correct form elements
# ---------------------------------------------------------------------------
header("TEST 5: Exam page UI elements")
r = requests.get(f"{BASE}/learning/exam", timeout=10)
html = r.text
for elem_id, label in [
    ("kbCheckList", "KB checklist"),
    ("topicInput", "Topic input"),
    ("difficultySelect", "Difficulty dropdown"),
    ("webSearchToggle", "Web search toggle"),
    ("startBtn", "Start button"),
    ("phaseSection", "Phase indicator"),
    ("examTabs", "Tab bar"),
    ("tabPaper", "Paper tab"),
    ("tabAnswerKey", "Answer key tab"),
    ("paperContent", "Paper content"),
    ("answerKeyContent", "Answer key content"),
    ("examList", "History list"),
]:
    results.append(check(f"Exam has #{elem_id} ({label})", elem_id in html))

# Phase steps
for phase in ["phase-planning", "phase-generating", "phase-answer_key", "phase-formatting"]:
    results.append(check(f"Exam has {phase}", phase in html))

# ---------------------------------------------------------------------------
# Test 6: Translation keys exist
# ---------------------------------------------------------------------------
header("TEST 6: Translation keys in page JSON")
r = requests.get(f"{BASE}/learning/lecture", timeout=10)
html = r.text
# Extract translations JSON (it's embedded in the page)
new_keys = [
    "lecture_maker", "lecture_topic", "generate_lecture",
    "analyzing_phase", "outlining_phase", "writing_phase", "summarizing_phase",
    "saved_lectures", "export_lecture", "copy_lecture", "lecture_complete",
    "exam_generator", "exam_topic", "generate_exam",
    "generating_phase", "answer_key_phase", "formatting_phase",
    "saved_exams", "exam_paper_tab", "answer_key_tab",
    "export_paper", "export_answer_key", "exam_complete",
]
for key in new_keys:
    results.append(check(f"Translation key '{key}' in page", f'"{key}"' in html))

# ---------------------------------------------------------------------------
# Test 7: Vector DB abstraction (F1)
# ---------------------------------------------------------------------------
header("TEST 7: Vector DB abstraction")
# Check the KB list endpoint works (uses CHROMA.list_collections internally)
r = requests.get(f"{BASE}/api/kb_list", timeout=10)
ok = r.status_code == 200
results.append(check("KB list API (/api/kb_list)", ok, f"status={r.status_code}"))
if ok:
    data = r.json()
    results.append(check("KB list returns list", isinstance(data, list), f"count={len(data)}"))

# ---------------------------------------------------------------------------
# Test 8: Lecture list API
# ---------------------------------------------------------------------------
header("TEST 8: Lecture/Exam list APIs")
r = requests.get(f"{BASE}/api/learning/lecture/list", timeout=10)
results.append(check("Lecture list API", r.status_code == 200, f"status={r.status_code}"))

r = requests.get(f"{BASE}/api/learning/exam/list", timeout=10)
results.append(check("Exam list API", r.status_code == 200, f"status={r.status_code}"))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
header("SUMMARY")
passed = sum(results)
total = len(results)
failed = total - passed
print(f"  Total: {total}  Passed: {passed}  Failed: {failed}", flush=True)
if failed == 0:
    print("  ALL TESTS PASSED!", flush=True)
else:
    print(f"  {failed} TESTS FAILED", flush=True)
