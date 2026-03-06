"""GangDan - Offline Development Assistant powered by Ollama and ChromaDB."""

__version__ = "1.0.4"

from .api import ToolResult, chat, index_documents

__all__ = [
    "__version__",
    "ToolResult",
    "chat",
    "index_documents",
]
