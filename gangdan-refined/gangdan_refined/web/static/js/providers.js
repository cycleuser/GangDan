// Provider configurations - synced with gangdan/core/llm_client.py PROVIDER_CONFIGS
// Models are now fetched dynamically from the API after key validation.
// Only default_model is kept as a fallback hint.
var PROVIDER_CONFIGS = {
    ollama: {
        name: 'ollama',
        display_name: 'Ollama (本地)',
        api_type: 'ollama',
        base_url: 'http://localhost:11434',
        requires_key: false,
        models: [],
        key_url: '',
        help: '本地 Ollama 服务，无需 API Key，点击"加载模型"获取可用模型',
        default_model: ''
    },
    'bailian-coding': {
        name: 'bailian-coding',
        display_name: '阿里云百炼 Coding Plan',
        api_type: 'openai',
        base_url: 'https://coding.dashscope.aliyuncs.com/v1',
        requires_key: true,
        models: [],
        key_url: 'https://bailian.console.aliyun.com',
        help: '阿里云百炼 Coding Plan，输入 API Key 后点击"加载模型"验证并获取可用模型',
        default_model: 'qwen3.5-plus'
    },
    minimax: {
        name: 'minimax',
        display_name: 'MiniMax',
        api_type: 'openai',
        base_url: 'https://api.minimaxi.com/v1',
        requires_key: true,
        models: [],
        key_url: 'https://platform.minimaxi.com/user-center/basic-information/interface-key',
        help: 'MiniMax 开放平台，输入 API Key 后自动获取可用模型',
        default_model: 'MiniMax-M2.7'
    },
    dashscope: {
        name: 'dashscope',
        display_name: '阿里云百炼 (DashScope)',
        api_type: 'openai',
        base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        requires_key: true,
        models: [],
        key_url: 'https://bailian.console.aliyun.com',
        help: '阿里云百炼 DashScope API，输入 API Key 后自动获取可用模型',
        default_model: 'qwen-plus'
    },
    openai: {
        name: 'openai',
        display_name: 'OpenAI',
        api_type: 'openai',
        base_url: 'https://api.openai.com/v1',
        requires_key: true,
        models: [],
        key_url: 'https://platform.openai.com/api-keys',
        help: 'OpenAI 官方 API，输入 API Key 后自动获取可用模型',
        default_model: 'gpt-4o'
    },
    deepseek: {
        name: 'deepseek',
        display_name: 'DeepSeek',
        api_type: 'openai',
        base_url: 'https://api.deepseek.com/v1',
        requires_key: true,
        models: [],
        key_url: 'https://platform.deepseek.com',
        help: 'DeepSeek API，输入 API Key 后自动获取可用模型',
        default_model: 'deepseek-chat'
    },
    moonshot: {
        name: 'moonshot',
        display_name: 'Moonshot',
        api_type: 'openai',
        base_url: 'https://api.moonshot.cn/v1',
        requires_key: true,
        models: [],
        key_url: 'https://platform.moonshot.cn',
        help: 'Moonshot API，输入 API Key 后自动获取可用模型',
        default_model: 'moonshot-v1-8k'
    },
    zhipu: {
        name: 'zhipu',
        display_name: '智谱 AI',
        api_type: 'openai',
        base_url: 'https://open.bigmodel.cn/api/paas/v4',
        requires_key: true,
        models: [],
        key_url: 'https://open.bigmodel.cn',
        help: '智谱 AI 开放平台，输入 API Key 后自动获取可用模型',
        default_model: 'glm-4'
    },
    siliconflow: {
        name: 'siliconflow',
        display_name: 'SiliconFlow',
        api_type: 'openai',
        base_url: 'https://api.siliconflow.cn/v1',
        requires_key: true,
        models: [],
        key_url: 'https://cloud.siliconflow.cn',
        help: 'SiliconFlow API，输入 API Key 后自动获取可用模型',
        default_model: 'Qwen/Qwen2.5-72B-Instruct'
    },
    custom: {
        name: 'custom',
        display_name: '自定义 API',
        api_type: 'openai',
        base_url: '',
        requires_key: true,
        models: [],
        key_url: '',
        help: '输入任意 OpenAI 兼容 API',
        default_model: ''
    }
};

function getProviderConfig(provider) {
    return PROVIDER_CONFIGS[provider] || PROVIDER_CONFIGS.custom;
}

function getProviderSelectOptions() {
    return Object.keys(PROVIDER_CONFIGS)
        .filter(function(k) { return k !== 'custom'; })
        .map(function(k) {
            var config = PROVIDER_CONFIGS[k];
            return '<option value="' + k + '">' + config.display_name + '</option>';
        }).join('');
}

/**
 * Fetch models from the provider API after key validation.
 * Populates the model <select> element and returns the model list.
 *
 * @param {string} provider - Provider name (e.g. 'minimax', 'openai')
 * @param {string} apiKey - API key for the provider
 * @param {string} baseUrl - Optional base URL override
 * @param {HTMLSelectElement} modelSelectEl - The <select> to populate
 * @param {HTMLElement} statusEl - Status indicator element
 * @returns {Promise<string[]>} Array of model IDs
 */
async function fetchProviderModels(provider, apiKey, baseUrl, modelSelectEl, statusEl) {
    var config = getProviderConfig(provider);
    if (!modelSelectEl) return [];
    if (config.requires_key && !apiKey) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">请先输入 API Key</span>';
        modelSelectEl.innerHTML = '<option value="">-- 请输入 API Key --</option>';
        return [];
    }

    if (statusEl) statusEl.innerHTML = '<span style="color: var(--text-muted);">正在验证并获取模型列表...</span>';

    try {
        var res = await fetch('/api/provider/models', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({provider: provider, api_key: apiKey, base_url: baseUrl || config.base_url})
        });
        var data = await res.json();

        if (data.success && data.models && data.models.length > 0) {
            var defaultModel = data.default_model || '';
            modelSelectEl.innerHTML = '<option value="">-- 选择模型 --</option>' +
                data.models.map(function(m) {
                    var selected = (m === defaultModel) ? ' selected' : '';
                    return '<option value="' + m + '"' + selected + '>' + m + '</option>';
                }).join('');
            if (statusEl) statusEl.innerHTML = '<span style="color: #4caf50;">✓ 已加载 ' + data.models.length + ' 个模型</span>';
            if (config.key_url) {
                if (statusEl) statusEl.innerHTML += ' <a href="' + config.key_url + '" target="_blank" style="font-size: 0.85em;">获取 Key</a>';
            }
            return data.models;
        } else {
            var errMsg = data.error || '无法获取模型列表';
            modelSelectEl.innerHTML = '<option value="">-- 手动输入模型名 --</option>';
            if (defaultModel = data.default_model || config.default_model) {
                modelSelectEl.innerHTML += '<option value="' + defaultModel + '">' + defaultModel + ' (推荐)</option>';
            }
            if (statusEl) statusEl.innerHTML = '<span style="color: #ff9800;">' + errMsg + '，请手动输入模型名</span>';
            return [];
        }
    } catch (e) {
        modelSelectEl.innerHTML = '<option value="">-- 手动输入模型名 --</option>';
        if (config.default_model) {
            modelSelectEl.innerHTML += '<option value="' + config.default_model + '">' + config.default_model + ' (推荐)</option>';
        }
        if (statusEl) statusEl.innerHTML = '<span style="color: #ef5350;">错误: ' + e.message + '</span>';
        return [];
    }
}