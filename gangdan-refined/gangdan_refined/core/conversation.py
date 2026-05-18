"""Conversation manager with auto-persistence."""

from __future__ import annotations

import json
import logging
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from gangdan_refined.core.config import DATA_DIR

logger = logging.getLogger(__name__)
DEFAULT_MAX_HISTORY = 20
DEFAULT_SAVE_PATH = "cli_conversation.json"


class ConversationManager:
    """Manages conversation history with optional auto-persistence."""

    def __init__(self, max_history: int = DEFAULT_MAX_HISTORY,
                 auto_save: bool = False, save_path: Optional[Path] = None) -> None:
        self.max_history = max_history
        self._messages: List[Dict[str, str]] = []
        self._auto_save = auto_save
        self._save_path = save_path or (DATA_DIR / DEFAULT_SAVE_PATH)
        self._save_queue: Optional[queue.Queue] = None
        self._save_thread: Optional[threading.Thread] = None
        if auto_save:
            self._start_save_thread()

    def _start_save_thread(self) -> None:
        self._save_queue = queue.Queue()
        def worker() -> None:
            while True:
                try:
                    item = self._save_queue.get()
                    if item is None:
                        break
                    self._write_to_disk(item)
                except Exception as e:
                    logger.error("Auto-save error: %s", str(e))
        self._save_thread = threading.Thread(target=worker, daemon=True)
        self._save_thread.start()

    def _write_to_disk(self, messages: List[Dict[str, Any]]) -> None:
        self._save_path.parent.mkdir(parents=True, exist_ok=True)
        content = {
            "version": "1.0", "app": "GangDan Refined",
            "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "messages": messages,
        }
        self._save_path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})
        if len(self._messages) > self.max_history:
            self._messages = self._messages[-self.max_history:]
        if self._auto_save and self._save_queue:
            self._save_queue.put(self._messages.copy())

    def get_messages(self, limit: int = 10) -> List[Dict[str, str]]:
        return self._messages[-limit:]

    def get_all(self) -> List[Dict[str, str]]:
        return self._messages.copy()

    def clear(self) -> None:
        self._messages.clear()
        if self._auto_save and self._save_queue:
            self._save_queue.put([])

    def set_messages(self, messages: List[Dict[str, str]]) -> None:
        self._messages = messages.copy()
        if len(self._messages) > self.max_history:
            self._messages = self._messages[-self.max_history:]
        if self._auto_save and self._save_queue:
            self._save_queue.put(self._messages.copy())

    def load_from_file(self, filepath: Optional[Path] = None) -> bool:
        path = filepath or self._save_path
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            messages = data.get("messages", [])
            if isinstance(messages, list):
                self._messages = messages
                return True
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load conversation: %s", str(e))
        return False

    def save_to_file(self, filepath: Path) -> bool:
        try:
            self._write_to_disk(self._messages)
            return True
        except OSError as e:
            logger.error("Failed to save conversation: %s", str(e))
            return False

    def load_auto_saved(self) -> int:
        if self.load_from_file(self._save_path):
            return len(self._messages)
        return 0

    def shutdown(self) -> None:
        if self._save_queue:
            self._save_queue.put(None)
        if self._save_thread:
            self._save_thread.join(timeout=2)
