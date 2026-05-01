"""Unified LLM client for GangDan.

Supports multiple providers:
- Ollama (local)
- OpenAI
- Aliyun Bailian Coding Plan (Anthropic-compatible)
- MiniMax (OpenAI-compatible)
- DeepSeek
- Moonshot
- Zhipu
- SiliconFlow
- Custom APIs
"""

import sys
import json
from typing import List, Dict, Iterator, Optional, Any
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""
    name: str
    display_name: str
    base_url: str
    api_type: str = "openai"  # "openai", "anthropic", "ollama"
    requires_key: bool = True
    models: List[str] = field(default_factory=list)
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
        help="本地 Ollama 服务，无需 API Key",
    ),
    "bailian-coding": ProviderConfig(
        name="bailian-coding",
        display_name="阿里云百炼 Coding Plan",
        base_url="https://coding.dashscope.aliyuncs.com/apps/anthropic/v1",
        api_type="anthropic",
        requires_key=True,
        models=[
            "qwen3.5-plus",
            "qwen3-max-2026-01-23",
            "qwen3-coder-next",
            "qwen3-coder-plus",
            "MiniMax-M2.5",
            "glm-5",
            "glm-4.7",
            "kimi-k2.5",
        ],
        key_url="https://bailian.console.aliyun.com",
        help="阿里云百炼 Coding Plan，从控制台获取 API Key",
        default_model="qwen3.5-plus",
    ),
    "minimax": ProviderConfig(
        name="minimax",
        display_name="MiniMax",
        base_url="https://api.minimaxi.com/v1",
        api_type="openai",
        requires_key=True,
        models=[
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2.1",
            "MiniMax-M2.1-highspeed",
            "MiniMax-M2",
        ],
        key_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
        help="MiniMax 开放平台，从用户中心获取 API Key",
        default_model="MiniMax-M2.7",
    ),
    "dashscope": ProviderConfig(
        name="dashscope",
        display_name="阿里云百炼 (DashScope)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_type="openai",
        requires_key=True,
        models=[
            "qwen-plus",
            "qwen-max",
            "qwen-turbo",
            "qwen-long",
            "qwen-max-latest",
            "qwen-coder-plus",
            "qwen-coder-turbo",
            "qwen-vl-plus",
            "qwen-vl-max",
        ],
        key_url="https://bailian.console.aliyun.com",
        help="阿里云百炼 DashScope API，从控制台获取 API Key",
        default_model="qwen-plus",
    ),
    "openai": ProviderConfig(
        name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_type="openai",
        requires_key=True,
        models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        key_url="https://platform.openai.com/api-keys",
        help="OpenAI 官方 API",
        default_model="gpt-4o",
    ),
    "deepseek": ProviderConfig(
        name="deepseek",
        display_name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        api_type="openai",
        requires_key=True,
        models=["deepseek-chat", "deepseek-coder"],
        key_url="https://platform.deepseek.com",
        help="DeepSeek API",
        default_model="deepseek-chat",
    ),
    "moonshot": ProviderConfig(
        name="moonshot",
        display_name="Moonshot (月之暗面)",
        base_url="https://api.moonshot.cn/v1",
        api_type="openai",
        requires_key=True,
        models=["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        key_url="https://platform.moonshot.cn",
        help="Moonshot API",
        default_model="moonshot-v1-8k",
    ),
    "zhipu": ProviderConfig(
        name="zhipu",
        display_name="智谱 AI",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_type="openai",
        requires_key=True,
        models=["glm-4", "glm-4-plus", "glm-4-flash", "glm-4-air", "glm-4-airx", "glm-3-turbo"],
        key_url="https://open.bigmodel.cn",
        help="智谱 AI 开放平台",
        default_model="glm-4",
    ),
    "siliconflow": ProviderConfig(
        name="siliconflow",
        display_name="SiliconFlow",
        base_url="https://api.siliconflow.cn/v1",
        api_type="openai",
        requires_key=True,
        models=["Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "deepseek-ai/DeepSeek-V2.5"],
        key_url="https://cloud.siliconflow.cn",
        help="SiliconFlow API",
        default_model="Qwen/Qwen2.5-72B-Instruct",
    ),
}


class BaseLLMClient:
    """Base class for LLM clients."""
    
    EMBEDDING_PATTERNS = [
        "embed", "embedding", "text-embedding", "bge", "e5", "gte",
        "jina", "nomic", "all-minilm", "sentence",
    ]
    
    def __init__(self, api_key: str = "", base_url: str = "", provider: str = ""):
        self.api_key = api_key
        self.base_url = base_url
        self.provider = provider
        self._stop_flag = False
        self._session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        session.mount("http://", HTTPAdapter(max_retries=retry))
        session.mount("https://", HTTPAdapter(max_retries=retry))
        return session
    
    def stop_generation(self):
        self._stop_flag = True
    
    def reset_stop(self):
        self._stop_flag = False
    
    def is_stopped(self) -> bool:
        return self._stop_flag
    
    def get_models(self) -> List[str]:
        raise NotImplementedError
    
    def chat_complete(self, messages: List[Dict], model: str, **kwargs) -> str:
        raise NotImplementedError
    
    def chat_stream(self, messages: List[Dict], model: str, **kwargs) -> Iterator[str]:
        raise NotImplementedError
    
    def embed(self, text: str, model: str) -> List[float]:
        raise NotImplementedError


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI-compatible APIs."""
    
    def __init__(self, api_key: str = "", base_url: str = "", provider: str = "openai"):
        super().__init__(api_key, base_url, provider)
        if self.api_key:
            self._session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            })
    
    def get_models(self) -> List[str]:
        config = PROVIDER_CONFIGS.get(self.provider)
        if config and config.models:
            return config.models
        
        if not self.api_key:
            return []
        
        try:
            url = f"{self.base_url.rstrip('/')}/models"
            r = self._session.get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
                return sorted(models)
        except Exception as e:
            print(f"[OpenAI] Error fetching models: {e}", file=sys.stderr)
        
        return config.models if config else []
    
    def chat_complete(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> str:
        self.reset_stop()
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        
        try:
            url = f"{self.base_url.rstrip('/')}/chat/completions"
            print(f"[OpenAI] POST {url}", file=sys.stderr)
            r = self._session.post(url, json=payload, timeout=300)
            r.raise_for_status()
            data = r.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            print(f"[OpenAI] Error: {e}", file=sys.stderr)
            return f"[Error: {e}]"
    
    def chat_stream(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> Iterator[str]:
        self.reset_stop()
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        
        try:
            url = f"{self.base_url.rstrip('/')}/chat/completions"
            print(f"[OpenAI] POST {url} (streaming)", file=sys.stderr)
            r = self._session.post(url, json=payload, stream=True, timeout=300)
            r.raise_for_status()
            
            for line in r.iter_lines():
                if self._stop_flag:
                    r.close()
                    break
                
                if not line:
                    continue
                
                line = line.decode("utf-8")
                
                if line.startswith("data: "):
                    line = line[6:]
                
                if line == "[DONE]":
                    break
                
                try:
                    data = json.loads(line)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue
                    
        except Exception as e:
            print(f"[OpenAI] Stream error: {e}", file=sys.stderr)
            yield f"\n\n[Error: {e}]"
    
    def embed(self, text: str, model: str) -> List[float]:
        text = text[:8000] if len(text) > 8000 else text
        
        payload = {"model": model, "input": text}
        
        try:
            url = f"{self.base_url.rstrip('/')}/embeddings"
            r = self._session.post(url, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            return data.get("data", [{}])[0].get("embedding", [])
        except Exception as e:
            print(f"[OpenAI] Embedding error: {e}", file=sys.stderr)
            return []


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic-compatible APIs (e.g., Aliyun Bailian Coding Plan)."""
    
    def __init__(self, api_key: str = "", base_url: str = "", provider: str = "anthropic"):
        super().__init__(api_key, base_url, provider)
        if self.api_key:
            self._session.headers.update({
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            })
    
    def get_models(self) -> List[str]:
        config = PROVIDER_CONFIGS.get(self.provider)
        return config.models if config else []
    
    def _convert_messages(self, messages: List[Dict]) -> tuple:
        """Convert OpenAI-format messages to Anthropic format."""
        system = ""
        anthropic_messages = []
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "system":
                system = content
            elif role in ["user", "assistant"]:
                anthropic_messages.append({
                    "role": role,
                    "content": content
                })
        
        return system, anthropic_messages
    
    def chat_complete(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> str:
        self.reset_stop()
        
        system, anthropic_messages = self._convert_messages(messages)
        
        payload = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
        }
        if system:
            payload["system"] = system
        if temperature != 1.0:
            payload["temperature"] = temperature
        
        try:
            url = f"{self.base_url.rstrip('/')}/messages"
            print(f"[Anthropic] POST {url}", file=sys.stderr)
            r = self._session.post(url, json=payload, timeout=300)
            r.raise_for_status()
            data = r.json()
            
            content = data.get("content", [])
            if content and len(content) > 0:
                return content[0].get("text", "")
            return ""
        except Exception as e:
            print(f"[Anthropic] Error: {e}", file=sys.stderr)
            return f"[Error: {e}]"
    
    def chat_stream(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> Iterator[str]:
        self.reset_stop()
        
        system, anthropic_messages = self._convert_messages(messages)
        
        payload = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if temperature != 1.0:
            payload["temperature"] = temperature
        
        try:
            url = f"{self.base_url.rstrip('/')}/messages"
            print(f"[Anthropic] POST {url} (streaming)", file=sys.stderr)
            r = self._session.post(url, json=payload, stream=True, timeout=300)
            r.raise_for_status()
            
            for line in r.iter_lines():
                if self._stop_flag:
                    r.close()
                    break
                
                if not line:
                    continue
                
                line = line.decode("utf-8")
                
                if not line.startswith("data: "):
                    continue
                
                line = line[6:]
                
                try:
                    data = json.loads(line)
                    event_type = data.get("type", "")
                    
                    if event_type == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield text
                    elif event_type == "message_stop":
                        break
                except json.JSONDecodeError:
                    continue
                    
        except Exception as e:
            print(f"[Anthropic] Stream error: {e}", file=sys.stderr)
            yield f"\n\n[Error: {e}]"
    
    def embed(self, text: str, model: str) -> List[float]:
        print(f"[Anthropic] Embedding not directly supported, attempting OpenAI-compatible endpoint", file=sys.stderr)
        openai_url = self.base_url.rstrip('/').replace('/anthropic/v1', '/embeddings')
        if '/anthropic' not in self.base_url:
            openai_url = self.base_url.rstrip('/') + '/embeddings'
        
        payload = {"model": "gte-large-en", "input": text[:8000] if len(text) > 8000 else text}
        
        try:
            r = self._session.post(openai_url, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            return data.get("data", [{}])[0].get("embedding", [])
        except Exception as e:
            print(f"[Anthropic] Embedding fallback error: {e}", file=sys.stderr)
            return []


def create_client(provider: str, api_key: str = "", base_url: str = "") -> Any:
    """Factory function to create the appropriate LLM client.
    
    Parameters
    ----------
    provider : str
        Provider name (ollama, bailian-coding, minimax, openai, etc.)
    api_key : str
        API key for authentication
    base_url : str
        Custom base URL (overrides provider default)
    
    Returns
    -------
    BaseLLMClient
        The appropriate client instance
    """
    config = PROVIDER_CONFIGS.get(provider)
    
    if not config:
        config = ProviderConfig(
            name="custom",
            display_name="Custom",
            base_url=base_url or "",
            api_type="openai",
            requires_key=True,
            models=[],
        )
    
    final_url = base_url or config.base_url
    final_key = api_key
    
    if config.api_type == "ollama":
        from gangdan.core.ollama_client import OllamaClient
        return OllamaClient(final_url.replace("/v1", ""))
    elif config.api_type == "anthropic":
        return AnthropicClient(api_key=final_key, base_url=final_url, provider=provider)
    else:
        return OpenAIClient(api_key=final_key, base_url=final_url, provider=provider)


def get_provider_config(provider: str) -> Optional[ProviderConfig]:
    """Get configuration for a provider."""
    return PROVIDER_CONFIGS.get(provider)


def list_providers() -> List[Dict[str, Any]]:
    """Get list of all available providers."""
    return [
        {
            "name": config.name,
            "display_name": config.display_name,
            "base_url": config.base_url,
            "api_type": config.api_type,
            "requires_key": config.requires_key,
            "models": config.models,
            "key_url": config.key_url,
            "help": config.help,
            "default_model": config.default_model,
        }
        for config in PROVIDER_CONFIGS.values()
    ]