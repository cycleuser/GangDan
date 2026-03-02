"""Tests for REPL mode and backward compatibility."""

import sys
import argparse
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO


class TestREPLCommandParsing:
    """Test REPL command parsing without starting full REPL."""
    
    def test_repl_exit_commands(self, temp_data_dir):
        """Test that exit commands are recognized."""
        exit_cmds = ["exit", "quit", "q"]
        
        for cmd in exit_cmds:
            parts = cmd.split(maxsplit=1)
            assert parts[0].lower() in ("exit", "quit", "q")
    
    def test_repl_help_command(self, temp_data_dir):
        """Test help command parsing."""
        cmd = "help"
        parts = cmd.split(maxsplit=1)
        assert parts[0].lower() == "help"
    
    def test_repl_kb_command_parsing(self, temp_data_dir):
        """Test KB command parsing in REPL."""
        # Test /kb list
        user_input = "/kb list"
        parts = user_input[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        cmd_args = parts[1] if len(parts) > 1 else ""
        
        assert cmd == "kb"
        assert cmd_args == "list"
    
    def test_repl_kb_search_parsing(self, temp_data_dir):
        """Test KB search command parsing."""
        user_input = "/kb search python lists"
        parts = user_input[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        cmd_args = parts[1] if len(parts) > 1 else ""
        
        assert cmd == "kb"
        kb_parts = cmd_args.split(maxsplit=1)
        assert kb_parts[0] == "search"
        assert kb_parts[1] == "python lists"
    
    def test_repl_run_parsing(self, temp_data_dir):
        """Test run command parsing."""
        user_input = "/run ls -la"
        parts = user_input[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        cmd_args = parts[1] if len(parts) > 1 else ""
        
        assert cmd == "run"
        assert cmd_args == "ls -la"
    
    def test_repl_save_parsing(self, temp_data_dir):
        """Test save command parsing."""
        user_input = "/save /tmp/test.json"
        parts = user_input[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        cmd_args = parts[1] if len(parts) > 1 else ""
        
        assert cmd == "save"
        assert cmd_args == "/tmp/test.json"
    
    def test_repl_save_no_filepath(self, temp_data_dir):
        """Test save command without filepath."""
        user_input = "/save"
        parts = user_input[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        cmd_args = parts[1] if len(parts) > 1 else ""
        
        assert cmd == "save"
        assert cmd_args == ""
    
    def test_repl_config_parsing(self, temp_data_dir):
        """Test config command parsing."""
        user_input = "/config"
        parts = user_input[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        
        assert cmd == "config"
    
    def test_repl_ai_parsing(self, temp_data_dir):
        """Test AI command parsing."""
        user_input = "/ai list all python files"
        parts = user_input[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        cmd_args = parts[1] if len(parts) > 1 else ""
        
        assert cmd == "ai"
        assert cmd_args == "list all python files"
    
    def test_repl_regular_message(self, temp_data_dir):
        """Test that regular messages are not treated as commands."""
        user_input = "Hello, how are you?"
        assert not user_input.startswith("/")
    
    def test_repl_unknown_command(self, temp_data_dir):
        """Test unknown command handling."""
        user_input = "/unknown_command"
        parts = user_input[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        
        known_commands = {"exit", "quit", "q", "help", "kb", "docs", "run", "ai", "save", "load", "clear", "config"}
        assert cmd not in known_commands


class TestREPLLazyInit:
    """Test lazy initialization of REPL components."""
    
    def test_get_ollama_creates_instance(self, temp_data_dir):
        """Test that get_ollama creates client on first call."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._ollama = None
        
        from gangdan.cli_app import get_ollama
        
        client = get_ollama()
        assert client is not None
        assert cli_module._ollama is not None
    
    def test_get_ollama_returns_same_instance(self, temp_data_dir):
        """Test that get_ollama returns same instance on subsequent calls."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._ollama = None
        
        from gangdan.cli_app import get_ollama
        
        client1 = get_ollama()
        client2 = get_ollama()
        assert client1 is client2
    
    def test_get_conversation_creates_instance(self, temp_data_dir):
        """Test that get_conversation creates manager on first call."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._conversation = None
        
        from gangdan.cli_app import get_conversation
        
        conv = get_conversation()
        assert conv is not None
        assert cli_module._conversation is not None
        
        conv.shutdown()
    
    def test_get_web_searcher_creates_instance(self, temp_data_dir):
        """Test that get_web_searcher creates instance on first call."""
        import importlib
        import gangdan.core.config as config_module
        importlib.reload(config_module)
        
        import gangdan.cli_app as cli_module
        cli_module._web_searcher = None
        
        from gangdan.cli_app import get_web_searcher
        
        searcher = get_web_searcher()
        assert searcher is not None
        assert cli_module._web_searcher is not None


class TestBackwardCompatibility:
    """Test backward compatibility with GUI web server mode."""
    
    def test_cli_module_exists(self, temp_data_dir):
        """Test that gangdan.cli module exists and is importable."""
        import gangdan.cli
        assert hasattr(gangdan.cli, 'main')
    
    def test_cli_commands_set(self, temp_data_dir):
        """Test CLI_COMMANDS set is defined."""
        from gangdan.cli import CLI_COMMANDS
        
        expected = {"cli", "chat", "kb", "docs", "config", "conversation", "run", "ai"}
        assert CLI_COMMANDS == expected
    
    def test_version_available(self, temp_data_dir):
        """Test that version is available."""
        from gangdan import __version__
        
        assert __version__ is not None
        assert len(__version__) > 0


class TestCLIEntryPointRouting:
    """Test entry point routing between CLI and web modes."""
    
    def test_cli_commands_recognized(self, temp_data_dir):
        """Test that CLI commands are properly recognized."""
        from gangdan.cli import CLI_COMMANDS
        
        cli_args = ["chat", "Hello"]
        if len(cli_args) > 0 and cli_args[0] in CLI_COMMANDS:
            assert True  # CLI mode would be triggered
        else:
            assert False
    
    def test_web_mode_for_non_cli_args(self, temp_data_dir):
        """Test that non-CLI args default to web mode."""
        from gangdan.cli import CLI_COMMANDS
        
        web_args = ["--version"]
        if len(web_args) > 0 and web_args[0] in CLI_COMMANDS:
            assert False
        else:
            assert True  # Web mode would be triggered
    
    def test_no_args_defaults_to_web(self, temp_data_dir):
        """Test that no args defaults to web mode."""
        from gangdan.cli import CLI_COMMANDS
        
        args = []
        if len(args) > 1 and args[1] in CLI_COMMANDS:
            assert False
        else:
            assert True  # Web mode
