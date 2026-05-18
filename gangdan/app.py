#!/usr/bin/env python3
"""
GangDan - Knowledge Management & Teaching Assistant
========================================

Flask application backend with:
- Multi-language UI (10 languages)
- Ollama chat with streaming
- ChromaDB vector knowledge base
- Web search with multiple engines
- Documentation download and indexing

Frontend is decoupled into separate files:
- templates/index.html  (Jinja2 template)
- static/css/style.css  (Pure CSS)
- static/js/*.js         (Pure JavaScript modules)

Usage:
    pip install flask flask-cors requests chromadb
    python app.py
"""

# Standard library imports
import hashlib
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

# Use Chinese mirror for HuggingFace model downloads (docling, transformers, etc.)
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# Third-party imports
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from flask import (
        Flask,
        jsonify,
        render_template,
        request,
        Response,
        stream_with_context,
    )
    from flask_cors import CORS
except ImportError as e:
    logging.critical("Missing dependency: %s", e)
    logging.critical("\nPlease install required packages:")
    logging.critical("  pip install flask flask-cors requests chromadb")
    sys.exit(1)

from gangdan.core.config import (
    CHROMA_DIR,
    CONFIG,
    DATA_DIR,
    DOCS_DIR,
    LANGUAGES,
    TRANSLATIONS,
    delete_user_kb,
    detect_language,
    get_proxies,
    load_config,
    load_user_kbs,
    save_config,
    save_user_kb,
    sanitize_kb_name,
    t,
)

# =============================================================================
# Logging Setup
# =============================================================================

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# User Knowledge Base Manifest file path (functions imported from core.config)
USER_KBS_FILE = DATA_DIR / "user_kbs.json"


def _resolve_kb_dir(kb_name: str) -> tuple:
    """Resolve a KB name to its directory and internal_name.

    Checks DOCS_DIR first, then CUSTOM_KBS_DIR, then user_kbs.json for display_name mapping.

    Returns
    -------
    tuple of (Path or None, str)
        (kb_dir, internal_name) - kb_dir is None if not found.
    """
    from gangdan.core.kb_manager import CUSTOM_KBS_DIR

    user_kbs = load_user_kbs()

    candidates = [kb_name]
    if not kb_name.startswith("user_"):
        candidates.append(f"user_{kb_name}")

    for iname, meta in user_kbs.items():
        if meta.get("display_name") == kb_name or iname == kb_name:
            if iname not in candidates:
                candidates.append(iname)

    for name in candidates:
        docs_path = DOCS_DIR / name
        if docs_path.exists():
            return (docs_path, name)
        custom_path = CUSTOM_KBS_DIR / name
        if custom_path.exists():
            return (custom_path, name)

    return (None, kb_name)


def update_user_kb_name(old_internal_name: str, new_internal_name: str) -> None:
    """Update a user KB name in the registry.

    Parameters
    ----------
    old_internal_name : str
        Current internal name of the knowledge base.
    new_internal_name : str
        New internal name for the knowledge base.
    """
    kbs = load_user_kbs()
    if old_internal_name in kbs:
        kbs[new_internal_name] = kbs.pop(old_internal_name)
        kbs[new_internal_name]["display_name"] = new_internal_name.replace(
            "user_", "", 1
        )
    USER_KBS_FILE.write_text(
        json.dumps(kbs, indent=2, ensure_ascii=False), encoding="utf-8"
    )


from gangdan.core.doc_manager import DOC_SOURCES  # noqa: E402


# =============================================================================
# Ollama Client
# =============================================================================


class OllamaClient:
    # Comprehensive embedding model patterns (prioritized)
    EMBEDDING_PATTERNS = [
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

    # Reranker model patterns
    RERANKER_PATTERNS = [
        "bge-reranker",
        "rerank",
        "ms-marco",
        "cross-encoder",
        "jina-reranker",
        "colbert",
    ]

    def __init__(self, api_url: str = "http://localhost:11434"):
        self.api_url = api_url.rstrip("/")
        self._session = requests.Session()
        retry = Retry(
            total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
        )
        self._session.mount("http://", HTTPAdapter(max_retries=retry))
        self._stop_flag = False
        self._context_length = 4096
        self._model_info_cache = {}

    def set_context_length(self, length: int):
        """Set the context length for chat requests."""
        self._context_length = max(512, min(length, 1000000))

    def get_context_length(self) -> int:
        """Get the current context length setting."""
        return self._context_length

    def get_model_info(self, model: str) -> Dict:
        """Get detailed model information."""
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
                f"{self.api_url}/api/show", json={"name": model}, timeout=30
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

                if "B" in str(info["parameter_size"]):
                    try:
                        size_str = str(info["parameter_size"]).replace("B", "")
                        params = float(size_str)
                        quant = (
                            str(info["quantization"]).lower()
                            if info["quantization"] != "unknown"
                            else "q4"
                        )
                        quant_multiplier = {
                            "q4": 0.5,
                            "q5": 0.6,
                            "q6": 0.7,
                            "q8": 1.0,
                            "fp16": 2.0,
                        }.get(quant, 0.5)
                        info["memory_required_gb"] = round(params * quant_multiplier, 1)
                    except (ValueError, KeyError, TypeError):
                        pass

                self._model_info_cache[model] = info
        except Exception as e:
            print(
                f"[Ollama] Failed to get model info for {model}: {e}", file=sys.stderr
            )

        return info

    def get_running_models(self) -> List[Dict]:
        """Get currently running models with memory usage."""
        try:
            r = self._session.get(f"{self.api_url}/api/ps", timeout=10)
            if r.status_code == 200:
                data = r.json()
                return data.get("models", [])
        except Exception as e:
            logger.error("[Ollama] Failed to get running models: %s", e)
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
        except (requests.RequestException, requests.Timeout):
            return False

    def get_models(self) -> List[str]:
        try:
            r = self._session.get(f"{self.api_url}/api/tags", timeout=30)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except (
            requests.RequestException,
            requests.Timeout,
            KeyError,
            json.JSONDecodeError,
        ):
            return []

    def get_embedding_models(self) -> List[str]:
        """Get embedding models with comprehensive pattern matching."""
        models = self.get_models()
        result = []

        # First pass: prioritized patterns
        for pattern in self.EMBEDDING_PATTERNS:
            for m in models:
                m_lower = m.lower()
                # Skip reranker models
                if any(rp in m_lower for rp in self.RERANKER_PATTERNS):
                    continue
                if pattern in m_lower and m not in result:
                    result.append(m)

        # Log found models
        if result:
            print(
                f"[Ollama] Found {len(result)} embedding models: {', '.join(result[:5])}{'...' if len(result) > 5 else ''}",
                file=sys.stderr,
            )

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
            print(
                f"[Ollama] Found {len(result)} reranker models: {', '.join(result)}",
                file=sys.stderr,
            )

        return result

    def get_chat_models(self) -> List[str]:
        """Get chat models, excluding embedding and reranker models."""
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
        text = text[:500] if len(text) > 500 else text
        r = self._session.post(
            f"{self.api_url}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("embedding", [])

    def translate(self, text: str, from_lang: str, to_lang: str) -> str:
        """Translate text using chat model for cross-lingual RAG search."""
        if not text.strip() or from_lang == to_lang:
            return text

        lang_names = {
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

        from_name = lang_names.get(from_lang, from_lang)
        to_name = lang_names.get(to_lang, to_lang)

        prompt = f"Translate the following text from {from_name} to {to_name}. Output ONLY the translation, nothing else:\n\n{text[:500]}"

        try:
            result = self.chat_complete(
                model=CONFIG.chat_model,
                messages=[{"role": "user", "content": prompt}],
            )
            return result.strip() if result else ""
        except Exception as e:
            logger.error("[Translation] Error: %s", e)
            return ""

    def chat_complete(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = 0.7,
        num_ctx: int = None,
    ) -> str:
        """Non-streaming chat completion. Returns the full response text."""
        ctx_len = num_ctx or self._context_length
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": ctx_len},
        }
        try:
            r = self._session.post(
                f"{self.api_url}/api/chat", json=payload, timeout=300
            )
            r.raise_for_status()
            data = r.json()
            return data.get("message", {}).get("content", "")
        except Exception as e:
            logger.error("[Ollama] chat_complete error: %s", e)
            return ""

    def chat_stream(
        self,
        messages: List[Dict],
        model: str,
        temperature: float = 0.7,
        num_ctx: int = None,
    ) -> Iterator[str]:
        self.reset_stop()
        ctx_len = num_ctx or self._context_length
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature, "num_ctx": ctx_len},
        }
        try:
            r = self._session.post(
                f"{self.api_url}/api/chat", json=payload, stream=True, timeout=300
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


OLLAMA = OllamaClient(CONFIG.ollama_url)
RESEARCH_CLIENT = None


def get_research_client():
    """Get LLM client for deep research (falls back to chat client)."""
    global RESEARCH_CLIENT
    if not CONFIG.research_provider or CONFIG.research_provider == "ollama":
        return get_chat_client()  # Use main chat client
    else:
        if (
            RESEARCH_CLIENT is None
            or RESEARCH_CLIENT.api_key != CONFIG.research_api_key
        ):
            from gangdan.core.llm_client import OpenAIClient

            RESEARCH_CLIENT = OpenAIClient(
                api_key=CONFIG.research_api_key,
                base_url=CONFIG.research_api_base_url,
                provider=CONFIG.research_provider,
            )
        return RESEARCH_CLIENT


def get_chat_client():
    """Get LLM client for main chat (supports Ollama and OpenAI-compatible APIs)."""
    provider = CONFIG.chat_provider
    
    if provider == "ollama":
        OLLAMA.api_url = CONFIG.ollama_url
        return OLLAMA
    else:
        from gangdan.core.llm_client import OpenAIClient
        
        return OpenAIClient(
            api_key=CONFIG.chat_api_key,
            base_url=CONFIG.chat_api_base_url,
            provider=provider,
        )

# Monkey-patch OLLAMA to fallback to configured chat client when Ollama is unavailable
_orig_ollama_chat_complete = OLLAMA.chat_complete
_orig_ollama_chat_stream = OLLAMA.chat_stream

def _fallback_chat_complete(messages, model=None, **kwargs):
    result = _orig_ollama_chat_complete(messages, model or CONFIG.chat_model, **kwargs)
    if result and not str(result).startswith("[Error"):
        return result
    fb = get_chat_client()
    if fb is not OLLAMA:
        try:
            fallback_result = fb.chat_complete(messages, model or CONFIG.chat_model, **kwargs)
            if fallback_result:
                return fallback_result
        except Exception:
            pass
    return ""

def _fallback_chat_stream(messages, model=None, **kwargs):
    success = False
    try:
        for chunk in _orig_ollama_chat_stream(messages, model or CONFIG.chat_model, **kwargs):
            if "[Error" not in str(chunk):
                success = True
                yield chunk
    except Exception:
        pass
    if not success:
        fb = get_chat_client()
        if fb is not OLLAMA:
            try:
                yield from fb.chat_stream(messages, model or CONFIG.chat_model, **kwargs)
            except Exception:
                pass

OLLAMA.chat_complete = _fallback_chat_complete
OLLAMA.chat_stream = _fallback_chat_stream


# =============================================================================
# Vector Database (uses abstraction layer from core.vector_db)
# =============================================================================


# =============================================================================
# Document Downloader & Indexer
# =============================================================================


class DocManager:
    def __init__(self, docs_dir: Path, chroma, ollama: OllamaClient):
        self.docs_dir = docs_dir
        self.chroma = chroma
        self.ollama = ollama
        self._session = requests.Session()

    def download_source(self, source_name: str) -> Tuple[int, List[str]]:
        if source_name not in DOC_SOURCES:
            logger.error("[Download] Unknown source: %s", source_name)
            return 0, [f"Unknown source: {source_name}"]

        source = DOC_SOURCES[source_name]
        urls = source["urls"]
        downloaded = 0
        errors = []
        proxies = get_proxies()

        source_dir = self.docs_dir / source_name
        source_dir.mkdir(parents=True, exist_ok=True)

        logger.info("[Download] Starting %s: %s URLs", source_name, len(urls))
        if proxies:
            print(
                f"[Download] Using proxy: {proxies.get('http', 'N/A')}", file=sys.stderr
            )

        for url in urls:
            filename = url.split("/")[-1]
            try:
                r = self._session.get(url, timeout=30, proxies=proxies)
                r.raise_for_status()
                content = r.text

                # Convert to markdown if needed
                if filename.endswith(".rst"):
                    filename = filename.replace(".rst", ".md")
                elif filename.endswith(".py") or filename.endswith(".ipynb"):
                    content = f"```python\n{content}\n```"
                    filename = filename.replace(".py", ".md").replace(".ipynb", ".md")
                elif filename.endswith(".html"):
                    filename = filename.replace(".html", ".md")
                elif filename.endswith(".texi"):
                    filename = filename.replace(".texi", ".md")
                elif filename.endswith(".cpp"):
                    content = f"```cpp\n{content}\n```"
                    filename = filename.replace(".cpp", ".md")
                elif not filename.endswith(".md"):
                    filename += ".md"

                filepath = source_dir / filename
                filepath.write_text(content, encoding="utf-8")
                downloaded += 1
                logger.info("[Download] OK: %s", filename)
            except Exception as e:
                err_msg = f"{filename}: {type(e).__name__}"
                errors.append(err_msg)
                logger.error("[Download] FAIL: %s", err_msg)

            time.sleep(0.2)

        print(
            f"[Download] Completed {source_name}: {downloaded} success, {len(errors)} errors",
            file=sys.stderr,
        )
        return downloaded, errors

    def index_source(
        self, source_name: str, process_images: bool = True, image_mode: str = "copy"
    ) -> Tuple[int, int, int]:
        if self.chroma is None or self.chroma.client is None:
            print(
                f"[Index] Skipped {source_name} - ChromaDB not available",
                file=sys.stderr,
            )
            return 0, 0, 0
        if not CONFIG.embedding_model:
            print(
                f"[Index] Skipped {source_name} - no embedding model configured",
                file=sys.stderr,
            )
            return 0, 0, 0

        source_dir = self.docs_dir / source_name
        if not source_dir.exists():
            print(
                f"[Index] Skipped {source_name} - directory not found", file=sys.stderr
            )
            return 0, 0, 0

        files = list(source_dir.glob("*.md")) + list(source_dir.glob("*.txt"))
        if not files:
            print(
                f"[Index] Skipped {source_name} - no markdown/text files found",
                file=sys.stderr,
            )
            return 0, 0, 0

        logger.info("[Index] Processing %s: %s files", source_name, len(files))
        if process_images:
            logger.info("[Index] Image mode: %s", image_mode)

        documents = []
        embeddings = []
        metadatas = []
        ids = []
        detected_languages = set()
        total_images = 0

        for filepath in files:
            content = filepath.read_text(encoding="utf-8")

            # Process images in markdown files
            if process_images and filepath.suffix.lower() == ".md":
                content, img_count = self._process_document_images(
                    source_dir, filepath, content, image_mode
                )
                if img_count > 0:
                    total_images += img_count
                    print(
                        f"[Index]   {filepath.name}: processed {img_count} images",
                        file=sys.stderr,
                    )

            # Detect document language for cross-lingual search
            doc_lang = detect_language(content)
            detected_languages.add(doc_lang)
            print(
                f"[Index]   {filepath.name}: detected language = {doc_lang}",
                file=sys.stderr,
            )

            # Simple chunking
            chunks = self._chunk_text(content, CONFIG.chunk_size, CONFIG.chunk_overlap)
            file_chunks = 0

            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) < 50:
                    continue
                try:
                    emb = self.ollama.embed(chunk, CONFIG.embedding_model)
                    doc_id = hashlib.md5(f"{filepath.name}_{i}".encode()).hexdigest()

                    documents.append(chunk)
                    embeddings.append(emb)
                    metadatas.append(
                        {
                            "source": source_name,
                            "file": filepath.name,
                            "chunk": i,
                            "language": doc_lang,
                        }
                    )
                    ids.append(doc_id)
                    file_chunks += 1
                except Exception as e:
                    print(
                        f"[Index]   Error embedding chunk {i} of {filepath.name}: {e}",
                        file=sys.stderr,
                    )
                    continue

            logger.info("[Index] %s: %s chunks", filepath.name, file_chunks)

        if documents:
            self.chroma.add_documents(
                source_name, documents, embeddings, metadatas, ids
            )
            emb_dim = len(embeddings[0]) if embeddings else 0
            if emb_dim > 0:
                self.chroma.set_collection_embedding_model(
                    source_name, CONFIG.embedding_model, emb_dim
                )
            print(
                f"[Index] Added {len(documents)} chunks to collection '{source_name}'",
                file=sys.stderr,
            )
            print(
                f"[Index] Languages detected: {', '.join(detected_languages)}",
                file=sys.stderr,
            )
            print(
                f"[Index] Embedding model: {CONFIG.embedding_model}, dimension: {emb_dim}",
                file=sys.stderr,
            )

        return len(files), len(documents), total_images

    def _process_document_images(
        self,
        kb_dir: Path,
        source_path: Path,
        content: str,
        image_mode: str = "copy",
    ) -> Tuple[str, int]:
        from gangdan.core.image_handler import ImageHandler

        try:
            handler = ImageHandler(kb_dir)
            result = handler.process_document(
                content, source_path, embed_mode=image_mode
            )

            if result.copied_count > 0:
                source_path.write_text(result.updated_content, encoding="utf-8")

            return result.updated_content, result.copied_count
        except Exception as e:
            logger.error("[Index] Error processing images: %s", e)
            return content, 0

    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        if overlap >= chunk_size:
            overlap = max(0, chunk_size - 1)
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start = end - overlap
        return chunks

    def list_downloaded(self) -> List[Dict]:
        result = []
        if self.docs_dir.exists():
            for d in self.docs_dir.iterdir():
                if d.is_dir():
                    files = list(d.glob("*.md"))
                    result.append({"name": d.name, "files": len(files)})
        return result


# =============================================================================
# Web Search
# =============================================================================


class WebSearcher:
    def __init__(self):
        self._timeout = 15
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )

    def _get_proxies(self):
        return get_proxies()

    def search(self, query: str, num_results: int = 5) -> List[Dict]:
        results = []
        proxies = self._get_proxies()

        if proxies:
            print(
                f"[WebSearch] Using proxy: {proxies.get('http', 'N/A')}",
                file=sys.stderr,
            )

        # Try DuckDuckGo
        try:
            url = "https://html.duckduckgo.com/html/"
            resp = self._session.post(
                url, data={"q": query}, timeout=self._timeout, proxies=proxies
            )
            resp.raise_for_status()

            pattern = re.compile(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>.*?'
                r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>',
                re.DOTALL,
            )

            for match in pattern.finditer(resp.text):
                if len(results) >= num_results:
                    break
                link, title, snippet = match.groups()
                if "uddg=" in link:
                    from urllib.parse import unquote, parse_qs

                    parsed = parse_qs(link.split("?")[-1])
                    link = unquote(parsed.get("uddg", [link])[0])

                results.append(
                    {
                        "title": title.strip(),
                        "url": link,
                        "snippet": snippet.strip()[:200],
                    }
                )
        except Exception as e:
            logger.error("[WebSearch] DuckDuckGo error: %s", e)

        return results


WEB_SEARCHER = WebSearcher()


# =============================================================================
# Conversation Manager
# =============================================================================


from gangdan.core.conversation import ConversationManager  # noqa: E402


CONVERSATION = ConversationManager()


# =============================================================================
# Flask Application
# =============================================================================

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB upload limit

# Register learning module Blueprint
from gangdan.learning_routes import learning_bp

app.register_blueprint(learning_bp)

# Register research module Blueprint
from gangdan.research_routes import research_bp

app.register_blueprint(research_bp)

# Register preprint intelligence module Blueprint
from gangdan.preprint_routes import preprint_bp

app.register_blueprint(preprint_bp)

# Register custom knowledge base Blueprint
from gangdan.kb_routes import kb_bp

app.register_blueprint(kb_bp)

# Register batch export Blueprint
from gangdan.export_routes import export_bp

app.register_blueprint(export_bp)

# Initialize components
DATA_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
load_config()

try:
    from gangdan.core.vector_db import create_vector_db_auto

    CHROMA = create_vector_db_auto(str(CHROMA_DIR), preferred=CONFIG.vector_db_type)
except BaseException as e:
    logger.critical("[VectorDB] Init failed: %s", e)
    logger.critical("[VectorDB] App will run without knowledge base features")
    CHROMA = None

DOC_MANAGER = DocManager(DOCS_DIR, CHROMA, OLLAMA)


# =============================================================================
# API Routes
# =============================================================================


@app.route("/")
def index():
    lang = request.args.get("lang", CONFIG.language)
    CONFIG.language = lang
    save_config()

    return render_template(
        "index.html",
        lang=lang,
        languages=LANGUAGES,
        t=t,
        config=CONFIG,
        doc_sources=DOC_SOURCES,
        translations_json=json.dumps(TRANSLATIONS, ensure_ascii=False),
    )


@app.route("/api/models")
def get_models():
    OLLAMA.api_url = CONFIG.ollama_url

    chat_models = OLLAMA.get_chat_models()
    embed_models = OLLAMA.get_embedding_models()
    reranker_models = OLLAMA.get_reranker_models()

    research_client = get_research_client()
    research_models = []
    if CONFIG.research_provider != "ollama":
        research_models = research_client.get_chat_models()

    chat_provider_models = []
    if CONFIG.chat_provider != "ollama":
        chat_client = get_chat_client()
        chat_provider_models = chat_client.get_chat_models()

    return jsonify(
        {
            "ollama_available": OLLAMA.is_available(),
            "chat_models": chat_models,
            "embed_models": embed_models,
            "reranker_models": reranker_models,
            "research_models": research_models,
            "chat_provider_models": chat_provider_models,
            "current_chat": CONFIG.chat_model,
            "current_embed": CONFIG.embedding_model,
            "current_reranker": CONFIG.reranker_model,
            "current_translate_model": CONFIG.translate_model,
            "current_research_model": CONFIG.research_model,
            "current_chat_provider_model": CONFIG.chat_model_name,
            "research_provider": CONFIG.research_provider,
            "chat_provider": CONFIG.chat_provider,
            "vector_db_type": CONFIG.vector_db_type,
            "rag_distance_threshold": CONFIG.rag_distance_threshold,
            "chat_temperature": CONFIG.chat_temperature,
            "chat_max_tokens": CONFIG.chat_max_tokens,
        }
    )


@app.route("/api/model/info/<path:model_name>")
def get_model_info(model_name):
    """Get detailed model information including context length and memory requirements."""
    OLLAMA.api_url = CONFIG.ollama_url
    info = OLLAMA.get_model_info(model_name)
    return jsonify(info)


@app.route("/api/memory")
def get_memory_usage():
    """Get current Ollama memory/VRAM usage."""
    OLLAMA.api_url = CONFIG.ollama_url
    usage = OLLAMA.get_memory_usage()
    return jsonify(usage)


@app.route("/api/context-length", methods=["GET", "POST"])
def context_length():
    """Get or set the context length for Ollama calls."""
    if request.method == "POST":
        data = request.json or {}
        length = data.get("context_length", 4096)
        OLLAMA.set_context_length(length)
        return jsonify({"success": True, "context_length": OLLAMA.get_context_length()})
    return jsonify({"context_length": OLLAMA.get_context_length()})


@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.json

    if "ollama_url" in data:
        CONFIG.ollama_url = data["ollama_url"]
        OLLAMA.api_url = data["ollama_url"]
    if "chat_model" in data:
        CONFIG.chat_model = data["chat_model"]
    if "embed_model" in data:
        CONFIG.embedding_model = data["embed_model"]
    if "reranker_model" in data:
        CONFIG.reranker_model = data["reranker_model"]
    if "context_length" in data:
        CONFIG.context_length = int(data["context_length"])
        if hasattr(OLLAMA, "set_context_length"):
            OLLAMA.set_context_length(CONFIG.context_length)
    if "max_context_tokens" in data:
        CONFIG.max_context_tokens = int(data["max_context_tokens"])
    if "output_language" in data:
        CONFIG.output_language = data["output_language"]
    if "proxy_mode" in data:
        CONFIG.proxy_mode = data["proxy_mode"]
    if "proxy_http" in data:
        CONFIG.proxy_http = data["proxy_http"]
    if "proxy_https" in data:
        CONFIG.proxy_https = data["proxy_https"]
    if "strict_kb_mode" in data:
        CONFIG.strict_kb_mode = bool(data["strict_kb_mode"])
    if "vector_db_type" in data:
        CONFIG.vector_db_type = data["vector_db_type"]
    if "research_provider" in data:
        old_rprovider = CONFIG.research_provider
        CONFIG.research_provider = data["research_provider"]
        if old_rprovider and old_rprovider != data["research_provider"]:
            old_rkey = CONFIG.research_api_key
            old_rurl = CONFIG.research_api_base_url
            if old_rkey:
                CONFIG.provider_keys[old_rprovider + "_research"] = old_rkey
            if old_rurl:
                CONFIG.provider_base_urls[old_rprovider + "_research"] = old_rurl
            new_rkey = CONFIG.provider_keys.get(data["research_provider"] + "_research", "")
            new_rurl = CONFIG.provider_base_urls.get(data["research_provider"] + "_research", "")
            CONFIG.research_api_key = new_rkey
            CONFIG.research_api_base_url = new_rurl
    if "research_api_key" in data:
        CONFIG.research_api_key = data["research_api_key"]
        rprovider = data.get("research_provider", CONFIG.research_provider)
        if data["research_api_key"]:
            CONFIG.provider_keys[rprovider + "_research"] = data["research_api_key"]
    if "research_api_base_url" in data:
        CONFIG.research_api_base_url = data["research_api_base_url"]
        rprovider = data.get("research_provider", CONFIG.research_provider)
        if data["research_api_base_url"]:
            CONFIG.provider_base_urls[rprovider + "_research"] = data["research_api_base_url"]
    if "research_model" in data:
        CONFIG.research_model = data["research_model"]
    if "chat_provider" in data:
        old_provider = CONFIG.chat_provider
        CONFIG.chat_provider = data["chat_provider"]
        if old_provider and old_provider != data["chat_provider"]:
            old_key = CONFIG.chat_api_key
            old_url = CONFIG.chat_api_base_url
            if old_key:
                CONFIG.provider_keys[old_provider] = old_key
            if old_url:
                CONFIG.provider_base_urls[old_provider] = old_url
            new_key = CONFIG.provider_keys.get(data["chat_provider"], "")
            new_url = CONFIG.provider_base_urls.get(data["chat_provider"], "")
            CONFIG.chat_api_key = new_key
            CONFIG.chat_api_base_url = new_url
    if "chat_api_key" in data:
        CONFIG.chat_api_key = data["chat_api_key"]
        provider = data.get("chat_provider", CONFIG.chat_provider)
        if data["chat_api_key"]:
            CONFIG.provider_keys[provider] = data["chat_api_key"]
    if "chat_api_base_url" in data:
        CONFIG.chat_api_base_url = data["chat_api_base_url"]
        provider = data.get("chat_provider", CONFIG.chat_provider)
        if data["chat_api_base_url"]:
            CONFIG.provider_base_urls[provider] = data["chat_api_base_url"]
    if "chat_model_name" in data:
        CONFIG.chat_model_name = data["chat_model_name"]
    if "translate_model" in data:
        CONFIG.translate_model = data["translate_model"]
    if "rag_distance_threshold" in data:
        CONFIG.rag_distance_threshold = float(data["rag_distance_threshold"])
    if "chat_temperature" in data:
        CONFIG.chat_temperature = float(data["chat_temperature"])
    if "chat_max_tokens" in data:
        CONFIG.chat_max_tokens = int(data["chat_max_tokens"])

    save_config()
    return jsonify({"success": True, "message": "Settings saved"})


@app.route("/api/provider/keys", methods=["POST"])
def save_provider_keys():
    """Save per-provider API keys and base URLs."""
    data = request.json or {}
    provider = data.get("provider", "")
    api_key = data.get("api_key", "")
    base_url = data.get("base_url", "")
    scope = data.get("scope", "chat")

    if not provider:
        return jsonify({"success": False, "error": "provider required"})

    key_key = provider if scope == "chat" else provider + "_research"
    url_key = provider if scope == "chat" else provider + "_research"

    if api_key:
        CONFIG.provider_keys[key_key] = api_key
    elif key_key in CONFIG.provider_keys:
        del CONFIG.provider_keys[key_key]

    if base_url:
        CONFIG.provider_base_urls[url_key] = base_url
    elif url_key in CONFIG.provider_base_urls:
        del CONFIG.provider_base_urls[url_key]

    save_config()
    return jsonify({"success": True})


@app.route("/api/provider/keys", methods=["GET"])
def get_provider_keys():
    """Retrieve stored per-provider API keys."""
    result = {"provider_keys": CONFIG.provider_keys, "provider_base_urls": CONFIG.provider_base_urls}
    return jsonify(result)


@app.route("/api/set-language", methods=["POST"])
def set_language():
    data = request.json
    lang = data.get("language", "zh")
    if lang in LANGUAGES:
        CONFIG.language = lang
        save_config()
        return jsonify({"success": True, "language": lang})
    return jsonify({"success": False, "message": "Unsupported language"}), 400


@app.route("/api/test-connection", methods=["POST"])
def test_connection():
    data = request.json
    url = data.get("url", CONFIG.ollama_url)

    try:
        r = requests.get(f"{url.rstrip('/')}/api/tags", timeout=5)
        if r.status_code == 200:
            return jsonify({"success": True, "message": "Connection successful"})
        return jsonify({"success": False, "message": f"HTTP {r.status_code}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route("/api/chat-providers")
def get_chat_providers():
    """Get list of available chat providers with their info."""
    from gangdan.core.llm_client import list_providers, get_provider_config
    
    providers = list_providers()
    return jsonify({"providers": providers})


@app.route("/api/provider/models", methods=["POST"])
def get_provider_models():
    """Dynamically fetch available models from a provider, validating the API key.

    For providers that don't support /models endpoint, validates key via a
    minimal chat request and returns preset model list.

    Request JSON: { provider: str, api_key: str, base_url: str }
    Returns: { success: bool, models: list, default_model: str, error: str }
    """
    from gangdan.core.llm_client import create_client, PROVIDER_CONFIGS

    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "").strip()
    api_key = data.get("api_key", "").strip()
    base_url = data.get("base_url", "").strip()

    if not provider or provider == "ollama":
        ollama_url = base_url or CONFIG.ollama_url
        try:
            r = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=10)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                chat_models = [m for m in models if not any(
                    p in m.lower() for p in ["embed", "mxbai", "nomic", "bge", "e5", "gte"]
                )]
                return jsonify({
                    "success": True,
                    "models": sorted(chat_models),
                    "default_model": chat_models[0] if chat_models else "",
                })
        except Exception as e:
            return jsonify({"success": False, "models": [], "error": str(e)})
        return jsonify({"success": False, "models": [], "error": "Cannot reach Ollama"})

    config = PROVIDER_CONFIGS.get(provider)
    if not config:
        return jsonify({"success": False, "models": [], "error": "Unknown provider"})

    if config.requires_key and not api_key:
        return jsonify({"success": False, "models": [], "error": "API Key required"})

    final_url = base_url or config.base_url

    try:
        client = create_client(provider=provider, api_key=api_key, base_url=final_url)
        models = client.get_models()

        chat_models = [m for m in models if not any(
            p in m.lower() for p in ["embed", "embedding", "bge", "e5", "gte", "tts", "whisper", "dall-e"]
        )]

        if chat_models:
            return jsonify({
                "success": True,
                "models": sorted(chat_models),
                "default_model": config.default_model if config.default_model in chat_models else (chat_models[0] if chat_models else ""),
            })

        # /models endpoint returned empty — validate key via minimal chat request
        # and return preset model list as fallback
        if api_key and config.default_model:
            try:
                test_resp = client.chat_complete(
                    model=config.default_model,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=1,
                )
                if test_resp and not test_resp.startswith("[Error"):
                    preset_chat = config.default_chat_models
                    if config.default_model not in preset_chat:
                        preset_chat = [config.default_model] + preset_chat
                    return jsonify({
                        "success": True,
                        "models": sorted(preset_chat),
                        "default_model": config.default_model,
                    })
            except Exception:
                pass

        return jsonify({
            "success": False,
            "models": [],
            "default_model": config.default_model or "",
            "error": "API Key 无效或无法获取模型列表，请检查后重试",
        })
    except Exception as e:
        logger.warning("[ProviderModels] Error: %s", e)
        return jsonify({
            "success": False,
            "models": [],
            "default_model": config.default_model if config else "",
            "error": str(e),
        })


@app.route("/api/test-api", methods=["POST"])
def test_api():
    """Test API connection and return models. Works with Ollama or OpenAI-compatible APIs."""
    data = request.json
    base_url = data.get("base_url", "").strip()
    api_key = data.get("api_key", "").strip()
    test_model = data.get("model", "").strip()

    logger.info("\n[API Test] ========== Starting ==========")
    logger.info("[API Test] URL: %s", base_url)
    print(
        f"[API Test] API Key: {'***' + api_key[-8:] if len(api_key) > 8 else '(not provided)'}",
        file=sys.stderr,
    )
    logger.info("[API Test] Model: %s", test_model or "(not specified)")

    if not base_url:
        logger.error("[API Test] API URL is required")
        return jsonify({"success": False, "message": "API URL is required"})

    base_url = base_url.rstrip("/")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    models = []

    # If model name provided, test it directly with a simple chat request
    if test_model:
        print(
            f"[API Test] Testing model '{test_model}' with chat request...",
            file=sys.stderr,
        )
        try:
            test_url = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
            logger.info("[API Test] POST %s/chat/completions", test_url)

            r = requests.post(
                f"{test_url}/chat/completions",
                headers=headers,
                json={
                    "model": test_model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5,
                },
                timeout=30,
            )
            logger.info("[API Test] Response: HTTP %s", r.status_code)

            if r.status_code == 200:
                resp_data = r.json()
                if "choices" in resp_data:
                    content = (
                        resp_data["choices"][0].get("message", {}).get("content", "")
                    )
                    print(
                        f"[API Test] SUCCESS! Model responded: '{content[:30]}...'",
                        file=sys.stderr,
                    )
                else:
                    logger.info("[API Test] SUCCESS! Response received")
                return jsonify(
                    {"success": True, "message": f"Model '{test_model}' works!"}
                )
            else:
                try:
                    err_data = r.json()
                    err_msg = err_data.get("error", {}).get(
                        "message", f"HTTP {r.status_code}"
                    )
                    logger.error("[API Test] FAILED: %s", err_msg)
                    return jsonify({"success": False, "message": err_msg})
                except (json.JSONDecodeError, KeyError, ValueError):
                    print(
                        f"[API Test] FAILED: HTTP {r.status_code} - {r.text[:100]}",
                        file=sys.stderr,
                    )
                    return jsonify(
                        {"success": False, "message": f"HTTP {r.status_code}"}
                    )
        except requests.exceptions.Timeout:
            logger.error("[API Test] FAILED: Connection timeout")
            return jsonify({"success": False, "message": "Connection timeout"})
        except requests.exceptions.ConnectionError as e:
            logger.error("[API Test] FAILED: Cannot connect - %s", str(e)[:50])
            return jsonify({"success": False, "message": "Cannot connect to API"})
        except Exception as e:
            logger.error("[API Test] FAILED: %s", str(e))
            return jsonify({"success": False, "message": str(e)})

    # No model provided, try to list models
    logger.info("[API Test] No model specified, trying to list models...")

    # Try OpenAI-compatible API first (/v1/models)
    try:
        test_url = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
        logger.info("[API Test] GET %s/models", test_url)

        r = requests.get(f"{test_url}/models", headers=headers, timeout=15)
        print(f"[API Test] Response: HTTP {r.status_code}", file=sys.stderr)

        if r.status_code == 200:
            for m in r.json().get("data", []):
                model_id = m.get("id", "")
                if model_id:
                    models.append(model_id)
            if models:
                print(
                    f"[API Test] SUCCESS! Found {len(models)} models via /v1/models",
                    file=sys.stderr,
                )
                return jsonify(
                    {
                        "success": True,
                        "message": f"Found {len(models)} models",
                        "models": sorted(models),
                    }
                )
    except Exception as e:
        print(f"[API Test] /v1/models failed: {str(e)[:50]}", file=sys.stderr)

    # Try Ollama native API (/api/tags) - no auth needed
    try:
        ollama_url = base_url.replace("/v1", "")
        print(f"[API Test] GET {ollama_url}/api/tags (Ollama native)", file=sys.stderr)

        r = requests.get(f"{ollama_url}/api/tags", timeout=10)
        print(f"[API Test] Response: HTTP {r.status_code}", file=sys.stderr)

        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            if models:
                print(
                    f"[API Test] SUCCESS! Found {len(models)} Ollama models",
                    file=sys.stderr,
                )
                return jsonify(
                    {
                        "success": True,
                        "message": f"Ollama - {len(models)} models",
                        "models": models,
                    }
                )
    except Exception as e:
        print(f"[API Test] Ollama /api/tags failed: {str(e)[:50]}", file=sys.stderr)

    # Return error with helpful message
    print(f"[API Test] ========== Failed ==========", file=sys.stderr)
    return jsonify(
        {
            "success": False,
            "message": "Cannot list models. Please enter model name manually (e.g., qwen-max, deepseek-chat)",
        }
    )


@app.route("/api/providers")
def get_providers():
    """Get list of available LLM providers for deep research."""
    from gangdan.core.llm_client import OpenAIClient

    providers = OpenAIClient.list_providers()
    return jsonify(
        {
            "providers": providers,
            "current": CONFIG.research_provider,
        }
    )


@app.route("/api/test-provider", methods=["POST"])
def test_provider():
    """Test connection to a provider's API for deep research."""
    data = request.json
    provider = data.get("provider", CONFIG.research_provider)
    api_key = data.get("api_key", CONFIG.research_api_key)
    base_url = data.get("base_url", CONFIG.research_api_base_url)

    if provider == "ollama":
        url = base_url or CONFIG.ollama_url
        try:
            r = requests.get(f"{url.rstrip('/')}/api/tags", timeout=10)
            if r.status_code == 200:
                return jsonify(
                    {"success": True, "message": "Ollama connection successful"}
                )
            return jsonify({"success": False, "message": f"HTTP {r.status_code}"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    if not api_key:
        return jsonify({"success": False, "message": "API key required"})

    from gangdan.core.llm_client import OpenAIClient

    client = OpenAIClient(api_key=api_key, base_url=base_url, provider=provider)

    try:
        models = client.get_models()
        if models:
            is_default = (
                provider in ["dashscope", "zhipu", "siliconflow"] and len(models) <= 15
            )
            return jsonify(
                {
                    "success": True,
                    "message": f"Connected successfully. {'Using default model list.' if is_default else f'Found {len(models)} models.'}",
                    "models": models[:10],
                }
            )
        return jsonify(
            {
                "success": True,
                "message": "Connected. Please enter model name manually.",
                "models": [],
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    use_kb = data.get("use_kb", True)
    use_web = data.get("use_web", False)
    use_images = data.get("use_images", False)
    output_word_limit = data.get("output_word_limit", 0)
    kb_scope = data.get("kb_scope", None)
    doc_scope = data.get("doc_scope", None)
    req_output_language = data.get("output_language", None)

    # Debug logging
    print(f"[Chat] use_kb={use_kb}, kb_scope={kb_scope}", file=sys.stderr)
    print(f"[Chat] doc_scope={doc_scope}", file=sys.stderr)
    print(f"[Chat] CONFIG.embedding_model={CONFIG.embedding_model}", file=sys.stderr)

    if not CONFIG.chat_model:

        def error_stream():
            error_data = {"content": "Error: No chat model selected", "done": True}
            yield f"data: {json.dumps(error_data)}\n\n"

        return Response(error_stream(), mimetype="text/event-stream")

    kb_query_patterns = [
        r"知识库.*情况",
        r"知识库.*统计",
        r"知识库.*概览",
        r"知识库.*信息",
        r"有多少.*文献",
        r"文献.*数量",
        r"文献.*多少",
        r"有多少.*文档",
        r"文档.*数量",
        r"文档.*多少",
        r"库.*情况",
        r"库.*统计",
        r"kb.*status",
        r"knowledge.*base.*status",
        r"how many.*documents",
        r"document.*count",
        r"文献分布",
        r"年份分布",
        r"年代分布",
        r"知识库.*介绍",
        r"介绍.*知识库",
        r"知识库.*概述",
    ]

    is_kb_query = False
    for pattern in kb_query_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            is_kb_query = True
            break

    if is_kb_query:

        def kb_info_stream():
            kb_summary = get_kb_summary_text()
            yield f"data: {json.dumps({'content': kb_summary, 'done': True}, ensure_ascii=False)}\n\n"

        return Response(kb_info_stream(), mimetype="text/event-stream")

    def generate():
        context = ""
        image_context = []  # Store image references for response

        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"[Chat] New message received", file=sys.stderr)
        print(
            f"[Chat] Query: {message[:100]}{'...' if len(message) > 100 else ''}",
            file=sys.stderr,
        )
        print(
            f"[Chat] Options: KB={use_kb}, Web={use_web}, Images={use_images}",
            file=sys.stderr,
        )
        print(f"{'=' * 60}", file=sys.stderr)

        # Web search
        if use_web:
            print(f"\n[WebSearch] Searching for: {message[:50]}...", file=sys.stderr)
            try:
                results = WEB_SEARCHER.search(message)
                print(f"[WebSearch] Found {len(results)} results", file=sys.stderr)

                if results:
                    context += "\n--- Web Results ---\n"
                    for i, r in enumerate(results[:3]):
                        context += f"[{r['title']}] {r['snippet']}\n"
                        print(
                            f"[WebSearch]   {i + 1}. {r['title'][:50]}...",
                            file=sys.stderr,
                        )
                        print(
                            f"[WebSearch]      URL: {r['url'][:60]}...", file=sys.stderr
                        )

                    print(
                        f"[WebSearch] Using top {min(3, len(results))} results in context",
                        file=sys.stderr,
                    )
                else:
                    print(f"[WebSearch] No results found", file=sys.stderr)
            except Exception as e:
                print(f"[WebSearch] Error: {type(e).__name__}: {e}", file=sys.stderr)

        # RAG retrieval with cross-lingual search
        kb_references = []  # Track sources for citations
        if use_kb and CONFIG.embedding_model:
            print(
                f"\n[RAG] Searching knowledge base (cross-lingual)...", file=sys.stderr
            )
            print(f"[RAG] Embedding model: {CONFIG.embedding_model}", file=sys.stderr)
            print(f"[RAG] doc_scope received: {doc_scope}", file=sys.stderr)

            try:
                # 1. Detect query language
                query_lang = detect_language(message)
                print(f"[RAG] Query language: {query_lang}", file=sys.stderr)

                collections = CHROMA.list_collections()
                if kb_scope:
                    collections = [c for c in collections if c in kb_scope]
                print(
                    f"[RAG] Querying collections: {', '.join(collections) if collections else 'None'}",
                    file=sys.stderr,
                )

                # If doc_scope is provided, fetch those documents directly (Strict Mode)
                if doc_scope and len(doc_scope) > 0:
                    print(f"[RAG] Strict mode: Fetching documents by doc_id from {len(doc_scope)} selected IDs", file=sys.stderr)
                    direct_docs = []
                    doc_scope_set = set(doc_scope)
                    
                    for coll_name in collections:
                        try:
                            # Fetch all documents from this collection (limit high enough to cover all)
                            docs_data = CHROMA.get_documents(coll_name, limit=10000, include=["documents", "metadatas", "ids"])
                            if docs_data and docs_data.get("documents"):
                                count = len(docs_data["documents"])
                                for i in range(count):
                                    meta = docs_data["metadatas"][i] if docs_data.get("metadatas") else {}
                                    doc_id = meta.get("doc_id", "")
                                    
                                    # Match by doc_id in metadata
                                    if doc_id in doc_scope_set:
                                        doc_text = docs_data["documents"][i]
                                        direct_docs.append({
                                            "coll": coll_name,
                                            "doc": doc_text,
                                            "id": doc_id,
                                            "dist": 0.0,
                                            "query_lang": query_lang,
                                            "file": meta.get("file", "unknown"),
                                            "source": meta.get("source", coll_name),
                                            "title": meta.get("title", "Unknown Title"),
                                            "metadata": meta,
                                        })
                        except Exception as e:
                            print(f"[RAG] Error fetching docs for {coll_name}: {e}", file=sys.stderr)
                    
                    if direct_docs:
                        print(f"[RAG] Strict mode: Found {len(direct_docs)} matching documents", file=sys.stderr)
                        merged = direct_docs
                        total_hits = len(merged)
                    else:
                        print(f"[RAG] Strict mode: No documents found for selected IDs", file=sys.stderr)
                        merged = []
                        total_hits = 0
                else:
                    # Normal vector search flow
                    # 2. Get languages present in selected KBs by sampling metadata
                    target_langs = set()
                    for coll_name in collections:
                        try:
                            sample = CHROMA.get_documents(
                                coll_name, limit=20, include=["metadatas"]
                            )
                            for meta in sample.get("metadatas", []):
                                if meta and meta.get("language"):
                                    target_langs.add(meta["language"])
                        except Exception:
                            pass

                    # Remove "unknown" from target languages for translation
                    target_langs.discard("unknown")
                    print(
                        f"[RAG] Target languages in KBs: {target_langs if target_langs else 'none detected'}",
                        file=sys.stderr,
                    )

                    # 3. Create query variants (original + translations)
                    query_variants = {query_lang: message}
                    for target_lang in target_langs:
                        if target_lang != query_lang:
                            try:
                                translate_client = get_chat_client()
                                lang_names = {"zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean", "ru": "Russian", "fr": "French", "de": "German", "es": "Spanish", "pt": "Portuguese", "it": "Italian"}
                                from_name = lang_names.get(query_lang, query_lang)
                                to_name = lang_names.get(target_lang, target_lang)
                                translate_model = CONFIG.translate_model or CONFIG.chat_model_name or CONFIG.chat_model
                                translate_prompt = f"Translate the following text from {from_name} to {to_name}. Output ONLY the translation, nothing else:\n\n{message[:500]}"
                                translated = translate_client.chat_complete(
                                    model=translate_model,
                                    messages=[{"role": "user", "content": translate_prompt}],
                                )
                                if translated and translated.strip() and translated.strip() != message:
                                    query_variants[target_lang] = translated.strip()
                                    print(
                                        f"[RAG] Translated to {target_lang}: {translated.strip()[:50]}{'...' if len(translated.strip()) > 50 else ''}",
                                        file=sys.stderr,
                                    )
                            except Exception as e:
                                print(f"[RAG] Translation to {target_lang} failed: {e}", file=sys.stderr)

                    print(
                        f"[RAG] Query variants: {list(query_variants.keys())}",
                        file=sys.stderr,
                    )

                    # 4. Embed all variants and search (with adaptive dimension)
                    all_results = []

                    # Pre-compute collection info once per collection (not per variant)
                    from gangdan.core.adaptive_search import (
                        adaptive_embed,
                        build_collection_info_cache,
                        get_current_model_dimension,
                    )

                    coll_info_cache = build_collection_info_cache(CHROMA, collections)
                    current_dim = get_current_model_dimension(OLLAMA, CONFIG.embedding_model)
                    print(
                        f"[RAG] Current embedding model '{CONFIG.embedding_model}' dimension: {current_dim or 'unknown'}",
                        file=sys.stderr,
                    )
                    if coll_info_cache:
                        coll_desc = ", ".join(
                            f"{name}={info.get('dimension',0)}d/{info.get('embedding_model','?')}"
                            for name, info in coll_info_cache.items()
                        )
                        print(f"[RAG] Collection info: {coll_desc}", file=sys.stderr)

                    for lang, query_text in query_variants.items():
                        try:
                            query_emb = OLLAMA.embed(query_text, CONFIG.embedding_model)
                            for coll_name in collections:
                                coll_info = coll_info_cache.get(coll_name, {})
                                ar = adaptive_embed(
                                    query_text=query_text,
                                    collection_name=coll_name,
                                    current_embedding=query_emb,
                                    current_dim=current_dim,
                                    current_model=CONFIG.embedding_model,
                                    coll_info=coll_info,
                                    ollama=OLLAMA,
                                )
                                if ar.skip or ar.embedding is None:
                                    continue

                                results = CHROMA.search(coll_name, ar.embedding, top_k=10)
                                for r in results:
                                    if (
                                        r.get("distance", 1) < CONFIG.rag_distance_threshold
                                    ):
                                        meta = r.get("metadata", {})
                                        all_results.append(
                                            {
                                                "coll": coll_name,
                                                "doc": r["document"],
                                                "dist": r["distance"],
                                                "id": r.get(
                                                    "id",
                                                    hashlib.md5(
                                                        r["document"][:100].encode()
                                                    ).hexdigest(),
                                                ),
                                                "query_lang": lang,
                                                "file": meta.get("file", "unknown"),
                                                "source": meta.get("source", coll_name),
                                                "_adapted": ar.adapted,
                                                "_adapt_reason": ar.reason,
                                            }
                                        )
                        except Exception as e:
                            print(f"[RAG] Search error for {lang}: {e}", file=sys.stderr)

                    # 5. Deduplicate by document ID, keep best score
                    seen = {}
                    for r in all_results:
                        if r["id"] not in seen or r["dist"] < seen[r["id"]]["dist"]:
                            seen[r["id"]] = r

                    # 6. Sort by distance and build context with citations
                    merged = sorted(seen.values(), key=lambda x: x["dist"])
                    
                    # Filter by doc_scope if provided (for normal search mode)
                    if doc_scope:
                        doc_scope_set = set(doc_scope)
                        before_count = len(merged)
                        filtered = []
                        for r in merged:
                            # Check both ChromaDB ID and metadata doc_id
                            rid = r.get("id", "")
                            meta_doc_id = r.get("metadata", {}).get("doc_id", "") if r.get("metadata") else ""
                            if rid in doc_scope_set or meta_doc_id in doc_scope_set:
                                filtered.append(r)
                        merged = filtered
                        print(f"[RAG] Filtered from {before_count} to {len(merged)} results by doc_scope", file=sys.stderr)
                    
                    total_hits = len(merged)

                # Track unique sources for references
                sources_used = set()
                for r in merged[: CONFIG.top_k]:
                    source_file = r.get("file", "unknown")
                    sources_used.add(source_file)
                    # Add content with source attribution
                    context += f"\n[Source: {source_file}]\n{r['doc'][:500]}\n"

                # Build references list
                kb_references = sorted(list(sources_used))

                if total_hits == 0:
                    print(
                        f"[RAG] No relevant documents found (threshold: distance < 0.5)",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"[RAG] Total: {total_hits} relevant documents after dedup (using top {min(total_hits, CONFIG.top_k)})",
                        file=sys.stderr,
                    )
                    print(f"[RAG] Sources: {', '.join(kb_references)}", file=sys.stderr)

            except Exception as e:
                print(f"[RAG] Error: {type(e).__name__}: {e}", file=sys.stderr)
        elif use_kb and not CONFIG.embedding_model:
            print(f"[RAG] Skipped - no embedding model configured", file=sys.stderr)

        # Image-aware RAG search
        if use_images and use_kb:
            print(f"\n[ImageRAG] Searching for relevant images...", file=sys.stderr)
            try:
                # Extract keywords from query
                keywords = message.lower().split()[:10]  # Top 10 words

                for coll_name in collections:
                    kb_dir = DOCS_DIR / coll_name
                    if kb_dir.exists():
                        from gangdan.core.image_handler import ImageHandler

                        handler = ImageHandler(kb_dir)

                        # Search images by keyword in alt text and source
                        images = handler.list_images()
                        for img in images:
                            alt_text = img.get("alt_text", "").lower()
                            source = img.get("source_file", "").lower()
                            name = img.get("name", "").lower()

                            # Check if any keyword matches
                            score = 0
                            for kw in keywords:
                                if kw in alt_text:
                                    score += 2
                                if kw in source:
                                    score += 1
                                if kw in name:
                                    score += 1

                            if score > 0:
                                image_context.append(
                                    {
                                        "kb": coll_name,
                                        "path": img.get("path"),
                                        "alt_text": img.get("alt_text", ""),
                                        "source_file": img.get(
                                            "source_file", "unknown"
                                        ),
                                        "name": img.get("name"),
                                        "relevance_score": score,
                                    }
                                )

                # Sort by relevance and take top images
                image_context.sort(key=lambda x: x["relevance_score"], reverse=True)
                image_context = image_context[:5]  # Top 5 images

                if image_context:
                    print(
                        f"[ImageRAG] Found {len(image_context)} relevant images",
                        file=sys.stderr,
                    )
                    for img in image_context:
                        print(
                            f"[ImageRAG]   {img['alt_text'][:50]}... (from {img['source_file']})",
                            file=sys.stderr,
                        )
                else:
                    print(f"[ImageRAG] No relevant images found", file=sys.stderr)
            except Exception as e:
                print(f"[ImageRAG] Error: {e}", file=sys.stderr)

        print(f"\n[Chat] Context length: {len(context)} chars", file=sys.stderr)
        print(f"[Chat] Images found: {len(image_context)}", file=sys.stderr)
        print(f"{'=' * 60}\n", file=sys.stderr)

        # Strict KB mode: refuse to answer if KB enabled but no results found
        if use_kb and CONFIG.strict_kb_mode and not kb_references and not use_web:
            error_msg = t("kb_no_results_strict")
            error_data = {"content": error_msg, "done": True}
            yield f"data: {json.dumps(error_data)}\n\n"
            return

        # Build messages
        messages = CONVERSATION.get_messages(10)

        # Determine output language: request param > CONFIG > auto
        # "auto" means follow the input language, no hard constraint
        effective_lang = req_output_language if req_output_language and req_output_language != "auto" else None
        if not effective_lang and CONFIG.output_language and CONFIG.output_language != "auto":
            effective_lang = CONFIG.output_language
        LANG_NAMES = {
            "zh": "Chinese (中文)", "en": "English", "ja": "Japanese (日本語)",
            "fr": "French (Français)", "ru": "Russian (Русский)", "de": "German (Deutsch)",
            "es": "Spanish (Español)", "pt": "Portuguese (Português)", "ko": "Korean (한국어)",
        }

        system_prompt = "You are a helpful programming assistant."
        if effective_lang and effective_lang != "auto":
            lang_name = LANG_NAMES.get(effective_lang, effective_lang)
            system_prompt += f"\n\nIMPORTANT: You MUST respond in {lang_name}. This is a strict requirement — do not use any other language regardless of the input language."

        if context:
            system_prompt += f"\n\nContext:\n{context}"
            if kb_references:
                system_prompt += "\n\nIMPORTANT: When answering, cite the source files in your response where appropriate."

        # Add image context to system prompt
        if image_context:
            image_section = "\n\nRelevant images found:\n"
            for img in image_context:
                image_section += f"- Image: {img['alt_text']} (from {img['source_file']}, path: {img['path']})\n"
            system_prompt += image_section
            system_prompt += "\nWhen appropriate, mention that relevant images are available and reference their source files."

        chat_messages = [{"role": "system", "content": system_prompt}]
        chat_messages.extend(messages)
        chat_messages.append({"role": "user", "content": message})

        # Stream response
        full_response = ""
        try:
            chat_client = get_chat_client()
            model_name = CONFIG.chat_model_name or CONFIG.chat_model
            
            # Ollama uses num_ctx, OpenAI-compatible uses max_tokens
            if CONFIG.chat_provider == "ollama":
                stream_kwargs = {
                    "temperature": CONFIG.chat_temperature,
                }
            else:
                stream_kwargs = {
                    "temperature": CONFIG.chat_temperature,
                    "max_tokens": CONFIG.chat_max_tokens,
                }
            
            for chunk in chat_client.chat_stream(
                chat_messages,
                model_name,
                **stream_kwargs,
            ):
                if chat_client.is_stopped():
                    stop_data = {"content": "\n\n[Stopped]", "stopped": True}
                    yield f"data: {json.dumps(stop_data)}\n\n"
                    break
                full_response += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"

            # Append references if we have KB sources
            if kb_references and full_response:
                ref_header = t("references")
                ref_text = f"\n\n---\n**{ref_header}:**\n"
                for ref in kb_references:
                    ref_text += f"- {ref}\n"
                ref_data = {"content": ref_text}
                yield f"data: {json.dumps(ref_data)}\n\n"
                full_response += ref_text

            # Append image references if images were found
            if image_context and full_response:
                img_header = "📷 **Related Images:**"
                img_text = f"\n\n---\n{img_header}\n"
                for img in image_context:
                    img_text += f"- ![{img['alt_text']}]({img['path']}) - {img['source_file']}\n"
                img_data = {"content": img_text, "images": image_context}
                yield f"data: {json.dumps(img_data)}\n\n"
                full_response += img_text

            yield f"data: {json.dumps({'done': True})}\n\n"

            # Save to conversation
            CONVERSATION.add("user", message)
            CONVERSATION.add("assistant", full_response)
        except Exception as e:
            error_data = {"content": f"\n\nError: {e}", "done": True}
            yield f"data: {json.dumps(error_data)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/stop", methods=["POST"])
def stop_generation():
    OLLAMA.stop_generation()
    return jsonify({"success": True})


@app.route("/api/clear", methods=["POST"])
def clear_chat():
    CONVERSATION.clear()
    return jsonify({"success": True})


@app.route("/api/export")
def export_chat():
    messages = CONVERSATION.get_all()

    lines = [
        f"# {t('app_title')} - Chat Export",
        f"*Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "---",
        "",
    ]

    for i, msg in enumerate(messages):
        role = "🧑 User" if msg["role"] == "user" else "🤖 Assistant"
        lines.append(f"### {role}")
        lines.append("")
        lines.append(msg["content"])
        lines.append("")
        lines.append("---")
        lines.append("")

    import json as _json

    conversation_data = {
        "version": "1.0",
        "app": "GangDan",
        "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "messages": messages,
    }
    lines.append("")
    lines.append("<!-- GANGDAN_CONVERSATION_DATA")
    lines.append(_json.dumps(conversation_data, ensure_ascii=False))
    lines.append("END_GANGDAN_CONVERSATION_DATA -->")

    content = "\n".join(lines)
    filename = f"chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    return jsonify({"content": content, "filename": filename})


@app.route("/api/save-conversation")
def save_conversation():
    messages = CONVERSATION.get_all()
    content = {
        "version": "1.0",
        "app": "GangDan",
        "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "messages": messages,
    }
    filename = f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return jsonify({"success": True, "content": content, "filename": filename})


@app.route("/api/load-conversation", methods=["POST"])
def load_conversation():
    data = request.json
    conversation = data.get("conversation", {})
    messages = conversation.get("messages", [])

    if not isinstance(messages, list):
        return jsonify({"success": False, "error": t("invalid_conversation_file")}), 400

    for msg in messages:
        if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
            return jsonify(
                {"success": False, "error": t("invalid_conversation_file")}
            ), 400

    CONVERSATION.clear()
    for msg in messages:
        CONVERSATION.add(msg["role"], msg["content"])

    return jsonify({"success": True, "message_count": len(messages)})


@app.route("/api/docs/list")
def list_docs():
    return jsonify(DOC_MANAGER.list_downloaded())


@app.route("/api/docs/download", methods=["POST"])
def download_docs():
    data = request.json
    source = data.get("source")

    downloaded, errors = DOC_MANAGER.download_source(source)
    return jsonify({"downloaded": downloaded, "errors": errors})


@app.route("/api/docs/index", methods=["POST"])
def index_docs():
    data = request.json
    source = data.get("source")
    image_mode = data.get("image_mode", "copy")

    files, chunks, images = DOC_MANAGER.index_source(source, image_mode=image_mode)
    return jsonify({"files": files, "chunks": chunks, "images_processed": images})


@app.route("/api/docs/batch-download", methods=["POST"])
def batch_download_docs():
    """Batch download multiple documentation sources."""
    data = request.json
    sources = data.get("sources", [])

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(
        f"[BatchDownload] Starting batch download for {len(sources)} sources",
        file=sys.stderr,
    )
    print(f"[BatchDownload] Sources: {', '.join(sources)}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    results = []
    total_downloaded = 0
    total_errors = 0

    for source in sources:
        print(f"[BatchDownload] Downloading: {source}...", file=sys.stderr)
        downloaded, errors = DOC_MANAGER.download_source(source)
        total_downloaded += downloaded
        total_errors += len(errors)

        results.append(
            {
                "source": source,
                "downloaded": downloaded,
                "errors": len(errors),
                "error_details": errors,
            }
        )

        if errors:
            for err in errors:
                print(f"[BatchDownload]   Error in {source}: {err}", file=sys.stderr)
        print(
            f"[BatchDownload]   {source}: {downloaded} files downloaded, {len(errors)} errors",
            file=sys.stderr,
        )

    print(
        f"\n[BatchDownload] Summary: {total_downloaded} total files, {total_errors} total errors",
        file=sys.stderr,
    )
    print(f"{'=' * 60}\n", file=sys.stderr)

    return jsonify(
        {
            "results": results,
            "total_downloaded": total_downloaded,
            "total_errors": total_errors,
        }
    )


@app.route("/api/docs/batch-index", methods=["POST"])
def batch_index_docs():
    """Batch index multiple documentation sources."""
    data = request.json
    sources = data.get("sources", [])

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(
        f"[BatchIndex] Starting batch indexing for {len(sources)} sources",
        file=sys.stderr,
    )
    print(
        f"[BatchIndex] Embedding model: {CONFIG.embedding_model or 'NOT SET'}",
        file=sys.stderr,
    )
    print(f"{'=' * 60}", file=sys.stderr)

    if not CONFIG.embedding_model:
        print(f"[BatchIndex] ERROR: No embedding model selected!", file=sys.stderr)
        return jsonify({"error": "No embedding model selected", "results": []})

    results = []
    total_files = 0
    total_chunks = 0
    total_images = 0

    for source in sources:
        print(f"[BatchIndex] Indexing: {source}...", file=sys.stderr)
        files, chunks, images = DOC_MANAGER.index_source(source)
        total_files += files
        total_chunks += chunks
        total_images += images

        results.append(
            {"source": source, "files": files, "chunks": chunks, "images": images}
        )
        print(
            f"[BatchIndex]   {source}: {files} files -> {chunks} chunks indexed, {images} images",
            file=sys.stderr,
        )

    print(
        f"\n[BatchIndex] Summary: {total_files} files, {total_chunks} chunks, {total_images} images",
        file=sys.stderr,
    )
    print(f"{'=' * 60}\n", file=sys.stderr)

    return jsonify(
        {
            "results": results,
            "total_files": total_files,
            "total_chunks": total_chunks,
            "total_images": total_images,
        }
    )


@app.route("/api/docs/web-search-to-kb", methods=["POST"])
def web_search_to_kb():
    """Search the web and index results into knowledge base."""
    data = request.json
    query = data.get("query", "")
    from gangdan.core.config import sanitize_kb_name
    display_name = data.get("name", "Web Search")
    kb_name = sanitize_kb_name(display_name)

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[WebSearchToKB] Query: {query}", file=sys.stderr)
    print(f"[WebSearchToKB] Target KB: {kb_name}", file=sys.stderr)
    print(
        f"[WebSearchToKB] Embedding model: {CONFIG.embedding_model or 'NOT SET'}",
        file=sys.stderr,
    )
    print(f"{'=' * 60}", file=sys.stderr)

    if not CONFIG.embedding_model:
        print(f"[WebSearchToKB] ERROR: No embedding model selected!", file=sys.stderr)
        return jsonify(
            {"error": "No embedding model selected", "found": 0, "indexed": 0}
        )

    if not query:
        return jsonify({"error": "No query provided", "found": 0, "indexed": 0})

    # Search the web
    print(f"[WebSearchToKB] Searching web...", file=sys.stderr)
    try:
        results = WEB_SEARCHER.search(query, num_results=10)
        print(f"[WebSearchToKB] Found {len(results)} results", file=sys.stderr)
    except Exception as e:
        print(f"[WebSearchToKB] Search error: {e}", file=sys.stderr)
        return jsonify({"error": str(e), "found": 0, "indexed": 0})

    if not results:
        print(f"[WebSearchToKB] No results found", file=sys.stderr)
        return jsonify({"found": 0, "indexed": 0})

    # Log found results
    for i, r in enumerate(results):
        print(
            f"[WebSearchToKB]   {i + 1}. {r['title'][:50]}... ({r['url'][:50]}...)",
            file=sys.stderr,
        )

    # Index results into KB
    print(f"\n[WebSearchToKB] Indexing results into KB '{kb_name}'...", file=sys.stderr)

    documents = []
    embeddings = []
    metadatas = []
    ids = []

    for i, result in enumerate(results):
        # Create document from search result
        doc_text = f"Title: {result['title']}\nURL: {result['url']}\nContent: {result['snippet']}"

        try:
            emb = OLLAMA.embed(doc_text, CONFIG.embedding_model)
            doc_id = hashlib.md5(f"{kb_name}_{query}_{i}".encode()).hexdigest()

            documents.append(doc_text)
            embeddings.append(emb)
            metadatas.append(
                {
                    "source": "web_search",
                    "query": query,
                    "title": result["title"],
                    "url": result["url"],
                    "index": i,
                }
            )
            ids.append(doc_id)
            print(
                f"[WebSearchToKB]   Embedded result {i + 1}: {result['title'][:40]}...",
                file=sys.stderr,
            )
        except Exception as e:
            print(
                f"[WebSearchToKB]   Error embedding result {i + 1}: {e}",
                file=sys.stderr,
            )
            continue

    if documents:
        try:
            CHROMA.add_documents(kb_name, documents, embeddings, metadatas, ids)
            emb_dim = len(embeddings[0]) if embeddings else 0
            if emb_dim > 0:
                CHROMA.set_collection_embedding_model(kb_name, CONFIG.embedding_model, emb_dim)
            print(
                f"\n[WebSearchToKB] Successfully indexed {len(documents)} documents to '{kb_name}'",
                file=sys.stderr,
            )
            try:
                save_user_kb(kb_name, display_name, len(documents), languages=[])
                print(f"[WebSearchToKB] Registered KB '{kb_name}' in user_kbs", file=sys.stderr)
                kb_dir = DOCS_DIR / kb_name
                kb_dir.mkdir(parents=True, exist_ok=True)
                doc_manifest = {
                    "kb_name": kb_name,
                    "display_name": display_name,
                    "source": "web_search",
                    "document_count": len(documents),
                    "created_at": datetime.now().isoformat(),
                    "documents": {
                        doc_id: {"title": meta.get("title", ""), "url": meta.get("url", ""), "id": doc_id}
                        for doc_id, meta in zip(ids, metadatas)
                    },
                }
                (kb_dir / "documents.json").write_text(
                    json.dumps(doc_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                print(f"[WebSearchToKB] Created KB directory: {kb_dir}", file=sys.stderr)
            except Exception as e:
                print(f"[WebSearchToKB] Warning: Failed to register KB in manifest: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[WebSearchToKB] Error adding to ChromaDB: {e}", file=sys.stderr)
            return jsonify({"error": str(e), "found": len(results), "indexed": 0})

    print(f"{'=' * 60}\n", file=sys.stderr)

    return jsonify(
        {"found": len(results), "indexed": len(documents), "kb_name": kb_name}
    )


@app.route("/api/docs/upload", methods=["POST"])
def upload_docs():
    """Upload user documents to create a custom knowledge base.

    Supports:
    - Duplicate handling with 'duplicate_action' parameter
    - Folder upload via webkitdirectory
    - Image processing with 'image_mode' parameter
    - Output word limit for content generation
    """
    kb_name = request.form.get("kb_name", "").strip()
    if not kb_name:
        return jsonify(
            {"success": False, "error": "Knowledge base name is required"}
        ), 400

    files = request.files.getlist("files")
    if not files:
        return jsonify({"success": False, "error": "No files provided"}), 400

    duplicate_action = request.form.get("duplicate_action", "skip")
    image_mode = request.form.get("image_mode", "copy")
    output_word_limit = int(request.form.get("output_word_limit", 1000))
    upload_mode = request.form.get("upload_mode", "files")
    kb_languages = request.form.get("languages", "")  # Comma-separated language codes

    internal_name = sanitize_kb_name(kb_name)
    target_dir = DOCS_DIR / internal_name
    target_dir.mkdir(parents=True, exist_ok=True)

    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
    doc_extensions = {".md", ".txt"}
    allowed_extensions = doc_extensions | image_extensions

    saved_count = 0
    skipped_count = 0
    overwritten_count = 0
    image_count = 0
    md_count = 0
    errors = []

    # Track relative paths for folder uploads
    path_map = {}  # original relative path -> new path

    for f in files:
        if not f.filename:
            continue

        # Get the relative path for folder uploads
        filename = f.filename
        # Normalize path separators
        filename = filename.replace("\\", "/")

        ext = Path(filename).suffix.lower()
        if ext not in allowed_extensions:
            continue

        # For folder uploads, preserve directory structure for images
        if upload_mode == "folder" and "/" in filename:
            parts = filename.split("/")
            # Check if it's an image in a subdirectory
            if ext in image_extensions:
                # Store images in images/ subdirectory
                safe_name = parts[-1]
                images_dir = target_dir / "images"
                images_dir.mkdir(parents=True, exist_ok=True)
                target_path = images_dir / safe_name
                # Map original relative path to new path
                path_map[filename] = f"images/{safe_name}"
            else:
                # Documents go in root
                safe_name = parts[-1]
                target_path = target_dir / safe_name
                path_map[filename] = safe_name
        else:
            safe_name = Path(filename).name
            if ext in image_extensions:
                images_dir = target_dir / "images"
                images_dir.mkdir(parents=True, exist_ok=True)
                target_path = images_dir / safe_name
                image_count += 1
            else:
                target_path = target_dir / safe_name

        if target_path.exists():
            if duplicate_action == "skip":
                skipped_count += 1
                print(f"[Upload] Skipped duplicate: {safe_name}", file=sys.stderr)
                continue
            else:
                overwritten_count += 1
                print(f"[Upload] Overwriting: {safe_name}", file=sys.stderr)

        try:
            f.save(str(target_path))
            saved_count += 1
            if ext in doc_extensions:
                md_count += 1
        except Exception as e:
            errors.append(f"{safe_name}: {str(e)}")
            print(f"[Upload] Error saving {safe_name}: {e}", file=sys.stderr)

    total_files = saved_count + skipped_count
    if total_files == 0 and image_count == 0:
        return jsonify(
            {"success": False, "error": "No valid files uploaded", "details": errors}
        ), 400

    # Process markdown files to extract and save image references
    for md_file in target_dir.glob("*.md"):
        try:
            from gangdan.core.image_handler import ImageHandler

            content = md_file.read_text(encoding="utf-8")
            handler = ImageHandler(target_dir)
            result = handler.process_document(content, md_file, embed_mode="copy")

            if result.copied_count > 0:
                md_file.write_text(result.updated_content, encoding="utf-8")

            # Always save manifest if there are images
            if result.images:
                handler.save_image_manifest(md_file.name, result.images)
                print(
                    f"[Upload] {md_file.name}: saved manifest for {len(result.images)} images",
                    file=sys.stderr,
                )
        except Exception as e:
            print(
                f"[Upload] Error processing images in {md_file.name}: {e}",
                file=sys.stderr,
            )

    # Save output word limit to KB metadata
    kb_lang_list = (
        [l.strip() for l in kb_languages.split(",") if l.strip()]
        if kb_languages
        else []
    )
    save_user_kb(
        internal_name,
        kb_name,
        total_files,
        languages=kb_lang_list,
        output_word_limit=output_word_limit,
    )

    print(
        f"[Upload] Saved {saved_count} files (md:{md_count}, images:{image_count}, skipped:{skipped_count}, overwritten:{overwritten_count}) to '{internal_name}'",
        file=sys.stderr,
    )

    return jsonify(
        {
            "success": True,
            "name": internal_name,
            "display_name": kb_name,
            "file_count": total_files,
            "saved_count": saved_count,
            "skipped_count": skipped_count,
            "overwritten_count": overwritten_count,
            "image_count": image_count,
            "md_count": md_count,
            "errors": errors,
        }
    )


def _update_image_paths(content: str, path_map: dict) -> str:
    """Update image paths in markdown content based on path mapping."""
    import re

    # Pattern for markdown images: ![alt](path)
    pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

    def replace_path(match):
        alt_text = match.group(1)
        original_path = match.group(2)

        # Normalize the path
        normalized = original_path.replace("\\", "/")

        # Try to find a match in path_map
        for orig, new in path_map.items():
            if normalized.endswith(orig) or orig.endswith(normalized.split("/")[-1]):
                return f"![{alt_text}]({new})"

        # Return original if no match
        return match.group(0)

    return pattern.sub(replace_path, content)


@app.route("/api/docs/import-directory", methods=["POST"])
def import_directory():
    """Import a local server-side directory into a knowledge base with SSE progress.

    Body: {
        "kb_name": "arXiv",
        "directory": "/path/to/files",
        "image_mode": "copy",
        "output_word_limit": 1000,
        "languages": "en"
    }

    Returns SSE events with progress updates for large directories.
    """
    import shutil
    from gangdan.core.config import sanitize_kb_name, save_user_kb

    data = request.json or {}
    kb_name = data.get("kb_name", "").strip()
    directory = data.get("directory", "").strip()
    image_mode = data.get("image_mode", "copy")
    output_word_limit = int(data.get("output_word_limit", 1000))
    kb_languages = data.get("languages", "")

    if not kb_name:
        return jsonify({"success": False, "error": "Knowledge base name is required"}), 400
    if not directory:
        return jsonify({"success": False, "error": "Directory path is required"}), 400

    source_dir = Path(directory)
    if not source_dir.is_dir():
        return jsonify({"success": False, "error": f"Directory not found: {directory}"}), 400

    internal_name = sanitize_kb_name(kb_name)
    target_dir = DOCS_DIR / internal_name
    target_dir.mkdir(parents=True, exist_ok=True)

    doc_extensions = {".md", ".txt"}
    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
    allowed_extensions = doc_extensions | image_extensions

    # Collect all files first
    all_files = []
    for fp in sorted(source_dir.rglob("*")):
        if fp.is_file() and fp.suffix.lower() in allowed_extensions:
            all_files.append(fp)

    total = len(all_files)
    if total == 0:
        return jsonify({"success": False, "error": f"No .md/.txt files found in {directory}"}), 400

    # Save KB metadata early
    kb_lang_list = [l.strip() for l in kb_languages.split(",") if l.strip()] if kb_languages else []
    save_user_kb(internal_name, kb_name, total, languages=kb_lang_list, output_word_limit=output_word_limit)

    def generate():
        copied = 0
        skipped = 0
        md_count = 0
        image_count = 0
        errors = []
        indexed_count = 0

        yield f"data: {json.dumps({'type': 'status', 'phase': 'copy', 'total': total, 'message': f'Copying {total} files...'})}\n\n"

        # Phase 1: Copy files
        batch_size = 500
        for i, fp in enumerate(all_files):
            if hasattr(OLLAMA, 'is_stopped') and OLLAMA.is_stopped():
                yield f"data: {json.dumps({'type': 'error', 'message': 'Import stopped by user'})}\n\n"
                return

            try:
                rel = fp.relative_to(source_dir)
                target_path = target_dir / rel
                ext = fp.suffix.lower()

                if ext in image_extensions:
                    target_path = target_dir / "images" / rel.name
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    image_count += 1
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    md_count += 1

                if target_path.exists():
                    skipped += 1
                else:
                    shutil.copy2(str(fp), str(target_path))
                    copied += 1
            except Exception as e:
                errors.append(f"{fp.name}: {str(e)[:100]}")

            if (i + 1) % batch_size == 0 or i == total - 1:
                pct = round((i + 1) / total * 70)
                yield f"data: {json.dumps({'type': 'progress', 'phase': 'copy', 'percent': pct, 'current': i + 1, 'total': total, 'copied': copied, 'skipped': skipped})}\n\n"

        # Phase 2: Index to ChromaDB
        yield f"data: {json.dumps({'type': 'status', 'phase': 'index', 'message': f'Indexing {md_count} documents to ChromaDB...'})}\n\n"

        doc_files = sorted(target_dir.glob("*.md")) + sorted(target_dir.glob("*.txt"))
        total_docs = len(doc_files)

        chunk_size = getattr(CONFIG, 'chunk_size', 1000)
        chunk_overlap = getattr(CONFIG, 'chunk_overlap', 100)

        if total_docs > 0 and CONFIG.embedding_model:
            chunk_batch = []
            embed_batch = []
            meta_batch = []
            id_batch = []
            total_chunks = 0

            for doc_idx, doc_file in enumerate(doc_files):
                if hasattr(OLLAMA, 'is_stopped') and OLLAMA.is_stopped():
                    break
                try:
                    content = doc_file.read_text(encoding="utf-8", errors="replace")
                    if not content.strip():
                        continue

                    chunks = DOC_MANAGER._chunk_text(content, chunk_size, chunk_overlap)
                    if not chunks:
                        chunks = [content[:chunk_size]]

                    for chunk_idx, chunk in enumerate(chunks):
                        if len(chunk.strip()) < 50:
                            continue
                        doc_id = hashlib.md5(f"{doc_file.name}_{chunk_idx}".encode()).hexdigest()
                        meta = {
                            "file": doc_file.name,
                            "source": internal_name,
                            "chunk": chunk_idx,
                        }
                        chunk_batch.append(chunk[:2000])
                        meta_batch.append(meta)
                        id_batch.append(doc_id)

                    if len(chunk_batch) >= 100:
                        try:
                            for ci, chk in enumerate(chunk_batch):
                                emb = OLLAMA.embed(chk, CONFIG.embedding_model)
                                embed_batch.append(emb)
                            if embed_batch:
                                CHROMA.add_documents(internal_name, chunk_batch, embed_batch, meta_batch, id_batch)
                                total_chunks += len(chunk_batch)
                        except Exception as e:
                            print(f"[ImportDir] Embedding batch error: {e}", file=sys.stderr)
                            errors.append(f"Batch embed error: {str(e)[:100]}")

                        chunk_batch = []
                        embed_batch = []
                        meta_batch = []
                        id_batch = []

                    indexed_count += 1
                    if (doc_idx + 1) % 200 == 0 or doc_idx == total_docs - 1:
                        pct2 = 70 + round((doc_idx + 1) / total_docs * 28)
                        yield f"data: {json.dumps({'type': 'progress', 'phase': 'index', 'percent': pct2, 'current': doc_idx + 1, 'total': total_docs, 'chunks': total_chunks, 'indexed': indexed_count})}\n\n"

                except Exception as e:
                    errors.append(f"{doc_file.name}: {str(e)[:100]}")

            # Flush remaining batch
            if chunk_batch:
                try:
                    for ci, chk in enumerate(chunk_batch):
                        emb = OLLAMA.embed(chk, CONFIG.embedding_model)
                        embed_batch.append(emb)
                    if embed_batch:
                        CHROMA.add_documents(internal_name, chunk_batch, embed_batch, meta_batch, id_batch)
                        total_chunks += len(chunk_batch)
                except Exception as e:
                    print(f"[ImportDir] Final batch error: {e}", file=sys.stderr)

        # Update KB metadata with actual counts
        save_user_kb(internal_name, kb_name, copied + skipped, languages=kb_lang_list, output_word_limit=output_word_limit)

        # Store embedding model metadata for adaptive search
        if CONFIG.embedding_model and total_chunks > 0 and CHROMA and CHROMA.is_available:
            try:
                sample_emb = OLLAMA.embed("test", CONFIG.embedding_model)
                if sample_emb:
                    CHROMA.set_collection_embedding_model(internal_name, CONFIG.embedding_model, len(sample_emb))
            except Exception:
                pass

        yield f"data: {json.dumps({'type': 'done', 'success': True, 'name': internal_name, 'display_name': kb_name, 'total_files': total, 'copied': copied, 'skipped': skipped, 'md_count': md_count, 'image_count': image_count, 'indexed': indexed_count, 'errors': errors[:20]}, ensure_ascii=False)}\n\n"

        print(f"[ImportDir] Imported '{directory}' -> '{internal_name}': {copied} copied, {skipped} skipped, {indexed_count} indexed, {len(errors)} errors", file=sys.stderr)

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/docs/check-duplicates", methods=["POST"])
def check_duplicates():
    """Check for duplicate files before upload.

    Returns a list of filenames that already exist in the target KB.
    """
    kb_name = request.form.get("kb_name", "").strip()
    if not kb_name:
        return jsonify(
            {"success": False, "error": "Knowledge base name is required"}
        ), 400

    files = request.files.getlist("files")
    if not files:
        return jsonify({"success": False, "error": "No files provided"}), 400

    internal_name = sanitize_kb_name(kb_name)
    target_dir = DOCS_DIR / internal_name

    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
    doc_extensions = {".md", ".txt"}
    allowed_extensions = doc_extensions | image_extensions

    duplicates = []
    new_files = []
    image_files = []

    for f in files:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in allowed_extensions:
            continue

        safe_name = Path(f.filename).name
        target_path = target_dir / safe_name

        if ext in image_extensions:
            image_files.append(safe_name)

        if target_path.exists():
            duplicates.append(safe_name)
        else:
            new_files.append(safe_name)

    return jsonify(
        {
            "success": True,
            "kb_name": internal_name,
            "duplicates": duplicates,
            "new_files": new_files,
            "image_files": image_files,
            "has_duplicates": len(duplicates) > 0,
            "has_images": len(image_files) > 0,
        }
    )


@app.route("/api/kb/list")
def list_kbs():
    """List all available knowledge bases (built-in + user-created).

    Note: The kb_routes.py blueprint registers the primary handler at /api/kb/list.
    This route exists as a fallback if the blueprint is not registered.
    """
    from gangdan.kb_routes import list_kbs as _list_kbs
    return _list_kbs()


@app.route("/api/kb/reindex", methods=["POST"])
def reindex_kb():
    """Re-index an existing knowledge base to add language metadata.

    This is useful for KBs created before language detection was added,
    enabling cross-lingual search for existing documents.
    """
    data = request.json
    kb_name = data.get("name", "").strip()

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[Reindex] Starting reindex for: {kb_name}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    # Check if KB directory exists
    source_dir, resolved_name = _resolve_kb_dir(kb_name)
    if source_dir is None:
        return jsonify(
            {"success": False, "error": f"KB directory not found: {kb_name}"}
        ), 404
    kb_name = resolved_name

    # Delete existing collection if present
    if CHROMA and CHROMA.is_available:
        try:
            CHROMA.delete_collection(kb_name)
            print(f"[Reindex] Deleted existing collection: {kb_name}", file=sys.stderr)
        except Exception:
            print(f"[Reindex] No existing collection to delete", file=sys.stderr)

    # Re-index with language detection
    files, chunks, images = DOC_MANAGER.index_source(kb_name)

    # Update user KB manifest with detected languages if it's a user KB
    user_kbs = load_user_kbs()
    if kb_name in user_kbs:
        # Get detected languages from the new collection
        detected_langs = []
        if CHROMA and CHROMA.is_available:
            try:
                sample = CHROMA.get_documents(kb_name, limit=50, include=["metadatas"])
                langs = set()
                for meta in sample.get("metadatas", []):
                    if meta and meta.get("language"):
                        langs.add(meta["language"])
                langs.discard("unknown")
                detected_langs = sorted(list(langs))
            except Exception:
                pass

        # Update manifest
        save_user_kb(
            kb_name,
            user_kbs[kb_name].get("display_name", kb_name),
            user_kbs[kb_name].get("file_count", files),
            detected_langs,
        )
        print(
            f"[Reindex] Updated manifest with languages: {detected_langs}",
            file=sys.stderr,
        )

    print(
        f"[Reindex] Completed: {files} files, {chunks} chunks, {images} images",
        file=sys.stderr,
    )
    print(f"{'=' * 60}\n", file=sys.stderr)

    return jsonify(
        {
            "success": True,
            "name": kb_name,
            "files": files,
            "chunks": chunks,
            "images": images,
        }
    )


@app.route("/api/kb/annotate-dimensions", methods=["POST"])
def annotate_kb_dimensions():
    """Annotate all collections with their embedding dimension and model (without re-indexing).

    This is a lightweight operation that reads the stored embedding dimension from each
    collection and writes it as metadata, enabling adaptive search for legacy collections.
    If the current embedding model is configured, it is recorded as the model name.
    """
    if not CHROMA or not CHROMA.is_available:
        return jsonify({"success": False, "error": "ChromaDB not available"}), 503

    if not CONFIG.embedding_model:
        return jsonify({"success": False, "error": "No embedding model configured"}), 400

    results = []
    current_dim = 0
    current_model = CONFIG.embedding_model
    try:
        test_emb = OLLAMA.embed("test", CONFIG.embedding_model)
        if test_emb:
            current_dim = len(test_emb)
    except Exception:
        pass

    for coll_name in CHROMA.list_collections():
        existing = CHROMA.get_collection_info(coll_name) if hasattr(CHROMA, 'get_collection_info') else {}
        if existing.get("embedding_model") and existing.get("dimension"):
            results.append({"name": coll_name, "status": "already_annotated", "dimension": existing["dimension"], "model": existing["embedding_model"]})
            continue

        coll_dim = CHROMA.get_collection_dimension(coll_name)
        if coll_dim == 0:
            results.append({"name": coll_name, "status": "empty_or_unavailable", "dimension": 0, "model": ""})
            continue

        model_to_record = current_model
        status = "annotated_current"
        if current_dim > 0 and coll_dim != current_dim:
            status = "annotated_mismatch"
            print(
                f"[AnnotateDim] '{coll_name}': dimension {coll_dim}d != current model {current_dim}d ({current_model}). "
                f"Recording dimension but NOT model name (collection may have been built with a different model).",
                file=sys.stderr,
            )
            model_to_record = ""
        elif current_dim == 0:
            status = "annotated_dim_only"
            model_to_record = ""

        ok = CHROMA.set_collection_embedding_model(coll_name, model_to_record, coll_dim)
        results.append({"name": coll_name, "status": status if ok else "failed", "dimension": coll_dim, "model": model_to_record})

    annotated = sum(1 for r in results if "annotated" in r.get("status", ""))
    mismatches = sum(1 for r in results if "mismatch" in r.get("status", ""))
    print(
        f"[AnnotateDim] Annotated {annotated} collections, {mismatches} with dimension mismatch",
        file=sys.stderr,
    )

    return jsonify({"success": True, "results": results, "annotated": annotated, "mismatches": mismatches})


@app.route("/api/kb/delete", methods=["POST"])
def delete_kb():
    """Delete a knowledge base collection and optionally its source files.

    Request body:
    - name: KB name (required)
    - delete_files: Whether to also delete source files (default: False)
    """
    data = request.json
    kb_name = data.get("name", "").strip()
    delete_files = data.get("delete_files", False)

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[DeleteKB] Deleting KB: {kb_name}", file=sys.stderr)
    print(f"[DeleteKB] Delete files: {delete_files}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    deleted_collection = False
    deleted_files = 0

    if CHROMA and CHROMA.is_available:
        try:
            if CHROMA.collection_exists(kb_name):
                CHROMA.delete_collection(kb_name)
                deleted_collection = True
                print(f"[DeleteKB] Deleted collection: {kb_name}", file=sys.stderr)
        except Exception as e:
            print(f"[DeleteKB] Error deleting collection: {e}", file=sys.stderr)

    if delete_files:
        kb_dir_result = _resolve_kb_dir(kb_name)
        source_dir = kb_dir_result[0] if kb_dir_result[0] else DOCS_DIR / kb_name
        if source_dir.exists():
            try:
                import shutil

                shutil.rmtree(source_dir)
                deleted_files = 1
                print(
                    f"[DeleteKB] Deleted source directory: {source_dir}",
                    file=sys.stderr,
                )
            except Exception as e:
                print(
                    f"[DeleteKB] Error deleting source directory: {e}", file=sys.stderr
                )

    delete_user_kb(kb_name)

    print(
        f"[DeleteKB] Complete: collection={deleted_collection}, files={deleted_files}",
        file=sys.stderr,
    )
    print(f"{'=' * 60}\n", file=sys.stderr)

    return jsonify(
        {
            "success": True,
            "name": kb_name,
            "deleted_collection": deleted_collection,
            "deleted_files": deleted_files,
        }
    )


@app.route("/api/kb/images")
def list_kb_images():
    """List all images in a knowledge base.

    Query parameters:
    - name: KB name (required)
    """
    kb_name = request.args.get("name", "").strip()

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    from gangdan.core.image_handler import ImageHandler

    if not _find_kb_files_dir(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    handler = ImageHandler(kb_dir)
    images = handler.list_images()

    return jsonify(
        {"success": True, "name": kb_name, "images": images, "count": len(images)}
    )


@app.route("/api/kb/image/<kb_name>/<path:image_name>")
def get_kb_image(kb_name: str, image_name: str):
    """Get an image from a knowledge base.

    Parameters:
    - kb_name: Knowledge base name
    - image_name: Image filename (may include images/ prefix)
    """
    from gangdan.core.image_handler import ImageHandler

    if image_name.startswith("images/"):
        image_name = image_name[7:]

    if not _find_kb_files_dir(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    handler = ImageHandler(kb_dir)
    result = handler.get_image_data(image_name)

    if result is None:
        return jsonify({"success": False, "error": "Image not found"}), 404

    image_data, mime_type = result

    from flask import Response

    return Response(image_data, mimetype=mime_type)


@app.route("/api/kb/process-images", methods=["POST"])
def process_kb_images():
    """Process images in a knowledge base's documents.

    This endpoint re-processes all markdown files in a KB,
    copying images to the images/ directory and updating references.

    Request body:
    - name: KB name (required)
    - embed_mode: "copy", "base64", or "reference" (default: "copy")
    """
    data = request.json
    kb_name = data.get("name", "").strip()
    embed_mode = data.get("embed_mode", "copy")

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    if not _find_kb_files_dir(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    from gangdan.core.image_handler import ImageHandler, process_kb_images

    files = list(kb_dir.glob("*.md"))
    total_images = 0
    processed_files = 0
    errors = []

    for filepath in files:
        try:
            content = filepath.read_text(encoding="utf-8")
            result = process_kb_images(kb_dir, filepath, content, embed_mode)

            if result.copied_count > 0:
                filepath.write_text(result.updated_content, encoding="utf-8")
                total_images += result.copied_count

            processed_files += 1
            print(
                f"[ProcessImages] {filepath.name}: {result.copied_count} images",
                file=sys.stderr,
            )
        except Exception as e:
            errors.append(f"{filepath.name}: {str(e)}")
            print(
                f"[ProcessImages] Error processing {filepath.name}: {e}",
                file=sys.stderr,
            )

    return jsonify(
        {
            "success": True,
            "name": kb_name,
            "files_processed": processed_files,
            "total_images": total_images,
            "errors": errors,
        }
    )


@app.route("/api/kb/files")
def get_kb_files():
    """Get list of files in a knowledge base with document counts.

    Returns indexed files (from ChromaDB) plus any source files (PDF, HTML, TeX, etc.)
    found in the KB directory alongside the markdown files.
    """
    kb_name = request.args.get("name", "").strip()

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    if not CHROMA or not CHROMA.is_available:
        return jsonify(
            {"success": False, "error": "Vector database not available"}
        ), 500

    if not CHROMA.collection_exists(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    try:
        from gangdan.core.config import sanitize_kb_name, load_user_kbs

        files = CHROMA.get_collection_files(kb_name)

        internal_name = sanitize_kb_name(kb_name)
        kb_dir, resolved_name = _resolve_kb_dir(kb_name)
        if resolved_name != kb_name:
            internal_name = resolved_name

        SOURCE_EXTENSIONS = {".pdf", ".html", ".htm", ".tex", ".latex", ".epub", ".docx", ".doc", ".odt"}
        indexed_names = {f["file"] for f in files}

        if kb_dir is not None and kb_dir.exists():
            for ext in SOURCE_EXTENSIONS:
                for src_file in sorted(kb_dir.rglob(f"*{ext}")):
                    fname = src_file.name
                    if fname not in indexed_names:
                        files.append({
                            "file": fname,
                            "doc_count": 0,
                            "language": ext.lstrip("."),
                            "is_source": True,
                        })
                        indexed_names.add(fname)

        return jsonify(
            {
                "success": True,
                "name": kb_name,
                "files": files,
                "total_docs": sum(f["doc_count"] for f in files),
            }
        )
    except Exception as e:
        print(f"[GetKBFiles] Error: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/kb/images/search")
def search_kb_images():
    """Search images in a knowledge base with source attribution.

    Query parameters:
    - name: KB name (required) - can be internal_name or display_name
    - source_file: Filter by source file (optional)
    - query: Search query for alt text and metadata (optional)
    - limit: Max results (default: 50)
    """
    from gangdan.core.image_handler import ImageHandler

    kb_name = request.args.get("name", "").strip()
    source_file = request.args.get("source_file")
    query = request.args.get("query", "").lower()
    limit = int(request.args.get("limit", 50))

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    # Try to find the KB directory
    kb_dir, resolved_name = _resolve_kb_dir(kb_name)
    if resolved_name != kb_name:
        kb_name = resolved_name

    if kb_dir is None:
        available = (
            [d.name for d in DOCS_DIR.iterdir() if d.is_dir()]
            if DOCS_DIR.exists()
            else []
        )
        print(
            f"[ImageSearch] KB '{kb_name}' not found. Available: {available}",
            file=sys.stderr,
        )
        return jsonify(
            {
                "success": False,
                "error": f"KB '{kb_name}' not found",
                "available_kbs": available,
            }
        ), 404

    print(f"[ImageSearch] Searching images in KB: {kb_name}", file=sys.stderr)

    handler = ImageHandler(kb_dir)
    images = handler.list_images(source_file)

    # Filter by query if provided
    if query:
        filtered = []
        for img in images:
            alt_text = img.get("alt_text", "").lower()
            source = img.get("source_file", "").lower()
            name = img.get("name", "").lower()
            original = img.get("original_path", "").lower()
            # Search in all text fields
            if (
                query in alt_text
                or query in source
                or query in name
                or query in original
            ):
                filtered.append(img)
        images = filtered

    # Apply limit
    images = images[:limit]

    return jsonify(
        {
            "success": True,
            "kb_name": kb_name,
            "images": images,
            "count": len(images),
            "total_available": len(handler.list_images(source_file))
            if not query
            else len(images),
        }
    )


@app.route("/api/kb/gallery")
def get_kb_gallery():
    """Get complete image gallery for a knowledge base.

    Query parameters:
    - name: KB name (required) - can be internal_name or display_name
    - group_by: Group images by source file (default: "source_file")
    - include_metadata: Include full metadata (default: true)
    """
    from gangdan.core.image_handler import ImageHandler
    import json

    kb_name = request.args.get("name", "").strip()
    group_by = request.args.get("group_by", "source_file")
    include_metadata = request.args.get("include_metadata", "true").lower() == "true"

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    # Try to find the KB directory
    kb_dir, resolved_name = _resolve_kb_dir(kb_name)
    if resolved_name != kb_name:
        kb_name = resolved_name

    if kb_dir is None:
        # List available directories for debugging
        available = (
            [d.name for d in DOCS_DIR.iterdir() if d.is_dir()]
            if DOCS_DIR.exists()
            else []
        )
        print(
            f"[Gallery] KB '{kb_name}' not found. Available: {available}",
            file=sys.stderr,
        )
        return jsonify(
            {
                "success": False,
                "error": f"KB '{kb_name}' not found",
                "available_kbs": available,
            }
        ), 404

    print(f"[Gallery] Loading gallery for KB: {kb_name}", file=sys.stderr)

    handler = ImageHandler(kb_dir)
    images = handler.list_images()

    # Load full manifest for metadata
    manifest_path = kb_dir / ".image_manifest.json"
    manifests = {}
    if manifest_path.exists() and include_metadata:
        manifests = json.loads(manifest_path.read_text())

    # Group images
    if group_by == "source_file":
        gallery = {}
        for img in images:
            source = img.get("source_file", "unknown")
            if source not in gallery:
                gallery[source] = {
                    "source_file": source,
                    "images": [],
                    "count": 0,
                }
            gallery[source]["images"].append(img)
            gallery[source]["count"] += 1

        # Convert to list and add manifest metadata
        gallery_list = []
        for source, data in sorted(gallery.items()):
            if include_metadata and source in manifests:
                data["manifest"] = manifests[source]
            gallery_list.append(data)

        return jsonify(
            {
                "success": True,
                "kb_name": kb_name,
                "gallery": gallery_list,
                "total_images": len(images),
                "total_sources": len(gallery_list),
            }
        )
    else:
        # Flat list
        return jsonify(
            {
                "success": True,
                "kb_name": kb_name,
                "images": images,
                "count": len(images),
            }
        )


@app.route("/api/kb/delete-files", methods=["POST"])
def delete_kb_files():
    """Delete specific files from a knowledge base.

    Request body:
    - name: KB name (required)
    - files: List of file names to delete (required)
    """
    data = request.json
    kb_name = data.get("name", "").strip()
    files_to_delete = data.get("files", [])

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    if not files_to_delete:
        return jsonify({"success": False, "error": "No files specified"}), 400

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[DeleteKBFiles] KB: {kb_name}", file=sys.stderr)
    print(f"[DeleteKBFiles] Files: {files_to_delete}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    if not CHROMA or not CHROMA.is_available:
        return jsonify(
            {"success": False, "error": "Vector database not available"}
        ), 500

    if not CHROMA.collection_exists(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    files_set = set(files_to_delete)

    try:
        data = CHROMA.get_documents(kb_name, include=["metadatas", "ids"])

        ids_to_delete = []
        for i, meta in enumerate(data.get("metadatas", [])):
            if meta and meta.get("file") in files_set:
                ids_to_delete.append(data["ids"][i])

        if not ids_to_delete:
            return jsonify(
                {
                    "success": True,
                    "deleted_count": 0,
                    "message": "No matching documents found",
                }
            )

        success = CHROMA.delete_documents(kb_name, ids_to_delete)

        kb_dir_result = _resolve_kb_dir(kb_name)
        kb_base_dir = kb_dir_result[0] if kb_dir_result[0] else DOCS_DIR / kb_name

        for filename in files_to_delete:
            filepath = kb_base_dir / filename
            if filepath.exists():
                try:
                    filepath.unlink()
                    print(f"[DeleteKBFiles] Deleted file: {filepath}", file=sys.stderr)
                except Exception as e:
                    print(
                        f"[DeleteKBFiles] Error deleting file {filepath}: {e}",
                        file=sys.stderr,
                    )

        print(
            f"[DeleteKBFiles] Deleted {len(ids_to_delete)} documents from {len(files_to_delete)} files",
            file=sys.stderr,
        )
        print(f"{'=' * 60}\n", file=sys.stderr)

        return jsonify(
            {
                "success": success,
                "name": kb_name,
                "deleted_count": len(ids_to_delete),
                "files_processed": len(files_to_delete),
            }
        )
    except Exception as e:
        print(f"[DeleteKBFiles] Error: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/kb/export-files", methods=["POST"])
def export_kb_files():
    """Export selected files from a knowledge base as a ZIP download.

    Exports markdown, text, images, and any source files (PDF, HTML, TeX, etc.)
    found alongside the markdown files or referenced in documents.json.

    Request body:
    - name: KB name (required)
    - files: List of file names to export (optional; if empty, exports all)
    """
    data = request.json or {}
    kb_name = data.get("name", "").strip()
    files_to_export = data.get("files", [])

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    from gangdan.core.config import sanitize_kb_name

    internal_name = sanitize_kb_name(kb_name)
    kb_dir, resolved_name = _resolve_kb_dir(kb_name)
    if resolved_name != kb_name:
        internal_name = resolved_name

    if kb_dir is None:
            if not CHROMA or not CHROMA.is_available or not CHROMA.collection_exists(internal_name):
                return jsonify({"success": False, "error": f"KB not found: {kb_name}"}), 404
            return _export_kb_from_chromadb(internal_name, kb_name)

    SOURCE_EXTENSIONS = {".pdf", ".html", ".htm", ".tex", ".latex", ".epub", ".docx", ".doc", ".odt", ".rst"}

    buffer = io.BytesIO()
    exported = 0
    exported_paths = set()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        source_dir = kb_dir
        target_files = set(files_to_export) if files_to_export else None

        md_files = sorted(source_dir.rglob("*.md"))
        for md_file in md_files:
            rel_path = md_file.relative_to(source_dir)
            if target_files and md_file.name not in target_files and str(rel_path) not in target_files:
                continue
            try:
                zf.write(str(md_file), str(rel_path))
                exported += 1
                exported_paths.add(str(rel_path))
            except Exception as e:
                print(f"[ExportKBFiles] Error adding {md_file}: {e}", file=sys.stderr)

            stem = md_file.stem
            for ext in SOURCE_EXTENSIONS:
                source_file = md_file.with_suffix(ext)
                if source_file.exists() and str(source_file) not in exported_paths:
                    source_rel = source_file.relative_to(source_dir)
                    try:
                        zf.write(str(source_file), str(source_rel))
                        exported += 1
                        exported_paths.add(str(source_file))
                    except Exception as e:
                        print(f"[ExportKBFiles] Error adding source {source_file}: {e}", file=sys.stderr)

            # Also include _source.* files (e.g. 2308.12966_source.html, _source.pdf, _source.tar.gz)
            for src_ext in [".html", ".pdf", ".tar.gz", ".xml", ".tex"]:
                source_pattern = f"{stem}_source{src_ext}"
                source_candidate = md_file.parent / source_pattern
                if source_candidate.exists() and str(source_candidate) not in exported_paths:
                    source_rel = source_candidate.relative_to(source_dir)
                    try:
                        zf.write(str(source_candidate), str(source_rel))
                        exported += 1
                        exported_paths.add(str(source_candidate))
                    except Exception as e:
                        print(f"[ExportKBFiles] Error adding _source file {source_candidate}: {e}", file=sys.stderr)

        txt_files = sorted(source_dir.rglob("*.txt"))
        for txt_file in txt_files:
            rel_path = txt_file.relative_to(source_dir)
            if target_files and txt_file.name not in target_files and str(rel_path) not in target_files:
                continue
            try:
                zf.write(str(txt_file), str(rel_path))
                exported += 1
                exported_paths.add(str(txt_file))
            except Exception as e:
                print(f"[ExportKBFiles] Error adding {txt_file}: {e}", file=sys.stderr)

        for src_ext in SOURCE_EXTENSIONS:
            for src_file in sorted(source_dir.rglob(f"*{src_ext}")):
                if str(src_file) in exported_paths:
                    continue
                rel_path = src_file.relative_to(source_dir)
                if target_files and src_file.name not in target_files and str(rel_path) not in target_files:
                    continue
                try:
                    zf.write(str(src_file), str(rel_path))
                    exported += 1
                    exported_paths.add(str(src_file))
                except Exception as e:
                    print(f"[ExportKBFiles] Error adding source {src_file}: {e}", file=sys.stderr)

        # Also include _source.* files (preprint source files with _source suffix pattern)
        for src_file in sorted(source_dir.rglob("*_source.*")):
            if str(src_file) in exported_paths:
                continue
            rel_path = src_file.relative_to(source_dir)
            if target_files and src_file.name not in target_files and str(rel_path) not in target_files:
                continue
            try:
                zf.write(str(src_file), str(rel_path))
                exported += 1
                exported_paths.add(str(src_file))
            except Exception as e:
                print(f"[ExportKBFiles] Error adding _source file {src_file}: {e}", file=sys.stderr)

        images_dir = source_dir / "images"
        if images_dir.exists() and (target_files is None or any("images/" in str(f) for f in (target_files or []))):
            for img_file in sorted(images_dir.rglob("*")):
                if img_file.is_file():
                    try:
                        rel_path = img_file.relative_to(source_dir)
                        zf.write(str(img_file), str(rel_path))
                        exported += 1
                    except Exception as e:
                        print(f"[ExportKBFiles] Error adding {img_file}: {e}", file=sys.stderr)

        doc_json = kb_dir / "documents.json"
        if doc_json.exists():
            try:
                zf.write(str(doc_json), "documents.json")
                exported += 1
            except Exception:
                pass

            try:
                doc_data = json.loads(doc_json.read_text(encoding="utf-8"))
                documents = doc_data.get("documents", {})
                papers_dir = DATA_DIR / "papers"

                for doc_id, doc_info in documents.items():
                    md_path_str = doc_info.get("markdown_path", "")
                    if not md_path_str:
                        continue

                    external_md = Path(md_path_str)
                    if external_md.exists() and not str(external_md).startswith(str(source_dir)):
                        ext_rel = f"sources/{external_md.name}"
                        if ext_rel not in exported_paths:
                            try:
                                zf.write(str(external_md), ext_rel)
                                exported += 1
                                exported_paths.add(str(external_md))
                            except Exception as e:
                                print(f"[ExportKBFiles] Error adding external md {external_md}: {e}", file=sys.stderr)

                        stem = external_md.stem
                        for ext in SOURCE_EXTENSIONS:
                            source_candidate = external_md.with_suffix(ext)
                            if source_candidate.exists() and str(source_candidate) not in exported_paths:
                                src_rel = f"sources/{source_candidate.name}"
                                try:
                                    zf.write(str(source_candidate), src_rel)
                                    exported += 1
                                    exported_paths.add(str(source_candidate))
                                except Exception as e:
                                    print(f"[ExportKBFiles] Error adding source {source_candidate}: {e}", file=sys.stderr)

                        stem = external_md.stem
                        pdf_candidate = papers_dir / f"{stem}.pdf"
                        if pdf_candidate.exists() and str(pdf_candidate) not in exported_paths:
                            src_rel = f"sources/{pdf_candidate.name}"
                            try:
                                zf.write(str(pdf_candidate), src_rel)
                                exported += 1
                                exported_paths.add(str(pdf_candidate))
                            except Exception as e:
                                print(f"[ExportKBFiles] Error adding paper PDF {pdf_candidate}: {e}", file=sys.stderr)

                        for ext in SOURCE_EXTENSIONS:
                            source_candidate = external_md.parent / f"{stem}{ext}"
                            if source_candidate.exists() and str(source_candidate) not in exported_paths:
                                src_rel = f"sources/{source_candidate.name}"
                                try:
                                    zf.write(str(source_candidate), src_rel)
                                    exported += 1
                                    exported_paths.add(str(source_candidate))
                                except Exception as e:
                                    print(f"[ExportKBFiles] Error adding {source_candidate}: {e}", file=sys.stderr)

                    # Also include _source.* files from preprint_exports by source_id
                    source_id = doc_info.get("source_id", doc_id)
                    if source_id:
                        safe_sid = source_id.replace("/", "_").replace(":", "_").replace("(", "_").replace(")", "_")
                        exports_dir = DATA_DIR / "preprint_exports" / "preprints"
                        if exports_dir.exists():
                            for subdir in exports_dir.iterdir():
                                if not subdir.is_dir():
                                    continue
                                for src_ext in [".html", ".pdf", ".tar.gz", ".xml"]:
                                    src_candidate = subdir / f"{safe_sid}_source{src_ext}"
                                    if src_candidate.exists() and str(src_candidate) not in exported_paths:
                                        src_rel = f"sources/{src_candidate.name}"
                                        try:
                                            zf.write(str(src_candidate), src_rel)
                                            exported += 1
                                            exported_paths.add(str(src_candidate))
                                        except Exception as e:
                                            print(f"[ExportKBFiles] Error adding preprint source {src_candidate}: {e}", file=sys.stderr)

                    source_url = doc_info.get("url", "")
                    source_id = doc_info.get("source_id", "")
                    source_platform = doc_info.get("source_platform", "")
                    if source_id and papers_dir.exists():
                        for pdf_file in papers_dir.glob("*.pdf"):
                            if str(pdf_file) in exported_paths:
                                continue
                            pdf_stem = pdf_file.stem
                            if source_id in pdf_stem or source_id.replace("/", "_") in pdf_stem or source_id.replace(":", "_") in pdf_stem:
                                src_rel = f"sources/{pdf_file.name}"
                                try:
                                    zf.write(str(pdf_file), src_rel)
                                    exported += 1
                                    exported_paths.add(str(pdf_file))
                                except Exception as e:
                                    print(f"[ExportKBFiles] Error adding paper PDF {pdf_file}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"[ExportKBFiles] Error reading documents.json for source lookup: {e}", file=sys.stderr)

    if exported == 0:
        return jsonify({"success": False, "error": "No files to export"}), 404

    buffer.seek(0)
    from flask import Response
    filename = f"{internal_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    print(f"[ExportKBFiles] Exported {exported} files from '{kb_name}'", file=sys.stderr)

    return Response(
        buffer.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _export_kb_from_chromadb(internal_name: str, display_name: str):
    """Export KB data from ChromaDB when no filesystem directory exists.

    Dumps all documents, metadata, and ids from the ChromaDB collection
    into a JSON file inside a ZIP archive.
    """
    if not CHROMA or not CHROMA.is_available:
        return jsonify({"success": False, "error": "ChromaDB not available"}), 500

    try:
        docs_data = CHROMA.get_documents(internal_name, limit=0)
        documents = docs_data.get("documents", [])
        metadatas = docs_data.get("metadatas", [])
        ids = docs_data.get("ids", [])

        export_data = {
            "kb_name": display_name,
            "internal_name": internal_name,
            "exported_at": datetime.now().isoformat(),
            "total_documents": len(ids),
            "documents": [],
        }

        for i in range(len(ids)):
            export_data["documents"].append({
                "id": ids[i] if i < len(ids) else "",
                "document": (documents[i] if i < len(documents) else "")[:5000],
                "metadata": metadatas[i] if i < len(metadatas) else {},
            })

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "chromadb_export.json",
                json.dumps(export_data, indent=2, ensure_ascii=False),
            )
            exported = len(ids)

        if exported == 0:
            return jsonify({"success": False, "error": "No documents to export"}), 404

        buffer.seek(0)
        filename = f"{internal_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        print(f"[ExportKBFiles] Exported {exported} documents from ChromaDB for '{display_name}'", file=sys.stderr)

        return Response(
            buffer.getvalue(),
            mimetype="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        print(f"[ExportKBFiles] ChromaDB export error: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/kb/update", methods=["POST"])
def update_kb():
    """Update knowledge base metadata and settings.

    Request body:
    - name: Current KB name (required)
    - new_name: New KB name (optional)
    - description: KB description (optional)
    - auto_index: Auto-index on file upload (optional, default: True)
    """
    data = request.json
    kb_name = data.get("name", "").strip()
    new_name = data.get("new_name", "").strip()
    description = data.get("description")
    auto_index = data.get("auto_index", True)

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[UpdateKB] Updating KB: {kb_name}", file=sys.stderr)
    if new_name:
        print(f"[UpdateKB] New name: {new_name}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    if not _find_kb_files_dir(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    try:
        import json
        import shutil

        updated = False

        if new_name and new_name != kb_name:
            new_name_sanitized = sanitize_kb_name(new_name)
            new_dir = DOCS_DIR / new_name_sanitized

            if new_dir.exists():
                return jsonify(
                    {"success": False, "error": f"KB '{new_name}' already exists"}
                ), 400

            shutil.move(str(kb_dir), str(new_dir))
            print(
                f"[UpdateKB] Renamed directory: {kb_name} -> {new_name_sanitized}",
                file=sys.stderr,
            )

            if CHROMA and CHROMA.is_available and CHROMA.collection_exists(kb_name):
                print(
                    f"[UpdateKB] Note: Collection '{kb_name}' still exists in ChromaDB. Please reindex to sync.",
                    file=sys.stderr,
                )

            update_user_kb_name(kb_name, new_name_sanitized)
            kb_name = new_name_sanitized
            updated = True

        if description is not None:
            kb_metadata_path = kb_dir / ".kb_metadata.json"
            metadata = {}
            if kb_metadata_path.exists():
                metadata = json.loads(kb_metadata_path.read_text())

            metadata["description"] = description
            kb_metadata_path.write_text(json.dumps(metadata, indent=2))
            print(f"[UpdateKB] Updated description", file=sys.stderr)
            updated = True

        kb_config_path = kb_dir / ".kb_config.json"
        config = {"auto_index": auto_index}
        kb_config_path.write_text(json.dumps(config, indent=2))
        print(f"[UpdateKB] Updated config", file=sys.stderr)
        updated = True

        if description is not None:
            kb_metadata_path = kb_dir / ".kb_metadata.json"
            metadata = {}
            if kb_metadata_path.exists():
                metadata = json.loads(kb_metadata_path.read_text())

            metadata["description"] = description
            kb_metadata_path.write_text(json.dumps(metadata, indent=2))
            print(f"[UpdateKB] Updated description", file=sys.stderr)
            updated = True

        kb_config_path = kb_dir / ".kb_config.json"
        config = {"auto_index": auto_index}
        kb_config_path.write_text(json.dumps(config, indent=2))
        print(f"[UpdateKB] Updated config", file=sys.stderr)
        updated = True

        if description is not None:
            kb_metadata_path = kb_dir / ".kb_metadata.json"
            metadata = {}
            if kb_metadata_path.exists():
                import json

                metadata = json.loads(kb_metadata_path.read_text())

            metadata["description"] = description
            kb_metadata_path.write_text(json.dumps(metadata, indent=2))
            print(f"[UpdateKB] Updated description", file=sys.stderr)
            updated = True

        kb_config_path = kb_dir / ".kb_config.json"
        config = {"auto_index": auto_index}
        import json

        kb_config_path.write_text(json.dumps(config, indent=2))
        print(f"[UpdateKB] Updated config", file=sys.stderr)
        updated = True

        print(f"[UpdateKB] Complete: {updated}", file=sys.stderr)
        print(f"{'=' * 60}\n", file=sys.stderr)

        return jsonify(
            {
                "success": True,
                "name": kb_name,
                "updated": updated,
            }
        )
    except Exception as e:
        print(f"[UpdateKB] Error: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/kb/refine-query", methods=["POST"])
def refine_search_query():
    """Refine/translate a search query using AI.

    Uses the chat model by default (supports Ollama and online providers).
    Optionally accepts provider/model overrides for a separate refinement model.

    Request JSON: { query: str, context: str, provider: str, model: str, api_key: str, base_url: str }
    Returns: { success: bool, refined_query: str, original_query: str }
    """
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    context = data.get("context", "academic search").strip()

    if not query:
        return jsonify({"success": False, "error": "Query required"})

    # Determine which LLM client/model to use:
    # 1. If provider/model/api_key/base_url are provided, use the specified refinement model
    # 2. Otherwise, default to the chat model (which works with any provider)
    provider = data.get("provider", "")
    model_name = data.get("model", "")
    api_key = data.get("api_key", "")
    base_url = data.get("base_url", "")

    if provider and provider != "ollama":
        from gangdan.core.llm_client import create_client
        llm_client = create_client(
            provider=provider,
            api_key=api_key or CONFIG.chat_api_key,
            base_url=base_url or CONFIG.chat_api_base_url,
        )
        model = model_name or CONFIG.chat_model or CONFIG.chat_model_name
    elif provider == "ollama":
        llm_client = OLLAMA
        OLLAMA.api_url = CONFIG.ollama_url
        model = model_name or CONFIG.chat_model or CONFIG.chat_model_name or CONFIG.embedding_model
    else:
        # Default: use the same client as the chat model
        llm_client = get_chat_client()
        model = model_name or CONFIG.chat_model_name or CONFIG.chat_model or CONFIG.embedding_model

    if not model:
        return jsonify({"success": True, "refined_query": query, "original_query": query})

    try:
        prompt = f"""Refine the following search query for {context}.
Original query: "{query}"

Rules:
1. If the query is NOT in English, first translate it to English
2. Add relevant technical synonyms and related terms
3. Keep it under 100 characters
4. Return ONLY the refined query, nothing else

Refined query:"""

        result = llm_client.chat_complete(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )

        if result:
            refined = result.strip()
            if refined and len(refined) < 200:
                return jsonify({
                    "success": True,
                    "refined_query": refined,
                    "original_query": query,
                })

    except Exception as e:
        logger.warning("[RefineQuery] Failed: %s", e)

    return jsonify({"success": True, "refined_query": query, "original_query": query})


@app.route("/api/kb/translate", methods=["POST"])
def translate_text():
    """Translate markdown text to target language while preserving references.

    Request JSON: { text: str, target_lang: str }
    Returns: { success: bool, translated_text: str }
    """
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    target_lang = data.get("target_lang", "").strip()

    if not text or not target_lang:
        return jsonify({"success": False, "error": "text and target_lang required"})

    if not (CONFIG.chat_model or CONFIG.chat_model_name):
        return jsonify({"success": False, "error": "No chat model configured"})

    LANG_NAMES = {"zh": "Chinese", "en": "English", "ja": "Japanese", "fr": "French",
                  "ru": "Russian", "de": "German", "it": "Italian", "es": "Spanish",
                  "pt": "Portuguese", "ko": "Korean"}
    lang_name = LANG_NAMES.get(target_lang, target_lang)

    # Strip HTML tags for LLM but keep markdown
    import re as _re
    clean = _re.sub(r'<[^>]+>', '', text)
    # Extract references section (everything after "## References" or "## 参考文献")
    ref_match = _re.search(r'(?:\n|^)(?:##\s*(?:References|参考文献|参考|引用).*?$.*)', clean,
                           _re.DOTALL | _re.IGNORECASE)
    refs = ref_match.group(0) if ref_match else ""
    main = clean[:ref_match.start()] if ref_match else clean

    if len(main.strip()) < 50:
        return jsonify({"success": False, "error": "Text too short to translate"})

    prompt = f"""Translate the following academic text to {lang_name}. 

CRITICAL RULES:
1. Keep ALL markdown formatting (# ## ### ** * - etc.)
2. Keep ALL LaTeX formulas ($...$ and $$...$$) unchanged
3. Keep ALL numbers, dates, citations [n] unchanged
4. Keep ALL reference sections (---, References, 参考文献) at the end EXACTLY as-is - DO NOT translate them
5. Only translate the main content text
6. Return ONLY the translated text, no explanations

Original text:
{main[:8000]}

Translated text:"""

    try:
        client = get_chat_client()
        model = CONFIG.translate_model or CONFIG.chat_model_name or CONFIG.chat_model

        translated = client.chat_complete(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )

        if translated:
            result = translated.strip() + ("\n\n" + refs if refs else "")
            return jsonify({"success": True, "translated_text": result})
    except Exception as e:
        logger.warning("[Translate] Failed: %s", e)

    return jsonify({"success": False, "error": "Translation failed"})


def _find_kb_files_dir(kb_name: str) -> Path | None:
    """Find KB files directory from all possible locations (docs, custom_kbs, preprint_kbs)."""
    candidates = [
        DOCS_DIR / kb_name,
        DATA_DIR / "custom_kbs" / kb_name,
        DATA_DIR / "preprint_kbs" / kb_name,
    ]
    for d in candidates:
        if d.exists() and d.is_dir():
            return d
    return None


@app.route("/api/kb/literature-review", methods=["POST"])
def generate_literature_review():
    """Generate academic-style literature review for selected knowledge bases.

    This endpoint retrieves documents from selected KBs and uses the LLM
    to generate a scholarly literature review with comprehensive analysis
    based on the user's topic/question.
    """
    data = request.json
    kb_names = data.get("kb_names", [])
    user_lang = data.get("language", CONFIG.language)
    review_topic = data.get("topic", "").strip()
    output_size = data.get("output_size", "medium")
    doc_scope = data.get("doc_scope", None)  # List of doc_ids to strictly use

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[LitReview] Generating literature review", file=sys.stderr)
    print(f"[LitReview] KBs: {kb_names}", file=sys.stderr)
    print(f"[LitReview] Topic: {review_topic}", file=sys.stderr)
    print(f"[LitReview] Language: {user_lang}", file=sys.stderr)
    print(f"[LitReview] Output size: {output_size}", file=sys.stderr)
    print(f"[LitReview] doc_scope: {doc_scope}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    if not kb_names:
        return jsonify({"success": False, "error": t("no_kb_selected", user_lang)})

    if not (CONFIG.chat_model or CONFIG.chat_model_name):
        return jsonify({"success": False, "error": "No chat model configured"})

    # Output size configuration
    size_config = {
        "short": {"section_words": 200, "doc_limit": 5, "doc_truncate": 2000},
        "medium": {"section_words": 400, "doc_limit": 10, "doc_truncate": 3000},
        "long": {"section_words": 600, "doc_limit": 15, "doc_truncate": 4000},
    }.get(output_size, {"section_words": 400, "doc_limit": 10, "doc_truncate": 3000})

    # Collect all documents from selected KBs
    # Use KB manager to get documents with proper doc_ids for filtering
    all_docs = []
    try:
        from gangdan.kb_routes import get_kb_manager
        manager = get_kb_manager()
        
        for kb_name in kb_names:
            kb = manager.get_kb(kb_name)
            if kb is None:
                # Fallback to file-based reading for builtin KBs
                kb_dir = _find_kb_files_dir(kb_name)
                if kb_dir.exists():
                    for filepath in list(kb_dir.glob("*.md")) + list(kb_dir.glob("*.txt")):
                        try:
                            content = filepath.read_text(encoding="utf-8")
                            if len(content) > size_config["doc_truncate"]:
                                content = content[: size_config["doc_truncate"]] + "\n\n[... content truncated ...]"
                            all_docs.append({"kb": kb_name, "file": filepath.name, "content": content, "doc_id": filepath.stem})
                        except Exception as e:
                            print(f"[LitReview] Error reading {filepath}: {e}", file=sys.stderr)
                continue
            
            # Get documents from KB manager (has proper doc_ids)
            docs = manager.get_documents(kb_name)
            for doc in docs:
                try:
                    content = ""
                    if doc.markdown_path:
                        from pathlib import Path
                        md_path = Path(doc.markdown_path)
                        if md_path.exists():
                            content = md_path.read_text(encoding="utf-8")
                    if not content:
                        content = doc.content_preview or ""
                    
                    if len(content) > size_config["doc_truncate"]:
                        content = content[: size_config["doc_truncate"]] + "\n\n[... content truncated ...]"
                    
                    all_docs.append({
                        "kb": kb_name,
                        "file": Path(doc.markdown_path).name if doc.markdown_path else (doc.title or "unknown.md"),
                        "content": content,
                        "doc_id": doc.doc_id,
                        "title": doc.title,
                    })
                except Exception as e:
                    print(f"[LitReview] Error reading doc {doc.doc_id}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[LitReview] Error using KB manager: {e}", file=sys.stderr)
        # Fallback to file-based reading
        for kb_name in kb_names:
            kb_dir = _find_kb_files_dir(kb_name)
            if kb_dir.exists():
                for filepath in list(kb_dir.glob("*.md")) + list(kb_dir.glob("*.txt")):
                    try:
                        content = filepath.read_text(encoding="utf-8")
                        if len(content) > size_config["doc_truncate"]:
                            content = content[: size_config["doc_truncate"]] + "\n\n[... content truncated ...]"
                        all_docs.append({"kb": kb_name, "file": filepath.name, "content": content, "doc_id": filepath.stem})
                    except Exception as e:
                        print(f"[LitReview] Error reading {filepath}: {e}", file=sys.stderr)

    # If doc_scope is provided, filter to only those documents
    if doc_scope and len(doc_scope) > 0:
        print(f"[LitReview] Filtering to {len(doc_scope)} selected documents", file=sys.stderr)
        doc_scope_set = set(doc_scope)
        filtered_docs = []
        for doc in all_docs:
            # Match by doc_id, filename, or if doc_scope ID appears in filename
            doc_id_match = doc.get("doc_id") in doc_scope_set
            file_match = doc["file"] in doc_scope_set
            partial_match = any(doc_id in doc["file"] for doc_id in doc_scope_set)
            if doc_id_match or file_match or partial_match:
                filtered_docs.append(doc)
        
        if filtered_docs:
            all_docs = filtered_docs
            print(f"[LitReview] After filtering: {len(all_docs)} documents", file=sys.stderr)
        else:
            # If no match found, use all documents and warn
            print(f"[LitReview] WARNING: Could not match doc_scope to documents. Using all {len(all_docs)} documents.", file=sys.stderr)

    # Limit documents based on output size (only if not in strict mode)
    if not doc_scope and len(all_docs) > size_config["doc_limit"]:
        all_docs = all_docs[: size_config["doc_limit"]]

    if not all_docs:
        return jsonify(
            {
                "success": False,
                "error": "No documents found in selected knowledge bases",
            }
        )

    print(f"[LitReview] Found {len(all_docs)} documents", file=sys.stderr)

    # Language mapping for prompt
    LANG_NAMES = {
        "zh": "Chinese (简体中文)",
        "en": "English",
        "ja": "Japanese (日本語)",
        "fr": "French (Français)",
        "ru": "Russian (Русский)",
        "de": "German (Deutsch)",
        "it": "Italian (Italiano)",
        "es": "Spanish (Español)",
        "pt": "Portuguese (Português)",
        "ko": "Korean (한국어)",
    }
    lang_name = LANG_NAMES.get(user_lang, "English")

    # If no topic provided, use generic analysis
    if not review_topic:
        review_topic = "comprehensive analysis of the documents"

    def generate():
        """Stream the literature review generation."""
        total_tokens = 0
        docs_processed = 0

        chat_client = get_chat_client()
        model_name = CONFIG.chat_model_name or CONFIG.chat_model
        
        if CONFIG.chat_provider == "ollama":
            stream_kwargs = {}
        else:
            stream_kwargs = {"max_tokens": CONFIG.chat_max_tokens}

        def emit_stats():
            nonlocal total_tokens, docs_processed
            yield f"data: {json.dumps({'type': 'context', 'tokens': total_tokens, 'sections': docs_processed, 'sources': len(all_docs)})}\n\n"

        # Header
        topic_header = f": {review_topic}" if review_topic else ""
        header = f"# {t('lit_review', user_lang)}{topic_header}\n\n"
        total_tokens += len(header) // 4
        yield f"data: {json.dumps({'content': header})}\n\n"
        yield f"data: {json.dumps({'type': 'context', 'model': model_name, 'tokens': 0, 'sections': 0, 'sources': len(all_docs)})}\n\n"
        yield from emit_stats()

        # Introduction section - synthesize overview based on topic
        intro_prompt = f"""You are an academic researcher writing a literature review. 
Analyze the following documents in relation to this topic/question: "{review_topic}"

IMPORTANT: 
- Respond ONLY in {lang_name}
- Write a brief introduction (2-3 paragraphs) that:
  1. Introduces the topic and its significance
  2. Identifies the time period covered by the documents (note the years)
  3. Identifies key themes that emerge across the documents
  4. Outlines the structure of the review
- When citing documents, include author and year from the filenames

Documents:
---
{chr(10).join([f"[{d['file']}] {d['content'][:1500]}..." for d in all_docs[:5]])}
---

Write only the introduction section. Do not include any headers."""

        intro_header = (
            f"## {t('intro', user_lang)}\n\n"
        )
        yield f"data: {json.dumps({'content': intro_header})}\n\n"

        try:
            messages = [{"role": "user", "content": intro_prompt}]
            intro_content = ""
            for chunk in chat_client.chat_stream(
                messages, model_name, temperature=0.4, **stream_kwargs
            ):
                if chat_client.is_stopped():
                    yield f"data: {json.dumps({'content': chr(92) + chr(92) + 'n[Stopped]', 'stopped': True})}\n\n"
                    return
                intro_content += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            total_tokens += len(intro_content) // 4
            yield f"data: {json.dumps({'content': chr(92) + chr(92) + 'n'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*' + chr(92) + chr(92) + 'n'})}\n\n"

        yield from emit_stats()

        # Thematic analysis section - group documents by themes
        theme_prompt = f"""Based on the following documents and the topic "{review_topic}", identify 3-4 key themes or categories.

For each theme:
1. Provide a brief theme name
2. List which documents relate to this theme
3. Summarize the key insights from those documents about this theme
4. IMPORTANT: When multiple documents address the same theme, organize the discussion chronologically by year - show how ideas evolved over time. Identify the earliest work, how later work built upon or departed from it, and the current state of the art.

IMPORTANT:
- Respond ONLY in {lang_name}
- Use academic language
- When citing documents, include author and year information from the filenames
- For chronological analysis, explicitly state the years and show the progression
- Format as: ### Theme Name\\n[Theme content with citations]\\n\\n

Documents:
---
{chr(10).join([f"[{d['file']}] {d['content'][:2000]}" for d in all_docs])}
---

Write a thematic analysis organized by key themes. Pay special attention to the temporal evolution of ideas when multiple documents address the same theme."""

        theme_header = f"\n## {t('theme_analysis', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': theme_header})}\n\n"

        try:
            messages = [{"role": "user", "content": theme_prompt}]
            theme_content = ""
            for chunk in chat_client.chat_stream(
                messages, model_name, temperature=0.5, **stream_kwargs
            ):
                if chat_client.is_stopped():
                    yield f"data: {json.dumps({'content': chr(92) + chr(92) + 'n[Stopped]', 'stopped': True})}\n\n"
                    return
                theme_content += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            total_tokens += len(theme_content) // 4
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*' + chr(92) + chr(92) + 'n'})}\n\n"

        docs_processed = len(all_docs)
        yield from emit_stats()

        # Conclusion section
        conclusion_prompt = f"""Write a conclusion for a literature review on "{review_topic}".

Based on the following documents, provide:
1. Summary of key findings
2. Identified gaps in the literature
3. Suggestions for future research

IMPORTANT:
- Respond ONLY in {lang_name}
- Use academic language
- Be concise (2-3 paragraphs)

Documents analyzed: {len(all_docs)} documents from {", ".join(kb_names)}
---

Write only the conclusion section."""

        conclusion_header = f"\n## {t('conclusion', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': conclusion_header})}\n\n"

        try:
            messages = [{"role": "user", "content": conclusion_prompt}]
            conclusion_content = ""
            for chunk in chat_client.chat_stream(
                messages, model_name, temperature=0.4, **stream_kwargs
            ):
                if chat_client.is_stopped():
                    yield f"data: {json.dumps({'content': chr(92) + chr(92) + 'n[Stopped]', 'stopped': True})}\n\n"
                    return
                conclusion_content += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            total_tokens += len(conclusion_content) // 4
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*' + chr(92) + chr(92) + 'n'})}\n\n"

        # References
        refs_header = f"\n## {t('references', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': refs_header})}\n\n"
        for i, doc in enumerate(all_docs):
            fname = doc['file'].replace('.md', '').replace('.txt', '')
            ref_line = f"[{i+1}] {fname}\n"
            yield f"data: {json.dumps({'content': ref_line})}\n\n"

        # Completion marker
        yield from emit_stats()
        yield f"data: {json.dumps({'done': True})}\n\n"
        print(
            f"[LitReview] Generation complete: {total_tokens} tokens, {docs_processed} docs",
            file=sys.stderr,
        )

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/kb/paper", methods=["POST"])
def generate_paper():
    """Generate a complete academic paper following AAAI standards from selected KBs."""
    data = request.json
    kb_names = data.get("kb_names", [])
    paper_topic = data.get("topic", "").strip()
    
    # Use output_language setting (respects user's language preference in settings)
    user_lang = CONFIG.output_language or CONFIG.language

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[Paper] Generating academic paper", file=sys.stderr)
    print(f"[Paper] KBs: {kb_names}", file=sys.stderr)
    print(f"[Paper] Topic: {paper_topic}", file=sys.stderr)
    print(f"[Paper] Language: {user_lang}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    if not kb_names:
        return jsonify({"success": False, "error": t("no_kb_selected", user_lang)})

    if not (CONFIG.chat_model or CONFIG.chat_model_name):
        return jsonify({"success": False, "error": "No chat model configured"})

    # Collect all documents from selected KBs
    all_docs = []
    for kb_name in kb_names:
        kb_dir = _find_kb_files_dir(kb_name)
        if kb_dir.exists():
            for filepath in list(kb_dir.glob("*.md")) + list(kb_dir.glob("*.txt")):
                try:
                    content = filepath.read_text(encoding="utf-8")
                    if len(content) > 4000:
                        content = content[:4000] + "\n\n[... content truncated ...]"
                    all_docs.append(
                        {"kb": kb_name, "file": filepath.name, "content": content}
                    )
                except Exception as e:
                    print(f"[Paper] Error reading {filepath}: {e}", file=sys.stderr)

    if not all_docs:
        return jsonify({"success": False, "error": "No documents found in selected knowledge bases"})

    print(f"[Paper] Found {len(all_docs)} documents", file=sys.stderr)

    # Language mapping
    LANG_NAMES = {
        "zh": "Chinese (简体中文)",
        "en": "English",
        "ja": "Japanese (日本語)",
        "fr": "French (Français)",
        "ru": "Russian (Русский)",
        "de": "German (Deutsch)",
        "it": "Italian (Italiano)",
        "es": "Spanish (Español)",
        "pt": "Portuguese (Português)",
        "ko": "Korean (한국어)",
    }
    lang_name = LANG_NAMES.get(user_lang, "English")

    # Writing style guidelines to avoid AI markers
    style_guide = f"""
WRITING STYLE REQUIREMENTS (CRITICAL):
- Write the ENTIRE paper in {lang_name}
- Write in fluent, elegant academic prose
- NEVER use colons in section titles (e.g., write "Introduction" not "Introduction:")
- NEVER use bold text for section titles
- NEVER use phrases like "首先", "然后", "最终", "firstly", "secondly", "finally", "in conclusion", "综上所述", "总而言之"
- NEVER use phrases like "值得注意的是", "需要指出的是", "it is worth noting that"
- NEVER use bullet points or numbered lists in the main text
- Use flowing paragraphs with smooth transitions
- Cite sources naturally within sentences, e.g., "Smith et al. demonstrated that..." or "Recent work by [1] shows..."
- Write in third person, formal academic tone
- Each section should be 2-4 substantial paragraphs
- Use proper academic hedging where appropriate
- Do not explicitly state what you are about to do or have done
- NEVER output any thinking, reasoning, or self-reflection text. Output ONLY the final paper content.
- NEVER include phrases like "Let me", "I will", "The user wants", "I need to", or any meta-commentary
"""

    def strip_thinking(text):
        """Remove thinking/reasoning blocks from model output."""
        import re
        # Remove <think>...</think> blocks
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Remove <think>...</think> blocks
        text = re.sub(r'<think>.*?</think_tag>', '', text, flags=re.DOTALL)
        # Remove lines that look like self-reflection (common patterns)
        lines = text.split('\n')
        filtered = []
        skip_block = False
        for line in lines:
            stripped = line.strip().lower()
            if any(stripped.startswith(p) for p in ['let me ', 'i need to ', 'i should ', 'the user wants', 'i\'ll ', 'i will ', 'let\'s ', 'okay, ', 'now i']):
                if len(stripped) < 200:
                    continue
            filtered.append(line)
        return '\n'.join(filtered)

    def stream_filtered(chat_client, messages, model_name, temperature, **kwargs):
        """Stream with thinking/think_tag filtering."""
        in_think = False
        for chunk in chat_client.chat_stream(messages, model_name, temperature=temperature, **kwargs):
            if chat_client.is_stopped():
                yield None, True
            if '<think>' in chunk or '<think>' in chunk:
                in_think = True
            if '</think>' in chunk or '</think>' in chunk:
                in_think = False
                chunk = chunk.split('</think>')[-1].split('</think>')[-1]
            if not in_think:
                cleaned = strip_thinking(chunk)
                if cleaned.strip():
                    yield cleaned, False
        yield None, False

    def generate():
        """Stream the paper generation."""
        total_tokens = 0
        chat_client = get_chat_client()
        model_name = CONFIG.chat_model_name or CONFIG.chat_model
        if CONFIG.chat_provider == "ollama":
            stream_kwargs = {}
        else:
            stream_kwargs = {"max_tokens": CONFIG.chat_max_tokens}

        docs_context = "\n\n".join([
            f"Document [{i+1}] from {d['kb']}/{d['file']}:\n{d['content'][:2500]}"
            for i, d in enumerate(all_docs[:15])
        ])

        # Title
        title = f"# {paper_topic}\n\n"
        yield f"data: {json.dumps({'content': title})}\n\n"

        # Abstract
        abstract_prompt = f"""Write an abstract for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The abstract should be a single paragraph (150-250 words) that:
- States the research problem and its significance
- Briefly describes the approach or methodology
- Summarizes key findings or contributions
- Does NOT contain citations

Source documents for context:
{docs_context[:6000]}

Write ONLY the abstract paragraph. No heading, no labels."""

        abstract_header = f"\n## {t('paper_abstract', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': abstract_header})}\n\n"

        try:
            messages = [{"role": "user", "content": abstract_prompt}]
            for cleaned, stopped in stream_filtered(chat_client, messages, model_name, 0.5, **stream_kwargs):
                if stopped:
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                if cleaned:
                    yield f"data: {json.dumps({'content': cleaned})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # Introduction
        intro_prompt = f"""Write the introduction for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The introduction should:
- Establish the broader context and motivation
- Identify the specific problem or gap
- Articulate the paper's contributions
- Be 3-4 paragraphs
- Include natural citations to the source documents where relevant

Source documents:
{docs_context[:8000]}

Write the introduction. No heading."""

        intro_header = f"\n## {t('paper_introduction', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': intro_header})}\n\n"

        try:
            messages = [{"role": "user", "content": intro_prompt}]
            for cleaned, stopped in stream_filtered(chat_client, messages, model_name, 0.5, **stream_kwargs):
                if stopped:
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                if cleaned:
                    yield f"data: {json.dumps({'content': cleaned})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # Related Work
        related_prompt = f"""Write a related work section for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The related work section should:
- Survey the relevant literature thematically
- Group related approaches and compare them
- Identify gaps that motivate this work
- Be 3-4 paragraphs
- Cite source documents naturally within the narrative

Source documents:
{docs_context}

Write the related work section. No heading."""

        related_header = f"\n## {t('paper_related_work', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': related_header})}\n\n"

        try:
            messages = [{"role": "user", "content": related_prompt}]
            for cleaned, stopped in stream_filtered(chat_client, messages, model_name, 0.5, **stream_kwargs):
                if stopped:
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                if cleaned:
                    yield f"data: {json.dumps({'content': cleaned})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # Method
        method_prompt = f"""Write a method section for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The method section should:
- Describe the technical approach in detail
- Explain key design choices and rationale
- Be 3-4 paragraphs
- Reference source documents where appropriate

Source documents:
{docs_context}

Write the method section. No heading."""

        method_header = f"\n## {t('paper_method', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': method_header})}\n\n"

        try:
            messages = [{"role": "user", "content": method_prompt}]
            for cleaned, stopped in stream_filtered(chat_client, messages, model_name, 0.5, **stream_kwargs):
                if stopped:
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                if cleaned:
                    yield f"data: {json.dumps({'content': cleaned})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # Experiments
        exp_prompt = f"""Write an experiments section for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The experiments section should:
- Describe the experimental setup
- Present and analyze results
- Compare with baselines or prior work where applicable
- Be 3-4 paragraphs
- Reference source documents for empirical evidence

Source documents:
{docs_context}

Write the experiments section. No heading."""

        exp_header = f"\n## {t('paper_experiments', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': exp_header})}\n\n"

        try:
            messages = [{"role": "user", "content": exp_prompt}]
            for cleaned, stopped in stream_filtered(chat_client, messages, model_name, 0.5, **stream_kwargs):
                if stopped:
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                if cleaned:
                    yield f"data: {json.dumps({'content': cleaned})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # Discussion
        disc_prompt = f"""Write a discussion section for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The discussion should:
- Interpret the results in broader context
- Discuss limitations honestly
- Suggest directions for future work
- Be 2-3 paragraphs
- Avoid phrases like "in conclusion", "综上所述", "总而言之"

Source documents:
{docs_context}

Write the discussion section. No heading."""

        disc_header = f"\n## {t('paper_discussion', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': disc_header})}\n\n"

        try:
            messages = [{"role": "user", "content": disc_prompt}]
            for cleaned, stopped in stream_filtered(chat_client, messages, model_name, 0.5, **stream_kwargs):
                if stopped:
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                if cleaned:
                    yield f"data: {json.dumps({'content': cleaned})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # Conclusion
        concl_prompt = f"""Write a conclusion for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The conclusion should:
- Briefly restate the main contributions
- Summarize key takeaways
- Be 1-2 paragraphs
- NEVER start with "In conclusion", "综上所述", "总而言之", or similar phrases
- End with a forward-looking statement

Source documents:
{docs_context[:4000]}

Write the conclusion. No heading."""

        concl_header = f"\n## {t('paper_conclusion', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': concl_header})}\n\n"

        try:
            messages = [{"role": "user", "content": concl_prompt}]
            for cleaned, stopped in stream_filtered(chat_client, messages, model_name, 0.5, **stream_kwargs):
                if stopped:
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                if cleaned:
                    yield f"data: {json.dumps({'content': cleaned})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # Introduction
        intro_prompt = f"""Write the introduction for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The introduction should:
- Establish the broader context and motivation
- Identify the specific problem or gap
- Articulate the paper's contributions
- Be 3-4 paragraphs
- Include natural citations to the source documents where relevant

Source documents:
{docs_context[:8000]}

Write the introduction. No heading."""

        intro_header = f"\n## {t('paper_introduction', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': intro_header})}\n\n"

        try:
            messages = [{"role": "user", "content": intro_prompt}]
            for chunk in chat_client.chat_stream(messages, model_name, temperature=0.5, **stream_kwargs):
                if chat_client.is_stopped():
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # Related Work
        related_prompt = f"""Write a related work section for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The related work section should:
- Survey the relevant literature thematically
- Group related approaches and compare them
- Identify gaps that motivate this work
- Be 3-4 paragraphs
- Cite source documents naturally within the narrative

Source documents:
{docs_context}

Write the related work section. No heading."""

        related_header = f"\n## {t('paper_related_work', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': related_header})}\n\n"

        try:
            messages = [{"role": "user", "content": related_prompt}]
            for chunk in chat_client.chat_stream(messages, model_name, temperature=0.5, **stream_kwargs):
                if chat_client.is_stopped():
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # Method
        method_prompt = f"""Write a method section for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The method section should:
- Describe the technical approach in detail
- Explain key design choices and rationale
- Be 3-4 paragraphs
- Reference source documents where appropriate

Source documents:
{docs_context}

Write the method section. No heading."""

        method_header = f"\n## {t('paper_method', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': method_header})}\n\n"

        try:
            messages = [{"role": "user", "content": method_prompt}]
            for chunk in chat_client.chat_stream(messages, model_name, temperature=0.5, **stream_kwargs):
                if chat_client.is_stopped():
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # Experiments
        exp_prompt = f"""Write an experiments section for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The experiments section should:
- Describe the experimental setup
- Present and analyze results
- Compare with baselines or prior work where applicable
- Be 3-4 paragraphs
- Reference source documents for empirical evidence

Source documents:
{docs_context}

Write the experiments section. No heading."""

        exp_header = f"\n## {t('paper_experiments', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': exp_header})}\n\n"

        try:
            messages = [{"role": "user", "content": exp_prompt}]
            for chunk in chat_client.chat_stream(messages, model_name, temperature=0.5, **stream_kwargs):
                if chat_client.is_stopped():
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # Discussion
        disc_prompt = f"""Write a discussion section for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The discussion should:
- Interpret the results in broader context
- Discuss limitations honestly
- Suggest directions for future work
- Be 2-3 paragraphs
- Avoid phrases like "in conclusion", "综上所述", "总而言之"

Source documents:
{docs_context}

Write the discussion section. No heading."""

        disc_header = f"\n## {t('paper_discussion', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': disc_header})}\n\n"

        try:
            messages = [{"role": "user", "content": disc_prompt}]
            for chunk in chat_client.chat_stream(messages, model_name, temperature=0.5, **stream_kwargs):
                if chat_client.is_stopped():
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # Conclusion
        concl_prompt = f"""Write a conclusion for an academic paper on "{paper_topic}" in {lang_name}.

{style_guide}

The conclusion should:
- Briefly restate the main contributions
- Summarize key takeaways
- Be 1-2 paragraphs
- NEVER start with "In conclusion", "综上所述", "总而言之", or similar phrases
- End with a forward-looking statement

Source documents:
{docs_context[:4000]}

Write the conclusion. No heading."""

        concl_header = f"\n## {t('paper_conclusion', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': concl_header})}\n\n"

        try:
            messages = [{"role": "user", "content": concl_prompt}]
            for chunk in chat_client.chat_stream(messages, model_name, temperature=0.5, **stream_kwargs):
                if chat_client.is_stopped():
                    yield f"data: {json.dumps({'content': '\\n[Stopped]', 'stopped': True})}\n\n"
                    return
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'*Error: {e}*\\n'})}\n\n"

        # References
        refs_header = f"\n## {t('paper_references', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': refs_header})}\n\n"
        for i, doc in enumerate(all_docs):
            ref_line = f"[{i+1}] {doc['file']}. {doc['kb']}.\n"
            yield f"data: {json.dumps({'content': ref_line})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"
        print(f"[Paper] Generation complete", file=sys.stderr)

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/wiki/list")
def wiki_list_kbs():
    """List KBs that have wiki pages."""
    from gangdan.core.wiki_builder import WikiBuilder
    
    result = []
    for kb_name in DOC_SOURCES:
        if _find_kb_files_dir(kb_name):
            builder = WikiBuilder(kb_name)
            has_wiki = builder.wiki_exists()
            pages = builder.get_wiki_pages() if has_wiki else []
            result.append({
                "name": kb_name,
                "display_name": DOC_SOURCES[kb_name]["name"],
                "has_wiki": has_wiki,
                "page_count": len(pages),
            })
    
    # Also check user KBs
    user_kbs = load_user_kbs()
    for kb_name in user_kbs:
        if _find_kb_files_dir(kb_name):
            builder = WikiBuilder(kb_name)
            has_wiki = builder.wiki_exists()
            pages = builder.get_wiki_pages() if has_wiki else []
            result.append({
                "name": kb_name,
                "display_name": user_kbs[kb_name].get("display_name", kb_name),
                "has_wiki": has_wiki,
                "page_count": len(pages),
            })
    
    return jsonify({"kbs": result})


@app.route("/api/wiki/build", methods=["POST"])
def wiki_build():
    """Build wiki for a specific KB."""
    from gangdan.core.wiki_builder import WikiBuilder
    
    data = request.json
    kb_name = data.get("kb_name", "")
    force = data.get("force", False)
    use_llm = data.get("use_llm", False)
    mode = data.get("mode", "auto")
    
    if not kb_name:
        return jsonify({"success": False, "error": "KB name required"})
    
    if not _find_kb_files_dir(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"})
    
    try:
        builder = WikiBuilder(kb_name, OLLAMA)
        stats = builder.generate_wiki(force=force, use_llm=use_llm, mode=mode)
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/wiki/pages")
def wiki_get_pages():
    """Get list of wiki pages for a KB."""
    from gangdan.core.wiki_builder import WikiBuilder
    
    kb_name = request.args.get("kb", "")
    if not kb_name:
        return jsonify({"success": False, "error": "KB name required"})
    
    builder = WikiBuilder(kb_name)
    pages = builder.get_wiki_pages()
    return jsonify({"pages": pages, "kb": kb_name})


@app.route("/api/wiki/page")
def wiki_get_page():
    """Get content of a specific wiki page."""
    from gangdan.core.wiki_builder import WikiBuilder
    
    kb_name = request.args.get("kb", "")
    page_path = request.args.get("path", "")
    
    if not kb_name or not page_path:
        return jsonify({"success": False, "error": "KB name and page path required"})
    
    builder = WikiBuilder(kb_name)
    content = builder.get_wiki_page(page_path)
    
    if content is None:
        return jsonify({"success": False, "error": "Page not found"}), 404
    
    return jsonify({"content": content, "kb": kb_name, "path": page_path})


@app.route("/api/wiki/build-cross", methods=["POST"])
def wiki_build_cross():
    """Build cross-KB wiki from multiple selected KBs."""
    from gangdan.core.wiki_builder import CrossWikiBuilder
    
    data = request.json
    kb_names = data.get("kb_names", [])
    force = data.get("force", False)
    
    if not kb_names or len(kb_names) < 2:
        return jsonify({"success": False, "error": "Select at least 2 KBs for cross-KB wiki"})
    
    # Validate KBs exist
    for kb_name in kb_names:
        kb_dir_result = _resolve_kb_dir(kb_name)
        if kb_dir_result[0] is None:
            return jsonify({"success": False, "error": f"KB '{kb_name}' not found"})
    
    try:
        builder = CrossWikiBuilder(kb_names)
        stats = builder.build(force=force)
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/wiki/cross-pages")
def wiki_cross_pages():
    """Get list of cross-KB wiki pages."""
    from gangdan.core.wiki_builder import CrossWikiBuilder
    
    kb_names = request.args.get("kbs", "").split(",")
    kb_names = [k.strip() for k in kb_names if k.strip()]
    
    if len(kb_names) < 2:
        return jsonify({"pages": [], "kbs": kb_names})
    
    builder = CrossWikiBuilder(kb_names)
    pages = builder.get_wiki_pages()
    return jsonify({"pages": pages, "kbs": kb_names})


@app.route("/api/wiki/cross-page")
def wiki_cross_page():
    """Get content of a specific cross-KB wiki page."""
    from gangdan.core.wiki_builder import CrossWikiBuilder
    
    kb_names = request.args.get("kbs", "").split(",")
    kb_names = [k.strip() for k in kb_names if k.strip()]
    page_path = request.args.get("path", "")
    
    if len(kb_names) < 2 or not page_path:
        return jsonify({"success": False, "error": "KB names and page path required"})
    
    builder = CrossWikiBuilder(kb_names)
    content = builder.get_wiki_page(page_path)
    
    if content is None:
        return jsonify({"success": False, "error": "Page not found"}), 404
    
    return jsonify({"content": content, "kbs": kb_names, "path": page_path})


@app.route("/api/wiki/status")
def wiki_status():
    """Get wiki status including dirty pages needing updates."""
    from gangdan.core.wiki_builder import WikiBuilder
    
    kb_name = request.args.get("kb", "")
    if not kb_name:
        return jsonify({"success": False, "error": "KB name required"})
    
    if not _find_kb_files_dir(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"})
    
    try:
        builder = WikiBuilder(kb_name)
        status = builder.get_wiki_status()
        return jsonify({"success": True, "status": status})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/wiki/update-dirty", methods=["POST"])
def wiki_update_dirty():
    """Update only dirty pages that need regeneration due to source changes."""
    from gangdan.core.wiki_builder import WikiBuilder
    
    data = request.json
    kb_name = data.get("kb_name", "")
    use_llm = data.get("use_llm", False)
    mode = data.get("mode", "auto")
    
    if not kb_name:
        return jsonify({"success": False, "error": "KB name required"})
    
    if not _find_kb_files_dir(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"})
    
    try:
        builder = WikiBuilder(kb_name, OLLAMA)
        result = builder.update_dirty_pages(use_llm=use_llm, mode=mode)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/wiki/regenerate-pages", methods=["POST"])
def wiki_regenerate_pages():
    """Regenerate specific wiki pages by slug."""
    from gangdan.core.wiki_builder import WikiBuilder
    
    data = request.json
    kb_name = data.get("kb_name", "")
    page_slugs = data.get("page_slugs", [])
    use_llm = data.get("use_llm", True)
    mode = data.get("mode", "auto")
    
    if not kb_name:
        return jsonify({"success": False, "error": "KB name required"})
    if not page_slugs:
        return jsonify({"success": False, "error": "page_slugs required"})
    
    if not _find_kb_files_dir(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"})
    
    try:
        builder = WikiBuilder(kb_name, OLLAMA)
        result = builder.regenerate_pages(page_slugs, use_llm=use_llm, mode=mode)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/wiki/cache/snapshots")
def wiki_cache_snapshots():
    """List all wiki snapshots for a KB."""
    from gangdan.core.wiki_builder import WikiBuilder
    
    kb_name = request.args.get("kb", "")
    if not kb_name:
        return jsonify({"success": False, "error": "KB name required"})
    
    if not _find_kb_files_dir(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"})
    
    try:
        builder = WikiBuilder(kb_name)
        snapshots = builder.cache.list_snapshots()
        return jsonify({"success": True, "snapshots": snapshots})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/wiki/cache/restore", methods=["POST"])
def wiki_cache_restore():
    """Restore wiki from a snapshot."""
    from gangdan.core.wiki_builder import WikiBuilder
    
    data = request.json
    kb_name = data.get("kb_name", "")
    snapshot_name = data.get("snapshot_name", "")
    
    if not kb_name:
        return jsonify({"success": False, "error": "KB name required"})
    if not snapshot_name:
        return jsonify({"success": False, "error": "snapshot_name required"})
    
    if not _find_kb_files_dir(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"})
    
    try:
        builder = WikiBuilder(kb_name)
        success = builder.cache.restore(snapshot_name)
        if success:
            return jsonify({"success": True, "message": f"Restored from snapshot '{snapshot_name}'"})
        else:
            return jsonify({"success": False, "error": f"Snapshot '{snapshot_name}' not found"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/wiki/cache/delete", methods=["POST"])
def wiki_cache_delete():
    """Delete a wiki snapshot."""
    from gangdan.core.wiki_builder import WikiBuilder
    
    data = request.json
    kb_name = data.get("kb_name", "")
    snapshot_name = data.get("snapshot_name", "")
    
    if not kb_name:
        return jsonify({"success": False, "error": "KB name required"})
    if not snapshot_name:
        return jsonify({"success": False, "error": "snapshot_name required"})
    
    if not _find_kb_files_dir(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"})
    
    try:
        builder = WikiBuilder(kb_name)
        success = builder.cache.delete_snapshot(snapshot_name)
        if success:
            return jsonify({"success": True, "message": f"Deleted snapshot '{snapshot_name}'"})
        else:
            return jsonify({"success": False, "error": f"Snapshot '{snapshot_name}' not found"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/wiki/cache/cleanup", methods=["POST"])
def wiki_cache_cleanup():
    """Clean up old wiki snapshots, keeping only the most recent ones."""
    from gangdan.core.wiki_builder import WikiBuilder
    
    data = request.json
    kb_name = data.get("kb_name", "")
    keep = data.get("keep", 5)
    
    if not kb_name:
        return jsonify({"success": False, "error": "KB name required"})
    
    if not _find_kb_files_dir(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"})
    
    try:
        builder = WikiBuilder(kb_name)
        before = len(builder.cache.list_snapshots())
        builder.cache.cleanup(keep=keep)
        after = len(builder.cache.list_snapshots())
        return jsonify({"success": True, "message": f"Cleaned up {before - after} old snapshots", "deleted": before - after})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/execute", methods=["POST"])
def execute_code():
    """Execute code in various languages."""
    data = request.json
    code = data.get("code", "")
    language = data.get("language", "").lower()

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[Execute] Language: {language}", file=sys.stderr)
    print(f"[Execute] Code length: {len(code)} chars", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    # Map language aliases
    lang_map = {
        "py": "python",
        "python3": "python",
        "js": "javascript",
        "node": "javascript",
        "sh": "bash",
        "shell": "bash",
    }
    language = lang_map.get(language, language)

    # Determine interpreter
    interpreters = {
        "python": ["python3", "python"],
        "javascript": ["node"],
        "bash": ["bash", "sh"],
    }

    if language not in interpreters:
        return jsonify({"error": f"Unsupported language: {language}"})

    # Find available interpreter
    interpreter = None
    for cmd in interpreters[language]:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
            interpreter = cmd
            break
        except (subprocess.SubprocessError, OSError, FileNotFoundError, TimeoutError):
            continue

    if not interpreter:
        return jsonify({"error": f"No interpreter found for {language}"})

    print(f"[Execute] Using interpreter: {interpreter}", file=sys.stderr)

    try:
        # Create temp file for code
        suffix = {"python": ".py", "javascript": ".js", "bash": ".sh"}.get(
            language, ".txt"
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
            f.write(code)
            temp_path = f.name

        # Execute with timeout
        result = subprocess.run(
            [interpreter, temp_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(DATA_DIR),
        )

        # Cleanup
        os.unlink(temp_path)

        output = result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr if output else result.stderr

        print(f"[Execute] Exit code: {result.returncode}", file=sys.stderr)
        print(f"[Execute] Output length: {len(output)} chars", file=sys.stderr)
        print(f"{'=' * 60}\n", file=sys.stderr)

        return jsonify(
            {
                "output": output,
                "exit_code": result.returncode,
                "error": None
                if result.returncode == 0
                else f"Exit code: {result.returncode}",
            }
        )

    except subprocess.TimeoutExpired:
        print(f"[Execute] Timeout after 30s", file=sys.stderr)
        return jsonify({"error": "Execution timed out (30s limit)", "output": ""})
    except Exception as e:
        print(f"[Execute] Error: {type(e).__name__}: {e}", file=sys.stderr)
        return jsonify({"error": str(e), "output": ""})


@app.route("/api/ai-command", methods=["POST"])
def ai_command():
    """Generate shell command or provide analysis using AI based on user description."""
    data = request.json
    query = data.get("query", "")
    terminal_context = data.get("terminal_context", "")
    chat_history = data.get("chat_history", [])
    force_regenerate = data.get("force_regenerate", False)
    context_status = data.get("context_status", {})
    user_lang = data.get("language", CONFIG.language)

    # Map language codes to full names for the prompt
    LANG_NAMES = {
        "zh": "Chinese (简体中文)",
        "en": "English",
        "ja": "Japanese (日本語)",
        "fr": "French (Français)",
        "ru": "Russian (Русский)",
        "de": "German (Deutsch)",
        "it": "Italian (Italiano)",
        "es": "Spanish (Español)",
        "pt": "Portuguese (Português)",
        "ko": "Korean (한국어)",
    }
    lang_name = LANG_NAMES.get(user_lang, "English")

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[AI-Command] Query: {query}", file=sys.stderr)
    print(f"[AI-Command] Language: {user_lang} ({lang_name})", file=sys.stderr)
    print(f"[AI-Command] Force regenerate: {force_regenerate}", file=sys.stderr)
    if context_status:
        print(
            f"[AI-Command] Context status: {context_status.get('reason', 'unknown')}",
            file=sys.stderr,
        )
    if terminal_context:
        print(
            f"[AI-Command] Terminal context: {len(terminal_context)} chars",
            file=sys.stderr,
        )
    if chat_history:
        print(
            f"[AI-Command] Chat history: {len(chat_history)} messages", file=sys.stderr
        )
    print(f"{'=' * 60}", file=sys.stderr)

    if not query:
        return jsonify({"error": "No query provided"})

    if not CONFIG.chat_model:
        return jsonify({"error": "No chat model configured"})

    # Build context section if terminal output is available
    context_section = ""
    if terminal_context:
        # Check for errors in terminal output
        has_error = any(
            err in terminal_context.lower()
            for err in [
                "error",
                "failed",
                "not found",
                "permission denied",
                "no such file",
                "command not found",
            ]
        )

        context_section = f"""
CURRENT TERMINAL CONTEXT (recent commands and output):
```
{terminal_context[-2000:]}
```
{"NOTE: There appear to be ERRORS in the terminal output. Consider this when generating your response." if has_error else ""}
"""

    # Build chat history context
    history_context = ""
    if chat_history:
        history_context = "\n\nPREVIOUS CONVERSATION:\n"
        for msg in chat_history[-6:]:
            role = "User" if msg.get("role") == "user" else "Assistant"
            history_context += f"{role}: {msg.get('content', '')[:300]}\n"

    # Add regeneration instruction if needed
    regen_instruction = ""
    if force_regenerate:
        reason = context_status.get("reason", "unknown")
        if reason == "stale":
            regen_instruction = "\nIMPORTANT: Previous context is outdated. Generate a FRESH command to get current information."
        elif reason == "low_relevance":
            regen_instruction = "\nIMPORTANT: Previous context doesn't match well. Generate a NEW appropriate command."
        elif reason == "no_context":
            regen_instruction = "\nNOTE: No previous execution context available. Generate an appropriate command."
        elif reason == "session_stale":
            regen_instruction = "\nIMPORTANT: Session has been idle. Generate a fresh command for current state."

    # Determine if user wants a command or analysis/summary
    analysis_keywords = [
        "explain",
        "summarize",
        "analyze",
        "what",
        "why",
        "how",
        "describe",
        "interpret",
        "解释",
        "总结",
        "分析",
        "什么",
        "为什么",
        "怎么",
        "描述",
        "整理",
        "detail",
        "verbose",
        "详细",
        "详解",
        "展开",
    ]
    needs_analysis = any(kw in query.lower() for kw in analysis_keywords)

    # Determine if user asks for detailed/verbose output
    detail_keywords = [
        "detail",
        "verbose",
        "in depth",
        "thorough",
        "comprehensive",
        "详细",
        "详解",
        "展开",
        "深入",
        "全面",
    ]
    wants_detail = any(kw in query.lower() for kw in detail_keywords)

    # Length constraint - 500 chars unless user explicitly asks for detail
    length_instruction = ""
    if not wants_detail:
        length_instruction = "\nIMPORTANT LENGTH CONSTRAINT: Keep your ENTIRE response (including explanation/analysis) under 500 characters. Be concise and to the point. Do NOT add unnecessary details or verbose explanations."

    # Create prompt for command generation or analysis
    prompt = f"""You are a Linux/Unix command line expert assistant. You can see the user's terminal context and recent execution history.
IMPORTANT: You MUST respond in {lang_name}. All explanations, analysis, and text output must be in {lang_name}.{length_instruction}
{context_section}
{history_context}
{regen_instruction}

USER REQUEST: "{query}"

Based on the user's request, determine what they need:

1. If they want to EXECUTE something (create, list, find, delete, move, run, etc.):
   Generate a shell command and respond in this exact format:
   TYPE: COMMAND
   COMMAND: <the actual shell command>
   EXPLANATION: <brief explanation of what the command does>

2. If they want to UNDERSTAND, ANALYZE, or get a SUMMARY of results:
   Provide analysis and respond in this format:
   TYPE: ANALYSIS
   RESPONSE: <your detailed analysis with markdown formatting - use tables, lists, code blocks as needed>

Important:
- For commands: Only generate safe commands (no rm -rf /, no dd, no destructive operations without confirmation)
- For analysis: Use proper Markdown formatting including tables for data, code blocks for technical content, and bullet points for lists
- Consider the terminal context when formulating your response
- If context is stale or missing, generate appropriate commands to gather fresh information
- Be concise - keep explanations brief and focused. Avoid unnecessary details unless the user explicitly asks for them."""

    try:
        messages = [{"role": "user", "content": prompt}]
        full_response = ""
        
        chat_client = get_chat_client()
        model_name = CONFIG.chat_model_name or CONFIG.chat_model
        if CONFIG.chat_provider == "ollama":
            stream_kwargs = {}
        else:
            stream_kwargs = {"max_tokens": CONFIG.chat_max_tokens}

        for chunk in chat_client.chat_stream(messages, model_name, temperature=0.3, **stream_kwargs):
            full_response += chunk

        # Parse response
        response_type = "COMMAND"
        command = ""
        explanation = ""
        analysis = ""

        for line in full_response.split("\n"):
            line_stripped = line.strip()
            if line_stripped.startswith("TYPE:"):
                response_type = line_stripped.replace("TYPE:", "").strip().upper()
            elif line_stripped.startswith("COMMAND:"):
                command = line_stripped.replace("COMMAND:", "").strip()
            elif line_stripped.startswith("EXPLANATION:"):
                explanation = line_stripped.replace("EXPLANATION:", "").strip()
            elif line_stripped.startswith("RESPONSE:"):
                # Capture everything after RESPONSE:
                idx = full_response.find("RESPONSE:")
                if idx >= 0:
                    analysis = full_response[idx + 9 :].strip()
                break

        # Fallback parsing if format wasn't followed exactly
        if response_type == "COMMAND" and not command:
            # Try to extract command from code block
            code_match = re.search(
                r"```(?:bash|sh)?\n?(.*?)\n?```", full_response, re.DOTALL
            )
            if code_match:
                command = code_match.group(1).strip()
            else:
                # Check if this should be analysis instead
                if needs_analysis or len(full_response) > 200:
                    analysis = full_response
                    response_type = "ANALYSIS"
                else:
                    # Just take the first line that looks like a command
                    for line in full_response.split("\n"):
                        line = line.strip()
                        if line and not line.startswith("#") and len(line) < 200:
                            command = line
                            break

        if not explanation and command:
            explanation = "Generated command for your request"

        print(f"[AI-Command] Response type: {response_type}", file=sys.stderr)
        if command:
            print(f"[AI-Command] Generated command: {command}", file=sys.stderr)
        if analysis:
            print(
                f"[AI-Command] Analysis length: {len(analysis)} chars", file=sys.stderr
            )
        print(f"{'=' * 60}\n", file=sys.stderr)

        if response_type == "ANALYSIS" or analysis:
            return jsonify(
                {
                    "response": analysis or full_response,
                    "command": None,
                    "explanation": None,
                }
            )
        else:
            return jsonify(
                {"command": command, "explanation": explanation, "response": None}
            )

    except Exception as e:
        print(f"[AI-Command] Error: {e}", file=sys.stderr)
        return jsonify({"error": str(e)})


@app.route("/api/ai-summarize", methods=["POST"])
def ai_summarize():
    """Summarize command execution results using AI."""
    data = request.json
    command = data.get("command", "")
    output = data.get("output", "")
    is_error = data.get("is_error", False)
    user_lang = data.get("language", CONFIG.language)

    LANG_NAMES = {
        "zh": "Chinese (简体中文)",
        "en": "English",
        "ja": "Japanese (日本語)",
        "fr": "French (Français)",
        "ru": "Russian (Русский)",
        "de": "German (Deutsch)",
        "it": "Italian (Italiano)",
        "es": "Spanish (Español)",
        "pt": "Portuguese (Português)",
        "ko": "Korean (한국어)",
    }
    lang_name = LANG_NAMES.get(user_lang, "English")

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[AI-Summarize] Command: {command}", file=sys.stderr)
    print(f"[AI-Summarize] Language: {user_lang} ({lang_name})", file=sys.stderr)
    print(f"[AI-Summarize] Output length: {len(output)} chars", file=sys.stderr)
    print(f"[AI-Summarize] Is error: {is_error}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    if not CONFIG.chat_model:
        return jsonify({"error": "No chat model configured"})

    # Create prompt for summarization
    prompt = f"""You are a system administrator assistant. Analyze and summarize the following command execution result.
IMPORTANT: You MUST respond in {lang_name}. All text output must be in {lang_name}.

COMMAND EXECUTED: `{command}`
STATUS: {"ERROR" if is_error else "SUCCESS"}

OUTPUT:
```
{output[:3000]}
```

Please provide a clear, well-formatted summary using Markdown. Keep the total response under 500 characters:

1. **Overview**: What the command did and whether it succeeded
2. **Key Findings**: Important information from the output
3. **Recommendations**: Suggested next steps (if any)

Format guidelines:
- Use tables for structured data (disk space, file sizes, process lists, etc.)
- Use code blocks for paths, commands, or technical details
- Be concise - focus on key results, not verbose explanations
- If there are errors, briefly explain what went wrong and how to fix it"""

    try:
        messages = [{"role": "user", "content": prompt}]
        full_response = ""
        
        chat_client = get_chat_client()
        model_name = CONFIG.chat_model_name or CONFIG.chat_model
        if CONFIG.chat_provider == "ollama":
            stream_kwargs = {}
        else:
            stream_kwargs = {"max_tokens": CONFIG.chat_max_tokens}

        for chunk in chat_client.chat_stream(messages, model_name, temperature=0.5, **stream_kwargs):
            full_response += chunk

        print(
            f"[AI-Summarize] Summary length: {len(full_response)} chars",
            file=sys.stderr,
        )
        print(f"{'=' * 60}\n", file=sys.stderr)

        return jsonify({"summary": full_response})

    except Exception as e:
        print(f"[AI-Summarize] Error: {e}", file=sys.stderr)
        return jsonify({"error": str(e)})


@app.route("/api/github-search", methods=["POST"])
def github_search():
    """Search GitHub for documentation repositories."""
    data = request.json
    query = data.get("query", "")
    language = data.get("language", "")

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[GitHub] Searching: {query} (lang: {language or 'any'})", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    if not query:
        return jsonify({"error": "No query provided", "results": []})

    # Build search query
    search_query = f"{query} documentation tutorial"
    if language:
        search_query += f" language:{language}"

    proxies = get_proxies()

    try:
        # Use GitHub API (no auth needed for basic search)
        url = "https://api.github.com/search/repositories"
        params = {"q": search_query, "sort": "stars", "order": "desc", "per_page": 10}
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GangDan-Dev-Assistant",
        }

        r = requests.get(
            url, params=params, headers=headers, proxies=proxies, timeout=30
        )
        r.raise_for_status()

        data = r.json()
        results = []

        for item in data.get("items", [])[:10]:
            results.append(
                {
                    "name": item["name"],
                    "full_name": item["full_name"],
                    "description": item.get("description", "")[:100],
                    "stars": item["stargazers_count"],
                    "url": item["html_url"],
                }
            )

        print(f"[GitHub] Found {len(results)} results", file=sys.stderr)
        for r in results[:3]:
            print(f"[GitHub]   - {r['name']} ({r['stars']} stars)", file=sys.stderr)
        print(f"{'=' * 60}\n", file=sys.stderr)

        return jsonify({"results": results})

    except Exception as e:
        print(f"[GitHub] Error: {e}", file=sys.stderr)
        return jsonify({"error": str(e), "results": []})


@app.route("/api/github-download", methods=["POST"])
def github_download():
    """Download README and documentation files from a GitHub repo."""
    data = request.json
    repo = data.get("repo", "")  # format: owner/repo
    name = data.get("name", repo.split("/")[-1] if repo else "github_doc")

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[GitHub-DL] Downloading from: {repo}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    if not repo:
        return jsonify({"success": False, "error": "No repo specified"})

    proxies = get_proxies()

    # Create directory
    doc_dir = DOCS_DIR / name.replace("/", "_")
    doc_dir.mkdir(parents=True, exist_ok=True)

    files_downloaded = 0

    # Files to try downloading
    doc_files = [
        "README.md",
        "readme.md",
        "README.rst",
        "CONTRIBUTING.md",
        "docs/README.md",
        "docs/index.md",
        "doc/README.md",
        "documentation/README.md",
        "TUTORIAL.md",
        "GUIDE.md",
    ]

    try:
        for doc_file in doc_files:
            url = f"https://raw.githubusercontent.com/{repo}/main/{doc_file}"
            try:
                r = requests.get(url, proxies=proxies, timeout=15)
                if r.status_code == 200:
                    filename = doc_file.replace("/", "_")
                    filepath = doc_dir / filename
                    filepath.write_text(r.text, encoding="utf-8")
                    files_downloaded += 1
                    print(f"[GitHub-DL]   OK: {doc_file}", file=sys.stderr)
            except (requests.RequestException, OSError):
                pass

            # Also try master branch
            url = f"https://raw.githubusercontent.com/{repo}/master/{doc_file}"
            try:
                r = requests.get(url, proxies=proxies, timeout=15)
                if r.status_code == 200:
                    filename = doc_file.replace("/", "_")
                    if not (doc_dir / filename).exists():
                        filepath = doc_dir / filename
                        filepath.write_text(r.text, encoding="utf-8")
                        files_downloaded += 1
                        print(f"[GitHub-DL]   OK: {doc_file} (master)", file=sys.stderr)
            except (requests.RequestException, OSError):
                pass

        print(f"[GitHub-DL] Downloaded {files_downloaded} files", file=sys.stderr)
        print(f"{'=' * 60}\n", file=sys.stderr)

        return jsonify({"success": True, "files": files_downloaded, "name": name})

    except Exception as e:
        print(f"[GitHub-DL] Error: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/export-raw-files")
def export_raw_files():
    """Export all raw document files as a zip archive."""
    if not DOCS_DIR.exists() or not any(DOCS_DIR.iterdir()):
        return jsonify({"success": False, "error": t("no_files_to_export")}), 404

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[ExportRawFiles] Exporting from: {DOCS_DIR}", file=sys.stderr)

    buffer = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(str(DOCS_DIR)):
            for fname in files:
                filepath = Path(root) / fname
                arcname = str(filepath.relative_to(DOCS_DIR))
                zf.write(str(filepath), arcname)
                file_count += 1

    if file_count == 0:
        return jsonify({"success": False, "error": t("no_files_to_export")}), 404

    buffer.seek(0)
    filename = f"gangdan_raw_files_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    print(f"[ExportRawFiles] Exported {file_count} files", file=sys.stderr)
    print(f"{'=' * 60}\n", file=sys.stderr)

    return Response(
        buffer.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/import-raw-files", methods=["POST"])
def import_raw_files():
    """Import raw document files from a zip archive."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.endswith(".zip"):
        return jsonify({"success": False, "error": "File must be a .zip archive"}), 400

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[ImportRawFiles] Importing from: {file.filename}", file=sys.stderr)

    try:
        with zipfile.ZipFile(io.BytesIO(file.read()), "r") as zf:
            # Security: prevent path traversal
            for name in zf.namelist():
                if ".." in name or name.startswith("/") or name.startswith("\\"):
                    return jsonify(
                        {"success": False, "error": f"Invalid path in archive: {name}"}
                    ), 400

            DOCS_DIR.mkdir(parents=True, exist_ok=True)
            zf.extractall(str(DOCS_DIR))

            # Update user_kbs manifest for any user_ directories found
            seen_user_dirs = set()
            for name in zf.namelist():
                parts = Path(name).parts
                if parts and parts[0].startswith("user_"):
                    seen_user_dirs.add(parts[0])

            existing_kbs = load_user_kbs()
            for internal_name in seen_user_dirs:
                if internal_name not in existing_kbs:
                    dir_path = DOCS_DIR / internal_name
                    file_count = len(
                        list(dir_path.glob("*.md")) + list(dir_path.glob("*.txt"))
                    )
                    save_user_kb(internal_name, internal_name, file_count)

            total = len([n for n in zf.namelist() if not n.endswith("/")])
            print(f"[ImportRawFiles] Imported {total} files", file=sys.stderr)
            print(f"{'=' * 60}\n", file=sys.stderr)

            return jsonify({"success": True, "message": f"Imported {total} files"})
    except zipfile.BadZipFile:
        return jsonify({"success": False, "error": "Invalid zip file"}), 400
    except Exception as e:
        print(f"[ImportRawFiles] Error: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/export-kb")
def export_kb():
    """Export knowledge base (ChromaDB collections) as a zip archive."""
    if not CHROMA or not CHROMA.is_available:
        return jsonify({"success": False, "error": "Vector DB not available"}), 500

    collections = CHROMA.list_collections()
    if not collections:
        return jsonify({"success": False, "error": t("no_kb_to_export")}), 404

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[ExportKB] Exporting {len(collections)} collections", file=sys.stderr)

    buffer = io.BytesIO()
    exported = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for coll_name in collections:
            try:
                data = CHROMA.get_documents(
                    coll_name, limit=0, include=["documents", "metadatas", "embeddings"]
                )

                raw_embeddings = data.get("embeddings") or []
                embeddings_list = []
                for emb in raw_embeddings:
                    if hasattr(emb, "tolist"):
                        embeddings_list.append(emb.tolist())
                    elif isinstance(emb, list):
                        embeddings_list.append(emb)
                    else:
                        embeddings_list.append(list(emb))

                coll_data = {
                    "name": coll_name,
                    "ids": data.get("ids", []),
                    "documents": data.get("documents", []),
                    "metadatas": data.get("metadatas", []),
                    "embeddings": embeddings_list,
                }

                zf.writestr(
                    f"collections/{coll_name}.json",
                    json.dumps(coll_data, ensure_ascii=False),
                )
                exported += 1
                print(
                    f"[ExportKB]   {coll_name}: {len(coll_data['ids'])} documents",
                    file=sys.stderr,
                )
            except Exception as e:
                print(
                    f"[ExportKB]   Error exporting '{coll_name}': {e}", file=sys.stderr
                )

        # Include user_kbs.json manifest
        if USER_KBS_FILE.exists():
            zf.write(str(USER_KBS_FILE), "user_kbs.json")

    buffer.seek(0)
    filename = f"gangdan_kb_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    print(f"[ExportKB] Exported {exported} collections", file=sys.stderr)
    print(f"{'=' * 60}\n", file=sys.stderr)

    return Response(
        buffer.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/import-kb", methods=["POST"])
def import_kb():
    """Import knowledge base from a zip archive."""
    if not CHROMA or not CHROMA.is_available:
        return jsonify({"success": False, "error": "Vector DB not available"}), 500

    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.endswith(".zip"):
        return jsonify({"success": False, "error": "File must be a .zip archive"}), 400

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[ImportKB] Importing from: {file.filename}", file=sys.stderr)

    try:
        imported = 0
        with zipfile.ZipFile(io.BytesIO(file.read()), "r") as zf:
            for name in zf.namelist():
                if name.startswith("collections/") and name.endswith(".json"):
                    coll_data = json.loads(zf.read(name).decode("utf-8"))
                    coll_name = coll_data.get("name", "")

                    if not coll_name:
                        continue

                    ids = coll_data.get("ids", [])
                    documents = coll_data.get("documents", [])
                    metadatas = coll_data.get("metadatas", [])
                    embeddings = coll_data.get("embeddings", [])

                    if not (ids and documents and embeddings):
                        print(
                            f"[ImportKB]   Skipped '{coll_name}': missing data",
                            file=sys.stderr,
                        )
                        continue

                    # Delete existing collection if present
                    try:
                        CHROMA.delete_collection(coll_name)
                    except Exception:
                        pass

                    # Recreate collection and add data in batches
                    batch_size = 5000
                    for start in range(0, len(ids), batch_size):
                        end = start + batch_size
                        CHROMA.add_documents(
                            coll_name,
                            documents[start:end],
                            embeddings[start:end],
                            metadatas[start:end],
                            ids[start:end],
                        )

                    imported += 1
                    print(
                        f"[ImportKB]   {coll_name}: {len(ids)} documents restored",
                        file=sys.stderr,
                    )

                elif name == "user_kbs.json":
                    imported_kbs = json.loads(zf.read(name).decode("utf-8"))
                    existing_kbs = load_user_kbs()
                    existing_kbs.update(imported_kbs)
                    DATA_DIR.mkdir(parents=True, exist_ok=True)
                    USER_KBS_FILE.write_text(
                        json.dumps(existing_kbs, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    print(
                        f"[ImportKB]   Restored user_kbs.json ({len(imported_kbs)} entries)",
                        file=sys.stderr,
                    )

        print(f"[ImportKB] Imported {imported} collections", file=sys.stderr)
        print(f"{'=' * 60}\n", file=sys.stderr)

        return jsonify({"success": True, "message": f"Imported {imported} collections"})
    except zipfile.BadZipFile:
        return jsonify({"success": False, "error": "Invalid zip file"}), 400
    except Exception as e:
        print(f"[ImportKB] Error: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/system/stats")
def system_stats():
    """Get system statistics including memory, context, and document counts."""
    import psutil

    stats = {
        "success": True,
        "context_tokens": 0,
        "max_context_tokens": CONFIG.max_context_tokens,
        "memory_mb": 0,
        "total_docs": 0,
        "kb_count": 0,
        "collection_stats": {},
    }

    try:
        process = psutil.Process(os.getpid())
        stats["memory_mb"] = round(process.memory_info().rss / 1024 / 1024, 1)
    except Exception:
        pass

    try:
        if CHROMA and CHROMA.is_available:
            coll_stats = CHROMA.get_stats()
            stats["collection_stats"] = coll_stats
            stats["total_docs"] = sum(coll_stats.values())
            stats["kb_count"] = len(coll_stats)
    except Exception:
        pass

    try:
        stats["context_tokens"] = min(
            stats["total_docs"] * 100,
            CONFIG.max_context_tokens,
        )
    except Exception:
        pass

    return jsonify(stats)


@app.route("/api/kb/detailed-stats")
def kb_detailed_stats():
    """Get detailed statistics about knowledge bases including year distribution."""
    import re
    from collections import Counter

    stats = {
        "success": True,
        "knowledge_bases": [],
        "total_documents": 0,
        "total_kbs": 0,
        "year_distribution": {},
        "file_types": {},
        "languages": {},
    }

    try:
        kb_list = []
        if CHROMA and CHROMA.is_available:
            collections = CHROMA.list_collections()
            user_kbs = load_user_kbs()

            year_pattern = re.compile(r"\b(19\d{2}|20\d{2})\b")
            all_years = []
            all_file_types = []
            all_languages = []

            for coll_name in collections:
                try:
                    coll = CHROMA.client.get_collection(coll_name)
                    doc_count = coll.count()
                    results = coll.get(limit=1000, include=["documents", "metadatas"])
                    docs = []
                    for i, doc in enumerate(results.get("documents", [])):
                        docs.append(
                            {
                                "document": doc,
                                "metadata": results.get("metadatas", [{}])[i]
                                if i < len(results.get("metadatas", []))
                                else {},
                            }
                        )

                    kb_info = {
                        "name": coll_name,
                        "display_name": user_kbs.get(coll_name, {}).get(
                            "display_name", coll_name
                        ),
                        "document_count": doc_count,
                        "languages": user_kbs.get(coll_name, {}).get("languages", []),
                    }

                    years_in_kb = []
                    file_types_in_kb = Counter()

                    if docs:
                        for doc in docs:
                            metadata = doc.get("metadata", {})
                            source = metadata.get("source", metadata.get("file", ""))

                            if source:
                                ext = Path(source).suffix.lower()
                                if ext:
                                    file_types_in_kb[ext] += 1
                                    all_file_types.append(ext)

                            content = doc.get("document", "") or doc.get("content", "")
                            if content:
                                found_years = year_pattern.findall(content)
                                years_in_kb.extend(found_years)
                                all_years.extend(found_years)

                    kb_info["year_distribution"] = dict(Counter(years_in_kb))
                    kb_info["file_types"] = dict(file_types_in_kb)

                    if kb_info.get("languages"):
                        all_languages.extend(kb_info["languages"])

                    kb_list.append(kb_info)

                except Exception as e:
                    print(f"[KB Stats] Error for {coll_name}: {e}", file=sys.stderr)

            stats["knowledge_bases"] = kb_list
            stats["total_documents"] = sum(
                kb.get("document_count", 0) for kb in kb_list
            )
            stats["total_kbs"] = len(kb_list)
            stats["year_distribution"] = dict(Counter(all_years))
            stats["file_types"] = dict(Counter(all_file_types))
            stats["languages"] = dict(Counter(all_languages))

    except Exception as e:
        print(f"[KB Stats] Error: {e}", file=sys.stderr)
        stats["error"] = str(e)

    return jsonify(stats)


def get_kb_summary_text():
    """Get a human-readable summary of knowledge base status."""
    import re
    from collections import Counter

    summary_parts = []

    try:
        if not CHROMA or not CHROMA.is_available:
            return "知识库系统未初始化"

        collections = CHROMA.list_collections()
        user_kbs = load_user_kbs()

        if not collections:
            return "当前没有任何知识库"

        year_pattern = re.compile(r"\b(19\d{2}|20\d{2})\b")
        total_docs = 0
        all_years = []
        kb_summaries = []

        for coll_name in collections:
            try:
                coll = CHROMA.client.get_collection(coll_name)
                doc_count = coll.count()
                total_docs += doc_count

                display_name = user_kbs.get(coll_name, {}).get(
                    "display_name", coll_name
                )
                languages = user_kbs.get(coll_name, {}).get("languages", [])

                years_in_kb = []

                try:
                    results = coll.get(limit=500, include=["documents"])
                    docs = results.get("documents", [])

                    if docs:
                        for content in docs:
                            if content:
                                found_years = year_pattern.findall(content)
                                years_in_kb.extend(found_years)
                                all_years.extend(found_years)
                except Exception as e:
                    print(
                        f"[KB Summary] Error getting docs for {coll_name}: {e}",
                        file=sys.stderr,
                    )

                kb_summaries.append(
                    {
                        "name": display_name,
                        "count": doc_count,
                        "years": Counter(years_in_kb),
                        "languages": languages,
                    }
                )

            except Exception as e:
                print(f"[KB Summary] Error for {coll_name}: {e}", file=sys.stderr)

        lines = [f"## 知识库概况\n"]
        lines.append(
            f"共有 **{len(collections)}** 个知识库，总计 **{total_docs}** 篇文献。\n"
        )

        for kb in kb_summaries:
            lang_str = f" [{', '.join(kb['languages'])}]" if kb["languages"] else ""
            lines.append(f"- **{kb['name']}**{lang_str}: {kb['count']} 篇文献")
            if kb["years"]:
                top_years = kb["years"].most_common(5)
                year_str = ", ".join([f"{y}({c})" for y, c in top_years])
                lines.append(f"  - 主要年份: {year_str}")

        if all_years:
            year_dist = Counter(all_years)
            top_years = year_dist.most_common(10)
            lines.append(f"\n## 年代分布（前10年）")
            for year, count in top_years:
                lines.append(f"- {year}年: {count} 处提及")

        return "\n".join(lines)

    except Exception as e:
        return f"获取知识库信息时出错: {str(e)}"


@app.route("/api/system/clear-cache", methods=["POST"])
def clear_cache():
    """Clear Python cache and run garbage collection."""
    import gc

    gc.collect()

    return jsonify(
        {"success": True, "message": "Cache cleared and garbage collection completed"}
    )


@app.route("/api/terminal", methods=["POST"])
def terminal_command():
    """Execute terminal/shell commands."""
    data = request.json
    command = data.get("command", "")

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[Terminal] Command: {command}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    if not command:
        return jsonify({"error": "No command provided"})

    # Security: block dangerous commands
    dangerous_patterns = [
        r"\brm\s+-rf\s+/",
        r"\bmkfs\b",
        r"\bdd\s+if=",
        r":(){",
        r">\s*/dev/sd",
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bhalt\b",
        r"\binit\s+0",
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            print(
                f"[Terminal] Blocked dangerous command pattern: {pattern}",
                file=sys.stderr,
            )
            return jsonify(
                {
                    "error": "Command blocked for safety reasons",
                    "stdout": "",
                    "stderr": "",
                }
            )

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(DATA_DIR),
        )

        print(f"[Terminal] Exit code: {result.returncode}", file=sys.stderr)
        if result.stdout:
            print(f"[Terminal] stdout: {len(result.stdout)} chars", file=sys.stderr)
        if result.stderr:
            print(f"[Terminal] stderr: {len(result.stderr)} chars", file=sys.stderr)
        print(f"{'=' * 60}\n", file=sys.stderr)

        return jsonify(
            {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "error": None,
            }
        )

    except subprocess.TimeoutExpired:
        print(f"[Terminal] Timeout after 60s", file=sys.stderr)
        return jsonify(
            {"error": "Command timed out (60s limit)", "stdout": "", "stderr": ""}
        )
    except Exception as e:
        print(f"[Terminal] Error: {type(e).__name__}: {e}", file=sys.stderr)
        return jsonify({"error": str(e), "stdout": "", "stderr": ""})


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    try:
        print("""
╔═══════════════════════════════════════════════════════════╗
║  🚀 纲担 / GangDan - Knowledge Mgmt & Teaching              ║
║                                                           ║
║  Open in browser: http://127.0.0.1:5000                   ║
╚═══════════════════════════════════════════════════════════╝
        """)
    except UnicodeEncodeError:
        print("\n  GangDan - Knowledge Management & Teaching Assistant")
        print("  Open in browser: http://127.0.0.1:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)


@app.route("/api/kb/images/search-advanced", methods=["POST"])
def search_kb_images_advanced():
    """Advanced image search with context matching.

    Request body:
    - kb_name: Knowledge base name (required)
    - query: Search query (required)
    - search_type: "text" | "context" | "all" (default: "all")
    - limit: Max results (default: 20)

    Returns images with:
    - Matching alt text
    - Surrounded by matching text context
    - Source file information
    - Context snippets
    """
    import json
    import re

    data = request.json
    kb_name = data.get("kb_name", "").strip()
    query = data.get("query", "").strip().lower()
    search_type = data.get("search_type", "all")
    limit = int(data.get("limit", 20))

    if not kb_name or not query:
        return jsonify(
            {"success": False, "error": "KB name and query are required"}
        ), 400

    # Find KB directory
    kb_dir_result = _resolve_kb_dir(kb_name)
    kb_dir = kb_dir_result[0]
    kb_name = kb_dir_result[1]

    if kb_dir is None:
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    print(
        f"[ImageSearch] Advanced search in KB: {kb_name} for '{query}'", file=sys.stderr
    )

    results = []
    query_words = set(query.split())

    # Load image manifest
    manifest_path = kb_dir / ".image_manifest.json"
    manifests = {}
    if manifest_path.exists():
        manifests = json.loads(manifest_path.read_text())

    # Search through markdown files
    for md_file in kb_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            content_lower = content.lower()

            # Check if file contains query words
            file_match_score = sum(1 for word in query_words if word in content_lower)

            if file_match_score > 0:
                # Get images from this file
                file_images = manifests.get(md_file.name, {}).get("images", [])

                for img in file_images:
                    # Extract context around image reference in original file
                    img_path = img.get("new_path", "")
                    context_snippet = ""
                    context_before = ""
                    context_after = ""

                    # Find image in content and extract surrounding text
                    img_pattern = re.escape(img_path)
                    matches = list(re.finditer(img_pattern, content))

                    for match in matches:
                        start = max(0, match.start() - 200)
                        end = min(len(content), match.end() + 200)
                        context_snippet = content[start:end].strip()

                        # Get sentences before and after
                        lines = content[: match.start()].split("\n")
                        context_before = (
                            "\n".join(lines[-3:])
                            if len(lines) >= 3
                            else "\n".join(lines)
                        )

                        lines_after = content[match.end() :].split("\n")
                        context_after = (
                            "\n".join(lines_after[:3])
                            if len(lines_after) >= 3
                            else "\n".join(lines_after)
                        )

                        break

                    # Score this image
                    score = file_match_score

                    # Boost score if alt text matches
                    alt_text = img.get("alt_text", "").lower()
                    if query in alt_text:
                        score += 5
                    elif any(word in alt_text for word in query_words):
                        score += 3

                    # Boost score if context matches
                    if (
                        query in context_before.lower()
                        or query in context_after.lower()
                    ):
                        score += 4
                    elif any(
                        word in context_before.lower() or word in context_after.lower()
                        for word in query_words
                    ):
                        score += 2

                    # Only include if score is high enough
                    if score >= 2:
                        results.append(
                            {
                                "kb": kb_name,
                                "path": img_path,
                                "alt_text": img.get("alt_text", ""),
                                "source_file": md_file.name,
                                "name": Path(img_path).name,
                                "context_before": context_before.strip()[:300],
                                "context_after": context_after.strip()[:300],
                                "context_snippet": context_snippet[:400],
                                "relevance_score": score,
                                "match_type": "context"
                                if file_match_score > 0
                                else "alt_text",
                            }
                        )
        except Exception as e:
            print(
                f"[ImageSearch] Error processing {md_file.name}: {e}", file=sys.stderr
            )

    # Sort by score and limit
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    results = results[:limit]

    print(f"[ImageSearch] Found {len(results)} matching images", file=sys.stderr)

    return jsonify(
        {
            "success": True,
            "kb_name": kb_name,
            "query": query,
            "images": results,
            "count": len(results),
            "search_type": search_type,
        }
    )


@app.route("/api/kb/images/browser")
def browse_kb_images():
    """Browse all images in a KB with pagination.

    Query parameters:
    - name: KB name (required)
    - page: Page number (default: 1)
    - per_page: Items per page (default: 50)
    - source_file: Filter by source file (optional)
    """
    from gangdan.core.image_handler import ImageHandler

    kb_name = request.args.get("name", "").strip()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    source_file = request.args.get("source_file")

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    # Find KB directory
    kb_dir_result = _resolve_kb_dir(kb_name)
    kb_dir = kb_dir_result[0]
    kb_name = kb_dir_result[1]

    if kb_dir is None:
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    handler = ImageHandler(kb_dir)
    all_images = handler.list_images(source_file)

    # Paginate
    total = len(all_images)
    total_pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    page_images = all_images[start:end]

    return jsonify(
        {
            "success": True,
            "kb_name": kb_name,
            "images": page_images,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }
    )
