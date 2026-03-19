// ============================================
// Settings Panel Functions
// ============================================

async function loadModels() {
    const response = await fetch('/api/models');
    const data = await response.json();
    
    const ollamaStatusEl = document.getElementById('ollamaStatus');
    if (data.ollama_available) {
        ollamaStatusEl.innerHTML = '<span class="status-dot online"></span> Ollama Online';
    } else {
        ollamaStatusEl.innerHTML = '<span class="status-dot offline"></span> Ollama Offline';
    }
    
    const chatSelect = document.getElementById('chatModel');
    const embedSelect = document.getElementById('embedModel');
    const rerankerSelect = document.getElementById('rerankerModel');
    const vectorDbSelect = document.getElementById('vectorDbType');
    const researchModelList = document.getElementById('researchModelList');
    
    chatSelect.innerHTML = '<option value="">-- Select --</option>' +
        (data.chat_models || []).map(m => `<option value="${m}" ${m === data.current_chat ? 'selected' : ''}>${m}</option>`).join('');
    
    embedSelect.innerHTML = '<option value="">-- Select --</option>' +
        (data.embed_models || []).map(m => `<option value="${m}" ${m === data.current_embed ? 'selected' : ''}>${m}</option>`).join('');
    
    rerankerSelect.innerHTML = '<option value="">-- None --</option>' +
        (data.reranker_models || []).map(m => `<option value="${m}" ${m === data.current_reranker ? 'selected' : ''}>${m}</option>`).join('');
    
    if (vectorDbSelect && data.vector_db_type) {
        vectorDbSelect.value = data.vector_db_type;
    }
    
    if (researchModelList && data.research_models) {
        researchModelList.innerHTML = data.research_models.map(m => `<option value="${m}">`).join('');
    }
    
    const researchModelInput = document.getElementById('researchModel');
    if (data.current_research_model && !researchModelInput.value) {
        researchModelInput.value = data.current_research_model;
    }
}

function onResearchProviderChange() {
    const provider = document.getElementById('researchProvider').value;
    const apiKeyGroup = document.getElementById('researchApiKeyGroup');
    const baseUrlGroup = document.getElementById('researchBaseUrlGroup');
    
    if (provider === 'ollama') {
        apiKeyGroup.style.display = 'none';
        baseUrlGroup.style.display = 'none';
    } else {
        apiKeyGroup.style.display = 'block';
        baseUrlGroup.style.display = provider === 'custom' ? 'block' : 'none';
    }
    
    document.getElementById('researchProviderStatus').innerHTML = '';
}

async function testOllamaConnection() {
    const url = document.getElementById('ollamaUrl').value;
    const statusEl = document.getElementById('ollamaStatus');
    statusEl.innerHTML = '<span class="status-dot"></span> Testing...';
    
    const response = await fetch('/api/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
    });
    const data = await response.json();
    
    if (data.success) {
        statusEl.innerHTML = '<span class="status-dot online"></span> ' + data.message;
        loadModels();
    } else {
        statusEl.innerHTML = '<span class="status-dot offline"></span> ' + data.message;
    }
}

async function testResearchProvider() {
    const provider = document.getElementById('researchProvider').value;
    const apiKey = document.getElementById('researchApiKey').value;
    const baseUrl = document.getElementById('researchBaseUrl').value;
    const statusEl = document.getElementById('researchProviderStatus');
    
    if (provider === 'ollama') {
        statusEl.innerHTML = '<span class="status-dot online"></span> Using local Ollama';
        return;
    }
    
    if (!apiKey) {
        statusEl.innerHTML = '<span class="status-dot offline"></span> API key required';
        return;
    }
    
    statusEl.innerHTML = '<span class="status-dot"></span> Testing...';
    
    const response = await fetch('/api/test-provider', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            provider,
            api_key: apiKey,
            base_url: baseUrl
        })
    });
    const data = await response.json();
    
    if (data.success) {
        let msg = data.message;
        if (data.models && data.models.length > 0) {
            msg += ` (${data.models.slice(0, 3).join(', ')}...)`;
        }
        statusEl.innerHTML = `<span class="status-dot online"></span> ${msg}`;
        
        const researchModelList = document.getElementById('researchModelList');
        if (researchModelList && data.models) {
            researchModelList.innerHTML = data.models.map(m => `<option value="${m}">`).join('');
        }
    } else {
        statusEl.innerHTML = `<span class="status-dot offline"></span> ${data.message}`;
    }
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
    
    const settingsProxyMode = document.getElementById('proxyMode');
    if (settingsProxyMode) settingsProxyMode.value = mode;
    
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
        vector_db_type: document.getElementById('vectorDbType').value,
        research_provider: document.getElementById('researchProvider').value,
        research_api_key: document.getElementById('researchApiKey').value,
        research_api_base_url: document.getElementById('researchBaseUrl').value,
        research_model: document.getElementById('researchModel').value,
    };
    
    const response = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
    });
    const data = await response.json();
    showToast(data.message, data.success ? 'success' : 'error');
    if (data.success) {
        loadModels();
    }
}

async function updateVectorDbType() {
    const vectorDbType = document.getElementById('vectorDbType').value;
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ vector_db_type: vectorDbType })
        });
        const data = await response.json();
        if (data.success) {
            showToast(getT('vector_db_restart_required') || 'Changing vector DB requires app restart', 'warning');
        }
    } catch (e) {
        console.error('Failed to update vector DB type:', e);
        showToast('Failed to update setting', 'error');
    }
}

// Init
document.addEventListener('DOMContentLoaded', () => {
    loadModels();
    refreshDocs();
    loadKbList();
});