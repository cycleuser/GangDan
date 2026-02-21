// ============================================
// Settings Panel Functions
// ============================================

async function loadModels() {
    const response = await fetch('/api/models');
    const data = await response.json();
    
    // Update status
    const statusEl = document.getElementById('ollamaStatus');
    if (data.available) {
        statusEl.innerHTML = '<span class="status-dot online"></span> Ollama Online';
    } else {
        statusEl.innerHTML = '<span class="status-dot offline"></span> Ollama Offline';
    }
    
    // Populate model dropdowns
    const chatSelect = document.getElementById('chatModel');
    const embedSelect = document.getElementById('embedModel');
    const rerankerSelect = document.getElementById('rerankerModel');
    
    chatSelect.innerHTML = '<option value="">-- Select --</option>' +
        data.chat_models.map(m => `<option value="${m}" ${m === data.current_chat ? 'selected' : ''}>${m}</option>`).join('');
    
    embedSelect.innerHTML = '<option value="">-- Select --</option>' +
        data.embed_models.map(m => `<option value="${m}" ${m === data.current_embed ? 'selected' : ''}>${m}</option>`).join('');
    
    rerankerSelect.innerHTML = '<option value="">-- None --</option>' +
        data.reranker_models.map(m => `<option value="${m}" ${m === data.current_reranker ? 'selected' : ''}>${m}</option>`).join('');
}

async function testConnection() {
    const url = document.getElementById('ollamaUrl').value;
    const response = await fetch('/api/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
    });
    const data = await response.json();
    showToast(data.message, data.success ? 'success' : 'error');
}

function toggleProxyInputs() {
    const mode = document.getElementById('proxyMode').value;
    const manualInputs = document.getElementById('manualProxyInputs');
    manualInputs.style.display = mode === 'manual' ? 'grid' : 'none';
}

async function updateDocProxy() {
    const mode = document.getElementById('docProxyMode').value;
    const manualDiv = document.getElementById('docManualProxy');
    manualDiv.style.display = mode === 'manual' ? 'block' : 'none';
    
    // Also update settings panel if it exists
    const settingsProxyMode = document.getElementById('proxyMode');
    if (settingsProxyMode) settingsProxyMode.value = mode;
    
    // Save proxy settings immediately
    const proxyUrl = document.getElementById('docProxyUrl').value;
    const settings = {
        proxy_mode: mode,
        proxy_http: proxyUrl,
        proxy_https: proxyUrl,
    };
    
    await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
    });
    
    showToast('Proxy settings updated', 'success');
}

async function saveSettings() {
    const settings = {
        ollama_url: document.getElementById('ollamaUrl').value,
        chat_model: document.getElementById('chatModel').value,
        embed_model: document.getElementById('embedModel').value,
        reranker_model: document.getElementById('rerankerModel').value,
        proxy_mode: document.getElementById('proxyMode').value,
        proxy_http: document.getElementById('proxyHttp').value,
        proxy_https: document.getElementById('proxyHttps').value,
    };
    
    const response = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
    });
    const data = await response.json();
    showToast(data.message, data.success ? 'success' : 'error');
    loadModels();
}

// Init
document.addEventListener('DOMContentLoaded', () => {
    loadModels();
    refreshDocs();
});
