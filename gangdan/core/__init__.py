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
from gangdan.core.constants import (
    # Timeouts
    HTTP_TIMEOUT_SHORT,
    HTTP_TIMEOUT_MEDIUM,
    HTTP_TIMEOUT_LONG,
    MAX_REQUEST_RETRIES,
    # Text processing
    CHUNK_SIZE_DEFAULT,
    CHUNK_OVERLAP_DEFAULT,
    MAX_EMBED_TEXT_LENGTH,
    MAX_CONTEXT_TOKENS_DEFAULT,
    # Vector DB
    DEFAULT_TOP_K,
    TOP_K_MIN,
    TOP_K_MAX,
    # Knowledge base
    KB_NAME_MIN_LENGTH,
    KB_NAME_MAX_LENGTH,
    KB_NAME_HASH_LENGTH,
    # LLM
    DEFAULT_CHAT_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    OLLAMA_DEFAULT_URL,
    # Conversation
    DEFAULT_MAX_HISTORY,
    CONVERSATION_SAVE_INTERVAL,
    # Web search
    DEFAULT_SEARCH_RESULTS,
    # Learning
    DEFAULT_QUESTION_COUNT,
    QUESTION_COUNT_MIN,
    QUESTION_COUNT_MAX,
    # Network
    DEFAULT_WEB_PORT,
    DEFAULT_WEB_HOST,
    # UI
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    # Metadata
    APP_NAME,
    APP_VERSION,
)
from gangdan.core.errors import (
    GangDanError,
    ConfigurationError,
    ValidationError,
    APIError,
    DatabaseError,
    FileError,
    TimeoutError,
    ModelError,
    ToolResult,
    ErrorContext,
    create_error_response,
)
from gangdan.core.ollama_client import OllamaClient
from gangdan.core.chroma_manager import ChromaManager
from gangdan.core.vector_db import (
    VectorDBBase,
    VectorDBType,
    ChromaVectorDB,
    FAISSVectorDB,
    InMemoryVectorDB,
    create_vector_db,
    create_vector_db_auto,
)
from gangdan.core.doc_manager import DocManager, DOC_SOURCES
from gangdan.core.web_searcher import WebSearcher
from gangdan.core.conversation import ConversationManager
from gangdan.core.image_handler import (
    ImageHandler,
    ImageRef,
    ImageProcessResult,
    process_kb_images,
    IMAGE_EXTENSIONS,
    IMAGE_MIME_TYPES,
)

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
    # Constants
    "HTTP_TIMEOUT_SHORT",
    "HTTP_TIMEOUT_MEDIUM",
    "HTTP_TIMEOUT_LONG",
    "MAX_REQUEST_RETRIES",
    "CHUNK_SIZE_DEFAULT",
    "CHUNK_OVERLAP_DEFAULT",
    "MAX_EMBED_TEXT_LENGTH",
    "MAX_CONTEXT_TOKENS_DEFAULT",
    "DEFAULT_TOP_K",
    "TOP_K_MIN",
    "TOP_K_MAX",
    "KB_NAME_MIN_LENGTH",
    "KB_NAME_MAX_LENGTH",
    "KB_NAME_HASH_LENGTH",
    "DEFAULT_CHAT_MODEL",
    "DEFAULT_EMBEDDING_MODEL",
    "OLLAMA_DEFAULT_URL",
    "DEFAULT_MAX_HISTORY",
    "CONVERSATION_SAVE_INTERVAL",
    "DEFAULT_SEARCH_RESULTS",
    "DEFAULT_QUESTION_COUNT",
    "QUESTION_COUNT_MIN",
    "QUESTION_COUNT_MAX",
    "DEFAULT_WEB_PORT",
    "DEFAULT_WEB_HOST",
    "DEFAULT_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "APP_NAME",
    "APP_VERSION",
    # Errors
    "GangDanError",
    "ConfigurationError",
    "ValidationError",
    "APIError",
    "DatabaseError",
    "FileError",
    "TimeoutError",
    "ModelError",
    "ToolResult",
    "ErrorContext",
    "create_error_response",
    # Vector Database
    "VectorDBBase",
    "VectorDBType",
    "ChromaVectorDB",
    "FAISSVectorDB",
    "InMemoryVectorDB",
    "create_vector_db",
    "create_vector_db_auto",
    # Services (legacy)
    "OllamaClient",
    "ChromaManager",
    "DocManager",
    "DOC_SOURCES",
    "WebSearcher",
    "ConversationManager",
    # Image handling
    "ImageHandler",
    "ImageRef",
    "ImageProcessResult",
    "process_kb_images",
    "IMAGE_EXTENSIONS",
    "IMAGE_MIME_TYPES",
]
