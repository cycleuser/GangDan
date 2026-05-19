"""Ollama LLM client for GangDan Refined.

Provides local LLM access via Ollama API.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Iterator, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..core.constants import (
    HTTP_TIMEOUT_MEDIUM,
    MAX_EMBED_TEXT_LENGTH,
    MAX_REQUEST_RETRIES,
)
from .base import BaseLLMClient

logger = logging.getLogger(__name__)

RETRY_STATUS_FORCELIST = [429, 500, 502, 503, 504]

MIN_CONTEXT_LENGTH = 512
MAX_CONTEXT_LENGTH = 128000
DEFAULT_CONTEXT_LENGTH = 4096


class OllamaClient(BaseLLMClient):
    """Client for interacting with local Ollama API.

    Supports chat completions (streaming and non-streaming),
    text embeddings, model discovery, memory tracking, and generation control.
    """

    EMBEDDING_PATTERNS: List[str] = [
        "nomic-embed", "bge-m3", "bge-large", "bge-base", "bge-small",
        "mxbai-embed", "all-minilm", "snowflake-arctic-embed",
        "multilingual-e5", "e5-large", "e5-base", "e5-small",
        "gte-large", "gte-base", "gte-small", "gte-qwen",
        "jina-embed", "paraphrase", "sentence-t5", "instructor",
        "text-embedding", "embed", "embedding",
    ]

    RERANKER_PATTERNS: List[str] = [
        "bge-reranker", "rerank", "ms-marco", "cross-encoder",
        "jina-reranker", "colbert",
    ]

    QUANT_MULTIPLIERS: Dict[str, float] = {
        "q4": 0.5, "q5": 0.6, "q6": 0.7, "q8": 1.0, "fp16": 2.0,
    }

    def __init__(self, api_url: str = "http://localhost:11434") -> None:
        self.api_url = api_url.rstrip("/")
        self._session = self._create_session()
        self._stop_flag = False
        self._context_length = DEFAULT_CONTEXT_LENGTH
        self._model_info_cache: Dict[str, Dict[str, Any]] = {}

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=MAX_REQUEST_RETRIES,
            backoff_factor=1,
            status_forcelist=RETRY_STATUS_FORCELIST,
        )
        session.mount("http://", HTTPAdapter(max_retries=retry))
        session.mount("https://", HTTPAdapter(max_retries=retry))
        return session

    def set_context_length(self, length: int) -> None:
        self._context_length = max(MIN_CONTEXT_LENGTH, min(length, MAX_CONTEXT_LENGTH))

    def get_context_length(self) -> int:
        return self._context_length

    def stop_generation(self) -> None:
        self._stop_flag = True

    def reset_stop(self) -> None:
        self._stop_flag = False

    def is_stopped(self) -> bool:
        return self._stop_flag

    def is_available(self) -> bool:
        try:
            response = self._session.get(f"{self.api_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    # --- Model discovery ---

    def get_models(self) -> List[str]:
        try:
            response = self._session.get(f"{self.api_url}/api/tags", timeout=30)
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        except Exception:
            return []

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

    def get_chat_models(self) -> List[str]:
        models = self.get_models()
        exclude = self.EMBEDDING_PATTERNS + self.RERANKER_PATTERNS
        return [m for m in models if not any(x in m.lower() for x in exclude)]

    def get_model_info(self, model: str) -> Dict[str, Any]:
        if model in self._model_info_cache:
            return self._model_info_cache[model]

        info: Dict[str, Any] = {
            "name": model,
            "context_length": DEFAULT_CONTEXT_LENGTH,
            "parameter_size": "unknown",
            "quantization": "unknown",
            "memory_required_gb": 0,
            "family": "unknown",
        }

        try:
            response = self._session.post(
                f"{self.api_url}/api/show",
                json={"name": model},
                timeout=30,
            )
            if response.status_code == 200:
                data = response.json()
                details = data.get("details", {})
                model_info = data.get("model_info", {})
                info["parameter_size"] = details.get("parameter_size", "unknown")
                info["quantization"] = details.get("quantization_level", "unknown")
                info["family"] = details.get("family", "unknown")
                context_length = model_info.get("context_length", DEFAULT_CONTEXT_LENGTH)
                if isinstance(context_length, int):
                    info["context_length"] = context_length
                if "B" in info["parameter_size"]:
                    info["memory_required_gb"] = self._estimate_memory(
                        info["parameter_size"], info["quantization"]
                    )
                self._model_info_cache[model] = info
        except Exception as e:
            logger.error("Error getting model info for %s: %s", model, e)

        return info

    def _estimate_memory(self, param_size: str, quantization: str) -> float:
        try:
            params = float(param_size.replace("B", ""))
            quant = quantization.lower() if quantization != "unknown" else "q4"
            multiplier = self.QUANT_MULTIPLIERS.get(quant, 0.5)
            return round(params * multiplier, 1)
        except (ValueError, TypeError):
            return 0.0

    def get_running_models(self) -> List[Dict]:
        try:
            response = self._session.get(f"{self.api_url}/api/ps", timeout=5)
            if response.status_code == 200:
                return response.json().get("models", [])
        except Exception:
            pass
        return []

    def get_memory_usage(self) -> Dict:
        running = self.get_running_models()
        total_memory_gb = 0.0
        models_loaded = []
        for m in running:
            name = m.get("name", "unknown")
            size_vram = m.get("size_vram", 0)
            size = m.get("size", 0)
            memory_gb = round(max(size_vram, size) / (1024**3), 2)
            total_memory_gb += memory_gb
            models_loaded.append({
                "name": name,
                "memory_gb": memory_gb,
                "expires_at": m.get("expires_at", ""),
            })
        return {
            "total_memory_gb": round(total_memory_gb, 2),
            "models_loaded": models_loaded,
            "model_count": len(models_loaded),
        }

    # --- BaseLLMClient interface ---

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        model = model or ""
        self.reset_stop()
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": kwargs.get("num_ctx", self._context_length),
            },
        }
        try:
            response = self._session.post(
                f"{self.api_url}/api/chat",
                json=payload,
                timeout=300,
            )
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")
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
        model = model or ""
        self.reset_stop()
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": kwargs.get("num_ctx", self._context_length),
            },
        }
        try:
            response = self._session.post(
                f"{self.api_url}/api/chat",
                json=payload,
                stream=True,
                timeout=300,
            )
            response.raise_for_status()
            for line in response.iter_lines():
                if self._stop_flag:
                    response.close()
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

    def embed(
        self,
        text: str | List[str],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        from ..core.config import CONFIG
        model = model or CONFIG.llm.embedding_model
        if isinstance(text, list):
            results = []
            for t in text:
                t = t[:MAX_EMBED_TEXT_LENGTH]
                try:
                    response = self._session.post(
                        f"{self.api_url}/api/embeddings",
                        json={"model": model, "prompt": t},
                        timeout=60,
                    )
                    response.raise_for_status()
                    results.append(response.json().get("embedding", []))
                except Exception as e:
                    logger.error("Embedding failed: %s", e)
                    results.append([])
            return results
        text = text[:MAX_EMBED_TEXT_LENGTH]
        try:
            response = self._session.post(
                f"{self.api_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=60,
            )
            response.raise_for_status()
            return response.json().get("embedding", [])
        except Exception as e:
            logger.error("Embedding failed: %s", e)
            return []

    # --- Legacy compat methods ---

    def chat_complete(self, messages, model, temperature=0.7, num_ctx=None):
        return self.chat(messages, model=model, temperature=temperature, num_ctx=num_ctx or self._context_length)