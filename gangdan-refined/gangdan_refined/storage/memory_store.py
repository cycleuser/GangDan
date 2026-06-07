"""Persistent memory system for GangDan.

File-based memory store using MEMORY.md for structured, human-editable memories
and history.jsonl for searchable conversation history.

Design inspired by nanobot's MemoryStore and DeepSeek-Reasonix's remember/forget pattern.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default memory directory relative to DATA_DIR
DEFAULT_MEMORY_DIR = "memory"

# Maximum history entries per session
DEFAULT_MAX_HISTORY = 1000

# Importance threshold for auto-remembering
AUTO_REMEMBER_THRESHOLD = 0.7


class MemoryStore:
    """File-based persistent memory store.

    Memories are stored as structured markdown entries in MEMORY.md.
    Conversation history is stored as JSONL in history.jsonl for searchability.

    Attributes
    ----------
    memory_dir : Path
        Directory containing memory files.
    memory_file : Path
        Path to MEMORY.md.
    history_file : Path
        Path to history.jsonl.
    """

    # Valid memory types
    MEMORY_TYPES = ("user", "research", "preference", "fact", "system")
    # Valid scopes
    SCOPES = ("project", "global")

    def __init__(self, data_dir: str | Path, scope: str = "project") -> None:
        """Initialize memory store.

        Parameters
        ----------
        data_dir : str or Path
            Base data directory (e.g., DATA_DIR).
        scope : str
            "project" or "global" — determines memory directory location.
        """
        base = Path(data_dir)
        if scope == "global":
            from pathlib import Path as _Path
            base = _Path.home() / ".gangdan"

        self.memory_dir = base / DEFAULT_MEMORY_DIR
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "history.jsonl"
        self._write_lock = threading.Lock()
        self._ensure_memory_file()

    def _ensure_memory_file(self) -> None:
        """Create MEMORY.md with header if it doesn't exist."""
        if not self.memory_file.exists():
            header = (
                "# GangDan Memory\n\n"
                "This file stores persistent knowledge across sessions.\n"
                "Memories are organized by type and importance.\n\n"
                "---\n\n"
            )
            self.memory_file.write_text(header, encoding="utf-8")

    # ------------------------------------------------------------------
    # Remember / Forget / List
    # ------------------------------------------------------------------

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Add a new memory entry.

        Parameters
        ----------
        content : str
            Memory content (markdown supported).
        memory_type : str
            One of: user, research, preference, fact, system.
        importance : float
            0.0-1.0 importance score. Higher = less likely to be pruned.
        metadata : dict, optional
            Additional metadata (e.g., source, tags, kb_id).

        Returns
        -------
        dict
            The created memory entry.
        """
        if memory_type not in self.MEMORY_TYPES:
            memory_type = "fact"
        importance = max(0.0, min(1.0, importance))

        now = datetime.now()
        entry_id = now.strftime("%Y%m%d_%H%M%S_%f")

        entry = {
            "id": entry_id,
            "type": memory_type,
            "content": content.strip(),
            "importance": importance,
            "created_at": now.isoformat(),
            "metadata": metadata or {},
        }

        # Append to MEMORY.md in human-readable format
        with self._write_lock:
            lines = self.memory_file.read_text(encoding="utf-8").rstrip()
            tag = f"[{now.strftime('%Y-%m-%d %H:%M')}] [{memory_type}] (importance: {importance:.2f}) [id:{entry_id}]"
            entry_text = f"\n\n{tag}\n{content.strip()}"
            self.memory_file.write_text(lines + entry_text + "\n", encoding="utf-8")

            # Also log to history.jsonl for searchability
            self._append_history({
                "action": "remember",
                "entry": entry,
                "timestamp": now.isoformat(),
            })

        logger.info("Memory: remembered [%s] (importance=%.2f)", memory_type, importance)
        return entry

    def forget(self, memory_id: str) -> bool:
        """Remove a memory entry by ID.

        Parameters
        ----------
        memory_id : str
            Entry ID (YYYYmmdd_HHMMSS_microseconds format).

        Returns
        -------
        bool
            True if entry was found and removed.
        """
        content = self.memory_file.read_text(encoding="utf-8")
        # Match the [id:...] pattern in the tag line
        id_pattern = re.compile(rf"\[id:{re.escape(memory_id)}\]")
        if not id_pattern.search(content):
            return False

        lines = content.split("\n")
        new_lines = []
        skipping = False
        found = False

        for i, line in enumerate(lines):
            if id_pattern.search(line):
                found = True
                skipping = True
                continue
            if skipping:
                if line.strip().startswith("[") and "]" in line and not line.strip().startswith("#"):
                    skipping = False
                    new_lines.append(line)
                continue
            new_lines.append(line)

        if found:
            with self._write_lock:
                self.memory_file.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
                self._append_history({
                    "action": "forget",
                    "memory_id": memory_id,
                    "timestamp": datetime.now().isoformat(),
                })
            logger.info("Memory: forgot entry %s", memory_id)
            return True

        return False

    def list_memories(
        self,
        memory_type: Optional[str] = None,
        min_importance: float = 0.0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List memory entries with optional filtering.

        Parameters
        ----------
        memory_type : str, optional
            Filter by memory type.
        min_importance : float
            Minimum importance score (0.0-1.0).
        limit : int
            Maximum entries to return.

        Returns
        -------
        List[dict]
            List of memory entries sorted by recency.
        """
        entries = self._parse_memories()
        if memory_type:
            entries = [e for e in entries if e.get("type") == memory_type]
        entries = [e for e in entries if e.get("importance", 0.0) >= min_importance]
        entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return entries[:limit]

    def search_memories(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search memories by keyword.

        Parameters
        ----------
        query : str
            Search query.
        limit : int
            Maximum results.

        Returns
        -------
        List[dict]
            Matching memory entries sorted by relevance.
        """
        entries = self._parse_memories()
        query_lower = query.lower()
        tokens = [t for t in query_lower.split() if len(t) > 1]

        scored: List[tuple] = []
        for entry in entries:
            content = entry.get("content", "").lower()
            if not content:
                continue
            score = sum(content.count(t) for t in tokens)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_memories(self) -> List[Dict[str, Any]]:
        """Parse MEMORY.md into structured entries.

        Returns
        -------
        List[dict]
            Parsed memory entries.
        """
        entries: List[Dict[str, Any]] = []
        if not self.memory_file.exists():
            return entries

        content = self.memory_file.read_text(encoding="utf-8")
        # Split on tags: [YYYY-MM-DD HH:MM] [type] (importance: X.XX) [id:...]
        # The id part is optional for backwards compat with older files
        pattern = re.compile(
            r"^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]\s+\[(\w+)\]\s+\(importance:\s*([\d.]+)\)\s*(?:\[id:(\w+)\])?\s*$",
            re.MULTILINE,
        )

        blocks = pattern.split(content)
        # blocks: [prefix, date1, type1, imp1, id1, body1, date2, type2, imp2, id2, body2, ...]
        stride = 5  # date, type, importance, id, body
        for i in range(1, len(blocks), stride):
            if i + stride - 1 >= len(blocks):
                break
            date_str = blocks[i]
            mem_type = blocks[i + 1]
            importance = float(blocks[i + 2])
            mem_id = blocks[i + 3]
            body = blocks[i + stride - 1].strip()

            if body:
                if mem_id:
                    entry_id = mem_id
                else:
                    entry_id = datetime.strptime(date_str, "%Y-%m-%d %H:%M").strftime("%Y%m%d_%H%M%S")
                    entry_id += "_{:06d}".format(hash(body) % 1000000)
                entries.append({
                    "id": entry_id,
                    "type": mem_type,
                    "content": body,
                    "importance": importance,
                    "created_at": f"{date_str}:00",
                })

        return entries

    def get_index(self) -> str:
        """Get the full MEMORY.md content for including in system prompts.

        Returns
        -------
        str
            MEMORY.md content, or empty string if file doesn't exist.
        """
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    # ------------------------------------------------------------------
    # Research memory
    # ------------------------------------------------------------------

    def record_research(
        self,
        topic: str,
        summary: str,
        kb_id: str = "",
        report_path: str = "",
    ) -> Dict[str, Any]:
        """Record a completed research as memory.

        Parameters
        ----------
        topic : str
            Research topic.
        summary : str
            Brief summary of findings.
        kb_id : str
            Knowledge base identifier.
        report_path : str
            Path to the saved report.

        Returns
        -------
        dict
            The created memory entry.
        """
        content = (
            f"**Research: {topic}**\n\n"
            f"{summary[:500]}"
        )
        if report_path:
            content += f"\n\nReport: {report_path}"

        return self.remember(
            content=content,
            memory_type="research",
            importance=0.8,
            metadata={"topic": topic, "kb_id": kb_id, "report_path": report_path},
        )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _append_history(self, record: Dict[str, Any]) -> None:
        """Append a record to history.jsonl."""
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Memory: failed to write history: %s", e)

    def get_recent_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent records from history.jsonl.

        Parameters
        ----------
        limit : int
            Maximum records to return.

        Returns
        -------
        List[dict]
            Recent history records.
        """
        records: List[Dict[str, Any]] = []
        if not self.history_file.exists():
            return records

        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            return records

        return records[-limit:]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def prune(self, max_entries: int = 200) -> int:
        """Prune low-importance memories to keep under max_entries.

        Parameters
        ----------
        max_entries : int
            Maximum entries to keep.

        Returns
        -------
        int
            Number of entries pruned.
        """
        entries = self._parse_memories()
        if len(entries) <= max_entries:
            return 0

        # Sort by importance ascending (lowest first to prune)
        entries.sort(key=lambda e: (e.get("importance", 0.0), e.get("created_at", "")))
        to_prune = entries[: len(entries) - max_entries]

        for entry in to_prune:
            self.forget(entry["id"])

        logger.info("Memory: pruned %d low-importance entries", len(to_prune))
        return len(to_prune)

    def clear(self) -> None:
        """Clear all memories and history."""
        with self._write_lock:
            self._ensure_memory_file()
            if self.history_file.exists():
                self.history_file.unlink()
        logger.info("Memory: cleared all entries")
