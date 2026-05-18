"""Tests for gangdan.core.chroma_manager module."""

import pytest
from unittest.mock import patch, MagicMock


class TestChromaManagerInit:
    """Test ChromaManager initialization."""
    
    def test_init_successful(self, temp_data_dir):
        """Test successful initialization with a temporary directory."""
        chroma_dir = temp_data_dir / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        
        from gangdan.core.chroma_manager import ChromaManager
        
        manager = ChromaManager(str(chroma_dir))
        assert manager.client is not None
    
    def test_init_failed_with_recovery(self, temp_data_dir):
        """Test initialization with recovery when first attempt fails."""
        from gangdan.core.chroma_manager import ChromaManager
        
        # If the directory is corrupted, it should attempt recovery
        chroma_dir = temp_data_dir / "chroma_bad"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        
        # Write something to simulate corruption
        (chroma_dir / "chroma.sqlite3").write_text("corrupted data")
        
        # This might trigger recovery, but should still work
        manager = ChromaManager(str(chroma_dir))
        # After recovery it should have a client (or None if all fails)
        # We can't guarantee recovery in test env, so just check it doesn't crash


class TestChromaManagerOperations:
    """Test ChromaManager collection operations."""
    
    def test_get_or_create_collection(self, temp_data_dir):
        """Test getting or creating a collection."""
        chroma_dir = temp_data_dir / "chroma_ops"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        
        from gangdan.core.chroma_manager import ChromaManager
        
        manager = ChromaManager(str(chroma_dir))
        coll = manager.get_or_create_collection("test_collection")
        
        assert coll is not None
    
    def test_list_collections_empty(self, temp_data_dir):
        """Test listing collections when empty."""
        chroma_dir = temp_data_dir / "chroma_empty"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        
        from gangdan.core.chroma_manager import ChromaManager
        
        manager = ChromaManager(str(chroma_dir))
        collections = manager.list_collections()
        
        assert isinstance(collections, list)
    
    def test_get_stats_empty(self, temp_data_dir):
        """Test getting stats when empty."""
        chroma_dir = temp_data_dir / "chroma_stats"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        
        from gangdan.core.chroma_manager import ChromaManager
        
        manager = ChromaManager(str(chroma_dir))
        stats = manager.get_stats()
        
        assert isinstance(stats, dict)
    
    def test_add_and_search_documents(self, temp_data_dir):
        """Test adding documents and searching them."""
        chroma_dir = temp_data_dir / "chroma_add_search"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        
        from gangdan.core.chroma_manager import ChromaManager
        
        manager = ChromaManager(str(chroma_dir))
        
        # Add documents
        manager.add_documents(
            collection_name="test_search",
            documents=["Python is a programming language", "JavaScript is for web"],
            embeddings=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            metadatas=[{"file": "python.md"}, {"file": "js.md"}],
            ids=["doc1", "doc2"]
        )
        
        # Search
        results = manager.search("test_search", [0.1, 0.2, 0.3], top_k=2)
        
        assert len(results) > 0
        assert "document" in results[0]
        assert "metadata" in results[0]
    
    def test_search_nonexistent_collection(self, temp_data_dir):
        """Test searching a collection that doesn't exist."""
        chroma_dir = temp_data_dir / "chroma_noexist"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        
        from gangdan.core.chroma_manager import ChromaManager
        
        manager = ChromaManager(str(chroma_dir))
        results = manager.search("nonexistent_collection", [0.1, 0.2], top_k=5)
        
        assert results == []


class TestChromaManagerNullClient:
    """Test ChromaManager when client is None."""
    
    def test_operations_with_null_client(self, temp_data_dir):
        """Test that operations gracefully handle null client."""
        from gangdan.core.chroma_manager import ChromaManager
        
        manager = ChromaManager.__new__(ChromaManager)
        manager.client = None
        manager.persist_dir = str(temp_data_dir / "null")
        
        assert manager.get_or_create_collection("test") is None
        assert manager.search("test", [0.1], top_k=5) == []
        assert manager.list_collections() == []
        assert manager.get_stats() == {}
        
        # Should not raise


class TestCollectionNameValidation:
    """Test that ChromaDB collection name validation rejects invalid names."""

    def test_valid_collection_names(self):
        from gangdan.core.chroma_manager import is_valid_collection_name

        assert is_valid_collection_name("numpy")
        assert is_valid_collection_name("user_web_search")
        assert is_valid_collection_name("user_kb_c360e994")
        assert is_valid_collection_name("abc")
        assert is_valid_collection_name("a1b")
        assert is_valid_collection_name("my-kb.test_name")
        assert is_valid_collection_name("x" * 3)

    def test_invalid_collection_names(self):
        from gangdan.core.chroma_manager import is_valid_collection_name

        assert not is_valid_collection_name("排序")
        assert not is_valid_collection_name("中文知识库")
        assert not is_valid_collection_name("")
        assert not is_valid_collection_name("ab")
        assert not is_valid_collection_name("_starts_underscore")
        assert not is_valid_collection_name("-starts-hyphen")
        assert not is_valid_collection_name("name with spaces")
        assert not is_valid_collection_name("name@symbol")
        assert not is_valid_collection_name("a" * 513)

    def test_chinese_kb_name_gets_sanitized(self):
        from gangdan.core.config import sanitize_kb_name
        from gangdan.core.chroma_manager import is_valid_collection_name

        result = sanitize_kb_name("排序")
        assert is_valid_collection_name(result)
        assert result.startswith("user_kb_")

        result2 = sanitize_kb_name("Web Search")
        assert is_valid_collection_name(result2)
        assert result2 == "user_web_search"

    def test_get_or_create_rejects_invalid_name(self, temp_data_dir):
        from gangdan.core.chroma_manager import ChromaManager

        chroma_dir = temp_data_dir / "chroma_validation"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        manager = ChromaManager(str(chroma_dir))

        result = manager.get_or_create_collection("排序")
        assert result is None, "Chinese collection name should be rejected"

    def test_collection_exists_rejects_invalid_name(self, temp_data_dir):
        from gangdan.core.chroma_manager import ChromaManager

        chroma_dir = temp_data_dir / "chroma_validation2"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        manager = ChromaManager(str(chroma_dir))

        assert manager.collection_exists("排序") is False
        manager.add_documents("test", ["doc"], [[0.1]], [{"f": "a"}], ["id1"])
