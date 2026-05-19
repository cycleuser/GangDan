"""LLM client factory for GangDan Refined.

Creates the appropriate client based on provider configuration.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import BaseLLMClient
from .ollama import OllamaClient
from .openai_compat import OpenAICompatClient, AnthropicCompatClient
from .models import ProviderConfig, PROVIDER_CONFIGS


def create_client(provider: str, api_key: str = "", base_url: str = "") -> BaseLLMClient:
    """Factory function to create the appropriate LLM client.

    Parameters
    ----------
    provider : str
        Provider name (ollama, openai, deepseek, bailian-coding, etc.)
    api_key : str
        API key for authentication.
    base_url : str
        Custom base URL (overrides provider default).

    Returns
    -------
    BaseLLMClient
        The appropriate client instance.
    """
    config = PROVIDER_CONFIGS.get(provider)
    if not config:
        config = ProviderConfig(
            name="custom",
            display_name="Custom",
            base_url=base_url or "",
            api_type="openai",
            requires_key=True,
            models=[],
        )

    final_url = base_url or config.base_url

    if config.api_type == "ollama":
        return OllamaClient(final_url.replace("/v1", ""))
    elif config.api_type == "anthropic":
        return AnthropicCompatClient(api_key=api_key, base_url=final_url, provider=provider)
    else:
        return OpenAICompatClient(api_key=api_key, base_url=final_url, provider=provider)


def create_chat_client() -> BaseLLMClient:
    """Create a chat client based on the current CONFIG settings.

    Uses CONFIG.llm.chat_provider and related settings.
    """
    from ..core.config import CONFIG

    provider = CONFIG.llm.chat_provider
    api_key = CONFIG.llm.chat_api_key or CONFIG.llm.provider_keys.get(provider, "")
    base_url = CONFIG.llm.chat_api_base_url or CONFIG.llm.provider_base_urls.get(provider, "")

    if provider == "ollama":
        return OllamaClient(CONFIG.llm.ollama_url)

    config = PROVIDER_CONFIGS.get(provider)
    if config and config.api_type == "anthropic":
        return AnthropicCompatClient(api_key=api_key, base_url=base_url or config.base_url, provider=provider)

    return OpenAICompatClient(api_key=api_key, base_url=base_url or config.base_url if config else base_url, provider=provider)


def create_embed_client() -> OllamaClient:
    """Create an embed client (always uses Ollama for embeddings).

    Returns
    -------
    OllamaClient
        Ollama client for embedding operations.
    """
    from ..core.config import CONFIG
    return OllamaClient(CONFIG.llm.ollama_url)


def list_providers() -> List[Dict[str, Any]]:
    """Get list of all available providers."""
    return [
        {
            "name": config.name,
            "display_name": config.display_name,
            "base_url": config.base_url,
            "api_type": config.api_type,
            "requires_key": config.requires_key,
            "models": config.models,
            "key_url": config.key_url,
            "help": config.help,
            "default_model": config.default_model,
        }
        for config in PROVIDER_CONFIGS.values()
    ]


def get_provider_config(provider: str) -> Optional[ProviderConfig]:
    """Get configuration for a provider."""
    return PROVIDER_CONFIGS.get(provider)