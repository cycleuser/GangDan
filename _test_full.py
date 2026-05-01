"""Full verification of learning module API endpoints."""
import sys, json

sys.stdout = open('_test_out.txt', 'w', encoding='utf-8')
sys.stderr = open('_test_err.txt', 'w', encoding='utf-8')

from gangdan.app import app
app.config['TESTING'] = True
c = app.test_client()

passed = 0
failed = 0

def check(label, actual, expected=200):
    global passed, failed
    ok = actual == expected
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}: {actual} (expected {expected})", flush=True)
    if ok:
        passed += 1
    else:
        failed += 1

print("=== Page Routes ===", flush=True)
for path in ['/question', '/guide', '/research']:
    r = c.get(path)
    check(f"GET {path}", r.status_code)

print("\n=== GET API Endpoints ===", flush=True)
for path in ['/api/learning/kb/list', '/api/learning/questions/list',
             '/api/learning/guide/sessions', '/api/learning/research/reports']:
    r = c.get(path)
    data = r.get_json()
    check(f"GET {path} -> keys={list(data.keys())}", r.status_code)

print("\n=== POST Validation (missing params) ===", flush=True)
r = c.post('/api/learning/questions/generate',
           data=json.dumps({'topic': 'test'}),
           content_type='application/json')
check("POST questions/generate (no kb_names)", r.status_code)
print(f"    response: {r.get_json()}", flush=True)

r = c.post('/api/learning/guide/create',
           data=json.dumps({'kb_names': []}),
           content_type='application/json')
check("POST guide/create (empty kb_names)", r.status_code)
print(f"    response: {r.get_json()}", flush=True)

r = c.post('/api/learning/research/run',
           data=json.dumps({'topic': 'test', 'kb_names': []}),
           content_type='application/json')
check("POST research/run (empty kb_names)", r.status_code)
print(f"    response: {r.get_json()}", flush=True)

print("\n=== 404 Not Found ===", flush=True)
r = c.get('/api/learning/guide/session/nonexistent')
check("GET guide/session/nonexistent", r.status_code, 404)

r = c.get('/api/learning/questions/notfound')
check("GET questions/notfound", r.status_code, 404)

r = c.get('/api/learning/research/report/notfound')
check("GET research/report/notfound", r.status_code, 404)

print("\n=== HTML Content Checks ===", flush=True)
r = c.get('/question')
html = r.data.decode('utf-8')
ok = 'kbCheckList' in html and 'question.js' in html and 'learning.css' in html and 'SERVER_CONFIG' in html
check("question.html content", 200 if ok else 500)

r = c.get('/guide')
html = r.data.decode('utf-8')
ok = 'setupPanel' in html and 'guide.js' in html and 'learning.css' in html and 'SERVER_CONFIG' in html
check("guide.html content", 200 if ok else 500)

r = c.get('/research')
html = r.data.decode('utf-8')
ok = 'phase-planning' in html and 'research.js' in html and 'learning.css' in html and 'SERVER_CONFIG' in html
check("research.html content", 200 if ok else 500)

# Check translations are in the rendered pages
r = c.get('/question')
html = r.data.decode('utf-8')
ok = 'question_generator' in html and 'translations' in html
check("question.html has translations", 200 if ok else 500)

print(f"\n{'='*50}", flush=True)
print(f"Results: {passed} passed, {failed} failed", flush=True)
if failed == 0:
    print("ALL TESTS PASSED", flush=True)
else:
    print("SOME TESTS FAILED", flush=True)

sys.stdout.close()
sys.stderr.close()
