"""Tests for gangdan.core.ollama_client module."""

import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock


class TestOllamaClientInit:
    """Test OllamaClient initialization."""
    
    def test_init_default_url(self, temp_data_dir):
        """Test default URL initialization."""
        from gangdan.core.ollama_client import OllamaClient
        
        client = OllamaClient()
        assert client.api_url == "http://localhost:11434"
    
    def test_init_custom_url(self, temp_data_dir):
        """Test custom URL initialization."""
        from gangdan.core.ollama_client import OllamaClient
        
        client = OllamaClient("http://custom:8080")
        assert client.api_url == "http://custom:8080"
    
    def test_init_url_strips_trailing_slash(self, temp_data_dir):
        """Test that trailing slash is stripped from URL."""
        from gangdan.core.ollama_client import OllamaClient
        
        client = OllamaClient("http://localhost:11434/")
        assert client.api_url == "http://localhost:11434"


class TestOllamaClientAvailability:
    """Test Ollama availability checking."""
    
    def test_is_available_when_online(self, temp_data_dir):
        """Test is_available returns True when API responds."""
        from gangdan.core.ollama_client import OllamaClient
        
        client = OllamaClient()
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        client._session.get = MagicMock(return_value=mock_response)
        
        assert client.is_available() == True
    
    def test_is_available_when_offline(self, temp_data_dir):
        """Test is_available returns False when API is down."""
        from gangdan.core.ollama_client import OllamaClient
        
        client = OllamaClient()
        client._session.get = MagicMock(side_effect=ConnectionError())
        
        assert client.is_available() == False


class TestOllamaClientModels:
    """Test model listing and classification."""
    
    def test_get_models(self, temp_data_dir):
        """Test getting all models."""
        from gangdan.core.ollama_client import OllamaClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.2:latest"},
                {"name": "nomic-embed-text:latest"},
                {"name": "qwen2.5:14b"},
            ]
        }
        
        with patch("requests.Session") as MockSession:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_response
            MockSession.return_value = mock_session
            
            client = OllamaClient()
            models = client.get_models()
            
            assert len(models) == 3
            assert "llama3.2:latest" in models
    
    def test_get_embedding_models(self, temp_data_dir):
        """Test filtering embedding models."""
        from gangdan.core.ollama_client import OllamaClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.2:latest"},
                {"name": "nomic-embed-text:latest"},
                {"name": "bge-m3:latest"},
                {"name": "qwen2.5:14b"},
            ]
        }
        
        with patch("requests.Session") as MockSession:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_response
            MockSession.return_value = mock_session
            
            client = OllamaClient()
            embed_models = client.get_embedding_models()
            
            assert "nomic-embed-text:latest" in embed_models
            assert "bge-m3:latest" in embed_models
            assert "llama3.2:latest" not in embed_models
    
    def test_get_chat_models(self, temp_data_dir):
        """Test filtering chat models (excluding embeddings)."""
        from gangdan.core.ollama_client import OllamaClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.2:latest"},
                {"name": "nomic-embed-text:latest"},
                {"name": "qwen2.5:14b"},
            ]
        }
        
        with patch("requests.Session") as MockSession:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_response
            MockSession.return_value = mock_session
            
            client = OllamaClient()
            chat_models = client.get_chat_models()
            
            assert "llama3.2:latest" in chat_models
            assert "qwen2.5:14b" in chat_models
            assert "nomic-embed-text:latest" not in chat_models
    
    def test_get_reranker_models(self, temp_data_dir):
        """Test filtering reranker models."""
        from gangdan.core.ollama_client import OllamaClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.2:latest"},
                {"name": "bge-reranker-v2:latest"},
                {"name": "qwen2.5:14b"},
            ]
        }
        
        with patch("requests.Session") as MockSession:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_response
            MockSession.return_value = mock_session
            
            client = OllamaClient()
            reranker_models = client.get_reranker_models()
            
            assert "bge-reranker-v2:latest" in reranker_models
            assert "llama3.2:latest" not in reranker_models


class TestOllamaClientEmbeddings:
    """Test embedding generation."""
    
    def test_embed(self, temp_data_dir):
        """Test generating embeddings."""
        from gangdan.core.ollama_client import OllamaClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "embedding": [0.1, 0.2, 0.3, 0.4, 0.5]
        }
        
        with patch("requests.Session") as MockSession:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_response
            MockSession.return_value = mock_session
            
            client = OllamaClient()
            embedding = client.embed("test text", "nomic-embed-text")
            
            assert len(embedding) == 5
            assert embedding[0] == 0.1
    
    def test_embed_truncates_long_text(self, temp_data_dir):
        """Test that long text is truncated to 500 chars."""
        from gangdan.core.ollama_client import OllamaClient
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1]}
        
        with patch("requests.Session") as MockSession:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_response
            MockSession.return_value = mock_session
            
            client = OllamaClient()
            long_text = "x" * 1000
            client.embed(long_text, "model")
            
            # Check that the text was truncated
            call_args = mock_session.post.call_args
            sent_text = call_args[1]["json"]["prompt"]
            assert len(sent_text) == 500


class TestOllamaClientChat:
    """Test chat functionality."""
    
    def test_chat_complete(self, temp_data_dir):
        """Test non-streaming chat completion."""
        from gangdan.core.ollama_client import OllamaClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Hello! How can I help you?"}
        }
        
        with patch("requests.Session") as MockSession:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_response
            MockSession.return_value = mock_session
            
            client = OllamaClient()
            messages = [{"role": "user", "content": "Hello"}]
            response = client.chat_complete(messages, "llama3.2")
            
            assert response == "Hello! How can I help you?"
    
    def test_chat_stream(self, temp_data_dir):
        """Test streaming chat."""
        from gangdan.core.ollama_client import OllamaClient
        
        # Mock streaming response
        def mock_iter_lines():
            yield b'{"message": {"content": "Hello"}}'
            yield b'{"message": {"content": " there"}}'
            yield b'{"message": {"content": "!"}, "done": true}'
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines = mock_iter_lines
        
        with patch("requests.Session") as MockSession:
            mock_session = MagicMock()
            mock_session.post.return_value = mock_response
            MockSession.return_value = mock_session
            
            client = OllamaClient()
            messages = [{"role": "user", "content": "Hi"}]
            
            chunks = list(client.chat_stream(messages, "llama3.2"))
            
            assert "Hello" in chunks
            assert " there" in chunks
    
    def test_chat_stream_stop(self, temp_data_dir):
        """Test stopping streaming chat."""
        from gangdan.core.ollama_client import OllamaClient
        
        client = OllamaClient()
        client.stop_generation()
        
        assert client.is_stopped() == True
        
        client.reset_stop()
        assert client.is_stopped() == False


class TestOllamaClientTranslation:
    """Test translation functionality."""
    
    def test_translate_same_language(self, temp_data_dir):
        """Test translation returns original when same language."""
        from gangdan.core.ollama_client import OllamaClient
        
        client = OllamaClient()
        result = client.translate("Hello", "en", "en")
        
        assert result == "Hello"
    
    def test_translate_empty_text(self, temp_data_dir):
        """Test translation returns empty for empty text."""
        from gangdan.core.ollama_client import OllamaClient
        
        client = OllamaClient()
        result = client.translate("", "en", "zh")
        
        assert result == ""
