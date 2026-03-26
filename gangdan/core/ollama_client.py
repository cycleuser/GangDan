"""Ollama client for chat and embeddings."""

import sys
import json
from typing import List, Dict, Iterator, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gangdan.core.config import CONFIG


class OllamaClient:
    """Client for interacting with Ollama API."""
    
    EMBEDDING_PATTERNS = [
        "nomic-embed", "bge-m3", "bge-large", "bge-base", "bge-small",
        "mxbai-embed", "all-minilm", "snowflake-arctic-embed",
        "multilingual-e5", "e5-large", "e5-base", "e5-small",
        "gte-large", "gte-base", "gte-small", "gte-qwen",
        "jina-embed", "paraphrase", "sentence-t5", "instructor",
        "text-embedding", "embed", "embedding"
    ]
    
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
        self._context_length = 4096
        self._model_info_cache = {}
    
    def set_context_length(self, length: int):
        """Set the context length for chat requests."""
        self._context_length = max(512, min(length, 128000))
    
    def get_context_length(self) -> int:
        """Get the current context length setting."""
        return self._context_length
    
    def get_model_info(self, model: str) -> Dict:
        """Get detailed model information including context length and memory requirements."""
        if model in self._model_info_cache:
            return self._model_info_cache[model]
        
        info = {
            "name": model,
            "context_length": 4096,
            "parameter_size": "unknown",
            "quantization": "unknown",
            "memory_required_gb": 0,
            "family": "unknown",
        }
        
        try:
            r = self._session.post(
                f"{self.api_url}/api/show",
                json={"name": model},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                details = data.get("details", {})
                model_info = data.get("model_info", {})
                
                info["parameter_size"] = details.get("parameter_size", "unknown")
                info["quantization"] = details.get("quantization_level", "unknown")
                info["family"] = details.get("family", "unknown")
                
                context_length = model_info.get("context_length", 4096)
                if isinstance(context_length, int):
                    info["context_length"] = context_length
                
                if "B" in info["parameter_size"]:
                    try:
                        size_str = info["parameter_size"].replace("B", "")
                        params = float(size_str)
                        quant = info["quantization"].lower() if info["quantization"] != "unknown" else "q4"
                        quant_multiplier = {"q4": 0.5, "q5": 0.6, "q6": 0.7, "q8": 1.0, "fp16": 2.0}.get(quant, 0.5)
                        info["memory_required_gb"] = round(params * quant_multiplier, 1)
                    except:
                        pass
                
                self._model_info_cache[model] = info
        except Exception as e:
            print(f"[Ollama] Failed to get model info for {model}: {e}", file=sys.stderr)
        
        return info
    
    def get_running_models(self) -> List[Dict]:
        """Get currently running models with memory usage."""
        try:
            r = self._session.get(f"{self.api_url}/api/ps", timeout=10)
            if r.status_code == 200:
                data = r.json()
                return data.get("models", [])
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
    
    def stop_generation(self):
        self._stop_flag = True
    
    def reset_stop(self):
        self._stop_flag = False
    
    def is_stopped(self) -> bool:
        return self._stop_flag
    
    def is_available(self) -> bool:
        try:
            r = self._session.get(f"{self.api_url}/api/tags", timeout=5)
            return r.status_code == 200
        except:
            return False
    
    def get_models(self) -> List[str]:
        try:
            r = self._session.get(f"{self.api_url}/api/tags", timeout=30)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except:
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
        
        if result:
            print(f"[Ollama] Found {len(result)} embedding models: {', '.join(result[:5])}{'...' if len(result) > 5 else ''}", file=sys.stderr)
        
        return result
    
    def get_reranker_models(self) -> List[str]:
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
        models = self.get_models()
        exclude_patterns = self.EMBEDDING_PATTERNS + self.RERANKER_PATTERNS
        chat_models = [m for m in models if not any(x in m.lower() for x in exclude_patterns)]
        
        if chat_models:
            print(f"[Ollama] Found {len(chat_models)} chat models: {', '.join(chat_models[:5])}{'...' if len(chat_models) > 5 else ''}", file=sys.stderr)
        
        return chat_models
    
    def embed(self, text: str, model: str) -> List[float]:
        text = text[:500] if len(text) > 500 else text
        r = self._session.post(
            f"{self.api_url}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=60
        )
        r.raise_for_status()
        return r.json().get("embedding", [])
    
    def translate(self, text: str, from_lang: str, to_lang: str) -> str:
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
    
    def chat_stream(self, messages: List[Dict], model: str, temperature: float = 0.7, num_ctx: int = None) -> Iterator[str]:
        self.reset_stop()
        ctx_len = num_ctx or self._context_length
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": ctx_len,
            }
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
    
    def chat_complete(self, messages: List[Dict], model: str, temperature: float = 0.7, num_ctx: int = None) -> str:
        self.reset_stop()
        ctx_len = num_ctx or self._context_length
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": ctx_len,
            }
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
