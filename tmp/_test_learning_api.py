"""Quick verification of learning module API endpoints."""
import sys, json, io

# Suppress ChromaDB init noise
_real_stderr = sys.stderr
sys.stderr = io.StringIO()

from gangdan.app import app
app.config['TESTING'] = True
c = app.test_client()

sys.stderr = _real_stderr
passed = 0
failed = 0

def check(label, status_code, expected=200):
    global passed, failed
    ok = status_code == expected
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}: {status_code} (expected {expected})")
    if ok:
        passed += 1
    else:
        failed += 1

print("=== Page Routes ===")
for path in ['/question', '/guide', '/research']:
    r = c.get(path)
    check(f"GET {path}", r.status_code)

print("\n=== GET API Endpoints ===")
for path in ['/api/learning/kb/list', '/api/learning/questions/list',
             '/api/learning/guide/sessions', '/api/learning/research/reports']:
    r = c.get(path)
    data = r.get_json()
    check(f"GET {path} -> keys={list(data.keys())}", r.status_code)

print("\n=== POST Validation (missing params) ===")
r = c.post('/api/learning/questions/generate',
           data=json.dumps({'topic': 'test'}),
           content_type='application/json')
check("POST questions/generate (no kb_names)", r.status_code)

r = c.post('/api/learning/guide/create',
           data=json.dumps({'kb_names': []}),
           content_type='application/json')
check("POST guide/create (empty kb_names)", r.status_code)

r = c.post('/api/learning/research/run',
           data=json.dumps({'topic': 'test', 'kb_names': []}),
           content_type='application/json')
check("POST research/run (empty kb_names)", r.status_code)

print("\n=== 404 Not Found ===")
r = c.get('/api/learning/guide/session/nonexistent')
check("GET guide/session/nonexistent", r.status_code, 404)

r = c.get('/api/learning/questions/notfound')
check("GET questions/notfound", r.status_code, 404)

r = c.get('/api/learning/research/report/notfound')
check("GET research/report/notfound", r.status_code, 404)

print("\n=== HTML Content Checks ===")
r = c.get('/question')
html = r.data.decode('utf-8')
has_kb = 'kbCheckList' in html
has_js = 'question.js' in html
has_css = 'learning.css' in html
check(f"question.html has kbCheckList={has_kb}, question.js={has_js}, learning.css={has_css}",
      200 if (has_kb and has_js and has_css) else 500)

r = c.get('/guide')
html = r.data.decode('utf-8')
has_setup = 'setupPanel' in html
has_js = 'guide.js' in html
check(f"guide.html has setupPanel={has_setup}, guide.js={has_js}",
      200 if (has_setup and has_js) else 500)

r = c.get('/research')
html = r.data.decode('utf-8')
has_phase = 'phase-planning' in html
has_js = 'research.js' in html
check(f"research.html has phase-planning={has_phase}, research.js={has_js}",
      200 if (has_phase and has_js) else 500)

print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL TESTS PASSED")
else:
    print("SOME TESTS FAILED")
    sys.exit(1)
