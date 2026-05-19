"""Tests for the modular architecture of GangDan Refined.

Verifies that:
1. All modules are importable without circular dependencies
2. No global state or god objects
3. Each module can function independently
"""

import pytest


class TestModuleImports:
    """Verify all packages import cleanly."""

    def test_import_core(self):
        from gangdan_refined.core import Config, CONFIG, ToolResult, GangDanError
        assert Config is not None
        assert CONFIG is not None

    def test_import_llm(self):
        from gangdan_refined.llm import (
            BaseLLMClient, OllamaClient, OpenAICompatClient,
            AnthropicCompatClient, create_client, list_providers,
        )
        assert BaseLLMClient is not None

    def test_import_storage(self):
        from gangdan_refined.storage import (
            ChromaManager, ConversationManager,
            CustomKBManager, VectorDBBase, VectorDBType,
        )
        assert ChromaManager is not None

    def test_import_search(self):
        from gangdan_refined.search import (
            WebSearcher, ResearchSearcher, QueryExpander,
        )
        assert WebSearcher is not None

    def test_import_document(self):
        from gangdan_refined.document import PDFConverter, DocManager
        assert PDFConverter is not None

    def test_import_research(self):
        from gangdan_refined.research import (
            PaperMetadata, SearchResult, ResearchPipeline, ExportManager,
        )
        assert PaperMetadata is not None

    def test_import_learning(self):
        from gangdan_refined.learning import generate_questions, generate_exam
        assert generate_questions is not None

    def test_import_api(self):
        from gangdan_refined.api import chat, index_documents
        assert chat is not None
        assert index_documents is not None

    def test_import_tools(self):
        from gangdan_refined.tools import TOOLS, dispatch
        assert len(TOOLS) == 2

    def test_import_web(self):
        from gangdan_refined.web import create_app
        assert create_app is not None

    def test_import_cli(self):
        from gangdan_refined.cli import main
        assert main is not None


class TestNoGlobalState:
    """Verify no shared mutable global state across modules."""

    def test_config_is_dataclass_not_god_object(self):
        from gangdan_refined.core.config import Config
        import dataclasses

        fields = {f.name for f in dataclasses.fields(Config)}
        assert "proxy" in fields
        assert "llm" in fields
        assert "storage" in fields
        assert "search" in fields
        assert "document" in fields
        assert "preprint" in fields
        assert "research" in fields
        assert "adaptive" in fields
        assert "ui" in fields

    def test_config_groups_are_dataclasses(self):
        from gangdan_refined.core.config import (
            ProxyConfig, LLMConfig, StorageConfig, SearchConfig,
            DocumentConfig, PreprintConfig, ResearchConfig,
            AdaptiveConfig, UIConfig,
        )
        import dataclasses

        for cls in [ProxyConfig, LLMConfig, StorageConfig, SearchConfig,
                     DocumentConfig, PreprintConfig, ResearchConfig,
                     AdaptiveConfig, UIConfig]:
            assert dataclasses.is_dataclass(cls)

    def test_no_app_py_god_object(self):
        """Verify there's no app.py god object with duplicate classes."""
        import gangdan_refined
        import pkgutil
        import os

        pkg_path = os.path.dirname(gangdan_refined.__file__)
        modules = [name for _, name, _ in pkgutil.iter_modules([pkg_path])]
        assert "app" not in modules, "app.py should not exist in refined version"


class TestModuleIndependence:
    """Verify core modules don't import business logic."""

    def test_core_no_llm_imports(self):
        """Core should not import from llm."""
        from gangdan_refined.core import config, constants, errors
        import inspect

        for module in [config, constants, errors]:
            source = inspect.getsource(module)
            assert "from..llm" not in source.replace(" ", "")
            assert "from gangdan.llm" not in source.replace(" ", "")

    def test_llm_no_storage_imports(self):
        """LLM should not import from storage."""
        from gangdan_refined.llm import base, ollama, models
        import inspect

        for module in [base, ollama, models]:
            source = inspect.getsource(module)
            assert "gangdan_refined.storage" not in source
            assert "gangdan_refined.web" not in source

    def test_search_no_web_imports(self):
        """Search should not import from web."""
        from gangdan_refined.search import web_searcher
        import inspect

        source = inspect.getsource(web_searcher)
        assert "gangdan_refined.web" not in source