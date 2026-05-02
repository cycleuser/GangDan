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
        
        const embedSelect = document.getElementById('embedModel');
        const rerankerSelect = document.getElementById('rerankerModel');
        const translateSelect = document.getElementById('translateModel');
        
        if (embedSelect) {
            embedSelect.innerHTML = '<option value="">-- Select --</option>' +
                (data.embed_models || []).map(m => `<option value="${m}" ${m === data.current_embed ? 'selected' : ''}>${m}</option>`).join('');
        }
        
        if (rerankerSelect) {
            rerankerSelect.innerHTML = '<option value="">-- None --</option>' +
                (data.reranker_models || []).map(m => `<option value="${m}" ${m === data.current_reranker ? 'selected' : ''}>${m}</option>`).join('');
        }
        
        if (translateSelect) {
            const chatModels = data.chat_models || [];
            translateSelect.innerHTML = '<option value="">Use Chat Model</option>' +
                chatModels.map(m => `<option value="${m}" ${m === data.current_translate_model ? 'selected' : ''}>${m}</option>`).join('');
        }
        
        // Populate chatModelName based on current provider
        const chatModelNameSelect = document.getElementById('chatModelName');
        const currentProvider = document.getElementById('chatProvider')?.value || 'ollama';
        if (chatModelNameSelect) {
            if (currentProvider === 'ollama') {
                const models = data.chat_models || [];
                const currentModel = data.current_chat || '';
                if (models.length > 0) {
                    chatModelNameSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                        models.map(m => `<option value="${m}" ${m === currentModel ? 'selected' : ''}>${m}</option>`).join('');
                } else {
                    chatModelNameSelect.innerHTML = '<option value="">-- 无可用模型 --</option>';
                }
            } else if (data.chat_provider_models && data.chat_provider_models.length > 0) {
                const currentModel = data.current_chat_provider_model || '';
                chatModelNameSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                    data.chat_provider_models.map(m => `<option value="${m}" ${m === currentModel ? 'selected' : ''}>${m}</option>`).join('');
            } else {
                const config = getProviderConfig(currentProvider);
                if (config?.models?.length > 0) {
                    chatModelNameSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                        config.models.map(m => `<option value="${m}" ${m === (data.current_chat_provider_model || config.default_model) ? 'selected' : ''}>${m}</option>`).join('');
                }
            }
        }
        
        // Load model parameters
        const settingsTemp = document.getElementById('settingsTemperature');
        const settingsTempVal = document.getElementById('settingsTempVal');
        if (settingsTemp && data.chat_temperature !== undefined) {
            settingsTemp.value = data.chat_temperature;
            if (settingsTempVal) settingsTempVal.textContent = data.chat_temperature;
        }
        
        const settingsMaxTokens = document.getElementById('settingsMaxTokens');
        if (settingsMaxTokens && data.chat_max_tokens !== undefined) {
            settingsMaxTokens.value = data.chat_max_tokens;
        }
        
        const settingsRag = document.getElementById('settingsRagThreshold');
        const settingsDistVal = document.getElementById('settingsDistVal');
        if (settingsRag && data.rag_distance_threshold !== undefined) {
            settingsRag.value = data.rag_distance_threshold;
            if (settingsDistVal) settingsDistVal.textContent = data.rag_distance_threshold;
        }
        
        // Sync chat panel advanced params
        const chatTemp = document.getElementById('chatTemperature');
        const tempVal = document.getElementById('tempVal');
        if (chatTemp && data.chat_temperature !== undefined) {
            chatTemp.value = data.chat_temperature;
            if (tempVal) tempVal.textContent = data.chat_temperature;
        }
        
        const chatDist = document.getElementById('ragDistance');
        const distVal = document.getElementById('distVal');
        if (chatDist && data.rag_distance_threshold !== undefined) {
            chatDist.value = data.rag_distance_threshold;
            if (distVal) distVal.textContent = data.rag_distance_threshold;
        }
        
        const chatMaxTok = document.getElementById('chatMaxTokens');
        if (chatMaxTok && data.chat_max_tokens !== undefined) {
            chatMaxTok.value = data.chat_max_tokens;
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
    
    const maxContextTokensInput = document.getElementById('maxContextTokens')?.value;
    const maxContextTokens = Math.max(500, Math.min(100000, parseInt(maxContextTokensInput) || 3000));
    
    const chatProvider = document.getElementById('chatProvider')?.value || 'ollama';
    const chatProviderConfig = getProviderConfig(chatProvider);
    let chatApiBaseUrl = '';
    
    if (chatProvider === 'custom') {
        chatApiBaseUrl = document.getElementById('chatApiBaseUrl')?.value.trim() || '';
    } else if (chatProviderConfig?.base_url) {
        chatApiBaseUrl = chatProviderConfig.base_url;
    }
    
    const chatModelName = document.getElementById('chatModelName')?.value || '';
    
    const settings = {
        ollama_url: document.getElementById('ollamaUrl')?.value,
        chat_model: chatModelName,
        embed_model: document.getElementById('embedModel')?.value,
        reranker_model: document.getElementById('rerankerModel')?.value,
        translate_model: document.getElementById('translateModel')?.value || '',
        context_length: contextLength,
        max_context_tokens: maxContextTokens,
        output_language: document.getElementById('outputLanguage')?.value || 'zh',
        proxy_mode: document.getElementById('proxyMode')?.value,
        proxy_http: document.getElementById('proxyHttp')?.value,
        proxy_https: document.getElementById('proxyHttps')?.value,
        vector_db_type: document.getElementById('vectorDbType')?.value,
        strict_kb_mode: document.getElementById('strictKbMode')?.checked || false,
        chat_provider: chatProvider,
        chat_api_key: document.getElementById('chatApiKey')?.value.trim() || '',
        chat_api_base_url: chatApiBaseUrl,
        chat_model_name: chatModelName,
        rag_distance_threshold: parseFloat(document.getElementById('settingsRagThreshold')?.value) || 0.5,
        chat_temperature: parseFloat(document.getElementById('settingsTemperature')?.value) || 0.7,
        chat_max_tokens: parseInt(document.getElementById('settingsMaxTokens')?.value) || 4096,
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