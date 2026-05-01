"""
GangDan - OpenAI function-calling tool definitions.

Provides TOOLS list and dispatch() for LLM agent integration.
"""

from __future__ import annotations

import json
from typing import Any

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "gangdan_chat",
            "description": (
                "Send a message to the GangDan offline development assistant "
                "powered by Ollama. Returns the assistant's reply."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The user message to send.",
                    },
                    "model": {
                        "type": "string",
                        "description": "Ollama model name (empty for default).",
                        "default": "",
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "System prompt override.",
                    },
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gangdan_index_documents",
            "description": (
                "Index documents from a directory into GangDan's ChromaDB "
                "knowledge base for retrieval-augmented generation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Path to directory containing documents to index.",
                    },
                    "collection": {
                        "type": "string",
                        "description": "ChromaDB collection name.",
                        "default": "default",
                    },
                },
                "required": ["directory"],
            },
        },
    },
]


def dispatch(name: str, arguments: dict[str, Any] | str) -> dict:
    """Dispatch a tool call to the appropriate API function."""
    if isinstance(arguments, str):
        arguments = json.loads(arguments)

    if name == "gangdan_chat":
        from .api import chat

        result = chat(**arguments)
        return result.to_dict()

    if name == "gangdan_index_documents":
        from .api import index_documents

        result = index_documents(**arguments)
        return result.to_dict()

    raise ValueError(f"Unknown tool: {name}")
