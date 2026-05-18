"""Configuration management with dataclass-based settings."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .constants import (
    CHUNK_OVERLAP_DEFAULT,
    CHUNK_SIZE_DEFAULT,
    DEFAULT_CHAT_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LANGUAGE,
    DEFAULT_TOP_K,
    MAX_CONTEXT_TOKENS_DEFAULT,
    OLLAMA_DEFAULT_URL,
)
from .i18n import LANGUAGES, TRANSLATIONS, t


def _get_data_dir() -> Path:
    """Determine the data directory based on environment or install context."""
    env = os.environ.get("GANGDAN_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()

    pkg_dir = Path(__file__).resolve().parent.parent
    if "site-packages" in str(pkg_dir) or "dist-packages" in str(pkg_dir):
        return Path.home() / ".gangdan-refined"
    return Path("./data")


DATA_DIR = _get_data_dir()
DOCS_DIR = DATA_DIR / "docs"
CHROMA_DIR = DATA_DIR / "chroma"
CONFIG_FILE = DATA_DIR / "gangdan_config.json"
USER_KBS_FILE = DATA_DIR / "user_kbs.json"


@dataclass
class Config:
    """GangDan Refined configuration with sensible defaults."""

    ollama_url: str = OLLAMA_DEFAULT_URL
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    chat_model: str = DEFAULT_CHAT_MODEL
    reranker_model: str = ""
    chunk_size: int = CHUNK_SIZE_DEFAULT
    chunk_overlap: int = CHUNK_OVERLAP_DEFAULT
    top_k: int = DEFAULT_TOP_K
    max_context_tokens: int = MAX_CONTEXT_TOKENS_DEFAULT
    language: str = DEFAULT_LANGUAGE
    output_language: str = DEFAULT_LANGUAGE
    context_length: int = 4096

    proxy_mode: str = "none"
    proxy_http: str = ""
    proxy_https: str = ""

    strict_kb_mode: bool = False
    vector_db_type: str = "chroma"

    research_provider: str = "ollama"
    research_api_key: str = ""
    research_api_base_url: str = ""
    research_model: str = ""

    chat_provider: str = "ollama"
    chat_api_key: str = ""
    chat_api_base_url: str = ""
    chat_model_name: str = ""

    provider_keys: dict = field(default_factory=dict)
    provider_base_urls: dict = field(default_factory=dict)

    translate_model: str = ""

    rag_distance_threshold: float = 0.5
    chat_temperature: float = 0.7
    chat_max_tokens: int = 4096

    query_expansion_enabled: bool = False
    query_expansion_model: str = ""
    research_search_sources: str = "arxiv,semantic_scholar,crossref,openalex,dblp"
    research_max_results: int = 10
    research_search_timeout: int = 15
    semantic_scholar_api_key: str = ""
    crossref_email: str = ""
    pubmed_api_key: str = ""
    github_token: str = ""
    openalex_email: str = ""

    pdf_rename_enabled: bool = True
    pdf_convert_enabled: bool = True
    pdf_convert_engine: str = "auto"
    unpaywall_email: str = "gangdan@localhost"

    web_search_engine: str = "duckduckgo"
    serper_api_key: str = ""
    brave_api_key: str = ""

    s2_cache_ttl: int = 86400

    research_pipeline_convert: bool = True
    research_pipeline_index: bool = False
    research_pipeline_rename: bool = True

    preprint_enabled: bool = True
    preprint_platforms: str = "arxiv,biorxiv,medrxiv"
    preprint_fetch_interval_hours: int = 24
    preprint_max_results: int = 20
    preprint_auto_index: bool = False
    preprint_prefer_html: bool = True
    preprint_prefer_tex: bool = True
    preprint_search_mode: str = "keyword"
    preprint_strict_categories: bool = False
    preprint_ai_refine: bool = False
    preprint_ai_model: str = ""

    # AI auto-control settings
    auto_chunk_size: bool = True
    auto_top_k: bool = True
    auto_model_selection: bool = False
    auto_language_detect: bool = True
    auto_error_recovery: bool = True


CONFIG = Config()


def get_proxies() -> Optional[Dict[str, str]]:
    """Get proxy configuration based on proxy_mode setting."""
    if CONFIG.proxy_mode == "none":
        return None
    if CONFIG.proxy_mode == "system":
        http_proxy = os.environ.get("HTTP_PROXY", os.environ.get("http_proxy", ""))
        https_proxy = os.environ.get("HTTPS_PROXY", os.environ.get("https_proxy", ""))
        if http_proxy or https_proxy:
            return {"http": http_proxy, "https": https_proxy or http_proxy}
        return None
    if CONFIG.proxy_mode == "manual":
        if CONFIG.proxy_http or CONFIG.proxy_https:
            return {"http": CONFIG.proxy_http, "https": CONFIG.proxy_https or CONFIG.proxy_http}
        return None
    return None


def load_config() -> None:
    """Load configuration from disk into the global CONFIG object."""
    global CONFIG
    if not CONFIG_FILE.exists():
        return
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        for field_info in dataclasses.fields(CONFIG):
            if field_info.name in data:
                setattr(CONFIG, field_info.name, data[field_info.name])
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Config] Error loading config, using defaults: {e}")


def save_config() -> None:
    """Save the global CONFIG object to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config_data = dataclasses.asdict(CONFIG)
    CONFIG_FILE.write_text(
        json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_user_kbs() -> Dict:
    """Load user-created knowledge base manifest."""
    if USER_KBS_FILE.exists():
        try:
            return json.loads(USER_KBS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_user_kb(
    internal_name: str,
    display_name: str,
    file_count: int,
    languages: Optional[List[str]] = None,
    output_word_limit: Optional[int] = None,
) -> None:
    """Add or update a user KB entry in the manifest."""
    kbs = load_user_kbs()
    entry: Dict = {
        "display_name": display_name,
        "created": datetime.now().isoformat(),
        "file_count": file_count,
        "languages": languages or [],
    }
    if output_word_limit is not None:
        entry["output_word_limit"] = output_word_limit
    kbs[internal_name] = entry
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USER_KBS_FILE.write_text(
        json.dumps(kbs, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def delete_user_kb(internal_name: str) -> None:
    """Remove a user KB entry from the manifest."""
    kbs = load_user_kbs()
    kbs.pop(internal_name, None)
    USER_KBS_FILE.write_text(
        json.dumps(kbs, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def sanitize_kb_name(name: str) -> str:
    """Sanitize user-provided KB name to a safe internal name with user_ prefix."""
    safe = re.sub(r"[^a-zA-Z0-9\s-]", "", name.strip()).strip()
    safe = re.sub(r"[\s-]+", "_", safe).lower()
    if not safe or len(safe) < 3:
        name_hash = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
        safe = f"kb_{name_hash}"
    return f"user_{safe}"


def detect_language(text: str) -> str:
    """Detect language using Unicode character ranges.

    Parameters
    ----------
    text : str
        Text sample for language detection.

    Returns
    -------
    str
        ISO 639-1 language code, or 'unknown' if unclear.
    """
    if not text:
        return "unknown"

    sample = text[:500]
    total = len(sample)
    if total == 0:
        return "unknown"

    cjk = sum(1 for c in sample if "\u4e00" <= c <= "\u9fff")
    hiragana = sum(1 for c in sample if "\u3040" <= c <= "\u309f")
    katakana = sum(1 for c in sample if "\u30a0" <= c <= "\u30ff")
    hangul = sum(1 for c in sample if "\uac00" <= c <= "\ud7af")
    cyrillic = sum(1 for c in sample if "\u0400" <= c <= "\u04ff")

    threshold = 0.1
    if (hiragana + katakana) / total > threshold:
        return "ja"
    if hangul / total > threshold:
        return "ko"
    if cjk / total > threshold:
        return "zh"
    if cyrillic / total > threshold:
        return "ru"
    return "en"
