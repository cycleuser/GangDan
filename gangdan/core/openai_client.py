"""OpenAI-compatible API client for GangDan.

Supports OpenAI, Azure OpenAI, DashScope, and other OpenAI-compatible APIs.
"""

import sys
import json
import time
from typing import List, Dict, Iterator, Optional
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class OpenAIClient:
    """Client for OpenAI-compatible APIs (OpenAI, Azure, DashScope, etc.)."""
    
    # Known provider presets
    PROVIDER_PRESETS = {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "models_endpoint": "/models",
            "chat_endpoint": "/chat/completions",
            "embeddings_endpoint": "/embeddings",
            "default_chat_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
            "default_embed_models": ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
        },
        "dashscope": {
            "base_url": "https://coding.dashscope.aliyuncs.com/v1",
            "models_endpoint": "/models",
            "chat_endpoint": "/chat/completions",
            "embeddings_endpoint": "/embeddings",
            "default_chat_models": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-max-longcontext", "qwen-coder-plus", "qwen-coder-turbo"],
            "default_embed_models": ["text-embedding-v3", "text-embedding-v2", "text-embedding-v1"],
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "models_endpoint": "/models",
            "chat_endpoint": "/chat/completions",
            "embeddings_endpoint": "/embeddings",
            "default_chat_models": ["deepseek-chat", "deepseek-coder"],
            "default_embed_models": [],
        },
        "moonshot": {
            "base_url": "https://api.moonshot.cn/v1",
            "models_endpoint": "/models",
            "chat_endpoint": "/chat/completions",
            "embeddings_endpoint": "/embeddings",
            "default_chat_models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
            "default_embed_models": [],
        },
        "zhipu": {
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "models_endpoint": "/models",
            "chat_endpoint": "/chat/completions",
            "embeddings_endpoint": "/embeddings",
            "default_chat_models": ["glm-4", "glm-4-plus", "glm-4-flash", "glm-4-air", "glm-4-airx", "glm-3-turbo"],
            "default_embed_models": ["embedding-3", "embedding-2"],
        },
        "siliconflow": {
            "base_url": "https://api.siliconflow.cn/v1",
            "models_endpoint": "/models",
            "chat_endpoint": "/chat/completions",
            "embeddings_endpoint": "/embeddings",
            "default_chat_models": ["Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-32B-Instruct", "deepseek-ai/DeepSeek-V2.5"],
            "default_embed_models": ["BAAI/bge-large-zh-v1.5", "BAAI/bge-m3"],
        },
    }
    
    # Known embedding model patterns
    EMBEDDING_PATTERNS = [
        "embed", "embedding", "text-embedding", "bge", "e5", "gte",
        "jina", "nomic", "all-minilm", "sentence",
    ]
    
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        provider: str = "openai",
    ):
        """Initialize OpenAI-compatible client.
        
        Parameters
        ----------
        api_key : str
            API key for authentication.
        base_url : str
            Base URL for the API (e.g., https://api.openai.com/v1).
        provider : str
            Provider preset name (openai, dashscope, deepseek, etc.).
        """
        self.api_key = api_key
        self._stop_flag = False
        
        # Get provider preset or use custom base_url
        preset = self.PROVIDER_PRESETS.get(provider, {})
        self.base_url = base_url or preset.get("base_url", "https://api.openai.com/v1")
        self.provider = provider
        
        # Set up session with retry
        self._session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self._session.mount("http://", HTTPAdapter(max_retries=retry))
        self._session.mount("https://", HTTPAdapter(max_retries=retry))
        
        # Set default headers
        if self.api_key:
            self._session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            })
    
    def set_api_key(self, api_key: str):
        """Update the API key."""
        self.api_key = api_key
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
        })
    
    def stop_generation(self):
        """Signal to stop the current generation."""
        self._stop_flag = True
    
    def reset_stop(self):
        """Reset the stop flag."""
        self._stop_flag = False
    
    def is_stopped(self) -> bool:
        """Check if generation was stopped."""
        return self._stop_flag
    
    def is_available(self) -> bool:
        """Check if API is available and configured."""
        if not self.api_key:
            return False
        try:
            models = self.get_models()
            return len(models) > 0
        except Exception:
            return False
    
    def get_models(self) -> List[str]:
        """Get list of available models."""
        if not self.api_key:
            return self._get_default_models()
        
        try:
            url = f"{self.base_url.rstrip('/')}/models"
            r = self._session.get(url, timeout=30)
            r.raise_for_status()
            data = r.json()
            
            models = []
            for model in data.get("data", []):
                model_id = model.get("id", "")
                if model_id:
                    models.append(model_id)
            
            if models:
                return sorted(models)
            
            return self._get_default_models()
        except Exception as e:
            print(f"[OpenAI] Error fetching models: {e}, using defaults", file=sys.stderr)
            return self._get_default_models()
    
    def _get_default_models(self) -> List[str]:
        """Get default models for the provider."""
        preset = self.PROVIDER_PRESETS.get(self.provider, {})
        chat_models = preset.get("default_chat_models", [])
        embed_models = preset.get("default_embed_models", [])
        return sorted(chat_models + embed_models)
    
    def get_chat_models(self) -> List[str]:
        """Get chat models (exclude embedding models)."""
        preset = self.PROVIDER_PRESETS.get(self.provider, {})
        default_chat = preset.get("default_chat_models", [])
        
        models = self.get_models()
        chat_models = [
            m for m in models
            if not any(p in m.lower() for p in self.EMBEDDING_PATTERNS)
        ]
        
        for m in default_chat:
            if m not in chat_models:
                chat_models.append(m)
        
        return sorted(chat_models)
    
    def get_embedding_models(self) -> List[str]:
        """Get embedding models."""
        preset = self.PROVIDER_PRESETS.get(self.provider, {})
        default_embed = preset.get("default_embed_models", [])
        
        models = self.get_models()
        embed_models = [
            m for m in models
            if any(p in m.lower() for p in self.EMBEDDING_PATTERNS)
        ]
        
        for m in default_embed:
            if m not in embed_models:
                embed_models.append(m)
        
        return sorted(embed_models)
    
    def chat_complete(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Non-streaming chat completion.
        
        Parameters
        ----------
        messages : List[Dict]
            Chat messages in OpenAI format.
        model : str
            Model name.
        temperature : float
            Sampling temperature.
        max_tokens : int
            Maximum tokens to generate.
        
        Returns
        -------
        str
            The assistant's response text.
        """
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
            r = self._session.post(url, json=payload, timeout=300)
            r.raise_for_status()
            data = r.json()
            
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            return f"[Error: {e}]"
    
    def chat_stream(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        """Stream chat responses token by token.
        
        Parameters
        ----------
        messages : List[Dict]
            Chat messages in OpenAI format.
        model : str
            Model name.
        temperature : float
            Sampling temperature.
        max_tokens : int
            Maximum tokens to generate.
        
        Yields
        ------
        str
            Text chunks from the response.
        """
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
            r = self._session.post(url, json=payload, stream=True, timeout=300)
            r.raise_for_status()
            
            for line in r.iter_lines():
                if self._stop_flag:
                    r.close()
                    break
                
                if not line:
                    continue
                
                line = line.decode("utf-8")
                
                # Skip data: prefix
                if line.startswith("data: "):
                    line = line[6:]
                
                # Check for end of stream
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
            yield f"\n\n[Error: {e}]"
    
    def embed(self, text: str, model: str) -> List[float]:
        """Generate embeddings for text.
        
        Parameters
        ----------
        text : str
            Text to embed.
        model : str
            Embedding model name.
        
        Returns
        -------
        List[float]
            Embedding vector.
        """
        # Truncate long text
        text = text[:8000] if len(text) > 8000 else text
        
        payload = {
            "model": model,
            "input": text,
        }
        
        try:
            url = f"{self.base_url.rstrip('/')}/embeddings"
            r = self._session.post(url, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            
            return data.get("data", [{}])[0].get("embedding", [])
        except Exception as e:
            print(f"[OpenAI] Embedding error: {e}", file=sys.stderr)
            return []
    
    @classmethod
    def list_providers(cls) -> List[Dict[str, str]]:
        """Get list of known provider presets.
        
        Returns
        -------
        List[Dict[str, str]]
            List of provider info dicts with 'name' and 'base_url'.
        """
        return [
            {"name": name, "base_url": info["base_url"]}
            for name, info in cls.PROVIDER_PRESETS.items()
        ]


def create_llm_client(config) -> object:
    """Factory function to create the appropriate LLM client.
    
    Parameters
    ----------
    config : Config
        Configuration object with llm_provider, api_key, etc.
    
    Returns
    -------
    OllamaClient or OpenAIClient
        The appropriate client based on configuration.
    """
    provider = getattr(config, "llm_provider", "ollama")
    
    if provider == "ollama":
        from gangdan.core.ollama_client import OllamaClient
        return OllamaClient(config.ollama_url)
    else:
        api_key = getattr(config, "api_key", "")
        base_url = getattr(config, "api_base_url", "")
        return OpenAIClient(
            api_key=api_key,
            base_url=base_url,
            provider=provider,
        )