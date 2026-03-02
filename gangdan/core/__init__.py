"""
GangDan Core Module - Shared backend services for GUI and CLI.

This module extracts core functionality from app.py so both Flask (GUI)
and CLI interfaces can share the same logic without duplication.
"""

from gangdan.core.config import (
    Config,
    CONFIG,
    CONFIG_FILE,
    DATA_DIR,
    DOCS_DIR,
    CHROMA_DIR,
    USER_KBS_FILE,
    load_config,
    save_config,
    get_proxies,
    load_user_kbs,
    save_user_kb,
    delete_user_kb,
    sanitize_kb_name,
    detect_language,
    LANGUAGES,
    TRANSLATIONS,
    t,
)
from gangdan.core.ollama_client import OllamaClient
from gangdan.core.chroma_manager import ChromaManager
from gangdan.core.doc_manager import DocManager, DOC_SOURCES
from gangdan.core.web_searcher import WebSearcher
from gangdan.core.conversation import ConversationManager

__all__ = [
    # Config
    "Config",
    "CONFIG",
    "CONFIG_FILE",
    "DATA_DIR",
    "DOCS_DIR",
    "CHROMA_DIR",
    "USER_KBS_FILE",
    "load_config",
    "save_config",
    "get_proxies",
    "load_user_kbs",
    "save_user_kb",
    "delete_user_kb",
    "sanitize_kb_name",
    "detect_language",
    "LANGUAGES",
    "TRANSLATIONS",
    "t",
    # Services
    "OllamaClient",
    "ChromaManager",
    "DocManager",
    "DOC_SOURCES",
    "WebSearcher",
    "ConversationManager",
]
