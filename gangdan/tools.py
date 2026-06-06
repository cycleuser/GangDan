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
    {
        "type": "function",
        "function": {
            "name": "gangdan_memory_remember",
            "description": (
                "Save a fact, preference, or research finding to persistent memory. "
                "The memory will be loaded across sessions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Content to remember (markdown supported).",
                    },
                    "memory_type": {
                        "type": "string",
                        "description": "Type: user, research, preference, fact, system.",
                        "enum": ["user", "research", "preference", "fact", "system"],
                        "default": "fact",
                    },
                    "importance": {
                        "type": "number",
                        "description": "Importance 0.0-1.0 (higher = less likely to be pruned).",
                        "default": 0.5,
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gangdan_memory_search",
            "description": (
                "Search persistent memory for previously stored facts, preferences, "
                "or research findings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query keywords.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return.",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gangdan_memory_forget",
            "description": (
                "Remove a memory entry by its content keyword match."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords to find the memory to forget.",
                    },
                },
                "required": ["query"],
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

    if name == "gangdan_memory_remember":
        from gangdan.core.memory_store import MemoryStore
        from gangdan.core.config import DATA_DIR

        store = MemoryStore(DATA_DIR)
        entry = store.remember(
            content=arguments["content"],
            memory_type=arguments.get("memory_type", "fact"),
            importance=arguments.get("importance", 0.5),
        )
        return {"success": True, "entry": entry}

    if name == "gangdan_memory_search":
        from gangdan.core.memory_store import MemoryStore
        from gangdan.core.config import DATA_DIR

        store = MemoryStore(DATA_DIR)
        results = store.search_memories(
            query=arguments["query"],
            limit=arguments.get("limit", 10),
        )
        return {"success": True, "results": results}

    if name == "gangdan_memory_forget":
        from gangdan.core.memory_store import MemoryStore
        from gangdan.core.config import DATA_DIR

        store = MemoryStore(DATA_DIR)
        results = store.search_memories(arguments["query"], limit=1)
        if results:
            store.forget(results[0]["id"])
            return {"success": True, "forgotten": results[0]["content"][:100]}
        return {"success": False, "error": "No matching memory found"}

    raise ValueError(f"Unknown tool: {name}")
