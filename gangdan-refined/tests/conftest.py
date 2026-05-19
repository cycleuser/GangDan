"""Test configuration and fixtures for GangDan Refined."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create an isolated temporary data directory."""
    data_dir = tmp_path / "gangdan_test_data"
    data_dir.mkdir()
    os.environ["GANGLAN_REFINED_DATA_DIR"] = str(data_dir)
    yield data_dir
    os.environ.pop("GANGLAN_REFINED_DATA_DIR", None)


@pytest.fixture
def mock_ollama_available():
    """Mock Ollama server as available with models."""
    with patch("gangdan_refined.llm.ollama.OllamaClient.is_available", return_value=True):
        with patch("gangdan_refined.llm.ollama.OllamaClient.get_models", return_value=["qwen2.5:7b", "nomic-embed-text"]):
            yield


@pytest.fixture
def mock_ollama_unavailable():
    """Mock Ollama server as unavailable."""
    with patch("gangdan_refined.llm.ollama.OllamaClient.is_available", return_value=False):
        with patch("gangdan_refined.llm.ollama.OllamaClient.get_models", return_value=[]):
            yield


@pytest.fixture
def mock_chroma_client():
    """Mock ChromaDB client."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection
    return mock_client