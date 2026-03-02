"""Tests for gangdan.cli_app CLI commands."""

import os
import sys
import json
import argparse
import pytest
from pathlib import Path
from io import StringIO
from unittest.mock import patch, MagicMock


class TestCLIConfigCommands:
    """Test CLI config get/set commands."""
    
    def test_config_get_all(self, temp_data_dir):
        """Test showing all configuration."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_config_get
        
        args = argparse.Namespace(key=None)
        result = cmd_config_get(args)
        
        assert result == 0
    
    def test_config_get_specific_key(self, temp_data_dir):
        """Test getting a specific config key."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_config_get
        
        args = argparse.Namespace(key="ollama_url")
        result = cmd_config_get(args)
        
        assert result == 0
    
    def test_config_get_unknown_key(self, temp_data_dir):
        """Test getting unknown config key."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_config_get
        
        args = argparse.Namespace(key="nonexistent_key")
        result = cmd_config_get(args)
        
        assert result == 1
    
    def test_config_set(self, temp_data_dir):
        """Test setting a config value."""
        import gangdan.cli_app as cli_module
        from gangdan.cli_app import cmd_config_set
        
        # Access the same CONFIG object that cli_app imported
        old_lang = cli_module.CONFIG.language
        
        args = argparse.Namespace(key="language", value="en")
        result = cmd_config_set(args)
        
        assert result == 0
        assert cli_module.CONFIG.language == "en"
        
        # Restore
        cli_module.CONFIG.language = old_lang
    
    def test_config_set_integer_key(self, temp_data_dir):
        """Test setting an integer config value."""
        import gangdan.cli_app as cli_module
        from gangdan.cli_app import cmd_config_set
        
        old_val = cli_module.CONFIG.top_k
        
        args = argparse.Namespace(key="top_k", value="20")
        result = cmd_config_set(args)
        
        assert result == 0
        assert cli_module.CONFIG.top_k == 20
        
        # Restore
        cli_module.CONFIG.top_k = old_val
    
    def test_config_set_invalid_integer(self, temp_data_dir):
        """Test setting invalid integer value."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_config_set
        
        args = argparse.Namespace(key="top_k", value="not_a_number")
        result = cmd_config_set(args)
        
        assert result == 1
    
    def test_config_set_unknown_key(self, temp_data_dir):
        """Test setting unknown config key."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_config_set
        
        args = argparse.Namespace(key="nonexistent", value="test")
        result = cmd_config_set(args)
        
        assert result == 1
    
    def test_config_set_missing_args(self, temp_data_dir):
        """Test setting config with missing arguments."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_config_set
        
        args = argparse.Namespace(key=None, value=None)
        result = cmd_config_set(args)
        
        assert result == 1
    
    def test_config_set_strict_kb_mode(self, temp_data_dir):
        """Test setting boolean strict_kb_mode."""
        import gangdan.cli_app as cli_module
        from gangdan.cli_app import cmd_config_set
        
        old_val = cli_module.CONFIG.strict_kb_mode
        
        args = argparse.Namespace(key="strict_kb_mode", value="true")
        result = cmd_config_set(args)
        
        assert result == 0
        assert cli_module.CONFIG.strict_kb_mode == True
        
        # Restore
        cli_module.CONFIG.strict_kb_mode = old_val


class TestCLIConversationCommands:
    """Test CLI conversation commands."""
    
    def test_conversation_save(self, temp_data_dir):
        """Test saving conversation."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        # Reset global instances
        cli_module._conversation = None
        
        from gangdan.cli_app import cmd_conversation_save, get_conversation
        
        # Add some messages first
        conv = get_conversation()
        conv.add("user", "Hello")
        conv.add("assistant", "Hi there!")
        
        filepath = str(temp_data_dir / "test_conv.json")
        args = argparse.Namespace(file=filepath)
        result = cmd_conversation_save(args)
        
        assert result == 0
        assert Path(filepath).exists()
        
        data = json.loads(Path(filepath).read_text())
        assert data["version"] == "1.0"
        assert len(data["messages"]) == 2
        
        conv.shutdown()
    
    def test_conversation_load(self, temp_data_dir, sample_conversation):
        """Test loading conversation."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._conversation = None
        
        from gangdan.cli_app import cmd_conversation_load, get_conversation
        
        filepath = temp_data_dir / "load_conv.json"
        filepath.write_text(json.dumps(sample_conversation))
        
        args = argparse.Namespace(file=str(filepath))
        result = cmd_conversation_load(args)
        
        assert result == 0
        
        conv = get_conversation()
        assert len(conv.get_all()) == 4
        
        conv.shutdown()
    
    def test_conversation_load_missing_file(self, temp_data_dir):
        """Test loading non-existent conversation file."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._conversation = None
        
        from gangdan.cli_app import cmd_conversation_load
        
        args = argparse.Namespace(file="/nonexistent/path.json")
        result = cmd_conversation_load(args)
        
        assert result == 1
    
    def test_conversation_load_no_file_arg(self, temp_data_dir):
        """Test loading with no file argument."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_conversation_load
        
        args = argparse.Namespace(file=None)
        result = cmd_conversation_load(args)
        
        assert result == 1
    
    def test_conversation_clear(self, temp_data_dir):
        """Test clearing conversation."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._conversation = None
        
        from gangdan.cli_app import cmd_conversation_clear, get_conversation
        
        conv = get_conversation()
        conv.add("user", "Test")
        
        args = argparse.Namespace()
        result = cmd_conversation_clear(args)
        
        assert result == 0
        assert len(conv.get_all()) == 0
        
        conv.shutdown()


class TestCLIChatCommand:
    """Test CLI chat command."""
    
    def test_chat_no_message(self, temp_data_dir):
        """Test chat without a message."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_chat
        
        args = argparse.Namespace(message=None, kb=None, web=False, no_stream=False)
        result = cmd_chat(args)
        
        assert result == 1
    
    def test_chat_empty_message(self, temp_data_dir):
        """Test chat with empty message."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_chat
        
        args = argparse.Namespace(message=[], kb=None, web=False, no_stream=False)
        result = cmd_chat(args)
        
        assert result == 1
    
    def test_chat_no_model_configured(self, temp_data_dir):
        """Test chat when no model is configured."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        config_module.CONFIG.chat_model = ""
        
        from gangdan.cli_app import cmd_chat
        
        args = argparse.Namespace(message=["Hello"], kb=None, web=False, no_stream=False)
        result = cmd_chat(args)
        
        assert result == 1


class TestCLIRunCommand:
    """Test CLI run command."""
    
    def test_run_no_command(self, temp_data_dir):
        """Test run without command."""
        from gangdan.cli_app import cmd_run
        
        args = argparse.Namespace(command=None)
        result = cmd_run(args)
        
        assert result == 1
    
    def test_run_empty_command(self, temp_data_dir):
        """Test run with empty command."""
        from gangdan.cli_app import cmd_run
        
        args = argparse.Namespace(command=[])
        result = cmd_run(args)
        
        assert result == 1
    
    def test_run_safe_command(self, temp_data_dir):
        """Test running a safe command."""
        from gangdan.cli_app import cmd_run
        
        args = argparse.Namespace(command=["echo", "hello"])
        result = cmd_run(args)
        
        assert result == 0
    
    def test_run_dangerous_command_blocked(self, temp_data_dir):
        """Test that dangerous commands are blocked."""
        from gangdan.cli_app import cmd_run
        
        dangerous_commands = [
            ["rm", "-rf", "/"],
            ["shutdown"],
            ["reboot"],
        ]
        
        for cmd in dangerous_commands:
            args = argparse.Namespace(command=cmd)
            result = cmd_run(args)
            assert result == 1, f"Dangerous command not blocked: {cmd}"


class TestCLIAICommand:
    """Test CLI AI command generation."""
    
    def test_ai_no_description(self, temp_data_dir):
        """Test AI command without description."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_ai
        
        args = argparse.Namespace(description=None, run=False)
        result = cmd_ai(args)
        
        assert result == 1
    
    def test_ai_empty_description(self, temp_data_dir):
        """Test AI command with empty description."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_ai
        
        args = argparse.Namespace(description=[], run=False)
        result = cmd_ai(args)
        
        assert result == 1
    
    def test_ai_no_model(self, temp_data_dir):
        """Test AI command when no model is configured."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        config_module.CONFIG.chat_model = ""
        
        from gangdan.cli_app import cmd_ai
        
        args = argparse.Namespace(description=["list", "files"], run=False)
        result = cmd_ai(args)
        
        assert result == 1


class TestCLIDocsCommands:
    """Test CLI docs commands."""
    
    def test_docs_list(self, temp_data_dir):
        """Test listing downloaded docs."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._doc_manager = None
        cli_module._chroma = None
        cli_module._ollama = None
        
        from gangdan.cli_app import cmd_docs_list
        
        args = argparse.Namespace()
        result = cmd_docs_list(args)
        
        assert result == 0
    
    def test_docs_download_no_sources(self, temp_data_dir):
        """Test docs download with no sources."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_docs_download
        
        args = argparse.Namespace(sources=None)
        result = cmd_docs_download(args)
        
        assert result == 1
    
    def test_docs_download_unknown_source(self, temp_data_dir):
        """Test docs download with unknown source."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._doc_manager = None
        cli_module._chroma = None
        cli_module._ollama = None
        
        from gangdan.cli_app import cmd_docs_download
        
        args = argparse.Namespace(sources=["unknown_source_xyz"])
        result = cmd_docs_download(args)
        
        assert result == 0  # Still returns 0, just prints warning
    
    def test_docs_index_no_sources(self, temp_data_dir):
        """Test docs index with no sources."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_docs_index
        
        args = argparse.Namespace(sources=None)
        result = cmd_docs_index(args)
        
        assert result == 1


class TestCLIKBCommands:
    """Test CLI KB commands."""
    
    def test_kb_list(self, temp_data_dir):
        """Test KB list command."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._chroma = None
        
        from gangdan.cli_app import cmd_kb_list
        
        args = argparse.Namespace()
        result = cmd_kb_list(args)
        
        assert result == 0
    
    def test_kb_search_no_query(self, temp_data_dir):
        """Test KB search without query."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cmd_kb_search
        
        args = argparse.Namespace(query=None, kb=None)
        result = cmd_kb_search(args)
        
        assert result == 1
    
    def test_kb_search_no_embedding_model(self, temp_data_dir):
        """Test KB search when no embedding model is configured."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        config_module.CONFIG.embedding_model = ""
        
        import gangdan.cli_app as cli_module
        cli_module._chroma = None
        
        from gangdan.cli_app import cmd_kb_search
        
        args = argparse.Namespace(query=["test", "query"], kb=None)
        result = cmd_kb_search(args)
        
        assert result == 1


class TestCLIMain:
    """Test CLI main entry point and argument parsing."""
    
    def test_cli_main_no_args(self, temp_data_dir):
        """Test CLI with no arguments shows help."""
        from gangdan.cli_app import cli_main
        
        result = cli_main([])
        assert result == 1
    
    def test_cli_main_config_get(self, temp_data_dir):
        """Test CLI config get subcommand."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cli_main
        
        result = cli_main(["config", "get"])
        assert result == 0
    
    def test_cli_main_config_set(self, temp_data_dir):
        """Test CLI config set subcommand."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        from gangdan.cli_app import cli_main
        
        result = cli_main(["config", "set", "language", "en"])
        assert result == 0
    
    def test_cli_main_conversation_clear(self, temp_data_dir):
        """Test CLI conversation clear subcommand."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._conversation = None
        
        from gangdan.cli_app import cli_main
        
        result = cli_main(["conversation", "clear"])
        
        assert result == 0
        
        if cli_module._conversation:
            cli_module._conversation.shutdown()
    
    def test_cli_main_run_echo(self, temp_data_dir):
        """Test CLI run echo command."""
        from gangdan.cli_app import cli_main
        
        result = cli_main(["run", "echo", "test"])
        assert result == 0
    
    def test_cli_main_docs_list(self, temp_data_dir):
        """Test CLI docs list subcommand."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._doc_manager = None
        cli_module._chroma = None
        cli_module._ollama = None
        
        from gangdan.cli_app import cli_main
        
        result = cli_main(["docs", "list"])
        assert result == 0
    
    def test_cli_main_kb_list(self, temp_data_dir):
        """Test CLI kb list subcommand."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._chroma = None
        
        from gangdan.cli_app import cli_main
        
        result = cli_main(["kb", "list"])
        assert result == 0
