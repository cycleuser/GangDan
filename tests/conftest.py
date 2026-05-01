"""Pytest configuration and shared fixtures for GangDan CLI tests."""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test data directory before importing gangdan modules
TEST_DATA_DIR = None


@pytest.fixture(scope="function")
def temp_data_dir(tmp_path):
    """Create a temporary data directory for each test."""
    data_dir = tmp_path / "gangdan_test_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories
    (data_dir / "docs").mkdir()
    (data_dir / "chroma").mkdir()
    
    # Set environment variable
    old_env = os.environ.get("GANGDAN_DATA_DIR")
    os.environ["GANGDAN_DATA_DIR"] = str(data_dir)
    
    yield data_dir
    
    # Restore environment
    if old_env:
        os.environ["GANGDAN_DATA_DIR"] = old_env
    else:
        os.environ.pop("GANGDAN_DATA_DIR", None)


@pytest.fixture
def mock_ollama_available():
    """Mock Ollama API responses for tests that don't need real API."""
    with patch("requests.Session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.2:latest"},
                {"name": "nomic-embed-text:latest"},
                {"name": "qwen2.5:14b"},
            ]
        }
        mock_session.return_value.get.return_value = mock_response
        yield mock_session


@pytest.fixture
def mock_ollama_unavailable():
    """Mock Ollama API being unavailable."""
    with patch("requests.Session") as mock_session:
        mock_session.return_value.get.side_effect = ConnectionError("Connection refused")
        yield mock_session


@pytest.fixture
def sample_conversation():
    """Sample conversation data for testing."""
    return {
        "version": "1.0",
        "app": "GangDan",
        "exported_at": "2025-01-15T10:30:00",
        "messages": [
            {"role": "user", "content": "Hello, how do I use Python lists?"},
            {"role": "assistant", "content": "Python lists are versatile data structures..."},
            {"role": "user", "content": "Can you show me an example?"},
            {"role": "assistant", "content": "Here's an example:\n```python\nmy_list = [1, 2, 3]\n```"},
        ]
    }


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "ollama_url": "http://localhost:11434",
        "embedding_model": "nomic-embed-text:latest",
        "chat_model": "llama3.2:latest",
        "reranker_model": "",
        "top_k": 15,
        "language": "en",
        "proxy_mode": "none",
        "proxy_http": "",
        "proxy_https": "",
        "strict_kb_mode": False,
    }


@pytest.fixture
def mock_chroma_client():
    """Mock ChromaDB client for tests that don't need real database."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.name = "test_kb"
    mock_collection.count.return_value = 100
    mock_client.list_collections.return_value = [mock_collection]
    mock_client.get_or_create_collection.return_value = mock_collection
    mock_client.get_collection.return_value = mock_collection
    
    # Mock query results
    mock_collection.query.return_value = {
        "ids": [["doc1", "doc2"]],
        "documents": [["Test document 1", "Test document 2"]],
        "metadatas": [[{"file": "test.md"}, {"file": "test2.md"}]],
        "distances": [[0.1, 0.2]],
    }
    
    return mock_client


@pytest.fixture
def mock_web_response():
    """Mock web search response."""
    html_response = '''
    <html>
    <body>
    <a class="result__a" href="https://example.com/page1">Test Result 1</a>
    <a class="result__snippet">This is a test snippet for result 1.</a>
    <a class="result__a" href="https://example.com/page2">Test Result 2</a>
    <a class="result__snippet">This is a test snippet for result 2.</a>
    </body>
    </html>
    '''
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html_response
    return mock_response


@pytest.fixture
def cli_runner():
    """Helper to run CLI commands and capture output."""
    from io import StringIO
    
    class CLIRunner:
        def __init__(self):
            self.stdout = None
            self.stderr = None
            self.exit_code = None
        
        def run(self, args):
            """Run CLI with given arguments."""
            from gangdan.cli_app import cli_main
            
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            
            sys.stdout = StringIO()
            sys.stderr = StringIO()
            
            try:
                self.exit_code = cli_main(args) or 0
            except SystemExit as e:
                self.exit_code = e.code if e.code is not None else 0
            finally:
                self.stdout = sys.stdout.getvalue()
                self.stderr = sys.stderr.getvalue()
                sys.stdout = old_stdout
                sys.stderr = old_stderr
            
            return self
    
    return CLIRunner()
