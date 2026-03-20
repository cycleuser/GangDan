"""Tests for gangdan.learning_routes module - provider selection and config tests."""

import pytest
from unittest.mock import patch, MagicMock


class TestResearchProviderSelection:
    """Test research provider selection logic."""

    def test_ollama_provider_used_when_selected(self, temp_data_dir):
        """Test Ollama client is used when ollama provider is selected."""
        from gangdan.core.llm_client import create_client
        
        client = create_client(provider="ollama", base_url="http://localhost:11434")
        assert client.__class__.__name__ == "OllamaClient"

    def test_bailian_coding_provider(self, temp_data_dir):
        """Test bailian-coding provider creates Anthropic client."""
        from gangdan.core.llm_client import create_client
        
        client = create_client(provider="bailian-coding", api_key="test-key")
        assert client.__class__.__name__ == "AnthropicClient"

    def test_minimax_provider(self, temp_data_dir):
        """Test minimax provider creates OpenAI client."""
        from gangdan.core.llm_client import create_client
        
        client = create_client(provider="minimax", api_key="test-key")
        assert client.__class__.__name__ == "OpenAIClient"
        assert "minimax" in client.base_url

    def test_custom_provider_with_url(self, temp_data_dir):
        """Test custom provider with URL."""
        from gangdan.core.llm_client import create_client
        
        client = create_client(
            provider="custom",
            api_key="test-key",
            base_url="https://custom.api.com/v1"
        )
        assert client.__class__.__name__ == "OpenAIClient"


class TestProviderConfigsIntegration:
    """Test provider configs work with research module."""

    def test_minimax_has_correct_models(self, temp_data_dir):
        """Test MiniMax config has expected models."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        
        minimax = PROVIDER_CONFIGS['minimax']
        assert 'MiniMax-M2.7' in minimax.models
        assert 'MiniMax-M2.5' in minimax.models

    def test_bailian_coding_has_correct_models(self, temp_data_dir):
        """Test bailian-coding config has expected models."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        
        bailian = PROVIDER_CONFIGS['bailian-coding']
        assert 'qwen3.5-plus' in bailian.models
        assert 'qwen3-coder-next' in bailian.models

    def test_provider_base_urls(self, temp_data_dir):
        """Test provider base URLs are correctly set."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        
        assert PROVIDER_CONFIGS['minimax'].base_url == 'https://api.minimaxi.com/v1'
        assert PROVIDER_CONFIGS['bailian-coding'].base_url == 'https://coding.dashscope.aliyuncs.com/apps/anthropic/v1'
        assert PROVIDER_CONFIGS['ollama'].base_url == 'http://localhost:11434'

    def test_all_providers_have_required_fields(self, temp_data_dir):
        """Test all providers have required configuration fields."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        
        required_fields = ['name', 'base_url', 'api_type', 'requires_key', 'models']
        for provider_name, config in PROVIDER_CONFIGS.items():
            for field in required_fields:
                assert hasattr(config, field), f"Provider {provider_name} missing field {field}"


class TestProviderAPIType:
    """Test API type assignments for providers."""

    def test_ollama_is_ollama_type(self, temp_data_dir):
        """Test Ollama has correct api_type."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        assert PROVIDER_CONFIGS['ollama'].api_type == 'ollama'

    def test_bailian_coding_is_anthropic_type(self, temp_data_dir):
        """Test bailian-coding has Anthropic api_type."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        assert PROVIDER_CONFIGS['bailian-coding'].api_type == 'anthropic'

    def test_minimax_is_openai_type(self, temp_data_dir):
        """Test minimax has OpenAI api_type."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        assert PROVIDER_CONFIGS['minimax'].api_type == 'openai'

    def test_dashscope_is_openai_type(self, temp_data_dir):
        """Test dashscope has OpenAI api_type."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        assert PROVIDER_CONFIGS['dashscope'].api_type == 'openai'


class TestProviderKeyRequirement:
    """Test API key requirements for providers."""

    def test_ollama_no_key_required(self, temp_data_dir):
        """Test Ollama doesn't require API key."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        assert PROVIDER_CONFIGS['ollama'].requires_key == False

    def test_online_providers_require_key(self, temp_data_dir):
        """Test online providers require API key."""
        from gangdan.core.llm_client import PROVIDER_CONFIGS
        
        online_providers = ['bailian-coding', 'minimax', 'dashscope', 'openai', 'deepseek', 'moonshot', 'zhipu', 'siliconflow']
        for provider in online_providers:
            assert PROVIDER_CONFIGS[provider].requires_key == True, f"{provider} should require API key"
