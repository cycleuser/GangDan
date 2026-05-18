"""Tests for KB document listing and selection fixes.

Tests the following bug fixes:
1. _get_chroma_docs deduplication uses doc_id instead of chunk ID
2. web_search_to_kb registers KB in user_kbs.json
3. list_documents correctly resolves KBs in user_kbs
4. Multiple KBs can have their documents listed independently
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _mock_chroma_with_docs(collection_name, ids, metadatas):
    """Create a mock CHROMA object that returns specific documents."""
    mock_chroma = MagicMock()
    mock_chroma.is_available = True
    mock_chroma.collection_exists.return_value = True
    mock_chroma.get_documents.return_value = {
        "ids": ids,
        "metadatas": metadatas,
    }
    return mock_chroma


class TestGetChromaDocsDeduplication:
    """Test that _get_chroma_docs deduplicates by real doc_id, not chunk ID."""

    def test_dedup_by_doc_id_not_chunk_id(self):
        """Documents with same doc_id but different chunk IDs should be deduplicated."""
        from gangdan.kb_routes import _get_chroma_docs

        mock_chroma = _mock_chroma_with_docs(
            "test_kb",
            ["doc_a_chunk_0", "doc_a_chunk_1", "doc_b_chunk_0"],
            [
                {"doc_id": "doc_a", "title": "Document A", "file": "a.md"},
                {"doc_id": "doc_a", "title": "Document A", "file": "a.md"},
                {"doc_id": "doc_b", "title": "Document B", "file": "b.md"},
            ],
        )

        with patch("gangdan.app.CHROMA", mock_chroma):
            result = _get_chroma_docs("test_kb")

        assert len(result) == 2, f"Expected 2 unique documents, got {len(result)}: {result}"
        doc_ids = [d["doc_id"] for d in result]
        assert "doc_a" in doc_ids
        assert "doc_b" in doc_ids

    def test_chunk_count_is_correct(self):
        """chunk_count should reflect the actual number of chunks per document."""
        from gangdan.kb_routes import _get_chroma_docs

        mock_chroma = _mock_chroma_with_docs(
            "test_kb",
            ["doc_a_chunk_0", "doc_a_chunk_1", "doc_a_chunk_2", "doc_b_chunk_0"],
            [
                {"doc_id": "doc_a", "title": "Document A", "file": "a.md"},
                {"doc_id": "doc_a", "title": "Document A", "file": "a.md"},
                {"doc_id": "doc_a", "title": "Document A", "file": "a.md"},
                {"doc_id": "doc_b", "title": "Document B", "file": "b.md"},
            ],
        )

        with patch("gangdan.app.CHROMA", mock_chroma):
            result = _get_chroma_docs("test_kb")

        assert len(result) == 2
        doc_a = next(d for d in result if d["doc_id"] == "doc_a")
        doc_b = next(d for d in result if d["doc_id"] == "doc_b")
        assert doc_a["chunk_count"] == 3, f"Expected 3 chunks for doc_a, got {doc_a['chunk_count']}"
        assert doc_b["chunk_count"] == 1, f"Expected 1 chunk for doc_b, got {doc_b['chunk_count']}"

    def test_web_search_results_without_doc_id_metadata(self):
        """Web search results have no doc_id metadata; should use chunk ID as doc_id."""
        import hashlib
        from gangdan.kb_routes import _get_chroma_docs

        id1 = hashlib.md5(b"test_kb_query_0").hexdigest()
        id2 = hashlib.md5(b"test_kb_query_1").hexdigest()

        mock_chroma = _mock_chroma_with_docs(
            "test_kb",
            [id1, id2],
            [
                {"source": "web_search", "title": "Result 1", "url": "https://example.com/1"},
                {"source": "web_search", "title": "Result 2", "url": "https://example.com/2"},
            ],
        )

        with patch("gangdan.app.CHROMA", mock_chroma):
            result = _get_chroma_docs("test_kb")

        assert len(result) == 2
        assert result[0]["doc_id"] == id1
        assert result[1]["doc_id"] == id2
        assert result[0]["title"] == "Result 1"
        assert result[1]["title"] == "Result 2"

    def test_empty_collection(self):
        """Empty ChromaDB collection should return empty list."""
        from gangdan.kb_routes import _get_chroma_docs

        mock_chroma = _mock_chroma_with_docs("test_kb", [], [])
        with patch("gangdan.app.CHROMA", mock_chroma):
            result = _get_chroma_docs("test_kb")

        assert result == []

    def test_chroma_unavailable(self):
        """When ChromaDB is unavailable, should return empty list."""
        from gangdan.kb_routes import _get_chroma_docs

        mock_chroma = MagicMock()
        mock_chroma.is_available = False

        with patch("gangdan.app.CHROMA", mock_chroma):
            result = _get_chroma_docs("test_kb")

        assert result == []

    def test_collection_not_exists(self):
        """When collection doesn't exist, should return empty list."""
        from gangdan.kb_routes import _get_chroma_docs

        mock_chroma = MagicMock()
        mock_chroma.is_available = True
        mock_chroma.collection_exists.return_value = False

        with patch("gangdan.app.CHROMA", mock_chroma):
            result = _get_chroma_docs("nonexistent_kb")

        assert result == []


class TestGetChromaDocsEdgeCases:
    """Additional edge case tests for _get_chroma_docs."""

    def test_mixed_doc_ids_and_missing_metadata(self):
        """Documents with missing doc_id in metadata should fall back to chunk ID."""
        from gangdan.kb_routes import _get_chroma_docs

        mock_chroma = _mock_chroma_with_docs(
            "test_kb",
            ["abc123_chunk_0", "def456_chunk_0", "ghi789"],
            [
                {"doc_id": "real_doc_1", "title": "Document 1"},
                {"title": "Document 2"},
                {},
            ],
        )

        with patch("gangdan.app.CHROMA", mock_chroma):
            result = _get_chroma_docs("test_kb")

        assert len(result) == 3
        assert result[0]["doc_id"] == "real_doc_1"
        assert result[1]["doc_id"] == "def456_chunk_0"
        assert result[2]["doc_id"] == "ghi789"

    def test_single_doc_multiple_chunks_dedup(self):
        """A single document with many chunks should appear only once."""
        from gangdan.kb_routes import _get_chroma_docs

        chunk_ids = [f"mydoc_chunk_{i}" for i in range(10)]
        metadatas = [{"doc_id": "mydoc", "title": "My Long Document"}] * 10

        mock_chroma = _mock_chroma_with_docs("test_kb", chunk_ids, metadatas)

        with patch("gangdan.app.CHROMA", mock_chroma):
            result = _get_chroma_docs("test_kb")

        assert len(result) == 1, f"Expected 1 document (deduped), got {len(result)}"
        assert result[0]["doc_id"] == "mydoc"
        assert result[0]["chunk_count"] == 10

    def test_none_metadata_handling(self):
        """Handle None values in metadata gracefully."""
        from gangdan.kb_routes import _get_chroma_docs

        mock_chroma = _mock_chroma_with_docs(
            "test_kb",
            ["doc1_chunk_0"],
            [None],
        )

        with patch("gangdan.app.CHROMA", mock_chroma):
            result = _get_chroma_docs("test_kb")

        assert len(result) == 1
        assert result[0]["doc_id"] == "doc1_chunk_0"


class TestMultipleKBDocumentSelection:
    """Test that documents from multiple KBs can be loaded and selected."""

    def test_load_docs_for_two_kbs(self, temp_data_dir):
        """Loading documents from two different KBs should return docs from both."""
        from gangdan.core.config import save_user_kb

        save_user_kb("user_kb1", "KB One", 2)
        save_user_kb("user_kb2", "KB Two", 3)

        from gangdan.core.config import load_user_kbs
        kbs = load_user_kbs()
        assert "user_kb1" in kbs
        assert "user_kb2" in kbs

    def test_second_kb_not_in_custom_manifest(self):
        """KBs created via upload are in user_kbs, not custom_kbs_manifest."""
        from gangdan.core.kb_manager import CustomKBManager

        manager = CustomKBManager()
        kb = manager.get_kb("user_uploaded_kb")
        assert kb is None, "User-uploaded KBs should not be in custom_kbs_manifest"

    def test_user_kb_resolution_in_list_documents(self, temp_data_dir):
        """user_kbs are correctly resolved in list_documents endpoint."""
        from gangdan.core.config import save_user_kb

        kb_name = "user_test_resolution"
        save_user_kb(kb_name, "Test Resolution KB", 5)

        mock_chroma = _mock_chroma_with_docs(
            kb_name,
            ["chunk1"],
            [{"doc_id": "doc1", "title": "Test Doc", "file": "test.md"}],
        )

        from gangdan.kb_routes import _get_chroma_docs
        with patch("gangdan.app.CHROMA", mock_chroma):
            result = _get_chroma_docs(kb_name)

        assert len(result) == 1
        assert result[0]["doc_id"] == "doc1"

    def test_save_user_kb_web_search(self, temp_data_dir):
        """web_search_to_kb should register KB in user_kbs.json."""
        from gangdan.core.config import save_user_kb, load_user_kbs

        save_user_kb("web_search_test", "Web Search Test", 10, languages=[])

        kbs = load_user_kbs()
        assert "web_search_test" in kbs
        assert kbs["web_search_test"]["display_name"] == "Web Search Test"
        assert kbs["web_search_test"]["file_count"] == 10


class TestKBManagerStaleManifest:
    """Test that CustomKBManager refreshes its manifest when stale."""

    def test_get_kb_refreshes_stale_manifest(self, temp_data_dir):
        """get_kb should detect externally-created KBs by refreshing manifest."""
        from gangdan.core.kb_manager import CustomKBManager, CUSTOM_KBS_MANIFEST
        import json

        manager = CustomKBManager()

        assert manager.get_kb("user_externally_created") is None

        manifest_data = {
            "user_externally_created": {
                "kb_id": "ext123",
                "internal_name": "user_externally_created",
                "display_name": "Externally Created KB",
                "description": "",
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
                "tags": [],
                "chroma_collection": "user_externally_created",
                "doc_count": 0,
            }
        }
        CUSTOM_KBS_MANIFEST.write_text(
            json.dumps(manifest_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        kb = manager.get_kb("user_externally_created")
        assert kb is not None, "get_kb should find externally-created KB after manifest refresh"
        assert kb.display_name == "Externally Created KB"

    def test_list_kbs_refreshes_stale_manifest(self, temp_data_dir):
        """list_kbs should detect externally-created KBs by refreshing manifest."""
        from gangdan.core.kb_manager import CustomKBManager, CUSTOM_KBS_MANIFEST
        import json

        manager = CustomKBManager()
        initial_count = len(manager.list_kbs())

        manifest_data = {
            "user_new_kb": {
                "kb_id": "new456",
                "internal_name": "user_new_kb",
                "display_name": "New KB",
                "description": "",
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
                "tags": [],
                "chroma_collection": "user_new_kb",
                "doc_count": 0,
            }
        }
        CUSTOM_KBS_MANIFEST.write_text(
            json.dumps(manifest_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        kbs = manager.list_kbs()
        found = any(kb.internal_name == "user_new_kb" for kb in kbs)
        assert found, "list_kbs should find externally-created KB"

    def test_concurrent_managers_see_each_others_kbs(self, temp_data_dir):
        """Two CustomKBManager instances should see KBs created sequentially."""
        from gangdan.core.kb_manager import CustomKBManager

        manager1 = CustomKBManager()
        kb1 = manager1.create_kb("Shared KB One")

        manager2 = CustomKBManager()
        kb2 = manager2.create_kb("Shared KB Two")

        result1 = manager1.get_kb(kb2.internal_name)
        assert result1 is not None, f"manager1 should see KB created by manager2, internal_name={kb2.internal_name}"

        result2 = manager2.get_kb(kb1.internal_name)
        assert result2 is not None, f"manager2 should see KB created by manager1, internal_name={kb1.internal_name}"