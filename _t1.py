import sys, os
sys.stdout = open('_t1_out.txt', 'w', encoding='utf-8')
sys.stderr = open('_t1_err.txt', 'w', encoding='utf-8')
from gangdan.app import app
print("imported", flush=True)
app.config['TESTING'] = True
c = app.test_client()
print("client ok", flush=True)
try:
    r = c.get('/api/learning/kb/list')
    print("status: " + str(r.status_code), flush=True)
    print("data: " + str(r.get_json()), flush=True)
except Exception as e:
    print("ERROR: " + str(e), flush=True)
    import traceback
    traceback.print_exc()
print("DONE", flush=True)
sys.stdout.close()
sys.stderr.close()
