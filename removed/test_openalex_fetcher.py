"""Tests for OpenAlexFetcher."""

import json
from unittest.mock import MagicMock, patch

from gangdan.core.research_searcher import OpenAlexFetcher


class TestOpenAlexFetcher:
    """Test OpenAlexFetcher functionality."""

    def test_openalex_fetcher_init(self):
        """Test fetcher initialization."""
        fetcher = OpenAlexFetcher(timeout=10, max_results=5)
        assert fetcher.name == "openalex"
        assert fetcher.timeout == 10
        assert fetcher.max_results == 5

    def test_openalex_fetcher_init_with_email(self):
        """Test fetcher initialization with email for polite pool."""
        fetcher = OpenAlexFetcher(email="test@example.com")
        assert fetcher.email == "test@example.com"
        assert "mailto" in fetcher._session.headers
        assert fetcher._session.headers["mailto"] == "test@example.com"

    def test_openalex_search_success(self):
        """Test successful search with valid response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": "https://openalex.org/W1234567890",
                    "title": "Attention Is All You Need",
                    "doi": "https://doi.org/10.5555/3295222.3295349",
                    "publication_year": 2017,
                    "abstract_inverted_index": {
                        "Attention": [0],
                        "Is": [1],
                        "All": [2],
                        "You": [3],
                        "Need": [4],
                    },
                    "authorships": [
                        {"author": {"display_name": "Ashish Vaswani"}},
                        {"author": {"display_name": "Noam Shazeer"}},
                    ],
                    "open_access": {"oa_url": "https://arxiv.org/pdf/1706.03762"},
                    "cited_by_count": 100000,
                    "primary_location": {
                        "landing_page_url": "https://arxiv.org/abs/1706.03762",
                        "source": {"display_name": "arXiv"},
                    },
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(OpenAlexFetcher, "__init__", lambda self, **kw: None):
            fetcher = OpenAlexFetcher()
            fetcher.timeout = 15
            fetcher.max_results = 10
            fetcher._get_proxies = lambda: None
            fetcher._session = MagicMock()
            fetcher._session.get.return_value = mock_response

            papers = fetcher.search("attention mechanism")

        assert len(papers) == 1
        paper = papers[0]
        assert paper.title == "Attention Is All You Need"
        assert paper.doi == "10.5555/3295222.3295349"
        assert paper.year == 2017
        assert paper.authors == ["Ashish Vaswani", "Noam Shazeer"]
        assert paper.source == "openalex"
        assert paper.citations == 100000
        assert paper.pdf_url == "https://arxiv.org/pdf/1706.03762"
        assert paper.url == "https://arxiv.org/abs/1706.03762"
        assert paper.journal == "arXiv"
        assert paper.abstract == "Attention Is All You Need"

    def test_openalex_search_empty_response(self):
        """Test search with empty results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()

        with patch.object(OpenAlexFetcher, "__init__", lambda self, **kw: None):
            fetcher = OpenAlexFetcher()
            fetcher.timeout = 15
            fetcher.max_results = 10
            fetcher._get_proxies = lambda: None
            fetcher._session = MagicMock()
            fetcher._session.get.return_value = mock_response

            papers = fetcher.search("nonexistent query")

        assert len(papers) == 0

    def test_openalex_search_api_error(self):
        """Test search with API error."""
        with patch.object(OpenAlexFetcher, "__init__", lambda self, **kw: None):
            fetcher = OpenAlexFetcher()
            fetcher.timeout = 15
            fetcher.max_results = 10
            fetcher._get_proxies = lambda: None
            fetcher._session = MagicMock()
            fetcher._session.get.side_effect = Exception("Connection failed")

            papers = fetcher.search("test")

        assert len(papers) == 0

    def test_openalex_decode_inverted_index(self):
        """Test abstract inverted index decoding."""
        inverted_index = {
            "Deep": [0],
            "learning": [1],
            "is": [2],
            "a": [3],
            "subset": [4],
            "of": [5],
            "ML": [6],
        }
        result = OpenAlexFetcher._decode_inverted_index(inverted_index)
        assert result == "Deep learning is a subset of ML"

    def test_openalex_decode_empty_inverted_index(self):
        """Test empty inverted index returns empty string."""
        assert OpenAlexFetcher._decode_inverted_index({}) == ""
        assert OpenAlexFetcher._decode_inverted_index(None) == ""

    def test_openalex_search_none_fields(self):
        """Test handling of None/missing fields in response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": None,
                    "title": None,
                    "doi": None,
                    "publication_year": None,
                    "abstract_inverted_index": None,
                    "authorships": None,
                    "open_access": None,
                    "cited_by_count": None,
                    "primary_location": None,
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(OpenAlexFetcher, "__init__", lambda self, **kw: None):
            fetcher = OpenAlexFetcher()
            fetcher.timeout = 15
            fetcher.max_results = 10
            fetcher._get_proxies = lambda: None
            fetcher._session = MagicMock()
            fetcher._session.get.return_value = mock_response

            papers = fetcher.search("test")

        assert len(papers) == 1
        paper = papers[0]
        assert paper.title == ""
        assert paper.doi == ""
        assert paper.year == 0
        assert paper.authors == []
