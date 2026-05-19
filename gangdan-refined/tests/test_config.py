"""Tests for core.config module."""

import json
import tempfile
from pathlib import Path

import pytest

from gangdan_refined.core.config import (
    Config,
    ProxyConfig,
    LLMConfig,
    StorageConfig,
    SearchConfig,
    DocumentConfig,
    PreprintConfig,
    ResearchConfig,
    AdaptiveConfig,
    UIConfig,
    sanitize_kb_name,
    detect_language,
    load_config,
    save_config,
)


class TestProxyConfig:
    def test_none_mode(self):
        config = ProxyConfig(mode="none")
        assert config.get_proxies() is None

    def test_manual_mode(self):
        config = ProxyConfig(mode="manual", http="http://proxy:8080")
        proxies = config.get_proxies()
        assert proxies == {"http": "http://proxy:8080", "https": "http://proxy:8080"}


class TestConfigGroups:
    def test_config_has_groups(self):
        config = Config()
        assert isinstance(config.proxy, ProxyConfig)
        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.storage, StorageConfig)
        assert isinstance(config.search, SearchConfig)
        assert isinstance(config.document, DocumentConfig)
        assert isinstance(config.preprint, PreprintConfig)
        assert isinstance(config.research, ResearchConfig)
        assert isinstance(config.adaptive, AdaptiveConfig)
        assert isinstance(config.ui, UIConfig)

    def test_convenience_aliases(self):
        config = Config()
        assert config.ollama_url == config.llm.ollama_url
        assert config.chat_model == config.llm.chat_model
        assert config.chunk_size == config.storage.chunk_size
        assert config.language == config.ui.language

    def test_alias_setter(self):
        config = Config()
        config.ollama_url = "http://test:1234"
        assert config.llm.ollama_url == "http://test:1234"
        config.chat_model = "test-model"
        assert config.llm.chat_model == "test-model"


class TestSanitizeKbName:
    def test_ascii_name(self):
        assert sanitize_kb_name("My Knowledge Base") == "user_my_knowledge_base"

    def test_chinese_name(self):
        result = sanitize_kb_name("中文知识库")
        assert result.startswith("user_")
        assert len(result) > 8

    def test_short_name(self):
        result = sanitize_kb_name("ab")
        assert result.startswith("user_kb_")


class TestDetectLanguage:
    def test_english(self):
        assert detect_language("Hello world") == "en"

    def test_chinese(self):
        assert detect_language("你好世界") == "zh"

    def test_japanese(self):
        assert detect_language("こんにちは") == "ja"

    def test_empty_string(self):
        assert detect_language("") == "unknown"


class TestConfigPersistence:
    def test_save_and_load(self, tmp_path):
        config_file = tmp_path / "test_config.json"
        from gangdan_refined.core import config as config_module

        original_file = config_module.CONFIG_FILE
        config_module.CONFIG_FILE = config_file
        config_module.DATA_DIR = tmp_path

        try:
            config = Config()
            config.llm.chat_model = "test-model"
            config_module.CONFIG = config
            save_config()

            config2 = Config()
            config_module.CONFIG = config2
            load_config()

            assert config_module.CONFIG.llm.chat_model == "test-model"
        finally:
            config_module.CONFIG_FILE = original_file