"""Configuration management for GangDan Refined.

Configuration is split into logical groups:
- LLMConfig: LLM provider settings
- StorageConfig: Vector DB and KB settings
- SearchConfig: Web and academic search settings
- DocumentConfig: PDF/conversion settings
- PreprintConfig: Preprint intelligence settings
- ProxyConfig: Network proxy settings

The global CONFIG object consolidates all groups and persists to JSON.
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
    env = os.environ.get("GANGLAN_REFINED_DATA_DIR") or os.environ.get("GANGDAN_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    pkg_dir = Path(__file__).resolve().parent.parent.parent
    if "site-packages" in str(pkg_dir) or "dist-packages" in str(pkg_dir):
        return Path.home() / ".gangdan-refined"
    return Path("./data")


DATA_DIR = _get_data_dir()
DOCS_DIR = DATA_DIR / "docs"
CHROMA_DIR = DATA_DIR / "chroma"
CONFIG_FILE = DATA_DIR / "gangdan_refined_config.json"
USER_KBS_FILE = DATA_DIR / "user_kbs.json"


@dataclass
class ProxyConfig:
    """Network proxy configuration."""
    mode: str = "none"
    http: str = ""
    https: str = ""

    def get_proxies(self) -> Optional[Dict[str, str]]:
        if self.mode == "none":
            return None
        if self.mode == "system":
            http_proxy = os.environ.get("HTTP_PROXY", os.environ.get("http_proxy", ""))
            https_proxy = os.environ.get("HTTPS_PROXY", os.environ.get("https_proxy", ""))
            if http_proxy or https_proxy:
                return {"http": http_proxy, "https": https_proxy or http_proxy}
            return None
        if self.mode == "manual":
            if self.http or self.https:
                return {"http": self.http, "https": self.https or self.http}
            return None
        return None


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    ollama_url: str = OLLAMA_DEFAULT_URL
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    chat_model: str = DEFAULT_CHAT_MODEL
    reranker_model: str = ""
    context_length: int = 4096

    chat_provider: str = "ollama"
    chat_api_key: str = ""
    chat_api_base_url: str = ""
    chat_model_name: str = ""
    chat_temperature: float = 0.7
    chat_max_tokens: int = 4096

    research_provider: str = "ollama"
    research_api_key: str = ""
    research_api_base_url: str = ""
    research_model: str = ""

    translate_model: str = ""
    provider_keys: dict = field(default_factory=dict)
    provider_base_urls: dict = field(default_factory=dict)


@dataclass
class StorageConfig:
    """Vector database and knowledge base configuration."""
    chunk_size: int = CHUNK_SIZE_DEFAULT
    chunk_overlap: int = CHUNK_OVERLAP_DEFAULT
    top_k: int = DEFAULT_TOP_K
    max_context_tokens: int = MAX_CONTEXT_TOKENS_DEFAULT
    vector_db_type: str = "chroma"
    rag_distance_threshold: float = 0.5
    strict_kb_mode: bool = False


@dataclass
class SearchConfig:
    """Web and academic search configuration."""
    web_search_engine: str = "duckduckgo"
    serper_api_key: str = ""
    brave_api_key: str = ""
    s2_cache_ttl: int = 86400

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


@dataclass
class DocumentConfig:
    """PDF and document processing configuration."""
    pdf_rename_enabled: bool = True
    pdf_convert_enabled: bool = True
    pdf_convert_engine: str = "auto"
    unpaywall_email: str = "gangdan@localhost"


@dataclass
class PreprintConfig:
    """Preprint intelligence configuration."""
    enabled: bool = True
    platforms: str = "arxiv,biorxiv,medrxiv"
    fetch_interval_hours: int = 24
    max_results: int = 20
    auto_index: bool = False
    prefer_html: bool = True
    prefer_tex: bool = True
    search_mode: str = "keyword"
    strict_categories: bool = False
    ai_refine: bool = False
    ai_model: str = ""


@dataclass
class ResearchConfig:
    """Research pipeline configuration."""
    pipeline_convert: bool = True
    pipeline_index: bool = False
    pipeline_rename: bool = True


@dataclass
class AdaptiveConfig:
    """AI auto-control configuration."""
    auto_chunk_size: bool = True
    auto_top_k: bool = True
    auto_model_selection: bool = True
    auto_language_detect: bool = True
    auto_error_recovery: bool = True


@dataclass
class UIConfig:
    """Language and display configuration."""
    language: str = DEFAULT_LANGUAGE
    output_language: str = DEFAULT_LANGUAGE


@dataclass
class Config:
    """Consolidated configuration combining all groups.

    Use ``Config.llm``, ``Config.storage``, etc. to access groups.
    Top-level convenience attributes are also available for backwards compatibility.
    """

    # Grouped configs
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    document: DocumentConfig = field(default_factory=DocumentConfig)
    preprint: PreprintConfig = field(default_factory=PreprintConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)
    adaptive: AdaptiveConfig = field(default_factory=AdaptiveConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    # Convenience aliases (redirect to grouped configs)
    @property
    def ollama_url(self) -> str:
        return self.llm.ollama_url

    @ollama_url.setter
    def ollama_url(self, value: str):
        self.llm.ollama_url = value

    @property
    def chat_model(self) -> str:
        return self.llm.chat_model

    @chat_model.setter
    def chat_model(self, value: str):
        self.llm.chat_model = value

    @property
    def embedding_model(self) -> str:
        return self.llm.embedding_model

    @embedding_model.setter
    def embedding_model(self, value: str):
        self.llm.embedding_model = value

    @property
    def chunk_size(self) -> int:
        return self.storage.chunk_size

    @chunk_size.setter
    def chunk_size(self, value: int):
        self.storage.chunk_size = value

    @property
    def top_k(self) -> int:
        return self.storage.top_k

    @top_k.setter
    def top_k(self, value: int):
        self.storage.top_k = value

    @property
    def language(self) -> str:
        return self.ui.language

    @language.setter
    def language(self, value: str):
        self.ui.language = value

    @property
    def web_search_engine(self) -> str:
        return self.search.web_search_engine

    @web_search_engine.setter
    def web_search_engine(self, value: str):
        self.search.web_search_engine = value


CONFIG = Config()


def load_config() -> None:
    """Load configuration from disk."""
    global CONFIG
    if not CONFIG_FILE.exists():
        return
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        flat = _flatten_config(data)
        for field_info in dataclasses.fields(CONFIG):
            name = field_info.name
            if name in flat:
                setattr(CONFIG, name, flat[name])
            elif name in data:
                subgroup_data = data[name]
                if isinstance(subgroup_data, dict):
                    subgroup_obj = getattr(CONFIG, name)
                    for sub_field in dataclasses.fields(subgroup_obj):
                        if sub_field.name in subgroup_data:
                            setattr(subgroup_obj, sub_field.name, subgroup_data[sub_field.name])
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Config] Error loading config, using defaults: {e}", file=sys.stderr)


def save_config() -> None:
    """Save configuration to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config_data = _serialize_config(CONFIG)
    CONFIG_FILE.write_text(
        json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _flatten_config(data: dict) -> dict:
    """Flatten grouped config data to top-level keys for backwards compatibility."""
    flat = {}
    for key, value in data.items():
        if isinstance(value, dict) and key in (
            "proxy", "llm", "storage", "search", "document",
            "preprint", "research", "adaptive", "ui",
        ):
            for sub_key, sub_value in value.items():
                flat[sub_key] = sub_value
        else:
            flat[key] = value
    return flat


def _serialize_config(config: Config) -> dict:
    """Serialize config preserving grouped structure."""
    result = {}
    for field_info in dataclasses.fields(config):
        name = field_info.name
        value = getattr(config, name)
        if dataclasses.is_dataclass(value):
            result[name] = dataclasses.asdict(value)
        else:
            result[name] = value
    return result


def get_proxies() -> Optional[Dict[str, str]]:
    """Get proxy configuration."""
    return CONFIG.proxy.get_proxies()


# --- Knowledge Base Manifest ---

def load_user_kbs() -> Dict:
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
    kbs = load_user_kbs()
    kbs.pop(internal_name, None)
    USER_KBS_FILE.write_text(
        json.dumps(kbs, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def sanitize_kb_name(name: str) -> str:
    from .constants import KB_NAME_HASH_LENGTH, KB_NAME_MIN_LENGTH
    safe = re.sub(r"[^a-zA-Z0-9\s-]", "", name.strip()).strip()
    safe = re.sub(r"[\s-]+", "_", safe).lower()
    if not safe or len(safe) < KB_NAME_MIN_LENGTH:
        name_hash = hashlib.md5(name.encode("utf-8")).hexdigest()[:KB_NAME_HASH_LENGTH]
        safe = f"kb_{name_hash}"
    return f"user_{safe}"


# --- Language Detection ---

LANGUAGE_THRESHOLD = 0.1
SAMPLE_SIZE = 500

CJK_RANGE = ("\u4e00", "\u9fff")
HIRAGANA_RANGE = ("\u3040", "\u309f")
KATAKANA_RANGE = ("\u30a0", "\u30ff")
HANGUL_RANGE = ("\uac00", "\ud7af")
CYRILLIC_RANGE = ("\u0400", "\u04ff")

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


def detect_language(text: str) -> str:
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