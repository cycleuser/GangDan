"""
Comprehensive tests for GangDan unified API, tools, and CLI flags.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestToolResult:
    def test_success_result(self):
        from gangdan.api import ToolResult
        r = ToolResult(success=True, data="reply text", metadata={"model": "x"})
        assert r.success is True
        assert r.data == "reply text"

    def test_failure_result(self):
        from gangdan.api import ToolResult
        r = ToolResult(success=False, error="no model")
        assert r.success is False
        assert r.error == "no model"

    def test_to_dict(self):
        from gangdan.api import ToolResult
        r = ToolResult(success=True, data="hello")
        d = r.to_dict()
        assert d["success"] is True
        assert d["data"] == "hello"
        assert d["error"] is None

    def test_default_metadata_isolation(self):
        from gangdan.api import ToolResult
        r1 = ToolResult(success=True)
        r2 = ToolResult(success=True)
        r1.metadata["k"] = 1
        assert "k" not in r2.metadata


class TestChatAPI:
    @patch("gangdan.core.ollama_client.OllamaClient")
    @patch("gangdan.core.config.load_config")
    @patch("gangdan.core.config.CONFIG")
    def test_chat_success(self, mock_cfg, mock_load, mock_client_cls):
        from gangdan.api import chat
        mock_cfg.ollama_url = "http://localhost:11434"
        mock_cfg.chat_model = "test"
        instance = MagicMock()
        instance.chat.return_value = "hello world"
        mock_client_cls.return_value = instance

        result = chat("hi", model="test")
        assert result.success is True
        assert result.data == "hello world"

    def test_chat_returns_toolresult(self):
        from gangdan.api import chat, ToolResult
        # Even if it fails (no Ollama), should return ToolResult
        result = chat("test message")
        assert isinstance(result, ToolResult)


class TestIndexDocumentsAPI:
    def test_invalid_directory(self):
        from gangdan.api import index_documents
        result = index_documents("/nonexistent/path/xyz")
        assert result.success is False
        assert "Not a directory" in result.error

    def test_accepts_path_object(self):
        from gangdan.api import index_documents
        result = index_documents(Path("/nonexistent"))
        assert result.success is False


class TestToolsSchema:
    def test_tools_is_list(self):
        from gangdan.tools import TOOLS
        assert isinstance(TOOLS, list)
        assert len(TOOLS) == 2

    def test_tool_names(self):
        from gangdan.tools import TOOLS
        names = [t["function"]["name"] for t in TOOLS]
        assert "gangdan_chat" in names
        assert "gangdan_index_documents" in names

    def test_tool_structure(self):
        from gangdan.tools import TOOLS
        for tool in TOOLS:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            assert func["parameters"]["type"] == "object"

    def test_required_fields_exist(self):
        from gangdan.tools import TOOLS
        for tool in TOOLS:
            func = tool["function"]
            props = func["parameters"]["properties"]
            for req in func["parameters"]["required"]:
                assert req in props


class TestToolsDispatch:
    def test_dispatch_unknown_tool(self):
        from gangdan.tools import dispatch
        with pytest.raises(ValueError, match="Unknown tool"):
            dispatch("nonexistent", {})

    def test_dispatch_json_string_args(self):
        from gangdan.tools import dispatch
        # This will likely fail connecting to Ollama, but should return dict
        args = json.dumps({"message": "test"})
        result = dispatch("gangdan_chat", args)
        assert isinstance(result, dict)
        assert "success" in result

    def test_dispatch_index_invalid_dir(self):
        from gangdan.tools import dispatch
        result = dispatch("gangdan_index_documents", {"directory": "/no/dir"})
        assert isinstance(result, dict)
        assert result["success"] is False


class TestCLIFlags:
    def _run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "gangdan"] + list(args),
            capture_output=True, text=True, timeout=15,
        )

    def test_version_flag(self):
        r = self._run_cli("-V")
        assert r.returncode == 0
        assert "gangdan" in r.stdout.lower()

    def test_help_contains_unified_flags(self):
        r = self._run_cli("--help")
        assert r.returncode == 0
        assert "--json" in r.stdout
        assert "--quiet" in r.stdout or "-q" in r.stdout
        assert "--verbose" in r.stdout or "-v" in r.stdout


class TestPackageExports:
    def test_version(self):
        import gangdan
        assert hasattr(gangdan, "__version__")

    def test_toolresult(self):
        from gangdan import ToolResult
        assert callable(ToolResult)

    def test_chat_exported(self):
        from gangdan import chat
        assert callable(chat)

    def test_index_documents_exported(self):
        from gangdan import index_documents
        assert callable(index_documents)
