"""LLM provider configuration models for GangDan Refined."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""
    name: str
    display_name: str
    base_url: str
    api_type: str = "openai"
    requires_key: bool = True
    models: List[str] = field(default_factory=list)
    default_chat_models: List[str] = field(default_factory=list)
    default_embed_models: List[str] = field(default_factory=list)
    key_url: str = ""
    help: str = ""
    default_model: str = ""


PROVIDER_CONFIGS: Dict[str, ProviderConfig] = {
    "ollama": ProviderConfig(
        name="ollama",
        display_name="Ollama (本地)",
        base_url="http://localhost:11434",
        api_type="ollama",
        requires_key=False,
        models=[],
        help="本地 Ollama 服务，无需 API Key，点击\"加载模型\"获取可用模型",
    ),
    "bailian-coding": ProviderConfig(
        name="bailian-coding",
        display_name="阿里云百炼 Coding Plan",
        base_url="https://coding.dashscope.aliyuncs.com/v1",
        api_type="anthropic",
        requires_key=True,
        models=["qwen3.5-plus", "qwen3-max-2026-01-23", "qwen3-coder-next",
                "qwen3-coder-plus", "MiniMax-M2.5", "glm-5", "glm-4.7", "kimi-k2.5"],
        default_chat_models=["qwen3.5-plus", "qwen3-max-2026-01-23", "qwen3-coder-next",
                             "qwen3-coder-plus", "MiniMax-M2.5", "glm-5", "glm-4.7", "kimi-k2.5"],
        default_embed_models=[],
        key_url="https://bailian.console.aliyun.com",
        help="阿里云百炼 Coding Plan，输入 API Key 后自动获取可用模型",
        default_model="qwen3.5-plus",
    ),
    "minimax": ProviderConfig(
        name="minimax",
        display_name="MiniMax",
        base_url="https://api.minimaxi.com/v1",
        api_type="openai",
        requires_key=True,
        models=["MiniMax-M2.7", "MiniMax-M2.7-highspeed",
                "MiniMax-M2.5", "MiniMax-M2.5-highspeed",
                "MiniMax-M2.1", "MiniMax-M2.1-highspeed", "MiniMax-M2"],
        default_chat_models=["MiniMax-M2.7", "MiniMax-M2.7-highspeed",
                             "MiniMax-M2.5", "MiniMax-M2.5-highspeed",
                             "MiniMax-M2.1", "MiniMax-M2.1-highspeed", "MiniMax-M2"],
        default_embed_models=[],
        key_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
        help="MiniMax 开放平台，输入 API Key 后自动获取可用模型",
        default_model="MiniMax-M2.7",
    ),
    "dashscope": ProviderConfig(
        name="dashscope",
        display_name="阿里云百炼 (DashScope)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_type="openai",
        requires_key=True,
        models=[],
        default_chat_models=["qwen-plus", "qwen-max", "qwen-turbo", "qwen-long",
                             "qwen-max-latest", "qwen-coder-plus", "qwen-coder-turbo"],
        default_embed_models=["text-embedding-v3", "text-embedding-v2", "text-embedding-v1"],
        key_url="https://bailian.console.aliyun.com",
        help="阿里云百炼 DashScope API，输入 API Key 后自动获取可用模型",
        default_model="qwen-plus",
    ),
    "openai": ProviderConfig(
        name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_type="openai",
        requires_key=True,
        models=[],
        default_chat_models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        default_embed_models=["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
        key_url="https://platform.openai.com/api-keys",
        help="OpenAI 官方 API，输入 API Key 后自动获取可用模型",
        default_model="gpt-4o",
    ),
    "deepseek": ProviderConfig(
        name="deepseek",
        display_name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        api_type="openai",
        requires_key=True,
        models=[],
        default_chat_models=["deepseek-chat", "deepseek-coder"],
        default_embed_models=[],
        key_url="https://platform.deepseek.com",
        help="DeepSeek API，输入 API Key 后自动获取可用模型",
        default_model="deepseek-chat",
    ),
    "moonshot": ProviderConfig(
        name="moonshot",
        display_name="Moonshot (月之暗面)",
        base_url="https://api.moonshot.cn/v1",
        api_type="openai",
        requires_key=True,
        models=[],
        default_chat_models=["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        default_embed_models=[],
        key_url="https://platform.moonshot.cn",
        help="Moonshot API，输入 API Key 后自动获取可用模型",
        default_model="moonshot-v1-8k",
    ),
    "zhipu": ProviderConfig(
        name="zhipu",
        display_name="智谱 AI",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_type="openai",
        requires_key=True,
        models=[],
        default_chat_models=["glm-4", "glm-4-plus", "glm-4-flash", "glm-4-air", "glm-4-airx", "glm-3-turbo"],
        default_embed_models=["embedding-3", "embedding-2"],
        key_url="https://open.bigmodel.cn",
        help="智谱 AI 开放平台，输入 API Key 后自动获取可用模型",
        default_model="glm-4",
    ),
    "siliconflow": ProviderConfig(
        name="siliconflow",
        display_name="SiliconFlow",
        base_url="https://api.siliconflow.cn/v1",
        api_type="openai",
        requires_key=True,
        models=[],
        default_chat_models=["Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "deepseek-ai/DeepSeek-V2.5"],
        default_embed_models=["BAAI/bge-large-zh-v1.5", "BAAI/bge-m3"],
        key_url="https://cloud.siliconflow.cn",
        help="SiliconFlow API，输入 API Key 后自动获取可用模型",
        default_model="Qwen/Qwen2.5-72B-Instruct",
    ),
}