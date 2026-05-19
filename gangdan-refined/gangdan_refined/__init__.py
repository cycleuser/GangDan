"""GangDan Refined - Modular LLM-powered knowledge management and teaching assistant.

Architecture:
    core/       - Foundation: config, constants, errors, i18n (zero business deps)
    llm/        - LLM abstraction: unified client for Ollama/OpenAI/Anthropic/etc
    storage/    - Data persistence: vector DB, KB manager, conversation
    search/     - Search engines: web, academic, adaptive, query expansion
    document/   - Document processing: PDF conversion, download, rename, images
    research/   - Research pipeline: search -> download -> convert -> index
    learning/   - Learning module: questions, guided, exam, research, lecture
    web/        - Flask web interface with thin route blueprints
    cli_app/    - CLI REPL interface
"""

__version__ = "2.0.0"

from .core.errors import (
    GangDanError,
    ConfigurationError,
    ValidationError,
    APIError,
    DatabaseError,
    FileError,
    TimeoutError,
    ModelError,
    ToolResult,
)

from .core.config import CONFIG
from .core.constants import APP_NAME, APP_VERSION, DEFAULT_LANGUAGE

from .api import chat, index_documents

__all__ = [
    "__version__",
    "APP_NAME",
    "APP_VERSION",
    "DEFAULT_LANGUAGE",
    "ToolResult",
    "chat",
    "index_documents",
    "GangDanError",
    "ConfigurationError",
    "ValidationError",
    "APIError",
    "DatabaseError",
    "FileError",
    "TimeoutError",
    "ModelError",
]