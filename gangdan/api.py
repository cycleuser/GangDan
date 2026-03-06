"""
GangDan - Unified Python API.

Provides ToolResult-based wrappers for programmatic usage
and agent integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ToolResult:
    """Standardised return type for all GangDan API functions."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
        }


def chat(
    message: str,
    *,
    model: str = "",
    conversation_id: str | None = None,
    system_prompt: str | None = None,
    data_dir: str | None = None,
) -> ToolResult:
    """Send a chat message to the GangDan assistant.

    Parameters
    ----------
    message : str
        User message to send.
    model : str
        Ollama model name (empty string for default).
    conversation_id : str or None
        ID to continue a conversation, or None for a new one.
    system_prompt : str or None
        System prompt override.
    data_dir : str or None
        Custom data directory.

    Returns
    -------
    ToolResult
        With data containing the assistant reply text.
    """
    import os

    if data_dir:
        os.environ["GANGDAN_DATA_DIR"] = data_dir

    try:
        from gangdan import __version__
        from gangdan.core.config import load_config, CONFIG
        from gangdan.core.ollama_client import OllamaClient

        load_config()
        client = OllamaClient(
            base_url=CONFIG.ollama_url,
        )

        model_name = model or CONFIG.chat_model
        if not model_name:
            # Try to pick the first available model
            models = client.list_models()
            if models:
                model_name = models[0]
            else:
                return ToolResult(
                    success=False,
                    error="No Ollama models available. Pull one with: ollama pull <model>",
                )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        reply = client.chat(model=model_name, messages=messages)

        return ToolResult(
            success=True,
            data=reply,
            metadata={
                "model": model_name,
                "version": __version__,
            },
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def index_documents(
    directory: str | Path,
    *,
    collection: str = "default",
    data_dir: str | None = None,
) -> ToolResult:
    """Index documents from a directory into the knowledge base.

    Parameters
    ----------
    directory : str or Path
        Directory containing documents to index.
    collection : str
        Collection name in ChromaDB.
    data_dir : str or None
        Custom data directory.

    Returns
    -------
    ToolResult
        With data containing indexing stats.
    """
    import os

    if data_dir:
        os.environ["GANGDAN_DATA_DIR"] = data_dir

    directory = Path(directory)
    if not directory.is_dir():
        return ToolResult(success=False, error=f"Not a directory: {directory}")

    try:
        from gangdan import __version__
        from gangdan.core.knowledge_base import KnowledgeBase

        kb = KnowledgeBase(collection_name=collection)
        count = kb.index_directory(str(directory))

        return ToolResult(
            success=True,
            data={"indexed": count},
            metadata={
                "directory": str(directory.resolve()),
                "collection": collection,
                "version": __version__,
            },
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))
