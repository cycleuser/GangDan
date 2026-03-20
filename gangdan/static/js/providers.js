// Provider configurations - based on official API documentation
// Synced with gangdan/core/llm_client.py PROVIDER_CONFIGS
var PROVIDER_CONFIGS = {
    ollama: {
        name: 'ollama',
        display_name: 'Ollama (本地)',
        api_type: 'ollama',
        base_url: 'http://localhost:11434',
        requires_key: false,
        models: [],
        key_url: '',
        help: '本地 Ollama 服务，无需 API Key',
        default_model: ''
    },
    'bailian-coding': {
        name: 'bailian-coding',
        display_name: '阿里云百炼 Coding Plan',
        api_type: 'anthropic',
        base_url: 'https://coding.dashscope.aliyuncs.com/apps/anthropic/v1',
        requires_key: true,
        models: [
            'qwen3.5-plus',
            'qwen3-max-2026-01-23',
            'qwen3-coder-next',
            'qwen3-coder-plus',
            'MiniMax-M2.5',
            'glm-5',
            'glm-4.7',
            'kimi-k2.5'
        ],
        key_url: 'https://bailian.console.aliyun.com',
        help: '阿里云百炼 Coding Plan，支持思考模式',
        default_model: 'qwen3.5-plus'
    },
    minimax: {
        name: 'minimax',
        display_name: 'MiniMax',
        api_type: 'openai',
        base_url: 'https://api.minimaxi.com/v1',
        requires_key: true,
        models: [
            'MiniMax-M2.7',
            'MiniMax-M2.7-highspeed',
            'MiniMax-M2.5',
            'MiniMax-M2.5-highspeed',
            'MiniMax-M2.1',
            'MiniMax-M2.1-highspeed',
            'MiniMax-M2'
        ],
        key_url: 'https://platform.minimaxi.com/user-center/basic-information/interface-key',
        help: 'MiniMax 开放平台',
        default_model: 'MiniMax-M2.7'
    },
    dashscope: {
        name: 'dashscope',
        display_name: '阿里云百炼 (DashScope)',
        api_type: 'openai',
        base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        requires_key: true,
        models: [
            'qwen-plus',
            'qwen-max',
            'qwen-turbo',
            'qwen-long',
            'qwen-max-latest',
            'qwen-coder-plus',
            'qwen-coder-turbo',
            'qwen-vl-plus',
            'qwen-vl-max'
        ],
        key_url: 'https://bailian.console.aliyun.com',
        help: '阿里云百炼 DashScope API',
        default_model: 'qwen-plus'
    },
    openai: {
        name: 'openai',
        display_name: 'OpenAI',
        api_type: 'openai',
        base_url: 'https://api.openai.com/v1',
        requires_key: true,
        models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
        key_url: 'https://platform.openai.com/api-keys',
        help: 'OpenAI 官方 API',
        default_model: 'gpt-4o'
    },
    deepseek: {
        name: 'deepseek',
        display_name: 'DeepSeek',
        api_type: 'openai',
        base_url: 'https://api.deepseek.com/v1',
        requires_key: true,
        models: ['deepseek-chat', 'deepseek-coder'],
        key_url: 'https://platform.deepseek.com',
        help: 'DeepSeek API',
        default_model: 'deepseek-chat'
    },
    moonshot: {
        name: 'moonshot',
        display_name: 'Moonshot',
        api_type: 'openai',
        base_url: 'https://api.moonshot.cn/v1',
        requires_key: true,
        models: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'],
        key_url: 'https://platform.moonshot.cn',
        help: 'Moonshot API',
        default_model: 'moonshot-v1-8k'
    },
    zhipu: {
        name: 'zhipu',
        display_name: '智谱 AI',
        api_type: 'openai',
        base_url: 'https://open.bigmodel.cn/api/paas/v4',
        requires_key: true,
        models: ['glm-4', 'glm-4-plus', 'glm-4-flash', 'glm-4-air', 'glm-4-airx', 'glm-3-turbo'],
        key_url: 'https://open.bigmodel.cn',
        help: '智谱 AI 开放平台',
        default_model: 'glm-4'
    },
    siliconflow: {
        name: 'siliconflow',
        display_name: 'SiliconFlow',
        api_type: 'openai',
        base_url: 'https://api.siliconflow.cn/v1',
        requires_key: true,
        models: ['Qwen/Qwen2.5-72B-Instruct', 'Qwen/Qwen2.5-32B-Instruct', 'deepseek-ai/DeepSeek-V2.5'],
        key_url: 'https://cloud.siliconflow.cn',
        help: 'SiliconFlow API',
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