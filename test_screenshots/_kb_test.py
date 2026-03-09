import os
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
import requests
r = requests.get('http://127.0.0.1:5000/api/learning/kb/list', timeout=10)
kbs = r.json().get('kbs', [])
print("Status:", r.status_code, "KBs:", len(kbs))
for kb in kbs[:8]:
    print(" ", kb["name"], ":", kb["doc_count"])
