// ============================================
// Settings Panel Functions
// ============================================

var memoryCheckInterval = null;

async function loadModels() {
    try {
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
        
        if (chatSelect) {
            chatSelect.innerHTML = '<option value="">-- Select --</option>' +
                (data.chat_models || []).map(m => `<option value="${m}" ${m === data.current_chat ? 'selected' : ''}>${m}</option>`).join('');
        }
        
        if (embedSelect) {
            embedSelect.innerHTML = '<option value="">-- Select --</option>' +
                (data.embed_models || []).map(m => `<option value="${m}" ${m === data.current_embed ? 'selected' : ''}>${m}</option>`).join('');
        }
        
        if (rerankerSelect) {
            rerankerSelect.innerHTML = '<option value="">-- None --</option>' +
                (data.reranker_models || []).map(m => `<option value="${m}" ${m === data.current_reranker ? 'selected' : ''}>${m}</option>`).join('');
        }
        
        updateMemoryUsage();
    } catch (e) {
        console.error('Failed to load models:', e);
        const ollamaStatusEl = document.getElementById('ollamaStatus');
        if (ollamaStatusEl) {
            ollamaStatusEl.innerHTML = '<span class="status-dot offline"></span> Error loading models';
        }
    }
}

async function updateMemoryUsage() {
    try {
        const res = await fetch('/api/memory');
        const data = await res.json();
        
        const memoryUsedEl = document.getElementById('memoryUsed');
        const modelsLoadedEl = document.getElementById('modelsLoaded');
        
        if (memoryUsedEl) {
            memoryUsedEl.textContent = data.total_memory_gb + ' GB';
        }
        if (modelsLoadedEl) {
            modelsLoadedEl.textContent = data.model_count;
        }
    } catch (e) {
        console.log('Memory check error:', e);
    }
}

async function testOllamaConnection() {
    const url = document.getElementById('ollamaUrl').value;
    const statusEl = document.getElementById('ollamaStatus');
    if (statusEl) statusEl.innerHTML = '<span class="status-dot"></span> Testing...';
    
    try {
        const response = await fetch('/api/test-connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await response.json();
        
        if (data.success) {
            if (statusEl) statusEl.innerHTML = '<span class="status-dot online"></span> ' + data.message;
            loadModels();
        } else {
            if (statusEl) statusEl.innerHTML = '<span class="status-dot offline"></span> ' + (data.message || 'Connection failed');
        }
    } catch (e) {
        if (statusEl) statusEl.innerHTML = '<span class="status-dot offline"></span> Error: ' + e.message;
    }
}

async function saveSettings() {
    const contextLengthInput = document.getElementById('contextLength')?.value;
    const contextLength = Math.max(512, Math.min(1000000, parseInt(contextLengthInput) || 4096));
    
    const settings = {
        ollama_url: document.getElementById('ollamaUrl')?.value,
        chat_model: document.getElementById('chatModel')?.value,
        embed_model: document.getElementById('embedModel')?.value,
        reranker_model: document.getElementById('rerankerModel')?.value,
        context_length: contextLength,
        proxy_mode: document.getElementById('proxyMode')?.value,
        proxy_http: document.getElementById('proxyHttp')?.value,
        proxy_https: document.getElementById('proxyHttps')?.value,
        vector_db_type: document.getElementById('vectorDbType')?.value,
        strict_kb_mode: document.getElementById('strictKbMode')?.checked || false,
    };
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        const data = await response.json();
        showToast(data.message || (data.success ? 'Settings saved' : 'Error'), data.success ? 'success' : 'error');
        if (data.success) {
            loadModels();
        }
    } catch (e) {
        showToast('Error saving settings: ' + e.message, 'error');
    }
}

function toggleProxyInputs() {
    const mode = document.getElementById('proxyMode')?.value;
    const manualInputs = document.getElementById('manualProxyInputs');
    if (manualInputs) manualInputs.style.display = mode === 'manual' ? 'grid' : 'none';
}

async function updateVectorDbType() {
    const vectorDbType = document.getElementById('vectorDbType')?.value;
    
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
    if (memoryCheckInterval) clearInterval(memoryCheckInterval);
    memoryCheckInterval = setInterval(updateMemoryUsage, 5000);
});