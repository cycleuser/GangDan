"""Tests for llm module."""

import pytest
from unittest.mock import patch, MagicMock

from gangdan_refined.llm.base import BaseLLMClient
from gangdan_refined.llm.ollama import OllamaClient
from gangdan_refined.llm.models import ProviderConfig, PROVIDER_CONFIGS
from gangdan_refined.llm.factory import create_client, list_providers, get_provider_config


class TestProviderConfig:
    def test_provider_configs_exist(self):
        assert "ollama" in PROVIDER_CONFIGS
        assert "openai" in PROVIDER_CONFIGS
        assert "deepseek" in PROVIDER_CONFIGS

    def test_ollama_no_key_required(self):
        assert PROVIDER_CONFIGS["ollama"].requires_key is False

    def test_openai_key_required(self):
        assert PROVIDER_CONFIGS["openai"].requires_key is True


class TestOllamaClient:
    def test_init(self):
        client = OllamaClient("http://localhost:11434")
        assert client.api_url == "http://localhost:11434"

    def test_init_trailing_slash(self):
        client = OllamaClient("http://localhost:11434/")
        assert client.api_url == "http://localhost:11434"


class TestFactory:
    def test_create_ollama_client(self):
        client = create_client("ollama")
        assert isinstance(client, OllamaClient)

    def test_create_openai_client(self):
        from gangdan_refined.llm.openai_compat import OpenAICompatClient
        client = create_client("openai", api_key="test-key")
        assert isinstance(client, OpenAICompatClient)

    def test_create_anthropic_client(self):
        from gangdan_refined.llm.openai_compat import AnthropicCompatClient
        client = create_client("bailian-coding", api_key="test-key")
        assert isinstance(client, AnthropicCompatClient)

    def test_create_custom_client(self):
        from gangdan_refined.llm.openai_compat import OpenAICompatClient
        client = create_client("custom", api_key="key", base_url="http://custom:8080/v1")
        assert isinstance(client, OpenAICompatClient)

    def test_list_providers(self):
        providers = list_providers()
        assert len(providers) > 0
        assert any(p["name"] == "ollama" for p in providers)

    def test_get_provider_config(self):
        config = get_provider_config("openai")
        assert config is not None
        assert config.name == "openai"

    def test_get_unknown_provider(self):
        config = get_provider_config("nonexistent")
        assert config is None