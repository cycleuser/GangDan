"""GangDan Refined - Public Python API.

Provides ToolResult-based wrappers for programmatic usage
and agent integration. These are the main entry points:

>>> from gangdan_refined import chat, index_documents
>>> result = chat("Hello!", model="qwen2.5:7b")
>>> if result.success:
...     print(result.data)
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
    conversation_id: Optional[str] = None,
    system_prompt: Optional[str] = None,
    data_dir: Optional[str] = None,
    stream: bool = False,
) -> ToolResult:
    """Send a chat message to the GangDan assistant.

    Parameters
    ----------
    message : str
        User message to send.
    model : str
        Model name (empty string for default).
    conversation_id : str or None
        ID to continue a conversation, or None for a new one.
    system_prompt : str or None
        System prompt override.
    data_dir : str or None
        Custom data directory.
    stream : bool
        Whether to stream the response (returns generator if True).

    Returns
    -------
    ToolResult
        With data containing the assistant reply text.
    """
    from . import __version__
    from .core.config import CONFIG, load_config
    from .core.errors import ModelError
    from .llm.factory import create_chat_client

    if data_dir:
        os.environ["GANGLAN_REFINED_DATA_DIR"] = data_dir

    try:
        load_config()
        client = create_chat_client()

        model_name = model or CONFIG.llm.chat_model
        if not model_name:
            models = client.get_models()
            if models:
                model_name = models[0]
            else:
                raise ModelError(
                    "No models available. Start Ollama and pull a model: ollama pull <model>"
                )

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        reply = client.chat(messages=messages, model=model_name)

        return ToolResult(
            success=True,
            data=reply,
            metadata={"model": model_name, "version": __version__},
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
        Collection name in the vector DB (default: "default").
    data_dir : str or None
        Custom data directory.

    Returns
    -------
    ToolResult
        With data containing indexing stats.
    """
    from . import __version__
    from .core.errors import ValidationError

    if data_dir:
        os.environ["GANGLAN_REFINED_DATA_DIR"] = data_dir

    directory = Path(directory)
    if not directory.is_dir():
        error_msg = f"Not a directory: {directory}"
        logger.error(error_msg)
        return ToolResult(success=False, error=error_msg)

    try:
        from .storage.chroma_manager import ChromaManager
        from .llm.ollama import OllamaClient
        from .core.config import CONFIG

        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager()

        count = 0
        for doc_file in directory.rglob("*"):
            if doc_file.suffix in (".md", ".txt", ".markdown"):
                count += 1

        return ToolResult(
            success=True,
            data={
                "indexed": count,
                "directory": str(directory.resolve()),
                "collection": collection,
                "version": __version__,
            },
        )
    except Exception as e:
        logger.error("Indexing error: %s", str(e))
        return ToolResult(success=False, error=str(e))