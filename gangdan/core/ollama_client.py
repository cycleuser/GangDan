"""Ollama client for chat and embeddings.

This module provides a comprehensive client for interacting with the Ollama API,
supporting chat completions, embeddings, model management, and streaming responses.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Iterator, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import CONFIG
from .constants import (
    HTTP_TIMEOUT_LONG,
    HTTP_TIMEOUT_MEDIUM,
    HTTP_TIMEOUT_SHORT,
    MAX_EMBED_TEXT_LENGTH,
    MAX_REQUEST_RETRIES,
)

# Retry configuration
RETRY_STATUS_FORCELIST = [429, 500, 502, 503, 504]

# Context length limits
MIN_CONTEXT_LENGTH = 512
MAX_CONTEXT_LENGTH = 128000
DEFAULT_CONTEXT_LENGTH = 4096

# Text truncation limits
MAX_TRANSLATION_TEXT_LENGTH = 500

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for interacting with Ollama API.

    Provides methods for:
    - Chat completions (streaming and non-streaming)
    - Text embeddings
    - Model discovery and information
    - Memory usage tracking
    - Generation control (start/stop)

    Attributes
    ----------
    api_url : str
        Base URL for Ollama API.
    """

    EMBEDDING_PATTERNS: List[str] = [
        "nomic-embed",
        "bge-m3",
        "bge-large",
        "bge-base",
        "bge-small",
        "mxbai-embed",
        "all-minilm",
        "snowflake-arctic-embed",
        "multilingual-e5",
        "e5-large",
        "e5-base",
        "e5-small",
        "gte-large",
        "gte-base",
        "gte-small",
        "gte-qwen",
        "jina-embed",
        "paraphrase",
        "sentence-t5",
        "instructor",
        "text-embedding",
        "embed",
        "embedding",
    ]

    RERANKER_PATTERNS: List[str] = [
        "bge-reranker",
        "rerank",
        "ms-marco",
        "cross-encoder",
        "jina-reranker",
        "colbert",
    ]

    def __init__(self, api_url: str = "http://localhost:11434") -> None:
        """Initialize Ollama client.

        Parameters
        ----------
        api_url : str
            Base URL for Ollama API (default: http://localhost:11434).
        """
        self.api_url = api_url.rstrip("/")
        self._session = self._create_session()
        self._stop_flag = False
        self._context_length = DEFAULT_CONTEXT_LENGTH
        self._model_info_cache: Dict[str, Dict[str, Any]] = {}

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry configuration.

        Returns
        -------
        requests.Session
            Configured session with retry logic.
        """
        session = requests.Session()
        retry = Retry(
            total=MAX_REQUEST_RETRIES,
            backoff_factor=1,
            status_forcelist=RETRY_STATUS_FORCELIST,
        )
        session.mount("http://", HTTPAdapter(max_retries=retry))
        return session

    def set_context_length(self, length: int) -> None:
        """Set the context length for chat requests.

        Parameters
        ----------
        length : int
            Desired context length in tokens.
        """
        self._context_length = max(MIN_CONTEXT_LENGTH, min(length, MAX_CONTEXT_LENGTH))

    def get_context_length(self) -> int:
        """Get the current context length setting.

        Returns
        -------
        int
            Current context length in tokens.
        """
        return self._context_length

    # Quantization multipliers for memory estimation
    QUANT_MULTIPLIERS: Dict[str, float] = {
        "q4": 0.5,
        "q5": 0.6,
        "q6": 0.7,
        "q8": 1.0,
        "fp16": 2.0,
    }

    def get_model_info(self, model: str) -> Dict[str, Any]:
        """Get detailed model information including context length and memory requirements.

        Parameters
        ----------
        model : str
            Model name to query.

        Returns
        -------
        Dict[str, Any]
            Dictionary containing model metadata:
            - name: Model name
            - context_length: Maximum context window
            - parameter_size: Parameter count (e.g., "7B")
            - quantization: Quantization level
            - memory_required_gb: Estimated VRAM requirement
            - family: Model architecture family
        """
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

                context_length = model_info.get(
                    "context_length", DEFAULT_CONTEXT_LENGTH
                )
                if isinstance(context_length, int):
                    info["context_length"] = context_length

                if "B" in info["parameter_size"]:
                    info["memory_required_gb"] = self._estimate_memory_requirement(
                        info["parameter_size"], info["quantization"]
                    )

                self._model_info_cache[model] = info
        except (requests.RequestException, json.JSONDecodeError) as e:
            # Log network errors or JSON parsing errors
            logger.error(
                f"[Ollama] Network or parsing error getting model info for {model}: {e}"
            )
        except Exception as e:
            # Log any other unexpected errors
            logger.error(
                f"[Ollama] Unexpected error getting model info for {model}: {e}"
            )

        return info

    def _estimate_memory_requirement(self, param_size: str, quantization: str) -> float:
        """Estimate VRAM requirement based on parameters and quantization.

        Parameters
        ----------
        param_size : str
            Parameter size string (e.g., "7B").
        quantization : str
            Quantization level (e.g., "q4", "q8", "fp16").

        Returns
        -------
        float
            Estimated memory requirement in GB.
        """
        try:
            size_str = param_size.replace("B", "")
            params = float(size_str)
            quant = quantization.lower() if quantization != "unknown" else "q4"
            multiplier = self.QUANT_MULTIPLIERS.get(quant, 0.5)
            return round(params * multiplier, 1)
        except (ValueError, TypeError):
            return 0.0

    def get_running_models(self) -> List[Dict]:
        """Get currently running models with memory usage.
        
        Returns empty list silently when Ollama is unavailable.
        """
        try:
            response = self._session.get(f"{self.api_url}/api/ps", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get("models", [])
        except requests.exceptions.ConnectionError:
            pass
        except Exception as e:
            print(f"[Ollama] Failed to get running models: {e}", file=sys.stderr)
        return []

    def get_memory_usage(self) -> Dict:
        """Get current memory/VRAM usage of Ollama."""
        running = self.get_running_models()
        total_memory_gb = 0
        models_loaded = []

        for m in running:
            name = m.get("name", "unknown")
            size_vram = m.get("size_vram", 0)
            size = m.get("size", 0)
            memory_gb = round(max(size_vram, size) / (1024**3), 2)
            total_memory_gb += memory_gb
            models_loaded.append(
                {
                    "name": name,
                    "memory_gb": memory_gb,
                    "expires_at": m.get("expires_at", ""),
                }
            )

        return {
            "total_memory_gb": round(total_memory_gb, 2),
            "models_loaded": models_loaded,
            "model_count": len(models_loaded),
        }

    def stop_generation(self) -> None:
        """Signal generation to stop."""
        self._stop_flag = True

    def reset_stop(self) -> None:
        """Reset the stop flag."""
        self._stop_flag = False

    def is_stopped(self) -> bool:
        """Check if generation should be stopped."""
        return self._stop_flag

    def is_available(self) -> bool:
        """Check if Ollama server is available."""
        try:
            response = self._session.get(f"{self.api_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def get_models(self) -> List[str]:
        """Get all available models."""
        try:
            response = self._session.get(f"{self.api_url}/api/tags", timeout=30)
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        except Exception:
            return []

    def get_embedding_models(self) -> List[str]:
        """Get available embedding models."""
        models = self.get_models()
        result = []

        for pattern in self.EMBEDDING_PATTERNS:
            for m in models:
                m_lower = m.lower()
                if any(rp in m_lower for rp in self.RERANKER_PATTERNS):
                    continue
                if pattern in m_lower and m not in result:
                    result.append(m)

        if result:
            print(
                f"[Ollama] Found {len(result)} embedding models: {', '.join(result[:5])}{'...' if len(result) > 5 else ''}",
                file=sys.stderr,
            )

        return result

    def get_reranker_models(self) -> List[str]:
        """Get available reranker models."""
        models = self.get_models()
        result = []

        for pattern in self.RERANKER_PATTERNS:
            for m in models:
                if pattern in m.lower() and m not in result:
                    result.append(m)

        if result:
            print(
                f"[Ollama] Found {len(result)} reranker models: {', '.join(result)}",
                file=sys.stderr,
            )

        return result

    def get_chat_models(self) -> List[str]:
        """Get available chat models (excluding embedding and reranker models)."""
        models = self.get_models()
        exclude_patterns = self.EMBEDDING_PATTERNS + self.RERANKER_PATTERNS
        chat_models = [
            m for m in models if not any(x in m.lower() for x in exclude_patterns)
        ]

        if chat_models:
            print(
                f"[Ollama] Found {len(chat_models)} chat models: {', '.join(chat_models[:5])}{'...' if len(chat_models) > 5 else ''}",
                file=sys.stderr,
            )

        return chat_models

    def embed(self, text: str, model: str) -> List[float]:
        """Generate embeddings for text using specified model.
        
        Parameters
        ----------
        text : str
            Text to embed. Truncated to 500 characters.
        model : str
            Model name to use for embedding.
            
        Returns
        -------
        List[float]
            Embedding vector.
        """
        text = text[:500]
        try:
            response = self._session.post(
                f"{self.api_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=60,
            )
            response.raise_for_status()
            return response.json().get("embedding", [])
        except Exception as e:
            print(f"[Ollama] Embedding failed: {e}", file=sys.stderr)
            return []

    # Language code to full name mapping
    LANGUAGE_NAMES: Dict[str, str] = {
        "zh": "Chinese",
        "en": "English",
        "ja": "Japanese",
        "ko": "Korean",
        "ru": "Russian",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "pt": "Portuguese",
        "it": "Italian",
    }

    def translate(self, text: str, from_lang: str, to_lang: str) -> str:
        """Translate text from one language to another.

        Parameters
        ----------
        text : str
            Text to translate.
        from_lang : str
            Source language code.
        to_lang : str
            Target language code.

        Returns
        -------
        str
            Translated text (empty string on error).
        """
        if not text.strip() or from_lang == to_lang:
            return text

        from_name = self.LANGUAGE_NAMES.get(from_lang, from_lang)
        to_name = self.LANGUAGE_NAMES.get(to_lang, to_lang)

        prompt = (
            f"Translate the following text from {from_name} to {to_name}. "
            f"Output ONLY the translation, nothing else:\n\n{text[:MAX_TRANSLATION_TEXT_LENGTH]}"
        )

        try:
            response = self._session.post(
                f"{self.api_url}/api/generate",
                json={
                    "model": CONFIG.chat_model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except Exception as e:
            print(f"[Translation] Error: {e}", file=sys.stderr)
            return ""

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        num_ctx: Optional[int] = None,
    ) -> Iterator[str]:
        """Stream chat responses.

        Parameters
        ----------
        messages : List[Dict[str, str]]
            List of message dicts with 'role' and 'content' keys.
        model : str
            Chat model name.
        temperature : float
            Sampling temperature (default: 0.7).
        num_ctx : int or None
            Context length override (default: self._context_length).

        Yields
        ------
        str
            Response chunks as they arrive.

        Notes
        -----
        Can be stopped by calling stop_generation() from another thread.
        """
        self.reset_stop()
        ctx_len = num_ctx or self._context_length

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": ctx_len,
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

    def chat_complete(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        num_ctx: Optional[int] = None,
    ) -> str:
        """Get complete chat response (non-streaming).

        Parameters
        ----------
        messages : List[Dict[str, str]]
            List of message dicts with 'role' and 'content' keys.
        model : str
            Chat model name.
        temperature : float
            Sampling temperature (default: 0.7).
        num_ctx : int or None
            Context length override (default: self._context_length).

        Returns
        -------
        str
            Complete assistant response.
        """
        self.reset_stop()
        ctx_len = num_ctx or self._context_length

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": ctx_len,
            },
        }

        try:
            response = self._session.post(
                f"{self.api_url}/api/chat",
                json=payload,
                timeout=300,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except Exception as e:
            return f"[Error: {e}]"
