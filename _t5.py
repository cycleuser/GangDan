"""Full API test with timeout protection."""
import sys, json, signal, threading

out = open('_t5_out.txt', 'w', encoding='utf-8')
sys.stderr = open('_t5_err.txt', 'w', encoding='utf-8')

def log(msg):
    out.write(msg + '\n')
    out.flush()

# Watchdog: force exit after 45s
def watchdog():
    import time; time.sleep(45)
    log("TIMEOUT - force exit")
    out.close()
    import os; os._exit(1)
threading.Thread(target=watchdog, daemon=True).start()

passed = 0
failed = 0
def check(label, actual, expected=200):
    global passed, failed
    ok = actual == expected
    log(f"  [{'PASS' if ok else 'FAIL'}] {label}: {actual}")
    passed += ok
    failed += (not ok)

try:
    from gangdan.app import app
    app.config['TESTING'] = True
    c = app.test_client()
    log("App loaded OK")

    log("=== Page Routes ===")
    for path in ['/question', '/guide', '/research']:
        r = c.get(path)
        check(f"GET {path}", r.status_code)

    log("=== GET API ===")
    r = c.get('/api/learning/kb/list')
    d = r.get_json()
    check(f"kb/list (kbs={len(d.get('kbs',[]))})", r.status_code)

    r = c.get('/api/learning/questions/list')
    d = r.get_json()
    check(f"questions/list (keys={list(d.keys())})", r.status_code)

    r = c.get('/api/learning/guide/sessions')
    d = r.get_json()
    check(f"guide/sessions (keys={list(d.keys())})", r.status_code)

    r = c.get('/api/learning/research/reports')
    d = r.get_json()
    check(f"research/reports (keys={list(d.keys())})", r.status_code)

    log("=== POST Validation ===")
    r = c.post('/api/learning/questions/generate', data=json.dumps({'topic':'t'}), content_type='application/json')
    check("q/generate no_kb", r.status_code)

    r = c.post('/api/learning/guide/create', data=json.dumps({'kb_names':[]}), content_type='application/json')
    check("g/create no_kb", r.status_code)

    r = c.post('/api/learning/research/run', data=json.dumps({'topic':'t','kb_names':[]}), content_type='application/json')
    check("r/run no_kb", r.status_code)

    log("=== 404 ===")
    r = c.get('/api/learning/guide/session/nonexistent')
    check("guide/session 404", r.status_code, 404)

    r = c.get('/api/learning/questions/xxx')
    check("questions/xxx 404", r.status_code, 404)

    r = c.get('/api/learning/research/report/xxx')
    check("research/report 404", r.status_code, 404)

    log("=== HTML Content ===")
    html = c.get('/question').data.decode()
    check("question.html content", 200 if all(x in html for x in ['kbCheckList','question.js','learning.css','SERVER_CONFIG']) else 500)

    html = c.get('/guide').data.decode()
    check("guide.html content", 200 if all(x in html for x in ['setupPanel','guide.js','learning.css','SERVER_CONFIG']) else 500)

    html = c.get('/research').data.decode()
    check("research.html content", 200 if all(x in html for x in ['phase-planning','research.js','learning.css','SERVER_CONFIG']) else 500)

    log(f"\n{'='*40}")
    log(f"Results: {passed} passed, {failed} failed")
    log("ALL TESTS PASSED" if failed == 0 else "SOME TESTS FAILED")

except Exception as e:
    import traceback
    log(f"EXCEPTION: {e}")
    log(traceback.format_exc())

out.close()
import os; os._exit(0)
