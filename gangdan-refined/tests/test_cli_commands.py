"""CLI command integration tests for gd-* tools.

Tests each CLI command's main() function to verify argument parsing,
help output, JSON output mode, and error handling.
"""

import json
import sys
import pytest
from io import StringIO
from unittest.mock import patch


class TestGDConfig:
    def test_show_json(self):
        from gangdan_refined.commands.config import main
        with patch("sys.argv", ["gd-config", "--json", "show"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                main()
                output = mock_out.getvalue()
        data = json.loads(output)
        assert data["success"] is True
        assert "config" in data

    def test_get_key_json(self):
        from gangdan_refined.commands.config import main
        with patch("sys.argv", ["gd-config", "--json", "get", "llm.chat_model"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                main()
                output = mock_out.getvalue()
        data = json.loads(output)
        assert data["success"] is True
        assert "value" in data

    def test_set_and_restore(self):
        from gangdan_refined.commands.config import main
        with patch("sys.argv", ["gd-config", "--json", "set", "llm.chat_model=test-model-cli"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                main()
                output = mock_out.getvalue()
        data = json.loads(output)
        assert data["success"] is True
        assert data["value"] == "test-model-cli"

        with patch("sys.argv", ["gd-config", "--json", "set", "llm.chat_model=qwen2.5:7b"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                main()

    def test_providers_json(self):
        from gangdan_refined.commands.config import main
        with patch("sys.argv", ["gd-config", "--json", "providers"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                main()
                output = mock_out.getvalue()
        data = json.loads(output)
        assert data["success"] is True
        assert "providers" in data

    def test_no_action_exits(self):
        from gangdan_refined.commands.config import main
        with patch("sys.argv", ["gd-config"]):
            with pytest.raises(SystemExit):
                main()


class TestGDSearchCLI:
    def test_help_exits(self):
        from gangdan_refined.commands.search import main
        with patch("sys.argv", ["gd-search", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestGDKBCLI:
    def test_help_exits(self):
        from gangdan_refined.commands.kb import main
        with patch("sys.argv", ["gd-kb", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestGDModelsCLI:
    def test_help_exits(self):
        from gangdan_refined.commands.models import main
        with patch("sys.argv", ["gd-models", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestGDChatCLI:
    def test_help_exits(self):
        from gangdan_refined.commands.chat import main
        with patch("sys.argv", ["gd-chat", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestGDTranslateCLI:
    def test_help_exits(self):
        from gangdan_refined.commands.translate import main
        with patch("sys.argv", ["gd-translate", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestGDSummarizeCLI:
    def test_help_exits(self):
        from gangdan_refined.commands.summarize import main
        with patch("sys.argv", ["gd-summarize", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestGDAskCLI:
    def test_help_exits(self):
        from gangdan_refined.commands.ask import main
        with patch("sys.argv", ["gd-ask", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestGDEmbedCLI:
    def test_help_exits(self):
        from gangdan_refined.commands.embed import main
        with patch("sys.argv", ["gd-embed", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestGDConvertCLI:
    def test_help_exits(self):
        from gangdan_refined.commands.convert import main
        with patch("sys.argv", ["gd-convert", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestGDDocsCLI:
    def test_help_exits(self):
        from gangdan_refined.commands.docs import main
        with patch("sys.argv", ["gd-docs", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestGDWebCLI:
    def test_help_exits(self):
        from gangdan_refined.commands.web import main
        with patch("sys.argv", ["gd-web", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0