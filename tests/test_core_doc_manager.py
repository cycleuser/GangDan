"""Tests for gangdan.core.doc_manager module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestDocSources:
    """Test documentation sources configuration."""
    
    def test_doc_sources_not_empty(self, temp_data_dir):
        """Test that DOC_SOURCES has entries."""
        from gangdan.core.doc_manager import DOC_SOURCES
        
        assert len(DOC_SOURCES) > 0
    
    def test_doc_sources_have_required_keys(self, temp_data_dir):
        """Test that each source has name and urls."""
        from gangdan.core.doc_manager import DOC_SOURCES
        
        for key, source in DOC_SOURCES.items():
            assert "name" in source, f"Source {key} missing 'name'"
            assert "urls" in source, f"Source {key} missing 'urls'"
            assert len(source["urls"]) > 0, f"Source {key} has no URLs"
    
    def test_popular_sources_present(self, temp_data_dir):
        """Test that popular doc sources are present."""
        from gangdan.core.doc_manager import DOC_SOURCES
        
        expected = ["numpy", "pandas", "pytorch", "rust", "git", "docker"]
        for source in expected:
            assert source in DOC_SOURCES, f"Expected source '{source}' not found"


class TestDocManagerInit:
    """Test DocManager initialization."""
    
    def test_init(self, temp_data_dir):
        """Test DocManager initialization."""
        from gangdan.core.doc_manager import DocManager
        
        mock_chroma = MagicMock()
        mock_ollama = MagicMock()
        docs_dir = temp_data_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        
        manager = DocManager(docs_dir, mock_chroma, mock_ollama)
        
        assert manager.docs_dir == docs_dir
        assert manager.chroma == mock_chroma
        assert manager.ollama == mock_ollama


class TestDocManagerDownload:
    """Test document downloading."""
    
    def test_download_unknown_source(self, temp_data_dir):
        """Test downloading unknown source."""
        from gangdan.core.doc_manager import DocManager
        
        mock_chroma = MagicMock()
        mock_ollama = MagicMock()
        docs_dir = temp_data_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        
        manager = DocManager(docs_dir, mock_chroma, mock_ollama)
        downloaded, errors = manager.download_source("nonexistent_source")
        
        assert downloaded == 0
        assert len(errors) > 0
    
    def test_download_source_success(self, temp_data_dir):
        """Test downloading with mocked HTTP responses."""
        from gangdan.core.doc_manager import DocManager
        
        mock_chroma = MagicMock()
        mock_ollama = MagicMock()
        docs_dir = temp_data_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        
        manager = DocManager(docs_dir, mock_chroma, mock_ollama)
        
        # Mock HTTP responses
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# Test Document\n\nThis is test content."
        manager._session.get = MagicMock(return_value=mock_response)
        
        downloaded, errors = manager.download_source("numpy")
        
        assert downloaded > 0
        assert len(errors) == 0
    
    def test_download_source_http_error(self, temp_data_dir):
        """Test handling HTTP errors during download."""
        from gangdan.core.doc_manager import DocManager
        
        mock_chroma = MagicMock()
        mock_ollama = MagicMock()
        docs_dir = temp_data_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        
        manager = DocManager(docs_dir, mock_chroma, mock_ollama)
        
        # Mock HTTP 404 error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        manager._session.get = MagicMock(return_value=mock_response)
        
        downloaded, errors = manager.download_source("numpy")
        
        assert downloaded == 0
        assert len(errors) > 0


class TestDocManagerIndex:
    """Test document indexing."""
    
    def test_index_no_chroma(self, temp_data_dir):
        """Test indexing when ChromaDB is not available."""
        from gangdan.core.doc_manager import DocManager
        
        mock_chroma = MagicMock()
        mock_chroma.client = None
        mock_ollama = MagicMock()
        docs_dir = temp_data_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        
        manager = DocManager(docs_dir, mock_chroma, mock_ollama)
        files, chunks = manager.index_source("numpy")
        
        assert files == 0
        assert chunks == 0
    
    def test_index_no_embedding_model(self, temp_data_dir):
        """Test indexing when no embedding model is configured."""
        import gangdan.core.doc_manager as dm_module
        from gangdan.core.doc_manager import DocManager
        
        old_embed = dm_module.CONFIG.embedding_model
        dm_module.CONFIG.embedding_model = ""
        
        mock_chroma = MagicMock()
        mock_chroma.client = MagicMock()
        mock_ollama = MagicMock()
        docs_dir = temp_data_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        
        manager = DocManager(docs_dir, mock_chroma, mock_ollama)
        files, chunks = manager.index_source("numpy")
        
        assert files == 0
        assert chunks == 0
        
        # Restore
        dm_module.CONFIG.embedding_model = old_embed
    
    def test_index_source_with_files(self, temp_data_dir):
        """Test indexing source that has downloaded files."""
        import gangdan.core.doc_manager as dm_module
        from gangdan.core.doc_manager import DocManager
        
        # Patch CONFIG in the doc_manager module's own namespace
        # to ensure it sees the change regardless of prior reloads
        old_embed = dm_module.CONFIG.embedding_model
        dm_module.CONFIG.embedding_model = "test-embed"
        
        # Create test doc files
        docs_dir = temp_data_dir / "docs"
        source_dir = docs_dir / "test_source"
        source_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "doc1.md").write_text("# Test Document\n\n" + "This is a test document with enough content to be indexed. " * 10)
        
        mock_chroma = MagicMock()
        mock_chroma.client = MagicMock()
        mock_ollama = MagicMock()
        mock_ollama.embed.return_value = [0.1, 0.2, 0.3]
        
        manager = DocManager(docs_dir, mock_chroma, mock_ollama)
        files, chunks = manager.index_source("test_source")
        
        assert files == 1
        assert chunks > 0
        
        # Restore
        dm_module.CONFIG.embedding_model = old_embed


class TestDocManagerListDownloaded:
    """Test listing downloaded documents."""
    
    def test_list_downloaded_empty(self, temp_data_dir):
        """Test listing when nothing is downloaded."""
        from gangdan.core.doc_manager import DocManager
        
        mock_chroma = MagicMock()
        mock_ollama = MagicMock()
        docs_dir = temp_data_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        
        manager = DocManager(docs_dir, mock_chroma, mock_ollama)
        result = manager.list_downloaded()
        
        assert result == []
    
    def test_list_downloaded_with_sources(self, temp_data_dir):
        """Test listing when sources are downloaded."""
        from gangdan.core.doc_manager import DocManager
        
        # Create test directories
        docs_dir = temp_data_dir / "docs"
        (docs_dir / "numpy").mkdir(parents=True)
        (docs_dir / "numpy" / "test.md").write_text("test")
        (docs_dir / "pandas").mkdir(parents=True)
        (docs_dir / "pandas" / "test.md").write_text("test")
        
        mock_chroma = MagicMock()
        mock_ollama = MagicMock()
        
        manager = DocManager(docs_dir, mock_chroma, mock_ollama)
        result = manager.list_downloaded()
        
        assert len(result) == 2
        names = [r["name"] for r in result]
        assert "numpy" in names
        assert "pandas" in names


class TestDocManagerChunking:
    """Test text chunking functionality."""
    
    def test_chunk_text(self, temp_data_dir):
        """Test basic text chunking."""
        from gangdan.core.doc_manager import DocManager
        
        manager = DocManager.__new__(DocManager)
        
        text = "a" * 100
        chunks = manager._chunk_text(text, chunk_size=30, overlap=10)
        
        assert len(chunks) > 1
        assert all(len(c) <= 30 for c in chunks)
    
    def test_chunk_text_small(self, temp_data_dir):
        """Test chunking text smaller than chunk_size."""
        from gangdan.core.doc_manager import DocManager
        
        manager = DocManager.__new__(DocManager)
        
        text = "short text"
        chunks = manager._chunk_text(text, chunk_size=100, overlap=10)
        
        assert len(chunks) == 1
        assert chunks[0] == "short text"
    
    def test_chunk_text_empty(self, temp_data_dir):
        """Test chunking empty text."""
        from gangdan.core.doc_manager import DocManager
        
        manager = DocManager.__new__(DocManager)
        
        chunks = manager._chunk_text("", chunk_size=100, overlap=10)
        
        assert chunks == []
