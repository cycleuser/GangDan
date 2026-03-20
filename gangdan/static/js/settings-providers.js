// Provider configurations - synced with providers.js
// This file provides settings-specific functions

function initResearchProviderSelect() {
    const providerSelect = document.getElementById('researchProvider');
    if (!providerSelect) return;
    
    if (typeof getProviderSelectOptions === 'function') {
        providerSelect.innerHTML = getProviderSelectOptions() + '<option value="custom">自定义 API</option>';
    }
    
    onResearchProviderChange();
}

function onResearchProviderChange() {
    const provider = document.getElementById('researchProvider')?.value || 'ollama';
    const customUrlDiv = document.getElementById('researchCustomUrl');
    const modelSelect = document.getElementById('researchModelSelect');
    const statusEl = document.getElementById('researchProviderStatus');
    
    if (customUrlDiv) customUrlDiv.style.display = provider === 'custom' ? 'block' : 'none';
    
    const config = getProviderConfig(provider);
    
    if (modelSelect) {
        if (provider === 'ollama') {
            modelSelect.innerHTML = '<option value="">-- 点击"加载模型"--</option>';
        } else if (config?.models?.length > 0) {
            modelSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                config.models.map(m => `<option value="${m}">${m}</option>`).join('');
            if (config.default_model) {
                modelSelect.value = config.default_model;
            }
        } else {
            modelSelect.innerHTML = '<option value="">-- 输入 URL 后加载 --</option>';
        }
    }
    
    if (statusEl) {
        if (provider === 'ollama') {
            statusEl.innerHTML = '<small style="color: var(--text-muted);">本地 Ollama，点击"加载模型"</small>';
        } else if (config?.help) {
            let statusHtml = '<small style="color: var(--text-muted);">' + config.help + '</small>';
            if (config.key_url) {
                statusHtml += ' <a href="' + config.key_url + '" target="_blank" style="font-size: 0.85em;">获取 Key</a>';
            }
            statusEl.innerHTML = statusHtml;
        } else {
            statusEl.innerHTML = '';
        }
    }
}

function getResearchBaseUrl(provider) {
    const config = getProviderConfig(provider);
    let baseUrl = config?.base_url || '';
    
    if (provider === 'custom') {
        const customUrlInput = document.getElementById('researchCustomUrlInput');
        baseUrl = customUrlInput?.value.trim() || '';
    }
    
    return baseUrl;
}

async function loadResearchModels() {
    const provider = document.getElementById('researchProvider')?.value || 'ollama';
    const apiKey = document.getElementById('researchApiKey')?.value.trim() || '';
    const modelSelect = document.getElementById('researchModelSelect');
    const statusEl = document.getElementById('researchProviderStatus');
    
    const config = getProviderConfig(provider);
    let baseUrl = getResearchBaseUrl(provider);
    
    if (provider === 'custom' && !baseUrl) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">请先输入 API URL</span>';
        return;
    }
    
    if (config?.requires_key && !apiKey) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">请输入 API Key</span>';
        return;
    }
    
    // For providers with preset models
    if (config?.models?.length > 0 && provider !== 'ollama') {
        if (modelSelect) {
            modelSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                config.models.map(m => `<option value="${m}">${m}</option>`).join('');
            if (config.default_model) {
                modelSelect.value = config.default_model;
            }
        }
        if (statusEl) statusEl.innerHTML = '<span style="color: #4caf50;">✓ 已加载 ' + config.models.length + ' 个模型</span>';
        return;
    }
    
    if (statusEl) statusEl.innerHTML = '<span style="color: var(--text-muted);">加载模型中...</span>';
    
    try {
        const res = await fetch('/api/test-api', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({base_url: baseUrl, api_key: apiKey})
        });
        const data = await res.json();
        
        if (data.success && data.models?.length > 0) {
            if (modelSelect) {
                modelSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                    data.models.map(m => `<option value="${m}">${m}</option>`).join('');
            }
            if (statusEl) statusEl.innerHTML = '<span style="color: #4caf50;">✓ 加载了 ' + data.models.length + ' 个模型</span>';
        } else {
            if (modelSelect) modelSelect.innerHTML = '<option value="">-- 手动输入模型名 --</option>';
            if (statusEl) statusEl.innerHTML = '<span style="color: #ff9800;">无法列出模型 - 请手动输入</span>';
        }
    } catch (e) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">错误: ' + e.message + '</span>';
    }
}

async function testResearchApi() {
    const provider = document.getElementById('researchProvider')?.value || 'ollama';
    const apiKey = document.getElementById('researchApiKey')?.value.trim() || '';
    const modelSelect = document.getElementById('researchModelSelect');
    const statusEl = document.getElementById('researchProviderStatus');
    
    const modelName = modelSelect?.value || '';
    const baseUrl = getResearchBaseUrl(provider);
    const config = getProviderConfig(provider);
    
    if (config?.requires_key && !apiKey) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">请输入 API Key</span>';
        return;
    }
    
    if (!modelName) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #ff9800;">请先选择模型</span>';
        return;
    }
    
    if (statusEl) statusEl.innerHTML = '<span style="color: var(--text-muted);">测试连接中...</span>';
    
    try {
        const res = await fetch('/api/test-api', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                base_url: baseUrl,
                api_key: apiKey,
                model: modelName,
                test_chat: true,
                api_type: config?.api_type || 'openai'
            })
        });
        const data = await res.json();
        
        if (data.success) {
            if (statusEl) statusEl.innerHTML = '<span style="color: #4caf50;">✓ 连接成功！</span>';
            showToast('连接成功！', 'success');
        } else {
            if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">✗ ' + (data.error || '连接失败') + '</span>';
        }
    } catch (e) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">错误: ' + e.message + '</span>';
    }
}