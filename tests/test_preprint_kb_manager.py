"""Tests for preprint_kb_manager module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gangdan.core.preprint_kb_manager import (
    KBSearchResult,
    PreprintKBEntry,
    PreprintKBManager,
)


class TestPreprintKBEntry:
    """Test PreprintKBEntry dataclass."""

    def test_defaults(self) -> None:
        entry = PreprintKBEntry()
        assert entry.preprint_id == ""
        assert entry.authors == []
        assert entry.tags == []

    def test_to_dict(self) -> None:
        entry = PreprintKBEntry(
            preprint_id="2301.12345",
            title="Test Paper",
            authors=["Alice", "Bob"],
            source_platform="arxiv",
        )
        d = entry.to_dict()
        assert d["preprint_id"] == "2301.12345"
        assert d["title"] == "Test Paper"
        assert d["authors"] == ["Alice", "Bob"]

    def test_from_dict(self) -> None:
        data = {
            "preprint_id": "2301.12345",
            "title": "Test",
            "authors": ["Alice"],
            "source_platform": "arxiv",
            "tags": ["AI"],
        }
        entry = PreprintKBEntry.from_dict(data)
        assert entry.preprint_id == "2301.12345"
        assert entry.authors == ["Alice"]
        assert entry.tags == ["AI"]

    def test_authors_str_empty(self) -> None:
        entry = PreprintKBEntry(authors=[])
        assert entry.authors_str == "Unknown"

    def test_authors_str_single(self) -> None:
        entry = PreprintKBEntry(authors=["Alice"])
        assert entry.authors_str == "Alice"

    def test_authors_str_multiple(self) -> None:
        entry = PreprintKBEntry(authors=["Alice", "Bob", "Charlie", "Dave"])
        assert entry.authors_str == "Alice, Bob, Charlie et al."

    def test_short_title_short(self) -> None:
        entry = PreprintKBEntry(title="Short")
        assert entry.short_title == "Short"

    def test_short_title_long(self) -> None:
        entry = PreprintKBEntry(title="A" * 100)
        assert len(entry.short_title) == 80


class TestKBSearchResult:
    """Test KBSearchResult dataclass."""

    def test_to_dict(self) -> None:
        entry = PreprintKBEntry(preprint_id="test", title="Test")
        result = KBSearchResult(entry=entry, score=0.8, match_type="keyword")
        d = result.to_dict()
        assert d["score"] == 0.8
        assert d["match_type"] == "keyword"


class TestPreprintKBManager:
    """Test PreprintKBManager."""

    def _make_manager(self) -> PreprintKBManager:
        """Create a manager with a temp KB file."""
        tmpdir = Path(tempfile.mkdtemp())
        kb_file = tmpdir / "preprint_kb.json"
        return PreprintKBManager(kb_file=kb_file)

    def test_init_empty(self) -> None:
        manager = self._make_manager()
        assert len(manager.entries) == 0

    def test_add_entry(self) -> None:
        manager = self._make_manager()
        entry = manager.add_entry(
            preprint_id="2301.12345",
            title="Test Paper",
            abstract="Test abstract",
            authors=["Alice"],
            source_platform="arxiv",
        )
        assert entry.preprint_id == "2301.12345"
        assert len(manager.entries) == 1

    def test_add_duplicate(self) -> None:
        manager = self._make_manager()
        manager.add_entry("2301.12345", "Title 1", "Abstract 1")
        manager.add_entry("2301.12345", "Title 2", "Abstract 2")
        assert len(manager.entries) == 1
        assert manager.entries["2301.12345"].title == "Title 2"

    def test_remove_entry(self) -> None:
        manager = self._make_manager()
        manager.add_entry("2301.12345", "Test", "Abstract")
        assert manager.remove_entry("2301.12345") is True
        assert len(manager.entries) == 0

    def test_remove_nonexistent(self) -> None:
        manager = self._make_manager()
        assert manager.remove_entry("nonexistent") is False

    def test_get_entry(self) -> None:
        manager = self._make_manager()
        manager.add_entry("2301.12345", "Test", "Abstract")
        entry = manager.get_entry("2301.12345")
        assert entry is not None
        assert entry.title == "Test"

    def test_get_nonexistent_entry(self) -> None:
        manager = self._make_manager()
        assert manager.get_entry("nonexistent") is None

    def test_keyword_search_title(self) -> None:
        manager = self._make_manager()
        manager.add_entry("1", "Machine Learning in Healthcare", "Abstract about ML")
        manager.add_entry("2", "Quantum Physics", "Abstract about physics")

        results = manager.search("machine learning", mode="keyword")
        assert len(results) >= 1
        assert results[0].entry.preprint_id == "1"
        assert "title" in results[0].matched_fields

    def test_keyword_search_abstract(self) -> None:
        manager = self._make_manager()
        manager.add_entry("1", "Title A", "This paper discusses neural networks and deep learning")
        manager.add_entry("2", "Title B", "This paper is about something else")

        results = manager.search("neural networks", mode="keyword")
        assert len(results) >= 1
        assert results[0].entry.preprint_id == "1"
        assert "abstract" in results[0].matched_fields

    def test_keyword_search_authors(self) -> None:
        manager = self._make_manager()
        manager.add_entry("1", "Title", "Abstract", authors=["John Smith", "Jane Doe"])
        manager.add_entry("2", "Title", "Abstract", authors=["Bob Wilson"])

        results = manager.search("John Smith", mode="keyword")
        assert len(results) >= 1
        assert results[0].entry.preprint_id == "1"

    def test_search_with_platform_filter(self) -> None:
        manager = self._make_manager()
        manager.add_entry("1", "ML Paper", "Abstract", source_platform="arxiv")
        manager.add_entry("2", "Bio Paper", "Abstract", source_platform="biorxiv")

        results = manager.search("paper", mode="keyword", platform="arxiv")
        assert all(r.entry.source_platform == "arxiv" for r in results)

    def test_search_with_date_filter(self) -> None:
        manager = self._make_manager()
        manager.add_entry("1", "Old Paper", "Abstract", published_date="2020-01-01")
        manager.add_entry("2", "New Paper", "Abstract", published_date="2024-01-01")

        results = manager.search("paper", mode="keyword", date_from="2023-01-01")
        assert len(results) == 1
        assert results[0].entry.published_date == "2024-01-01"

    def test_search_deduplication(self) -> None:
        manager = self._make_manager()
        manager.add_entry("1", "Test Paper", "Test abstract about testing")

        results = manager.search("test", mode="keyword")
        ids = [r.entry.preprint_id for r in results]
        assert len(ids) == len(set(ids))

    def test_search_limit(self) -> None:
        manager = self._make_manager()
        for i in range(30):
            manager.add_entry(str(i), f"Test Paper {i}", f"Abstract {i}")

        results = manager.search("test", mode="keyword", limit=5)
        assert len(results) <= 5

    def test_get_recent(self) -> None:
        manager = self._make_manager()
        manager.add_entry("1", "Recent", "Abstract")

        recent = manager.get_recent(days=30)
        assert len(recent) >= 1

    def test_get_by_platform(self) -> None:
        manager = self._make_manager()
        manager.add_entry("1", "Arxiv Paper", "Abstract", source_platform="arxiv")
        manager.add_entry("2", "Bio Paper", "Abstract", source_platform="biorxiv")

        arxiv = manager.get_by_platform("arxiv")
        assert all(e.source_platform == "arxiv" for e in arxiv)

    def test_get_statistics(self) -> None:
        manager = self._make_manager()
        manager.add_entry("1", "Paper 1", "Abstract", source_platform="arxiv", source_format="html")
        manager.add_entry("2", "Paper 2", "Abstract", source_platform="biorxiv", source_format="pdf")

        stats = manager.get_statistics()
        assert stats["total_entries"] == 2
        assert stats["by_platform"]["arxiv"] == 1
        assert stats["by_platform"]["biorxiv"] == 1

    def test_state_persistence(self) -> None:
        manager = self._make_manager()
        manager.add_entry("2301.12345", "Test", "Abstract")

        kb_file = manager.kb_file
        assert kb_file.exists()

        data = json.loads(kb_file.read_text())
        assert "2301.12345" in data["entries"]

    def test_state_load(self) -> None:
        tmpdir = Path(tempfile.mkdtemp())
        kb_file = tmpdir / "preprint_kb.json"
        data = {
            "entries": {
                "2301.12345": {
                    "preprint_id": "2301.12345",
                    "title": "Loaded Paper",
                    "authors": [],
                    "abstract": "Abstract",
                    "published_date": "",
                    "source_platform": "arxiv",
                    "category": "",
                    "markdown_path": "",
                    "source_format": "html",
                    "html_url": "",
                    "tex_source_url": "",
                    "pdf_url": "",
                    "url": "",
                    "indexed_at": "",
                    "embedding_id": "",
                    "tags": [],
                }
            },
            "updated_at": "2024-01-01T00:00:00",
        }
        kb_file.write_text(json.dumps(data))

        manager = PreprintKBManager(kb_file=kb_file)
        assert len(manager.entries) == 1
        assert manager.entries["2301.12345"].title == "Loaded Paper"

    def test_clear(self) -> None:
        manager = self._make_manager()
        manager.add_entry("1", "Test", "Abstract")
        manager.clear()
        assert len(manager.entries) == 0

    def test_chunk_text(self) -> None:
        manager = self._make_manager()
        text = "Line 1\nLine 2\nLine 3"
        chunks = manager._chunk_text(text, max_chunk_size=100)
        assert len(chunks) >= 1

    def test_chunk_text_large(self) -> None:
        manager = self._make_manager()
        text = "A" * 5000
        chunks = manager._chunk_text(text, max_chunk_size=1000)
        assert len(chunks) > 1
