"""LLM abstraction layer for GangDan Refined.

Provides unified access to multiple LLM providers:
- Ollama (local)
- OpenAI-compatible (OpenAI, DeepSeek, Moonshot, etc.)
- Anthropic-compatible (Bailian Coding, etc.)

Usage:
    from gangdan_refined.llm import create_client, OllamaClient

    client = create_client("ollama")
    result = client.chat([{"role": "user", "content": "Hello"}])
"""

from .base import BaseLLMClient
from .ollama import OllamaClient
from .openai_compat import OpenAICompatClient, AnthropicCompatClient
from .models import ProviderConfig, PROVIDER_CONFIGS
from .factory import create_client, create_chat_client, create_embed_client, list_providers

__all__ = [
    "BaseLLMClient",
    "OllamaClient",
    "OpenAICompatClient",
    "AnthropicCompatClient",
    "ProviderConfig",
    "PROVIDER_CONFIGS",
    "create_client",
    "create_chat_client",
    "create_embed_client",
    "list_providers",
]