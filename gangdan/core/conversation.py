"""Conversation manager with auto-persistence for CLI."""

import json
import threading
import queue
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from gangdan.core.config import DATA_DIR


class ConversationManager:
    """Manages conversation history with optional auto-persistence."""
    
    def __init__(self, max_history: int = 20, auto_save: bool = False, save_path: Optional[Path] = None):
        self.max_history = max_history
        self._messages: List[Dict] = []
        self._auto_save = auto_save
        self._save_path = save_path or (DATA_DIR / "cli_conversation.json")
        self._save_queue: Optional[queue.Queue] = None
        self._save_thread: Optional[threading.Thread] = None
        
        if auto_save:
            self._start_save_thread()
    
    def _start_save_thread(self):
        """Start background thread for async saves."""
        self._save_queue = queue.Queue()
        
        def worker():
            while True:
                try:
                    item = self._save_queue.get()
                    if item is None:  # Shutdown signal
                        break
                    self._write_to_disk(item)
                except Exception as e:
                    import sys
                    print(f"[Conversation] Auto-save error: {e}", file=sys.stderr)
        
        self._save_thread = threading.Thread(target=worker, daemon=True)
        self._save_thread.start()
    
    def _write_to_disk(self, messages: List[Dict]):
        """Write messages to disk."""
        self._save_path.parent.mkdir(parents=True, exist_ok=True)
        content = {
            "version": "1.0",
            "app": "GangDan",
            "exported_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            "messages": messages
        }
        self._save_path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    
    def add(self, role: str, content: str):
        """Add a message to the conversation."""
        self._messages.append({"role": role, "content": content})
        if len(self._messages) > self.max_history:
            self._messages = self._messages[-self.max_history:]
        
        # Trigger auto-save if enabled
        if self._auto_save and self._save_queue:
            self._save_queue.put(self._messages.copy())
    
    def get_messages(self, limit: int = 10) -> List[Dict]:
        """Get the last N messages."""
        return self._messages[-limit:]
    
    def get_all(self) -> List[Dict]:
        """Get all messages."""
        return self._messages.copy()
    
    def clear(self):
        """Clear all messages."""
        self._messages.clear()
        if self._auto_save and self._save_queue:
            self._save_queue.put([])
    
    def set_messages(self, messages: List[Dict]):
        """Replace all messages (used when loading)."""
        self._messages = messages.copy()
        if len(self._messages) > self.max_history:
            self._messages = self._messages[-self.max_history:]
        if self._auto_save and self._save_queue:
            self._save_queue.put(self._messages.copy())
    
    def load_from_file(self, filepath: Optional[Path] = None) -> bool:
        """Load conversation from a JSON file."""
        path = filepath or self._save_path
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            messages = data.get("messages", [])
            if isinstance(messages, list):
                self._messages = messages
                return True
        except Exception:
            pass
        return False
    
    def save_to_file(self, filepath: Path) -> bool:
        """Save conversation to a specific file."""
        try:
            self._write_to_disk(self._messages)
            return True
        except Exception:
            return False
    
    def load_auto_saved(self) -> int:
        """Load auto-saved conversation from default location.
        
        Returns the number of messages loaded, or 0 if none.
        """
        if self.load_from_file(self._save_path):
            return len(self._messages)
        return 0
    
    def shutdown(self):
        """Shutdown the auto-save thread gracefully."""
        if self._save_queue:
            self._save_queue.put(None)
        if self._save_thread:
            self._save_thread.join(timeout=2)
