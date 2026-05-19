"""OpenAI-compatible and Anthropic-compatible LLM clients."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Iterator, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import BaseLLMClient
from .models import PROVIDER_CONFIGS

RETRY_STATUS_FORCELIST = [429, 500, 502, 503, 504]


class OpenAICompatClient(BaseLLMClient):
    """Client for OpenAI-compatible APIs (OpenAI, DeepSeek, Moonshot, Zhipu, SiliconFlow, DashScope)."""

    EMBEDDING_PATTERNS = [
        "embed", "embedding", "text-embedding", "bge", "e5", "gte",
        "jina", "nomic", "all-minilm", "sentence",
    ]

    def __init__(self, api_key: str = "", base_url: str = "", provider: str = "openai"):
        self.api_key = api_key
        self.base_url = base_url
        self.provider = provider
        self._stop_flag = False
        self._session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=RETRY_STATUS_FORCELIST)
        session.mount("http://", HTTPAdapter(max_retries=retry))
        session.mount("https://", HTTPAdapter(max_retries=retry))
        if self.api_key:
            session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            })
        return session

    def stop_generation(self) -> None:
        self._stop_flag = True

    def reset_stop(self) -> None:
        self._stop_flag = False

    def is_stopped(self) -> bool:
        return self._stop_flag

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            return len(self.get_models()) > 0
        except Exception:
            return False

    def get_models(self) -> List[str]:
        if self.api_key:
            try:
                url = f"{self.base_url.rstrip('/')}/models"
                r = self._session.get(url, timeout=30)
                if r.status_code == 200:
                    data = r.json()
                    models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
                    if models:
                        return sorted(models)
            except Exception:
                pass
        config = PROVIDER_CONFIGS.get(self.provider)
        if config and config.default_chat_models:
            return sorted(set(config.default_chat_models + config.default_embed_models))
        if config and config.default_model:
            return [config.default_model]
        return []

    def get_chat_models(self) -> List[str]:
        config = PROVIDER_CONFIGS.get(self.provider)
        default_chat = config.default_chat_models if config else []
        models = self.get_models()
        chat_models = [m for m in models if not any(p in m.lower() for p in self.EMBEDDING_PATTERNS)]
        for m in default_chat:
            if m not in chat_models:
                chat_models.append(m)
        return sorted(chat_models)

    def get_embedding_models(self) -> List[str]:
        config = PROVIDER_CONFIGS.get(self.provider)
        default_embed = config.default_embed_models if config else []
        models = self.get_models()
        embed_models = [m for m in models if any(p in m.lower() for p in self.EMBEDDING_PATTERNS)]
        for m in default_embed:
            if m not in embed_models:
                embed_models.append(m)
        return sorted(embed_models)

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        self.reset_stop()
        model = model or ""
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
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Iterator[str]:
        self.reset_stop()
        model = model or ""
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
            yield f"\n\n[Error: {e}]"

    def embed(self, text: str | List[str], model: Optional[str] = None, **kwargs: Any) -> Any:
        model = model or ""
        if isinstance(text, list):
            text = text[0] if text else ""
        text = text[:8000]
        payload = {"model": model, "input": text}
        try:
            url = f"{self.base_url.rstrip('/')}/embeddings"
            r = self._session.post(url, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            return data.get("data", [{}])[0].get("embedding", [])
        except Exception:
            return []

    def chat_complete(self, messages, model, temperature=0.7, max_tokens=4096, **kwargs):
        return self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)


class AnthropicCompatClient(BaseLLMClient):
    """Client for Anthropic-compatible APIs (Bailian Coding Plan, etc.)."""

    def __init__(self, api_key: str = "", base_url: str = "", provider: str = "anthropic"):
        self.api_key = api_key
        self.base_url = base_url
        self.provider = provider
        self._stop_flag = False
        self._session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=RETRY_STATUS_FORCELIST)
        session.mount("http://", HTTPAdapter(max_retries=retry))
        session.mount("https://", HTTPAdapter(max_retries=retry))
        if self.api_key:
            session.headers.update({
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            })
        return session

    def stop_generation(self) -> None:
        self._stop_flag = True

    def reset_stop(self) -> None:
        self._stop_flag = False

    def is_stopped(self) -> bool:
        return self._stop_flag

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            return len(self.get_models()) > 0
        except Exception:
            return False

    def get_models(self) -> List[str]:
        try:
            url = f"{self.base_url.rstrip('/')}/models"
            r = self._session.get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
                if models:
                    return sorted(models)
        except Exception:
            pass
        config = PROVIDER_CONFIGS.get(self.provider)
        return [config.default_model] if config and config.default_model else []

    def _convert_messages(self, messages: List[Dict]) -> tuple:
        system = ""
        anthropic_messages = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system = content
            elif role in ["user", "assistant"]:
                anthropic_messages.append({"role": role, "content": content})
        return system, anthropic_messages

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        self.reset_stop()
        model = model or ""
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
            r = self._session.post(url, json=payload, timeout=300)
            r.raise_for_status()
            data = r.json()
            content = data.get("content", [])
            if content:
                return content[0].get("text", "")
            return ""
        except Exception as e:
            return f"[Error: {e}]"

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Iterator[str]:
        self.reset_stop()
        model = model or ""
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
            yield f"\n\n[Error: {e}]"

    def embed(self, text: str | List[str], model: Optional[str] = None, **kwargs: Any) -> Any:
        openai_url = self.base_url.rstrip("/").replace("/anthropic/v1", "/embeddings")
        if "/anthropic" not in self.base_url:
            openai_url = self.base_url.rstrip("/") + "/embeddings"
        if isinstance(text, list):
            text = text[0] if text else ""
        text = text[:8000]
        payload = {"model": model or "gte-large-en", "input": text}
        try:
            r = self._session.post(openai_url, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            return data.get("data", [{}])[0].get("embedding", [])
        except Exception:
            return []

    def chat_complete(self, messages, model, temperature=0.7, max_tokens=4096, **kwargs):
        return self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)