"""GangDan - Offline Development Assistant powered by Ollama and ChromaDB."""

__version__ = "1.0.16"

from .api import ToolResult, chat, index_documents
from .core.errors import (
    GangDanError,
    ConfigurationError,
    ValidationError,
    APIError,
    DatabaseError,
    FileError,
    TimeoutError,
    ModelError,
)
from .core.constants import APP_NAME, APP_VERSION, DEFAULT_LANGUAGE

__all__ = [
    # Version
    "__version__",
    # App info
    "APP_NAME",
    "APP_VERSION",
    "DEFAULT_LANGUAGE",
    # API
    "ToolResult",
    "chat",
    "index_documents",
    # Errors
    "GangDanError",
    "ConfigurationError",
    "ValidationError",
    "APIError",
    "DatabaseError",
    "FileError",
    "TimeoutError",
    "ModelError",
]
