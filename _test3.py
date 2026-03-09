"""Test API endpoints - all output to file."""
import sys, json

# Redirect everything BEFORE imports
out = open('_test3_out.txt', 'w', encoding='utf-8')
err = open('_test3_err.txt', 'w', encoding='utf-8')
sys.stdout = out
sys.stderr = err

def log(msg):
    out.write(msg + '\n')
    out.flush()

try:
    from gangdan.app import app
    app.config['TESTING'] = True
    c = app.test_client()
    log("App loaded OK")

    r = c.get('/api/learning/kb/list')
    log("kb/list: " + str(r.status_code))

    r = c.get('/api/learning/questions/list')
    log("q/list: " + str(r.status_code) + " -> " + str(r.get_json()))

    r = c.get('/api/learning/guide/sessions')
    log("g/sessions: " + str(r.status_code) + " -> " + str(r.get_json()))

    r = c.get('/api/learning/research/reports')
    log("r/reports: " + str(r.status_code) + " -> " + str(r.get_json()))

    r = c.post('/api/learning/questions/generate',
               data=json.dumps({'topic':'test'}),
               content_type='application/json')
    log("POST q/gen(no_kb): " + str(r.status_code) + " -> " + str(r.get_json()))

    r = c.post('/api/learning/guide/create',
               data=json.dumps({'kb_names':[]}),
               content_type='application/json')
    log("POST g/create(no_kb): " + str(r.status_code) + " -> " + str(r.get_json()))

    r = c.post('/api/learning/research/run',
               data=json.dumps({'topic':'t','kb_names':[]}),
               content_type='application/json')
    log("POST r/run(no_kb): " + str(r.status_code) + " -> " + str(r.get_json()))

    r = c.get('/api/learning/guide/session/xxx')
    log("g/session/xxx(404): " + str(r.status_code))

    r = c.get('/api/learning/questions/xxx')
    log("q/batch/xxx(404): " + str(r.status_code))

    r = c.get('/api/learning/research/report/xxx')
    log("r/report/xxx(404): " + str(r.status_code))

    log("ALL DONE")

except Exception as e:
    import traceback
    log("EXCEPTION: " + str(e))
    log(traceback.format_exc())

out.close()
err.close()
