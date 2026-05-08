// Provider settings - uses dynamic model fetching from API
// Key flow: select provider → input API key → click "validate & load models" → select model
// Per-provider key storage: keys are saved per provider and restored on switch

var PROVIDER_KEYS_CACHE = {};
var PROVIDER_URLS_CACHE = {};
var PREVIOUS_CHAT_PROVIDER = null;

// AppConfigUtil: syncs UI config to localStorage and restores on page load
var AppConfigUtil = (function() {
    function syncChatModel() {
        var provider = document.getElementById('chatProvider')?.value || 'ollama';
        var model = document.getElementById('chatModelName')?.value || '';
        AppState.set('chatProvider', provider);
        if (model) AppState.set('chatModel_' + provider, model);
    }

    function syncResearchModel() {
        var providerEl = document.getElementById('researchProvider') || document.getElementById('r-provider');
        var modelEl = document.getElementById('researchModelSelect') || document.getElementById('r-modelSelect');
        var provider = providerEl ? providerEl.value : 'ollama';
        var model = modelEl ? modelEl.value : '';
        AppState.set('researchProvider', provider);
        if (model) AppState.set('researchModel_' + provider, model);
    }

    function restoreResearchProvider() {
        var savedProvider = AppState.get('researchProvider', '');
        if (!savedProvider) return;

        var providerEl = document.getElementById('researchProvider') || document.getElementById('r-provider');
        if (!providerEl) return;

        providerEl.value = savedProvider;

        var modelEl = document.getElementById('researchModelSelect') || document.getElementById('r-modelSelect');
        var savedModel = AppState.get('researchModel_' + savedProvider, '');
        var cachedModels = AppState.get('researchModels_' + savedProvider, []);

        if (modelEl && cachedModels.length > 0 && savedProvider !== 'ollama') {
            modelEl.innerHTML = '<option value="">-- 选择模型 --</option>' +
                cachedModels.map(function(m) {
                    return '<option value="' + m + '"' + (m === savedModel ? ' selected' : '') + '>' + m + '</option>';
                }).join('');
        }

        if (providerEl.id === 'r-provider' && typeof ResearchModule !== 'undefined' && ResearchModule.onProviderChange) {
            ResearchModule.onProviderChange();
        } else if (typeof onResearchProviderChange === 'function') {
            onResearchProviderChange();
        }
    }

    function restoreChatProvider() {
        var savedProvider = AppState.get('chatProvider', '');
        if (!savedProvider) return;

        var providerSelect = document.getElementById('chatProvider');
        if (!providerSelect) return;

        providerSelect.value = savedProvider;
        onChatProviderChange();

        var savedModel = AppState.get('chatModel_' + savedProvider, '');
        var cachedModels = AppState.get('chatModels_' + savedProvider, []);

        if (savedProvider !== 'ollama' && cachedModels.length > 0) {
            var modelSelect = document.getElementById('chatModelName');
            if (modelSelect) {
                var hasOption = false;
                for (var i = 0; i < modelSelect.options.length; i++) {
                    if (modelSelect.options[i].value === savedModel) { hasOption = true; break; }
                }
                if (!hasOption && cachedModels.length > 0) {
                    modelSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                        cachedModels.map(function(m) {
                            return '<option value="' + m + '"' + (m === savedModel ? ' selected' : '') + '>' + m + '</option>';
                        }).join('');
                } else if (savedModel) {
                    modelSelect.value = savedModel;
                }
            }
        }
    }

    function restoreResearchProvider() {
        var savedProvider = AppState.get('researchProvider', '');
        if (!savedProvider) return;

        var providerEl = document.getElementById('researchProvider');
        if (!providerEl) return;

        providerEl.value = savedProvider;
        if (typeof onResearchProviderChange === 'function') onResearchProviderChange();

        var savedModel = AppState.get('researchModel_' + savedProvider, '');
        var cachedModels = AppState.get('researchModels_' + savedProvider, []);

        if (savedProvider !== 'ollama' && cachedModels.length > 0) {
            var modelSelect = document.getElementById('researchModelSelect');
            if (modelSelect) {
                modelSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                    cachedModels.map(function(m) {
                        return '<option value="' + m + '"' + (m === savedModel ? ' selected' : '') + '>' + m + '</option>';
                    }).join('');
            }
        }
    }

    return {
        syncChatModel: syncChatModel,
        syncResearchModel: syncResearchModel,
        restoreChatProvider: restoreChatProvider,
        restoreResearchProvider: restoreResearchProvider
    };
})();

async function loadProviderKeysCache() {
    if (window.SERVER_CONFIG) {
        PROVIDER_KEYS_CACHE = window.SERVER_CONFIG.providerKeys || {};
        PROVIDER_URLS_CACHE = window.SERVER_CONFIG.providerBaseUrls || {};
        var currentProvider = window.SERVER_CONFIG.chatProvider;
        var currentKey = window.SERVER_CONFIG.chatApiKey;
        var currentUrl = window.SERVER_CONFIG.chatApiBaseUrl;
        if (currentProvider && currentKey) {
            PROVIDER_KEYS_CACHE[currentProvider] = currentKey;
        }
        if (currentProvider && currentUrl) {
            PROVIDER_URLS_CACHE[currentProvider] = currentUrl;
        }
        PREVIOUS_CHAT_PROVIDER = currentProvider || 'ollama';
    }
    try {
        var res = await fetch('/api/provider/keys');
        var data = await res.json();
        var serverKeys = data.provider_keys || {};
        var serverUrls = data.provider_base_urls || {};
        for (var k in serverKeys) { PROVIDER_KEYS_CACHE[k] = serverKeys[k]; }
        for (var k in serverUrls) { PROVIDER_URLS_CACHE[k] = serverUrls[k]; }
    } catch (e) {
        console.warn('Failed to load provider keys from API, using embedded config:', e);
    }
}

function initChatProviderUI() {
    var chatProvider = document.getElementById('chatProvider');
    if (!chatProvider) return;
    var provider = chatProvider.value || 'ollama';
    PREVIOUS_CHAT_PROVIDER = provider;

    var config = getProviderConfig(provider);
    var apiKeyGroup = document.getElementById('chatApiKeyGroup');
    var baseUrlGroup = document.getElementById('chatApiBaseUrlGroup');
    var apiKeyInput = document.getElementById('chatApiKey');
    var baseUrlInput = document.getElementById('chatApiBaseUrl');

    if (apiKeyGroup) apiKeyGroup.style.display = config?.requires_key ? 'block' : 'none';
    if (baseUrlGroup) baseUrlGroup.style.display = provider === 'custom' ? 'block' : 'none';

    if (apiKeyInput && config?.requires_key) {
        apiKeyInput.value = PROVIDER_KEYS_CACHE[provider] || '';
    }
    if (baseUrlInput) {
        if (provider === 'custom') {
            baseUrlInput.value = PROVIDER_URLS_CACHE[provider] || '';
        } else if (config?.base_url) {
            baseUrlInput.value = PROVIDER_URLS_CACHE[provider] || config.base_url;
        }
    }

    resetChatModelSelect(provider);
}

function initResearchProviderSelect() {
    var providerSelect = document.getElementById('researchProvider');
    if (!providerSelect) return;
    if (typeof getProviderSelectOptions === 'function') {
        providerSelect.innerHTML = getProviderSelectOptions() + '<option value="custom">自定义 API</option>';
    }
    onResearchProviderChange();
}

document.addEventListener('DOMContentLoaded', function() {
    loadProviderKeysCache().then(function() {
        initChatProviderUI();
        AppConfigUtil.restoreChatProvider();
        AppConfigUtil.restoreResearchProvider();

        var chatModelSelect = document.getElementById('chatModelName');
        if (chatModelSelect) {
            chatModelSelect.addEventListener('change', function() {
                AppConfigUtil.syncChatModel();
            });
        }
        var researchModelSelect = document.getElementById('researchModelSelect');
        if (researchModelSelect) {
            researchModelSelect.addEventListener('change', function() {
                AppConfigUtil.syncResearchModel();
            });
        }

        if (typeof restoreNavState === 'function') restoreNavState();
    });
});

// Chat provider functions
function onChatProviderChange() {
    var provider = document.getElementById('chatProvider')?.value || 'ollama';
    var config = getProviderConfig(provider);

    var apiKeyGroup = document.getElementById('chatApiKeyGroup');
    var baseUrlGroup = document.getElementById('chatApiBaseUrlGroup');
    var ollamaCard = document.getElementById('ollamaChatModelCard');
    var apiKeyInput = document.getElementById('chatApiKey');
    var baseUrlInput = document.getElementById('chatApiBaseUrl');

    // Save current provider's key before switching
    if (PREVIOUS_CHAT_PROVIDER && apiKeyInput) {
        var currentKey = apiKeyInput.value.trim();
        var currentUrl = baseUrlInput ? baseUrlInput.value.trim() : '';
        if (currentKey) {
            PROVIDER_KEYS_CACHE[PREVIOUS_CHAT_PROVIDER] = currentKey;
        }
        if (currentUrl && PREVIOUS_CHAT_PROVIDER !== 'ollama') {
            PROVIDER_URLS_CACHE[PREVIOUS_CHAT_PROVIDER] = currentUrl;
        }
        saveProviderKeyToServer(PREVIOUS_CHAT_PROVIDER, currentKey, currentUrl, 'chat');
    }

    if (apiKeyGroup) apiKeyGroup.style.display = config?.requires_key ? 'block' : 'none';
    if (baseUrlGroup) baseUrlGroup.style.display = provider === 'custom' ? 'block' : 'none';
    if (ollamaCard) ollamaCard.style.display = 'none';

    // Restore the new provider's saved key and URL
    if (apiKeyInput) {
        apiKeyInput.value = PROVIDER_KEYS_CACHE[provider] || '';
    }
    if (baseUrlInput) {
        if (config?.base_url && provider !== 'custom' && provider !== 'ollama') {
            baseUrlInput.value = PROVIDER_URLS_CACHE[provider] || config.base_url;
        } else {
            baseUrlInput.value = PROVIDER_URLS_CACHE[provider] || '';
        }
    }

    PREVIOUS_CHAT_PROVIDER = provider;
    resetChatModelSelect(provider);
    AppState.set('chatProvider', provider);

    // Restore cached models for this provider
    var cachedModels = AppState.get('chatModels_' + provider, []);
    var savedModel = AppState.get('chatModel_' + provider, '');
    if (cachedModels.length > 0 && provider !== 'ollama') {
        var modelSelect = document.getElementById('chatModelName');
        if (modelSelect) {
            modelSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                cachedModels.map(function(m) {
                    return '<option value="' + m + '"' + (m === savedModel ? ' selected' : '') + '>' + m + '</option>';
                }).join('');
            if (savedModel) modelSelect.value = savedModel;
        }
    }
}

function saveProviderKeyToServer(provider, apiKey, baseUrl, scope) {
    fetch('/api/provider/keys', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            provider: provider,
            api_key: apiKey || '',
            base_url: baseUrl || '',
            scope: scope || 'chat'
        })
    }).catch(function(e) {
        console.warn('Failed to persist provider key:', e);
    });
}

function resetChatModelSelect(provider) {
    var modelSelect = document.getElementById('chatModelName');
    if (!modelSelect) return;

    if (provider === 'ollama') {
        modelSelect.innerHTML = '<option value="">-- 点击"加载模型" --</option>';
    } else {
        modelSelect.innerHTML = '<option value="">-- 输入 API Key 后加载模型 --</option>';
        var config = getProviderConfig(provider);
        if (config.default_model) {
            modelSelect.innerHTML += '<option value="' + config.default_model + '">' + config.default_model + ' (推荐)</option>';
        }
    }
}

async function loadChatProviderModels() {
    var provider = document.getElementById('chatProvider')?.value || 'ollama';
    var modelSelect = document.getElementById('chatModelName');

    if (!modelSelect) return;

    if (provider === 'ollama') {
        try {
            var response = await fetch('/api/models');
            var data = await response.json();
            var models = data.chat_models || [];
            var currentModel = data.current_chat || '';

            if (models.length > 0) {
                modelSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                    models.map(function(m) { return '<option value="' + m + '"' + (m === currentModel ? ' selected' : '') + '>' + m + '</option>'; }).join('');
            } else {
                modelSelect.innerHTML = '<option value="">-- 无可用模型 --</option>';
            }
            AppState.set('chatModels_' + provider, models);
            AppConfigUtil.syncChatModel();
        } catch (e) {
            console.error('Failed to load Ollama models:', e);
            modelSelect.innerHTML = '<option value="">-- 加载失败 --</option>';
        }
        return;
    }

    var apiKey = document.getElementById('chatApiKey')?.value.trim() || '';
    var baseUrl = document.getElementById('chatApiBaseUrl')?.value.trim() || getProviderConfig(provider)?.base_url || '';
    var statusEl = document.getElementById('chatConnectionStatus');

    if (apiKey) {
        PROVIDER_KEYS_CACHE[provider] = apiKey;
    }
    if (baseUrl) {
        PROVIDER_URLS_CACHE[provider] = baseUrl;
    }
    saveProviderKeyToServer(provider, apiKey, baseUrl, 'chat');

    await fetchProviderModels(provider, apiKey, baseUrl, modelSelect, statusEl);

    var models = [];
    for (var i = 0; i < modelSelect.options.length; i++) {
        var opt = modelSelect.options[i];
        if (opt.value) models.push(opt.value);
    }
    AppState.set('chatModels_' + provider, models);
    AppConfigUtil.syncChatModel();
}

async function testChatConnection() {
    var provider = document.getElementById('chatProvider')?.value || 'ollama';
    var statusEl = document.getElementById('chatConnectionStatus');
    var modelSelect = document.getElementById('chatModelName');
    var config = getProviderConfig(provider);

    if (provider === 'ollama') {
        testOllamaConnection();
        return;
    }

    var apiKey = document.getElementById('chatApiKey')?.value.trim() || '';
    var baseUrl = document.getElementById('chatApiBaseUrl')?.value.trim() || config?.base_url || '';
    var modelName = modelSelect?.value || '';

    if (config?.requires_key && !apiKey) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">请输入 API Key</span>';
        return;
    }

    if (!baseUrl) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">请输入 Base URL</span>';
        return;
    }

    if (!modelName) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #ff9800;">请先选择或输入模型名</span>';
        return;
    }

    if (statusEl) statusEl.innerHTML = '<span style="color: var(--text-muted);">测试连接中...</span>';

    try {
        var res = await fetch('/api/test-api', {
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
        var data = await res.json();

        if (data.success) {
            if (statusEl) statusEl.innerHTML = '<span style="color: #4caf50;">✓ 连接成功！</span>';
            showToast('连接成功！', 'success');
        } else {
            if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">✗ ' + (data.message || '连接失败') + '</span>';
        }
    } catch (e) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">错误: ' + e.message + '</span>';
    }
}

function getChatProviderBaseUrl() {
    var provider = document.getElementById('chatProvider')?.value || 'ollama';
    var config = getProviderConfig(provider);

    if (provider === 'custom') {
        return document.getElementById('chatApiBaseUrl')?.value.trim() || '';
    }

    return config?.base_url || '';
}

// Research provider functions
var PREVIOUS_RESEARCH_PROVIDER = null;

function onResearchProviderChange() {
    var provider = document.getElementById('researchProvider')?.value || 'ollama';
    var config = getProviderConfig(provider);
    var modelSelect = document.getElementById('researchModelSelect');
    var apiStatusEl = document.getElementById('researchProviderStatus');
    var apiKeyEl = document.getElementById('researchApiKey');
    var customUrlDiv = document.getElementById('researchCustomUrl');
    var customUrlInput = document.getElementById('researchCustomUrlInput');

    // Save current provider's key before switching
    if (PREVIOUS_RESEARCH_PROVIDER && apiKeyEl) {
        var oldKey = apiKeyEl.value.trim();
        var oldUrl = customUrlInput ? customUrlInput.value.trim() : '';
        if (oldKey) {
            PROVIDER_KEYS_CACHE[PREVIOUS_RESEARCH_PROVIDER + '_research'] = oldKey;
        }
        if (oldUrl) {
            PROVIDER_URLS_CACHE[PREVIOUS_RESEARCH_PROVIDER + '_research'] = oldUrl;
        }
        saveProviderKeyToServer(PREVIOUS_RESEARCH_PROVIDER, oldKey, oldUrl, 'research');
    }

    if (customUrlDiv) customUrlDiv.style.display = provider === 'custom' ? 'block' : 'none';

    // Restore saved key for the new provider
    if (apiKeyEl) {
        var savedKey = PROVIDER_KEYS_CACHE[provider + '_research'] || '';
        apiKeyEl.value = savedKey;
        apiKeyEl.placeholder = config.requires_key ? 'API Key (必填)' : 'API Key (本地无需)';
    }

    if (customUrlInput && provider === 'custom') {
        customUrlInput.value = PROVIDER_URLS_CACHE[provider + '_research'] || '';
    }

    if (modelSelect) {
        if (provider === 'ollama') {
            modelSelect.innerHTML = '<option value="">-- 点击"加载"获取模型 --</option>';
        } else {
            modelSelect.innerHTML = '<option value="">-- 输入 API Key 后点击"加载" --</option>';
            if (config.default_model) {
                modelSelect.innerHTML += '<option value="' + config.default_model + '">' + config.default_model + ' (推荐)</option>';
            }
        }
    }

    if (apiStatusEl) {
        var helpHtml = '<small>' + (config.help || '') + '</small>';
        if (config.key_url && config.requires_key) {
            helpHtml += ' <a href="' + config.key_url + '" target="_blank">获取Key</a>';
        }
        apiStatusEl.innerHTML = helpHtml;
    }

    PREVIOUS_RESEARCH_PROVIDER = provider;
    AppState.set('researchProvider', provider);

    // Restore cached models for this provider
    var cachedModels = AppState.get('researchModels_' + provider, []);
    var savedModel = AppState.get('researchModel_' + provider, '');
    if (cachedModels.length > 0 && provider !== 'ollama') {
        if (modelSelect) {
            modelSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                cachedModels.map(function(m) {
                    return '<option value="' + m + '"' + (m === savedModel ? ' selected' : '') + '>' + m + '</option>';
                }).join('');
            if (savedModel) modelSelect.value = savedModel;
        }
    }
}

function getResearchBaseUrl(provider) {
    var config = getProviderConfig(provider);
    var baseUrl = config?.base_url || '';

    if (provider === 'custom') {
        var customUrlInput = document.getElementById('researchCustomUrlInput');
        baseUrl = customUrlInput?.value.trim() || '';
    }

    return baseUrl;
}

async function loadResearchModels() {
    var provider = document.getElementById('researchProvider')?.value || 'ollama';
    var apiKey = document.getElementById('researchApiKey')?.value.trim() || '';
    var modelSelect = document.getElementById('researchModelSelect');
    var statusEl = document.getElementById('researchProviderStatus');
    var baseUrl = getResearchBaseUrl(provider);

    if (provider === 'custom' && !baseUrl) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">请先输入 API URL</span>';
        return;
    }

    if (provider === 'ollama') {
        var ollamaUrl = document.getElementById('researchOllamaUrl')?.value?.trim() || 'http://localhost:11434';
        try {
            var res = await fetch('/api/provider/models', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({provider: 'ollama', base_url: ollamaUrl})
            });
            var data = await res.json();
            if (data.success && data.models?.length > 0) {
                if (modelSelect) {
                    var defaultModel = data.default_model || '';
                    modelSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                        data.models.map(function(m) {
                            var sel = (m === defaultModel) ? ' selected' : '';
                            return '<option value="' + m + '"' + sel + '>' + m + '</option>';
                        }).join('');
                }
                if (statusEl) statusEl.innerHTML = '<span style="color: #4caf50;">✓ 加载了 ' + data.models.length + ' 个模型</span>';
                AppState.set('researchModels_ollama', data.models);
                if (defaultModel) AppState.set('researchModel_ollama', defaultModel);
            } else {
                if (modelSelect) modelSelect.innerHTML = '<option value="">-- 无可用模型 --</option>';
                if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">无法获取模型列表</span>';
            }
        } catch (e) {
            if (modelSelect) modelSelect.innerHTML = '<option value="">-- 加载失败 --</option>';
            if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">错误: ' + e.message + '</span>';
        }
        return;
    }

    // Persist research key
    if (apiKey) {
        PROVIDER_KEYS_CACHE[provider + '_research'] = apiKey;
    }
    if (baseUrl) {
        PROVIDER_URLS_CACHE[provider + '_research'] = baseUrl;
    }
    saveProviderKeyToServer(provider, apiKey, baseUrl, 'research');

    await fetchProviderModels(provider, apiKey, baseUrl, modelSelect, statusEl);

    var models = [];
    for (var i = 0; i < modelSelect.options.length; i++) {
        var opt = modelSelect.options[i];
        if (opt.value) models.push(opt.value);
    }
    AppState.set('researchModels_' + provider, models);
    AppConfigUtil.syncResearchModel();
}

async function testResearchApi() {
    var provider = document.getElementById('researchProvider')?.value || 'ollama';
    var apiKey = document.getElementById('researchApiKey')?.value.trim() || '';
    var modelSelect = document.getElementById('researchModelSelect');
    var statusEl = document.getElementById('researchProviderStatus');

    var modelName = modelSelect?.value || '';
    var baseUrl = getResearchBaseUrl(provider);
    var config = getProviderConfig(provider);

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
        var res = await fetch('/api/test-api', {
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
        var data = await res.json();

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