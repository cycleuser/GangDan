"""Tests for web searcher engine abstraction."""

from unittest.mock import MagicMock, patch

import pytest

from gangdan.core.web_searcher import (
    BraveSearcher,
    DuckDuckGoSearcher,
    SerperSearcher,
    WebSearcher,
)


class TestDuckDuckGoSearcher:
    """Test DuckDuckGo search engine."""

    @patch("gangdan.core.web_searcher.requests.Session.post")
    def test_search_success(self, mock_post):
        html = (
            '<a class="result__a" href="http://example.com">Example</a>'
            '<a class="result__snippet">This is an example</a>'
        )
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        searcher = DuckDuckGoSearcher()
        results = searcher.search("test", max_results=5)

        assert len(results) == 1
        assert results[0]["title"] == "Example"
        assert results[0]["url"] == "http://example.com"

    @patch("gangdan.core.web_searcher.requests.Session.post")
    def test_search_failure(self, mock_post):
        mock_post.side_effect = Exception("Network error")

        searcher = DuckDuckGoSearcher()
        results = searcher.search("test")

        assert results == []


class TestSerperSearcher:
    """Test Serper search engine."""

    @patch("gangdan.core.web_searcher.requests.Session.post")
    def test_search_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "organic": [
                {"title": "Result 1", "link": "http://example.com/1", "snippet": "Snippet 1"},
                {"title": "Result 2", "link": "http://example.com/2", "snippet": "Snippet 2"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        searcher = SerperSearcher(api_key="test_key")
        results = searcher.search("test", max_results=5)

        assert len(results) == 2
        assert results[0]["title"] == "Result 1"

    @patch("gangdan.core.web_searcher.requests.Session.post")
    def test_search_failure(self, mock_post):
        mock_post.side_effect = Exception("API error")

        searcher = SerperSearcher(api_key="test_key")
        results = searcher.search("test")

        assert results == []


class TestBraveSearcher:
    """Test Brave search engine."""

    @patch("gangdan.core.web_searcher.requests.Session.get")
    def test_search_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {"title": "Result 1", "url": "http://example.com/1", "description": "Desc 1"},
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        searcher = BraveSearcher(api_key="test_key")
        results = searcher.search("test", max_results=5)

        assert len(results) == 1
        assert results[0]["title"] == "Result 1"


class TestWebSearcher:
    """Test WebSearcher engine selection."""

    def test_default_engine(self):
        searcher = WebSearcher()
        assert isinstance(searcher._engine, DuckDuckGoSearcher)

    def test_serper_with_key(self):
        searcher = WebSearcher(engine="serper", serper_api_key="test_key")
        assert isinstance(searcher._engine, SerperSearcher)

    def test_brave_with_key(self):
        searcher = WebSearcher(engine="brave", brave_api_key="test_key")
        assert isinstance(searcher._engine, BraveSearcher)

    def test_serper_without_key_falls_back(self):
        searcher = WebSearcher(engine="serper", serper_api_key="")
        assert isinstance(searcher._engine, DuckDuckGoSearcher)

    def test_unknown_engine_falls_back(self):
        searcher = WebSearcher(engine="unknown")
        assert isinstance(searcher._engine, DuckDuckGoSearcher)
