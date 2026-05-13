"""Configuration management for GangDan.

This module handles global configuration, internationalization (i18n),
and utility functions for the GangDan application.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sys
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


def _get_data_dir() -> Path:
    """Determine the data directory based on environment or install context."""
    env = os.environ.get("GANGDAN_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()

    pkg_dir = Path(__file__).resolve().parent.parent
    if "site-packages" in str(pkg_dir) or "dist-packages" in str(pkg_dir):
        return Path.home() / ".gangdan"
    return Path("./data")


DATA_DIR = _get_data_dir()
DOCS_DIR = DATA_DIR / "docs"
CHROMA_DIR = DATA_DIR / "chroma"
CONFIG_FILE = DATA_DIR / "gangdan_config.json"
USER_KBS_FILE = DATA_DIR / "user_kbs.json"


@dataclass
class Config:
    """GangDan configuration with sensible defaults.

    .. warning::
       API keys and tokens are stored in plaintext JSON at ``CONFIG_FILE``.
       Restrict file permissions (chmod 600) on shared systems.
    """

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

    # Research search configuration
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

    # PDF processing configuration
    pdf_rename_enabled: bool = True
    pdf_convert_enabled: bool = True
    pdf_convert_engine: str = "auto"
    unpaywall_email: str = "gangdan@localhost"

    # Web search engine configuration
    web_search_engine: str = "duckduckgo"
    serper_api_key: str = ""
    brave_api_key: str = ""

    # Semantic Scholar cache TTL (seconds)
    s2_cache_ttl: int = 86400

    # Research pipeline configuration
    research_pipeline_convert: bool = True
    research_pipeline_index: bool = False
    research_pipeline_rename: bool = True

    # Preprint intelligence configuration
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
            return {
                "http": CONFIG.proxy_http,
                "https": CONFIG.proxy_https or CONFIG.proxy_http,
            }
        return None

    return None


def load_config() -> None:
    """Load configuration from disk."""
    global CONFIG

    if not CONFIG_FILE.exists():
        return

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        for field_info in dataclasses.fields(CONFIG):
            if field_info.name in data:
                setattr(CONFIG, field_info.name, data[field_info.name])
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Config] Error loading config, using defaults: {e}", file=sys.stderr)


def save_config() -> None:
    """Save configuration to disk."""
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
    """Sanitize user-provided KB name to a safe internal name with user_ prefix.

    Parameters
    ----------
    name : str
        User-provided knowledge base name.

    Returns
    -------
    str
        Sanitized internal name with 'user_' prefix.

    Notes
    -----
    - Removes special characters, keeping only alphanumeric, spaces, and hyphens
    - Converts spaces and hyphens to underscores
    - Uses MD5 hash if resulting name is too short
    - Always prefixes with 'user_'
    """
    from .constants import KB_NAME_HASH_LENGTH, KB_NAME_MIN_LENGTH

    safe = re.sub(r"[^a-zA-Z0-9\s-]", "", name.strip()).strip()
    safe = re.sub(r"[\s-]+", "_", safe).lower()

    if not safe or len(safe) < KB_NAME_MIN_LENGTH:
        name_hash = hashlib.md5(name.encode("utf-8")).hexdigest()[:KB_NAME_HASH_LENGTH]
        safe = f"kb_{name_hash}"

    return f"user_{safe}"


LANGUAGES = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "fr": "Français",
    "ru": "Русский",
    "de": "Deutsch",
    "it": "Italiano",
    "es": "Español",
    "pt": "Português",
    "ko": "한국어",
}

# Language detection thresholds
LANGUAGE_THRESHOLD = 0.1
SAMPLE_SIZE = 500

# Unicode ranges for language detection
CJK_RANGE = ("\u4e00", "\u9fff")
HIRAGANA_RANGE = ("\u3040", "\u309f")
KATAKANA_RANGE = ("\u30a0", "\u30ff")
HANGUL_RANGE = ("\uac00", "\ud7af")
CYRILLIC_RANGE = ("\u0400", "\u04ff")


def detect_language(text: str) -> str:
    """Detect language using Unicode character ranges.

    Parameters
    ----------
    text : str
        Text sample for language detection.

    Returns
    -------
    str
        ISO 639-1 language code (zh, en, ja, ko, ru, fr, de, es, pt, it).
        Returns 'unknown' if unclear.

    Notes
    -----
    Analyzes first 500 characters using Unicode block detection.
    """
    if not text:
        return "unknown"

    sample = text[:SAMPLE_SIZE]
    total = len(sample)

    cjk = sum(1 for c in sample if CJK_RANGE[0] <= c <= CJK_RANGE[1])
    hiragana = sum(1 for c in sample if HIRAGANA_RANGE[0] <= c <= HIRAGANA_RANGE[1])
    katakana = sum(1 for c in sample if KATAKANA_RANGE[0] <= c <= KATAKANA_RANGE[1])
    hangul = sum(1 for c in sample if HANGUL_RANGE[0] <= c <= HANGUL_RANGE[1])
    cyrillic = sum(1 for c in sample if CYRILLIC_RANGE[0] <= c <= CYRILLIC_RANGE[1])

    if (hiragana + katakana) / total > LANGUAGE_THRESHOLD:
        return "ja"
    if hangul / total > LANGUAGE_THRESHOLD:
        return "ko"
    if cjk / total > LANGUAGE_THRESHOLD:
        return "zh"
    if cyrillic / total > LANGUAGE_THRESHOLD:
        return "ru"

    return "en"



from .i18n import TRANSLATIONS, t  # noqa: E402
