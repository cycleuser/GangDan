"""Ollama client for chat and embeddings."""

import sys
import json
from typing import List, Dict, Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gangdan.core.config import CONFIG


class OllamaClient:
    """Client for interacting with Ollama API."""
    
    # Comprehensive embedding model patterns (prioritized)
    EMBEDDING_PATTERNS = [
        "nomic-embed", "bge-m3", "bge-large", "bge-base", "bge-small",
        "mxbai-embed", "all-minilm", "snowflake-arctic-embed",
        "multilingual-e5", "e5-large", "e5-base", "e5-small",
        "gte-large", "gte-base", "gte-small", "gte-qwen",
        "jina-embed", "paraphrase", "sentence-t5", "instructor",
        "text-embedding", "embed", "embedding"
    ]
    
    # Reranker model patterns
    RERANKER_PATTERNS = [
        "bge-reranker", "rerank", "ms-marco", "cross-encoder",
        "jina-reranker", "colbert"
    ]
    
    def __init__(self, api_url: str = "http://localhost:11434"):
        self.api_url = api_url.rstrip("/")
        self._session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self._session.mount("http://", HTTPAdapter(max_retries=retry))
        self._stop_flag = False
    
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
        """Check if Ollama API is available."""
        try:
            r = self._session.get(f"{self.api_url}/api/tags", timeout=5)
            return r.status_code == 200
        except:
            return False
    
    def get_models(self) -> List[str]:
        """Get list of all available models."""
        try:
            r = self._session.get(f"{self.api_url}/api/tags", timeout=30)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except:
            return []
    
    def get_embedding_models(self) -> List[str]:
        """Get embedding models with comprehensive pattern matching."""
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
            print(f"[Ollama] Found {len(result)} embedding models: {', '.join(result[:5])}{'...' if len(result) > 5 else ''}", file=sys.stderr)
        
        return result
    
    def get_reranker_models(self) -> List[str]:
        """Get reranker models for improved retrieval."""
        models = self.get_models()
        result = []
        
        for pattern in self.RERANKER_PATTERNS:
            for m in models:
                if pattern in m.lower() and m not in result:
                    result.append(m)
        
        if result:
            print(f"[Ollama] Found {len(result)} reranker models: {', '.join(result)}", file=sys.stderr)
        
        return result
    
    def get_chat_models(self) -> List[str]:
        """Get chat models, excluding embedding and reranker models."""
        models = self.get_models()
        exclude_patterns = self.EMBEDDING_PATTERNS + self.RERANKER_PATTERNS
        chat_models = [m for m in models if not any(x in m.lower() for x in exclude_patterns)]
        
        if chat_models:
            print(f"[Ollama] Found {len(chat_models)} chat models: {', '.join(chat_models[:5])}{'...' if len(chat_models) > 5 else ''}", file=sys.stderr)
        
        return chat_models
    
    def embed(self, text: str, model: str) -> List[float]:
        """Generate embeddings for text."""
        text = text[:500] if len(text) > 500 else text
        r = self._session.post(
            f"{self.api_url}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=60
        )
        r.raise_for_status()
        return r.json().get("embedding", [])
    
    def translate(self, text: str, from_lang: str, to_lang: str) -> str:
        """Translate text using chat model for cross-lingual RAG search."""
        if not text.strip() or from_lang == to_lang:
            return text
        
        lang_names = {
            "zh": "Chinese", "en": "English", "ja": "Japanese",
            "ko": "Korean", "ru": "Russian", "fr": "French",
            "de": "German", "es": "Spanish", "pt": "Portuguese", "it": "Italian"
        }
        
        from_name = lang_names.get(from_lang, from_lang)
        to_name = lang_names.get(to_lang, to_lang)
        
        prompt = f"Translate the following text from {from_name} to {to_name}. Output ONLY the translation, nothing else:\n\n{text[:500]}"
        
        try:
            r = self._session.post(
                f"{self.api_url}/api/generate",
                json={"model": CONFIG.chat_model, "prompt": prompt, "stream": False},
                timeout=30
            )
            r.raise_for_status()
            return r.json().get("response", "").strip()
        except Exception as e:
            print(f"[Translation] Error: {e}", file=sys.stderr)
            return ""
    
    def chat_stream(self, messages: List[Dict], model: str, temperature: float = 0.7) -> Iterator[str]:
        """Stream chat responses token by token."""
        self.reset_stop()
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature}
        }
        try:
            r = self._session.post(
                f"{self.api_url}/api/chat",
                json=payload,
                stream=True,
                timeout=300
            )
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
    
    def chat_complete(self, messages: List[Dict], model: str, temperature: float = 0.7) -> str:
        """Non-streaming chat completion. Returns full response at once."""
        self.reset_stop()
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature}
        }
        try:
            r = self._session.post(
                f"{self.api_url}/api/chat",
                json=payload,
                timeout=300
            )
            r.raise_for_status()
            data = r.json()
            return data.get("message", {}).get("content", "")
        except Exception as e:
            return f"[Error: {e}]"
