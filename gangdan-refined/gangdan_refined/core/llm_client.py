"""LLM client abstraction supporting Ollama and OpenAI-compatible APIs."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class ToolResult:
    """Standard result wrapper for API functions."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class BaseLLMClient:
    """Base class for LLM clients."""

    def is_available(self) -> bool:
        return False

    def get_models(self) -> List[str]:
        return []

    def get_chat_models(self) -> List[str]:
        return []

    def embed(self, text: str, model: str) -> List[float]:
        return []

    def chat_complete(self, messages: List[Dict], model: str,
                      temperature: float = 0.7, num_ctx: int = None,
                      max_tokens: int = None) -> str:
        return ""

    def chat_stream(self, messages: List[Dict], model: str,
                    temperature: float = 0.7, num_ctx: int = None,
                    max_tokens: int = None) -> Iterator[str]:
        yield ""

    def stop_generation(self):
        pass

    def reset_stop(self):
        pass

    def is_stopped(self) -> bool:
        return False


class OllamaClient(BaseLLMClient):
    """Ollama API client with streaming and embedding support."""

    EMBEDDING_PATTERNS = [
        "nomic-embed", "bge-m3", "bge-large", "bge-base", "bge-small",
        "mxbai-embed", "all-minilm", "snowflake-arctic-embed", "multilingual-e5",
        "e5-large", "e5-base", "e5-small", "gte-large", "gte-base", "gte-small",
        "gte-qwen", "jina-embed", "paraphrase", "sentence-t5", "instructor",
        "text-embedding", "embed", "embedding",
    ]
    RERANKER_PATTERNS = ["bge-reranker", "rerank", "ms-marco", "cross-encoder", "jina-reranker", "colbert"]

    def __init__(self, api_url: str = "http://localhost:11434"):
        self.api_url = api_url.rstrip("/")
        self._session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self._session.mount("http://", HTTPAdapter(max_retries=retry))
        self._stop_flag = False
        self._context_length = 4096
        self._model_info_cache: Dict[str, Dict] = {}

    def set_context_length(self, length: int):
        self._context_length = max(512, min(length, 1000000))

    def get_context_length(self) -> int:
        return self._context_length

    def is_available(self) -> bool:
        try:
            r = self._session.get(f"{self.api_url}/api/tags", timeout=5)
            return r.status_code == 200
        except (requests.RequestException, requests.Timeout):
            return False

    def get_models(self) -> List[str]:
        try:
            r = self._session.get(f"{self.api_url}/api/tags", timeout=30)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except (requests.RequestException, KeyError, json.JSONDecodeError):
            return []

    def get_chat_models(self) -> List[str]:
        models = self.get_models()
        exclude = self.EMBEDDING_PATTERNS + self.RERANKER_PATTERNS
        return [m for m in models if not any(x in m.lower() for x in exclude)]

    def get_embedding_models(self) -> List[str]:
        models = self.get_models()
        result = []
        for pattern in self.EMBEDDING_PATTERNS:
            for m in models:
                m_lower = m.lower()
                if any(rp in m_lower for rp in self.RERANKER_PATTERNS):
                    continue
                if pattern in m_lower and m not in result:
                    result.append(m)
        return result

    def get_reranker_models(self) -> List[str]:
        models = self.get_models()
        result = []
        for pattern in self.RERANKER_PATTERNS:
            for m in models:
                if pattern in m.lower() and m not in result:
                    result.append(m)
        return result

    def get_model_info(self, model: str) -> Dict:
        if model in self._model_info_cache:
            return self._model_info_cache[model]
        info = {"name": model, "context_length": 4096, "parameter_size": "unknown",
                "quantization": "unknown", "memory_required_gb": 0, "family": "unknown"}
        try:
            r = self._session.post(f"{self.api_url}/api/show", json={"name": model}, timeout=30)
            if r.status_code == 200:
                data = r.json()
                details = data.get("details", {})
                model_info = data.get("model_info", {})
                info["parameter_size"] = details.get("parameter_size", "unknown")
                info["quantization"] = details.get("quantization_level", "unknown")
                info["family"] = details.get("family", "unknown")
                ctx = model_info.get("context_length", 4096)
                if isinstance(ctx, int):
                    info["context_length"] = ctx
                self._model_info_cache[model] = info
        except Exception as e:
            print(f"[Ollama] Failed to get model info for {model}: {e}", file=sys.stderr)
        return info

    def get_memory_usage(self) -> Dict:
        try:
            r = self._session.get(f"{self.api_url}/api/ps", timeout=10)
            if r.status_code == 200:
                data = r.json()
                models = data.get("models", [])
                total_gb = 0
                model_list = []
                for m in models:
                    mem = round(max(m.get("size_vram", 0), m.get("size", 0)) / (1024**3), 2)
                    total_gb += mem
                    model_list.append({"name": m.get("name", "unknown"), "memory_gb": mem})
                return {"total_memory_gb": round(total_gb, 2), "models_loaded": model_list, "model_count": len(model_list)}
        except Exception:
            pass
        return {"total_memory_gb": 0, "models_loaded": [], "model_count": 0}

    def embed(self, text: str, model: str) -> List[float]:
        text = text[:500] if len(text) > 500 else text
        r = self._session.post(
            f"{self.api_url}/api/embeddings",
            json={"model": model, "prompt": text}, timeout=60,
        )
        r.raise_for_status()
        return r.json().get("embedding", [])

    def chat_complete(self, messages: List[Dict], model: str,
                      temperature: float = 0.7, num_ctx: int = None,
                      max_tokens: int = None) -> str:
        ctx_len = num_ctx or self._context_length
        payload = {
            "model": model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_ctx": ctx_len},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        try:
            r = self._session.post(f"{self.api_url}/api/chat", json=payload, timeout=300)
            r.raise_for_status()
            data = r.json()
            return data.get("message", {}).get("content", "")
        except Exception as e:
            print(f"[Ollama] chat_complete error: {e}", file=sys.stderr)
            return ""

    def chat_stream(self, messages: List[Dict], model: str,
                    temperature: float = 0.7, num_ctx: int = None,
                    max_tokens: int = None) -> Iterator[str]:
        self.reset_stop()
        ctx_len = num_ctx or self._context_length
        payload = {
            "model": model, "messages": messages, "stream": True,
            "options": {"temperature": temperature, "num_ctx": ctx_len},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        try:
            r = self._session.post(f"{self.api_url}/api/chat", json=payload, stream=True, timeout=300)
            r.raise_for_status()
            for line in r.iter_lines():
                if self._stop_flag:
                    r.close()
                    break
                if line:
                    try:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            yield f"\n\n[Error: {e}]"

    def stop_generation(self):
        self._stop_flag = True

    def reset_stop(self):
        self._stop_flag = False

    def is_stopped(self) -> bool:
        return self._stop_flag

    def translate(self, text: str, from_lang: str, to_lang: str, model: str = "") -> str:
        if not text.strip() or from_lang == to_lang:
            return text
        lang_names = {"zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
                      "ru": "Russian", "fr": "French", "de": "German", "es": "Spanish",
                      "pt": "Portuguese", "it": "Italian"}
        prompt = f"Translate the following text from {lang_names.get(from_lang, from_lang)} to {lang_names.get(to_lang, to_lang)}. Output ONLY the translation:\n\n{text[:500]}"
        try:
            return self.chat_complete(model=model, messages=[{"role": "user", "content": prompt}]).strip()
        except Exception:
            return ""


class OpenAIClient(BaseLLMClient):
    """OpenAI-compatible API client."""

    PROVIDER_CONFIGS = {
        "openai": {"base_url": "https://api.openai.com/v1", "requires_key": True, "default_model": "gpt-4o-mini", "default_chat_models": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]},
        "deepseek": {"base_url": "https://api.deepseek.com/v1", "requires_key": True, "default_model": "deepseek-chat", "default_chat_models": ["deepseek-chat", "deepseek-reasoner"]},
        "dashscope": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "requires_key": True, "default_model": "qwen-plus", "default_chat_models": ["qwen-plus", "qwen-turbo", "qwen-max"]},
        "zhipu": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "requires_key": True, "default_model": "glm-4-flash", "default_chat_models": ["glm-4-flash", "glm-4-plus", "glm-4"]},
        "moonshot": {"base_url": "https://api.moonshot.cn/v1", "requires_key": True, "default_model": "moonshot-v1-8k", "default_chat_models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]},
        "siliconflow": {"base_url": "https://api.siliconflow.cn/v1", "requires_key": True, "default_model": "Qwen/Qwen2.5-72B-Instruct", "default_chat_models": ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"]},
        "volcengine": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "requires_key": True, "default_model": "ep-20241201000000-xxxxx", "default_chat_models": []},
    }

    def __init__(self, api_key: str, base_url: str = "", provider: str = "openai"):
        self.api_key = api_key
        self.provider = provider
        config = self.PROVIDER_CONFIGS.get(provider, {})
        self.base_url = (base_url or config.get("base_url", "")).rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self._session.mount("https://", HTTPAdapter(max_retries=retry))

    def is_available(self) -> bool:
        try:
            r = self._session.get(f"{self.base_url}/models", timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    def get_models(self) -> List[str]:
        try:
            r = self._session.get(f"{self.base_url}/models", timeout=30)
            if r.status_code == 200:
                return [m.get("id", "") for m in r.json().get("data", [])]
        except Exception:
            pass
        config = self.PROVIDER_CONFIGS.get(self.provider, {})
        return config.get("default_chat_models", [])

    def get_chat_models(self) -> List[str]:
        models = self.get_models()
        exclude = ["embed", "embedding", "bge", "e5", "gte", "tts", "whisper", "dall-e"]
        return [m for m in models if not any(x in m.lower() for x in exclude)]

    def chat_complete(self, messages: List[Dict], model: str,
                      temperature: float = 0.7, num_ctx: int = None,
                      max_tokens: int = None) -> str:
        payload = {"model": model, "messages": messages, "temperature": temperature}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        try:
            r = self._session.post(f"{self.base_url}/chat/completions", json=payload, timeout=300)
            r.raise_for_status()
            data = r.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            print(f"[{self.provider}] chat_complete error: {e}", file=sys.stderr)
            return ""

    def chat_stream(self, messages: List[Dict], model: str,
                    temperature: float = 0.7, num_ctx: int = None,
                    max_tokens: int = None) -> Iterator[str]:
        payload = {"model": model, "messages": messages, "stream": True, "temperature": temperature}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        try:
            r = self._session.post(f"{self.base_url}/chat/completions", json=payload, stream=True, timeout=300)
            r.raise_for_status()
            for line in r.iter_lines():
                if line:
                    line_str = line.decode("utf-8")
                    if line_str.startswith("data: "):
                        line_str = line_str[6:]
                    if line_str == "[DONE]":
                        break
                    try:
                        data = json.loads(line_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            yield f"\n\n[Error: {e}]"

    @classmethod
    def list_providers(cls) -> List[Dict]:
        return [{"id": k, **v} for k, v in cls.PROVIDER_CONFIGS.items()]


def create_client(provider: str = "ollama", api_key: str = "", base_url: str = "",
                  ollama_url: str = "http://localhost:11434") -> BaseLLMClient:
    """Create an LLM client based on provider."""
    if provider == "ollama":
        return OllamaClient(api_url=ollama_url)
    return OpenAIClient(api_key=api_key, base_url=base_url, provider=provider)
