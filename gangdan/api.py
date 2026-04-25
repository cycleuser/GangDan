"""GangDan - Unified Python API.

Provides ToolResult-based wrappers for programmatic usage
and agent integration.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core.errors import ToolResult

logger = logging.getLogger(__name__)


def chat(
    message: str,
    *,
    model: str = "",
    conversation_id: Optional[str] = None,  # pylint: disable=unused-argument
    system_prompt: Optional[str] = None,
    data_dir: Optional[str] = None,
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

    Examples
    --------
    >>> result = chat("Hello!", model="llama2")
    >>> if result.success:
    ...     print(result.data)
    """
    from gangdan import __version__
    from gangdan.core.config import CONFIG, load_config
    from gangdan.core.errors import ModelError
    from gangdan.core.ollama_client import OllamaClient

    if data_dir:
        os.environ["GANGDAN_DATA_DIR"] = data_dir

    try:
        load_config()
        client = OllamaClient(base_url=CONFIG.ollama_url)

        model_name = model or CONFIG.chat_model
        if not model_name:
            models = client.get_models()
            if models:
                model_name = models[0]
            else:
                raise ModelError(
                    "No Ollama models available. Pull one with: ollama pull <model>"
                )

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        reply = client.chat_complete(messages=messages, model=model_name)

        return ToolResult(
            success=True,
            data=reply,
            metadata={
                "model": model_name,
                "version": __version__,
            },
        )
    except ModelError as e:
        logger.error("Chat model error: %s", str(e))
        return ToolResult(success=False, error=str(e))
    except Exception as e:
        logger.error("Chat error: %s", str(e))
        return ToolResult(success=False, error=str(e))


def index_documents(
    directory: str | Path,
    *,
    collection: str = "default",
    data_dir: Optional[str] = None,
) -> ToolResult:
    """Index documents from a directory into the knowledge base.

    Parameters
    ----------
    directory : str or Path
        Directory containing documents to index.
    collection : str
        Collection name in ChromaDB (default: "default").
    data_dir : str or None
        Custom data directory.

    Returns
    -------
    ToolResult
        With data containing indexing stats.

    Examples
    --------
    >>> result = index_documents("/path/to/docs")
    >>> if result.success:
    ...     print(f"Indexed {result.data['indexed']} documents")
    """
    from gangdan import __version__
    from gangdan.core.errors import ValidationError

    if data_dir:
        os.environ["GANGDAN_DATA_DIR"] = data_dir

    directory = Path(directory)
    if not directory.is_dir():
        error_msg = f"Not a directory: {directory}"
        logger.error(error_msg)
        return ToolResult(success=False, error=error_msg)

    try:
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
        logger.error("Indexing error: %s", str(e))
        return ToolResult(success=False, error=str(e))
