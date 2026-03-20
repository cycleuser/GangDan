"""Tests for gangdan.core.llm_client module."""

import pytest
from unittest.mock import patch, MagicMock


class TestProviderConfigs:
    """Test provider configurations."""

    def test_provider_configs_exist(self, temp_data_dir):
        """Test that all expected providers are configured."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        
        expected_providers = [
            'ollama', 'bailian-coding', 'minimax', 'dashscope',
            'openai', 'deepseek', 'moonshot', 'zhipu', 'siliconflow'
        ]
        for provider in expected_providers:
            assert provider in PROVIDER_CONFIGS, f"Provider {provider} not found"

    def test_ollama_config(self, temp_data_dir):
        """Test Ollama provider configuration."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        
        config = PROVIDER_CONFIGS['ollama']
        assert config.name == 'ollama'
        assert config.base_url == 'http://localhost:11434'
        assert config.api_type == 'ollama'
        assert config.requires_key == False

    def test_bailian_coding_config(self, temp_data_dir):
        """Test Bailian Coding provider configuration."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        
        config = PROVIDER_CONFIGS['bailian-coding']
        assert config.name == 'bailian-coding'
        assert config.api_type == 'anthropic'
        assert config.requires_key == True
        assert 'qwen3.5-plus' in config.models
        assert 'MiniMax-M2.5' in config.models

    def test_minimax_config(self, temp_data_dir):
        """Test MiniMax provider configuration."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        
        config = PROVIDER_CONFIGS['minimax']
        assert config.name == 'minimax'
        assert config.api_type == 'openai'
        assert config.base_url == 'https://api.minimaxi.com/v1'
        assert 'MiniMax-M2.7' in config.models
        assert 'MiniMax-M2.7-highspeed' in config.models


class TestOpenAIClient:
    """Test OpenAI-compatible client."""

    def test_create_openai_client(self, temp_data_dir):
        """Test creating OpenAI client."""
        from gangdan.core.llm_client import OpenAIClient
        
        client = OpenAIClient(api_key="test-key", base_url="https://api.test.com/v1")
        assert client.api_key == "test-key"
        assert client.base_url == "https://api.test.com/v1"

    def test_openai_client_headers(self, temp_data_dir):
        """Test OpenAI client sets correct headers."""
        from gangdan.core.llm_client import OpenAIClient
        
        client = OpenAIClient(api_key="sk-test123")
        assert "Authorization" in client._session.headers
        assert client._session.headers["Authorization"] == "Bearer sk-test123"

    def test_get_models_from_config(self, temp_data_dir):
        """Test getting models from provider config."""
        from gangdan.core.llm_client import OpenAIClient
        
        client = OpenAIClient(api_key="", base_url="https://api.test.com/v1", provider="minimax")
        models = client.get_models()
        assert 'MiniMax-M2.7' in models


class TestAnthropicClient:
    """Test Anthropic-compatible client (Bailian Coding)."""

    def test_create_anthropic_client(self, temp_data_dir):
        """Test creating Anthropic client."""
        from gangdan.core.llm_client import AnthropicClient
        
        client = AnthropicClient(api_key="test-key", base_url="https://coding.dashscope.aliyuncs.com/apps/anthropic/v1")
        assert client.api_key == "test-key"
        assert client.base_url == "https://coding.dashscope.aliyuncs.com/apps/anthropic/v1"

    def test_anthropic_client_headers(self, temp_data_dir):
        """Test Anthropic client sets correct headers."""
        from gangdan.core.llm_client import AnthropicClient
        
        client = AnthropicClient(api_key="test-anthropic-key")
        assert "x-api-key" in client._session.headers
        assert client._session.headers["x-api-key"] == "test-anthropic-key"
        assert "anthropic-version" in client._session.headers

    def test_get_models_from_config(self, temp_data_dir):
        """Test getting models from provider config."""
        from gangdan.core.llm_client import AnthropicClient
        
        client = AnthropicClient(api_key="", base_url="", provider="bailian-coding")
        models = client.get_models()
        assert 'qwen3.5-plus' in models


class TestCreateClient:
    """Test create_client factory function."""

    def test_create_ollama_client(self, temp_data_dir):
        """Test creating Ollama client via factory."""
        from gangdan.core.llm_client import create_client
        
        client = create_client(provider="ollama", base_url="http://localhost:11434")
        assert client.__class__.__name__ == "OllamaClient"

    def test_create_minimax_client(self, temp_data_dir):
        """Test creating MiniMax client via factory."""
        from gangdan.core.llm_client import create_client
        
        client = create_client(provider="minimax", api_key="test-key")
        assert client.__class__.__name__ == "OpenAIClient"
        assert "minimax" in client.base_url

    def test_create_bailian_coding_client(self, temp_data_dir):
        """Test creating Bailian Coding client via factory."""
        from gangdan.core.llm_client import create_client
        
        client = create_client(provider="bailian-coding", api_key="test-key")
        assert client.__class__.__name__ == "AnthropicClient"

    def test_create_unknown_provider(self, temp_data_dir):
        """Test creating client with unknown provider."""
        from gangdan.core.llm_client import create_client
        
        client = create_client(provider="unknown", base_url="https://custom.api.com/v1")
        assert client.__class__.__name__ == "OpenAIClient"


class TestListProviders:
    """Test list_providers function."""

    def test_list_providers_returns_list(self, temp_data_dir):
        """Test that list_providers returns a list."""
        from gangdan.core.llm_client import list_providers
        
        providers = list_providers()
        assert isinstance(providers, list)
        assert len(providers) >= 5

    def test_list_providers_structure(self, temp_data_dir):
        """Test provider list items have required fields."""
        from gangdan.core.llm_client import list_providers
        
        providers = list_providers()
        for p in providers:
            assert "name" in p
            assert "display_name" in p
            assert "base_url" in p
            assert "api_type" in p
            assert "requires_key" in p


class TestGetProviderConfig:
    """Test get_provider_config function."""

    def test_get_existing_provider(self, temp_data_dir):
        """Test getting existing provider config."""
        from gangdan.core.llm_client import get_provider_config
        
        config = get_provider_config("minimax")
        assert config is not None
        assert config.name == "minimax"

    def test_get_nonexistent_provider(self, temp_data_dir):
        """Test getting non-existent provider returns None."""
        from gangdan.core.llm_client import get_provider_config
        
        config = get_provider_config("nonexistent-provider")
        assert config is None
