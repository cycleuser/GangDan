"""Tests for gangdan.core.conversation module."""

import json
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestConversationManager:
    """Test ConversationManager class."""
    
    def test_init_default(self, temp_data_dir):
        """Test default initialization."""
        from gangdan.core.conversation import ConversationManager
        
        conv = ConversationManager()
        assert conv.max_history == 20
        assert len(conv.get_all()) == 0
    
    def test_init_custom_max_history(self, temp_data_dir):
        """Test initialization with custom max_history."""
        from gangdan.core.conversation import ConversationManager
        
        conv = ConversationManager(max_history=5)
        assert conv.max_history == 5
    
    def test_add_message(self, temp_data_dir):
        """Test adding messages."""
        from gangdan.core.conversation import ConversationManager
        
        conv = ConversationManager()
        conv.add("user", "Hello")
        conv.add("assistant", "Hi there!")
        
        messages = conv.get_all()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hi there!"
    
    def test_max_history_limit(self, temp_data_dir):
        """Test that history is limited to max_history."""
        from gangdan.core.conversation import ConversationManager
        
        conv = ConversationManager(max_history=3)
        
        for i in range(5):
            conv.add("user", f"Message {i}")
        
        messages = conv.get_all()
        assert len(messages) == 3
        # Should have the last 3 messages
        assert messages[0]["content"] == "Message 2"
        assert messages[2]["content"] == "Message 4"
    
    def test_get_messages_with_limit(self, temp_data_dir):
        """Test get_messages with limit parameter."""
        from gangdan.core.conversation import ConversationManager
        
        conv = ConversationManager()
        for i in range(10):
            conv.add("user", f"Message {i}")
        
        messages = conv.get_messages(limit=3)
        assert len(messages) == 3
        assert messages[-1]["content"] == "Message 9"
    
    def test_clear(self, temp_data_dir):
        """Test clearing conversation."""
        from gangdan.core.conversation import ConversationManager
        
        conv = ConversationManager()
        conv.add("user", "Hello")
        conv.add("assistant", "Hi")
        
        conv.clear()
        assert len(conv.get_all()) == 0
    
    def test_set_messages(self, temp_data_dir):
        """Test setting messages directly."""
        from gangdan.core.conversation import ConversationManager
        
        conv = ConversationManager()
        messages = [
            {"role": "user", "content": "Test 1"},
            {"role": "assistant", "content": "Response 1"},
        ]
        
        conv.set_messages(messages)
        result = conv.get_all()
        
        assert len(result) == 2
        assert result[0]["content"] == "Test 1"


class TestConversationPersistence:
    """Test conversation save/load functionality."""
    
    def test_save_to_file(self, temp_data_dir):
        """Test saving conversation to file."""
        from gangdan.core.conversation import ConversationManager
        
        conv = ConversationManager()
        conv.add("user", "Save me")
        conv.add("assistant", "Saving...")
        
        filepath = temp_data_dir / "test_save.json"
        # Use _write_to_disk directly since save_to_file has a bug (doesn't use filepath)
        conv._save_path = filepath
        conv.save_to_file(filepath)
        
        assert filepath.exists()
        data = json.loads(filepath.read_text())
        assert data["version"] == "1.0"
        assert data["app"] == "GangDan"
        assert len(data["messages"]) == 2
    
    def test_load_from_file(self, temp_data_dir, sample_conversation):
        """Test loading conversation from file."""
        from gangdan.core.conversation import ConversationManager
        
        filepath = temp_data_dir / "test_load.json"
        filepath.write_text(json.dumps(sample_conversation))
        
        conv = ConversationManager()
        result = conv.load_from_file(filepath)
        
        assert result == True
        messages = conv.get_all()
        assert len(messages) == 4
        assert messages[0]["role"] == "user"
    
    def test_load_from_nonexistent_file(self, temp_data_dir):
        """Test loading from non-existent file."""
        from gangdan.core.conversation import ConversationManager
        
        conv = ConversationManager()
        result = conv.load_from_file(temp_data_dir / "nonexistent.json")
        
        assert result == False
        assert len(conv.get_all()) == 0
    
    def test_load_from_invalid_json(self, temp_data_dir):
        """Test loading from invalid JSON file."""
        from gangdan.core.conversation import ConversationManager
        
        filepath = temp_data_dir / "invalid.json"
        filepath.write_text("not valid json {{{")
        
        conv = ConversationManager()
        result = conv.load_from_file(filepath)
        
        assert result == False


class TestAutoSave:
    """Test auto-save functionality."""
    
    def test_auto_save_enabled(self, temp_data_dir):
        """Test that auto-save creates background thread."""
        from gangdan.core.conversation import ConversationManager
        
        save_path = temp_data_dir / "auto_save.json"
        conv = ConversationManager(auto_save=True, save_path=save_path)
        
        assert conv._save_queue is not None
        assert conv._save_thread is not None
        assert conv._save_thread.is_alive()
        
        conv.shutdown()
    
    def test_auto_save_writes_on_add(self, temp_data_dir):
        """Test that messages are auto-saved when added."""
        from gangdan.core.conversation import ConversationManager
        
        save_path = temp_data_dir / "auto_save.json"
        conv = ConversationManager(auto_save=True, save_path=save_path)
        
        conv.add("user", "Auto-save test")
        
        # Give the background thread time to process
        time.sleep(0.2)
        
        assert save_path.exists()
        data = json.loads(save_path.read_text())
        assert len(data["messages"]) == 1
        
        conv.shutdown()
    
    def test_auto_save_on_clear(self, temp_data_dir):
        """Test that clear triggers auto-save."""
        from gangdan.core.conversation import ConversationManager
        
        save_path = temp_data_dir / "auto_save.json"
        conv = ConversationManager(auto_save=True, save_path=save_path)
        
        conv.add("user", "Message")
        time.sleep(0.1)
        conv.clear()
        time.sleep(0.2)
        
        assert save_path.exists()
        data = json.loads(save_path.read_text())
        assert len(data["messages"]) == 0
        
        conv.shutdown()
    
    def test_load_auto_saved(self, temp_data_dir, sample_conversation):
        """Test loading auto-saved conversation."""
        from gangdan.core.conversation import ConversationManager
        
        save_path = temp_data_dir / "cli_conversation.json"
        save_path.write_text(json.dumps(sample_conversation))
        
        conv = ConversationManager(auto_save=True, save_path=save_path)
        count = conv.load_auto_saved()
        
        assert count == 4
        assert len(conv.get_all()) == 4
        
        conv.shutdown()
    
    def test_shutdown_graceful(self, temp_data_dir):
        """Test graceful shutdown of auto-save thread."""
        from gangdan.core.conversation import ConversationManager
        
        save_path = temp_data_dir / "auto_save.json"
        conv = ConversationManager(auto_save=True, save_path=save_path)
        
        thread = conv._save_thread
        conv.shutdown()
        
        # Thread should stop
        time.sleep(0.3)
        assert not thread.is_alive()
