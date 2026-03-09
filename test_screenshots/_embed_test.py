import os
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
import requests
r = requests.post('http://localhost:11434/api/embeddings', json={
    'model': 'nomic-embed-text:latest',
    'prompt': 'test'
})
emb = r.json().get('embedding', [])
print("Status:", r.status_code, "embedding len:", len(emb))
