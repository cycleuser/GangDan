import sys

sys.stdout = open('_t4_out.txt', 'w', encoding='utf-8')
sys.stderr = open('_t4_err.txt', 'w', encoding='utf-8')

from gangdan.app import app
print("imported", flush=True)
app.config['TESTING'] = True
c = app.test_client()
print("client ok", flush=True)

try:
    r = c.get('/api/learning/kb/list')
    print("kb/list status: " + str(r.status_code), flush=True)
    d = r.get_json()
    print("kb count: " + str(len(d.get('kbs', []))), flush=True)
except Exception as e:
    print("ERROR: " + str(e), flush=True)

print("DONE", flush=True)
sys.stdout.close()
sys.stderr.close()
