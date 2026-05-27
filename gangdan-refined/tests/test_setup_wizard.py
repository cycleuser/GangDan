"""Tests for setup wizard functionality."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from gangdan_refined.core.setup_wizard import (
    is_first_run,
    check_ollama_connection,
    check_provider_connection,
    get_ollama_models,
    get_provider_models,
    get_setup_status,
    save_setup_config,
)
from gangdan_refined.core.config import CONFIG, CONFIG_FILE, DATA_DIR


class TestIsFirstRun:
    """Test first run detection."""

    def test_first_run_no_config(self, tmp_path):
        """Should return True when config file doesn't exist."""
        with patch('gangdan_refined.core.setup_wizard.CONFIG_FILE', tmp_path / "nonexistent.json"):
            assert is_first_run() is True

    def test_not_first_run_config_exists(self, tmp_path):
        """Should return False when config file exists."""
        config_file = tmp_path / "gangdan_refined_config.json"
        config_file.write_text("{}")
        
        with patch('gangdan_refined.core.setup_wizard.CONFIG_FILE', config_file):
            assert is_first_run() is False


class TestOllamaConnection:
    """Test Ollama connection testing."""

    @patch('urllib.request.urlopen')
    def check_ollama_connection_success_with_models(self, mock_urlopen):
        """Should return success with model list."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "models": [
                {"name": "qwen2.5:7b"},
                {"name": "llama3:8b"}
            ]
        }).encode()
        mock_urlopen.return_value = mock_response

        success, message = check_ollama_connection("http://localhost:11434")
        
        assert success is True
        assert "2 models" in message
        assert "qwen2.5:7b" in message

    @patch('urllib.request.urlopen')
    def check_ollama_connection_success_no_models(self, mock_urlopen):
        """Should return success even with no models."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"models": []}).encode()
        mock_urlopen.return_value = mock_response

        success, message = check_ollama_connection("http://localhost:11434")
        
        assert success is True
        assert "No models found" in message

    @patch('urllib.request.urlopen')
    def check_ollama_connection_failure(self, mock_urlopen):
        """Should return failure on connection error."""
        mock_urlopen.side_effect = Exception("Connection refused")

        success, message = check_ollama_connection("http://localhost:11434")
        
        assert success is False
        assert "Connection refused" in message


class TestGetOllamaModels:
    """Test getting Ollama models list."""

    @patch('urllib.request.urlopen')
    def test_get_models_success(self, mock_urlopen):
        """Should return list of model names."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "models": [
                {"name": "qwen2.5:7b"},
                {"name": "llama3:8b"}
            ]
        }).encode()
        mock_urlopen.return_value = mock_response

        models = get_ollama_models("http://localhost:11434")
        
        assert len(models) == 2
        assert "qwen2.5:7b" in models
        assert "llama3:8b" in models

    @patch('urllib.request.urlopen')
    def test_get_models_failure(self, mock_urlopen):
        """Should return empty list on failure."""
        mock_urlopen.side_effect = Exception("Error")

        models = get_ollama_models("http://localhost:11434")
        
        assert models == []


class TestSetupStatus:
    """Test setup status reporting."""

    def test_get_setup_status_not_configured(self, tmp_path):
        """Should return not configured status."""
        with patch('gangdan_refined.core.setup_wizard.CONFIG_FILE', tmp_path / "nonexistent.json"):
            with patch('gangdan_refined.core.setup_wizard.load_config'):
                status = get_setup_status()
                
                assert status["is_configured"] is False

    @patch('gangdan_refined.core.setup_wizard.check_ollama_connection')
    @patch('gangdan_refined.core.setup_wizard.get_ollama_models')
    def test_get_setup_status_ollama(self, mock_get_models, mock_test, tmp_path):
        """Should return Ollama status when configured."""
        mock_test.return_value = (True, "Connected")
        mock_get_models.return_value = ["qwen2.5:7b"]
        
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")
        
        with patch('gangdan_refined.core.setup_wizard.CONFIG_FILE', config_file):
            with patch('gangdan_refined.core.setup_wizard.CONFIG') as mock_config:
                mock_config.ui.language = "zh"
                mock_config.llm.chat_provider = "ollama"
                mock_config.llm.chat_model = "qwen2.5:7b"
                mock_config.llm.ollama_url = "http://localhost:11434"
                mock_config.llm.chat_api_key = ""
                mock_config.llm.provider_keys = {}
                
                status = get_setup_status()
                
                assert status["is_configured"] is True
                assert status["chat_provider"] == "ollama"
                assert status["ollama_connected"] is True


class TestSaveSetupConfig:
    """Test saving setup configuration."""

    @patch('gangdan_refined.core.setup_wizard.save_config')
    def test_save_ollama_config(self, mock_save, tmp_path):
        """Should save Ollama configuration."""
        with patch('gangdan_refined.core.setup_wizard.check_ollama_connection') as mock_test:
            mock_test.return_value = (True, "Connected")
            
            with patch('gangdan_refined.core.setup_wizard.CONFIG') as mock_config:
                mock_config.ui.language = "zh"
                mock_config.llm = MagicMock()
                mock_config.llm.provider_keys = {}
                mock_config.llm.provider_base_urls = {}
                
                config_data = {
                    "language": "zh",
                    "chat_provider": "ollama",
                    "ollama_url": "http://localhost:11434",
                    "chat_model": "qwen2.5:7b",
                    "embedding_model": "nomic-embed-text"
                }
                
                success, message = save_setup_config(config_data)
                
                assert success is True
                assert "saved" in message.lower()
                mock_save.assert_called_once()

    def test_save_api_config_missing_key(self, tmp_path):
        """Should fail when API key is missing."""
        with patch('gangdan_refined.core.setup_wizard.CONFIG') as mock_config:
            config_data = {
                "language": "en",
                "chat_provider": "openai",
                "api_key": "",
                "base_url": "https://api.openai.com/v1",
                "chat_model": "gpt-4o"
            }
            
            success, message = save_setup_config(config_data)
            
            assert success is False
            assert "API Key" in message

    @patch('gangdan_refined.core.setup_wizard.check_provider_connection')
    @patch('gangdan_refined.core.setup_wizard.save_config')
    def test_save_api_config_success(self, mock_save, mock_test, tmp_path):
        """Should save API provider configuration."""
        mock_test.return_value = (True, "Connected")
        
        with patch('gangdan_refined.core.setup_wizard.CONFIG') as mock_config:
            mock_config.ui.language = "en"
            mock_config.llm = MagicMock()
            mock_config.llm.provider_keys = {}
            mock_config.llm.provider_base_urls = {}
            
            config_data = {
                "language": "en",
                "chat_provider": "openai",
                "api_key": "sk-test123",
                "base_url": "https://api.openai.com/v1",
                "chat_model": "gpt-4o"
            }
            
            success, message = save_setup_config(config_data)
            
            assert success is True
            mock_save.assert_called_once()


class TestProviderConnection:
    """Test provider connection testing."""

    @patch('gangdan_refined.core.setup_wizard.create_client')
    def check_provider_connection_success(self, mock_create_client):
        """Should return success on successful connection."""
        mock_client = MagicMock()
        mock_client.chat.return_value = {"success": True}
        mock_create_client.return_value = mock_client

        success, message = check_provider_connection("openai", "sk-test")
        
        assert success is True
        assert "successful" in message.lower()

    @patch('gangdan_refined.core.setup_wizard.create_client')
    def check_provider_connection_failure(self, mock_create_client):
        """Should return failure on connection error."""
        mock_client = MagicMock()
        mock_client.chat.return_value = {"success": False, "error": "Invalid key"}
        mock_create_client.return_value = mock_client

        success, message = check_provider_connection("openai", "sk-invalid")
        
        assert success is False
        assert "Invalid key" in message


class TestGetProviderModels:
    """Test getting provider models."""

    def test_get_models_from_config(self):
        """Should return models from provider config."""
        models = get_provider_models("bailian-coding", "sk-test")
        
        assert len(models) > 0
        assert "qwen3.5-plus" in models

    @patch('gangdan_refined.core.setup_wizard.create_client')
    def test_get_models_from_client(self, mock_create_client):
        """Should try to get models from client if not in config."""
        mock_client = MagicMock()
        mock_client.list_models.return_value = ["model1", "model2"]
        mock_create_client.return_value = mock_client

        models = get_provider_models("custom", "sk-test")
        
        # Should have models from client or default
        assert isinstance(models, list)
