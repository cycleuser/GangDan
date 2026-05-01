"""Tests for gangdan.core.config module."""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch


class TestConfigDataclass:
    """Test Config dataclass and defaults."""

    def test_config_defaults(self, temp_data_dir):
        """Test that Config has correct default values."""
        # Import after setting env var
        from gangdan.core.config import Config

        config = Config()
        assert config.ollama_url == "http://localhost:11434"
        assert config.embedding_model == "nomic-embed-text"
        assert config.chat_model == "qwen2.5:7b"
        assert config.reranker_model == ""
        assert config.chunk_size == 800
        assert config.chunk_overlap == 150
        assert config.top_k == 15
        assert config.max_context_tokens == 3000
        assert config.language == "zh"
        assert config.proxy_mode == "none"
        assert config.proxy_http == ""
        assert config.proxy_https == ""
        assert config.strict_kb_mode == False

    def test_config_custom_values(self, temp_data_dir):
        """Test creating Config with custom values."""
        from gangdan.core.config import Config

        config = Config(
            ollama_url="http://custom:8000", chat_model="llama3:8b", language="en"
        )
        assert config.ollama_url == "http://custom:8000"
        assert config.chat_model == "llama3:8b"
        assert config.language == "en"


class TestConfigPersistence:
    """Test configuration save/load functionality."""

    def test_save_and_load_config(self, temp_data_dir, sample_config):
        """Test saving and loading configuration."""
        # Write config file
        config_file = temp_data_dir / "gangdan_config.json"
        config_file.write_text(json.dumps(sample_config, indent=2))

        # Force reimport to pick up new env
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        config_module.load_config()

        assert config_module.CONFIG.ollama_url == sample_config["ollama_url"]
        assert config_module.CONFIG.chat_model == sample_config["chat_model"]
        assert config_module.CONFIG.embedding_model == sample_config["embedding_model"]
        assert config_module.CONFIG.language == sample_config["language"]

    def test_load_config_missing_file(self, temp_data_dir):
        """Test loading config when file doesn't exist."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        # Should not raise, just use defaults
        config_module.load_config()
        assert config_module.CONFIG.ollama_url == "http://localhost:11434"

    def test_save_config_creates_file(self, temp_data_dir):
        """Test that save_config creates the config file."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        config_module.CONFIG.chat_model = "test-model"
        config_module.save_config()

        config_file = temp_data_dir / "gangdan_config.json"
        assert config_file.exists()

        data = json.loads(config_file.read_text())
        assert data["chat_model"] == "test-model"


class TestProxySettings:
    """Test proxy configuration."""

    def test_get_proxies_none(self, temp_data_dir):
        """Test proxy when mode is none."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        config_module.CONFIG.proxy_mode = "none"
        assert config_module.get_proxies() is None

    def test_get_proxies_manual(self, temp_data_dir):
        """Test proxy when mode is manual."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        config_module.CONFIG.proxy_mode = "manual"
        config_module.CONFIG.proxy_http = "http://proxy:8080"
        config_module.CONFIG.proxy_https = "https://proxy:8080"

        proxies = config_module.get_proxies()
        assert proxies is not None
        assert proxies["http"] == "http://proxy:8080"
        assert proxies["https"] == "https://proxy:8080"

    def test_get_proxies_system(self, temp_data_dir):
        """Test proxy when mode is system."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        config_module.CONFIG.proxy_mode = "system"

        with patch.dict(os.environ, {"HTTP_PROXY": "http://system:8080"}):
            proxies = config_module.get_proxies()
            assert proxies is not None
            assert proxies["http"] == "http://system:8080"


class TestLanguageDetection:
    """Test language detection function."""

    def test_detect_chinese(self, temp_data_dir):
        """Test detecting Chinese text."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        text = "你好世界，这是一段中文测试文本"
        assert config_module.detect_language(text) == "zh"

    def test_detect_english(self, temp_data_dir):
        """Test detecting English text."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        text = "Hello world, this is an English test text"
        assert config_module.detect_language(text) == "en"

    def test_detect_japanese(self, temp_data_dir):
        """Test detecting Japanese text."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        text = "こんにちは世界、これは日本語のテストです"
        assert config_module.detect_language(text) == "ja"

    def test_detect_korean(self, temp_data_dir):
        """Test detecting Korean text."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        text = "안녕하세요 세계, 이것은 한국어 테스트입니다"
        assert config_module.detect_language(text) == "ko"

    def test_detect_russian(self, temp_data_dir):
        """Test detecting Russian text."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        text = "Привет мир, это тестовый текст на русском языке"
        assert config_module.detect_language(text) == "ru"

    def test_detect_empty_text(self, temp_data_dir):
        """Test detecting empty text."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        assert config_module.detect_language("") == "unknown"
        assert config_module.detect_language(None) == "unknown"


class TestKBNameSanitization:
    """Test knowledge base name sanitization."""

    def test_sanitize_normal_name(self, temp_data_dir):
        """Test sanitizing a normal KB name."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        result = config_module.sanitize_kb_name("My Python Notes")
        assert result.startswith("user_")
        assert "my_python_notes" in result

    def test_sanitize_special_chars(self, temp_data_dir):
        """Test sanitizing name with special characters."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        result = config_module.sanitize_kb_name("Test@#$%Name!")
        assert result.startswith("user_")
        # Special chars should be removed
        assert "@" not in result
        assert "#" not in result

    def test_sanitize_short_name(self, temp_data_dir):
        """Test sanitizing very short name uses hash."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        result = config_module.sanitize_kb_name("AB")
        assert result.startswith("user_kb_")
        assert len(result) > 10  # Should have hash


class TestTranslation:
    """Test translation function."""

    def test_translate_english(self, temp_data_dir):
        """Test translating to English."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        config_module.CONFIG.language = "en"
        assert config_module.t("chat") == "Chat"
        assert config_module.t("settings") == "Settings"

    def test_translate_chinese(self, temp_data_dir):
        """Test translating to Chinese."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        config_module.CONFIG.language = "zh"
        assert config_module.t("chat") == "对话"
        assert config_module.t("settings") == "设置"

    def test_translate_unknown_key(self, temp_data_dir):
        """Test translating unknown key returns key."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        assert config_module.t("unknown_key_xyz") == "unknown_key_xyz"


class TestUserKBs:
    """Test user knowledge base manifest functions."""

    def test_save_and_load_user_kb(self, temp_data_dir):
        """Test saving and loading user KB manifest."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        # Save a user KB
        config_module.save_user_kb(
            internal_name="user_test_kb",
            display_name="Test Knowledge Base",
            file_count=10,
            languages=["en", "zh"],
        )

        # Load and verify
        kbs = config_module.load_user_kbs()
        assert "user_test_kb" in kbs
        assert kbs["user_test_kb"]["display_name"] == "Test Knowledge Base"
        assert kbs["user_test_kb"]["file_count"] == 10
        assert "en" in kbs["user_test_kb"]["languages"]

    def test_delete_user_kb(self, temp_data_dir):
        """Test deleting user KB from manifest."""
        import importlib
        import gangdan.core.config as config_module

        importlib.reload(config_module)

        # Save then delete
        config_module.save_user_kb("user_to_delete", "Delete Me", 5)
        config_module.delete_user_kb("user_to_delete")

        kbs = config_module.load_user_kbs()
        assert "user_to_delete" not in kbs
