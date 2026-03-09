"""Test API endpoints one at a time."""
import sys, json

out = open('_test2_out.txt', 'w', encoding='utf-8')

def log(msg):
    out.write(msg + '\n')
    out.flush()

try:
    sys.stderr = open('_test2_err.txt', 'w', encoding='utf-8')
    from gangdan.app import app
    app.config['TESTING'] = True
    c = app.test_client()
    log("App loaded OK")

    # 1
    log("Testing /api/learning/kb/list...")
    r = c.get('/api/learning/kb/list')
    d = r.get_json()
    log(f"  status={r.status_code}, kbs_count={len(d.get('kbs',[]))}")

    # 2
    log("Testing /api/learning/questions/list...")
    r = c.get('/api/learning/questions/list')
    d = r.get_json()
    log(f"  status={r.status_code}, keys={list(d.keys())}")

    # 3
    log("Testing /api/learning/guide/sessions...")
    r = c.get('/api/learning/guide/sessions')
    d = r.get_json()
    log(f"  status={r.status_code}, keys={list(d.keys())}")

    # 4
    log("Testing /api/learning/research/reports...")
    r = c.get('/api/learning/research/reports')
    d = r.get_json()
    log(f"  status={r.status_code}, keys={list(d.keys())}")

    # 5 POST validation
    log("Testing POST questions/generate (no kb)...")
    r = c.post('/api/learning/questions/generate', data=json.dumps({'topic':'test'}), content_type='application/json')
    log(f"  status={r.status_code}, body={r.get_json()}")

    # 6
    log("Testing POST guide/create (empty kb)...")
    r = c.post('/api/learning/guide/create', data=json.dumps({'kb_names':[]}), content_type='application/json')
    log(f"  status={r.status_code}, body={r.get_json()}")

    # 7
    log("Testing POST research/run (empty kb)...")
    r = c.post('/api/learning/research/run', data=json.dumps({'topic':'t','kb_names':[]}), content_type='application/json')
    log(f"  status={r.status_code}, body={r.get_json()}")

    # 8 404s
    log("Testing 404s...")
    r = c.get('/api/learning/guide/session/xxx')
    log(f"  guide/session/xxx: {r.status_code}")
    r = c.get('/api/learning/questions/xxx')
    log(f"  questions/xxx: {r.status_code}")
    r = c.get('/api/learning/research/report/xxx')
    log(f"  research/report/xxx: {r.status_code}")

    log("ALL DONE")

except Exception as e:
    import traceback
    log(f"EXCEPTION: {e}")
    log(traceback.format_exc())

out.close()
