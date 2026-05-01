"""Tests for enhanced Semantic Scholar fetcher methods."""

from unittest.mock import MagicMock, patch

import pytest

from gangdan.core.research_models import PaperMetadata
from gangdan.core.research_searcher import SemanticScholarFetcher
from gangdan.core.s2_cache import S2Cache


class TestSemanticScholarFetcherEnhanced:
    """Test enhanced S2 methods: get_paper, get_references, get_citations, get_recommendations, autocomplete."""

    def _make_fetcher(self):
        return SemanticScholarFetcher(api_key="", cache=S2Cache(ttl_seconds=60))

    @patch("gangdan.core.research_searcher.requests.Session.get")
    def test_get_paper_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "paperId": "abc123",
            "title": "Test Paper",
            "authors": [{"name": "Author One"}],
            "year": 2023,
            "abstract": "Test abstract",
            "externalIds": {"DOI": "10.1234/test"},
            "url": "https://example.com",
            "isOpenAccess": True,
            "openAccessPdf": {"url": "http://example.com/pdf"},
            "citationCount": 100,
            "influentialCitationCount": 10,
            "venue": "Test Conference",
            "journal": {"name": "Test Journal"},
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        fetcher = self._make_fetcher()
        result = fetcher.get_paper("abc123")

        assert result is not None
        assert result.title == "Test Paper"
        assert result.year == 2023

    @patch("gangdan.core.research_searcher.requests.Session.get")
    def test_get_paper_failure(self, mock_get):
        mock_get.side_effect = Exception("API error")

        fetcher = self._make_fetcher()
        result = fetcher.get_paper("abc123")

        assert result is None

    @patch("gangdan.core.research_searcher.requests.Session.get")
    def test_get_references(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "paperId": "ref1",
                    "title": "Reference Paper",
                    "authors": [{"name": "Ref Author"}],
                    "year": 2020,
                    "abstract": "Ref abstract",
                    "externalIds": {},
                    "url": "https://example.com/ref",
                    "isOpenAccess": False,
                    "openAccessPdf": {},
                    "citationCount": 50,
                    "influentialCitationCount": 5,
                    "venue": "",
                    "journal": {},
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        fetcher = self._make_fetcher()
        results = fetcher.get_references("abc123", limit=10)

        assert len(results) == 1
        assert results[0].title == "Reference Paper"

    @patch("gangdan.core.research_searcher.requests.Session.get")
    def test_get_citations(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "paperId": "cit1",
                    "title": "Citing Paper",
                    "authors": [{"name": "Cit Author"}],
                    "year": 2024,
                    "abstract": "Cit abstract",
                    "externalIds": {},
                    "url": "https://example.com/cit",
                    "isOpenAccess": False,
                    "openAccessPdf": {},
                    "citationCount": 10,
                    "influentialCitationCount": 1,
                    "venue": "",
                    "journal": {},
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        fetcher = self._make_fetcher()
        results = fetcher.get_citations("abc123", limit=10)

        assert len(results) == 1
        assert results[0].title == "Citing Paper"

    @patch("gangdan.core.research_searcher.requests.Session.get")
    def test_get_recommendations(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "recommendedPapers": [
                {
                    "paperId": "rec1",
                    "title": "Recommended Paper",
                    "authors": [{"name": "Rec Author"}],
                    "year": 2023,
                    "abstract": "Rec abstract",
                    "externalIds": {},
                    "url": "https://example.com/rec",
                    "isOpenAccess": True,
                    "openAccessPdf": {"url": "http://example.com/rec.pdf"},
                    "citationCount": 200,
                    "influentialCitationCount": 20,
                    "venue": "Rec Venue",
                    "journal": {"name": "Rec Journal"},
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        fetcher = self._make_fetcher()
        results = fetcher.get_recommendations("abc123", limit=10)

        assert len(results) == 1
        assert results[0].title == "Recommended Paper"

    @patch("gangdan.core.research_searcher.requests.Session.get")
    def test_autocomplete(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "suggestions": [
                {"title": "Attention Is All You Need", "score": 0.95},
                {"title": "Attention Mechanisms in NLP", "score": 0.85},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        fetcher = self._make_fetcher()
        results = fetcher.autocomplete("attention", limit=5)

        assert len(results) == 2
        assert results[0]["title"] == "Attention Is All You Need"

    @patch("gangdan.core.research_searcher.requests.Session.get")
    def test_autocomplete_failure(self, mock_get):
        mock_get.side_effect = Exception("API error")

        fetcher = self._make_fetcher()
        results = fetcher.autocomplete("test")

        assert results == []

    def test_cache_integration(self):
        cache = S2Cache(ttl_seconds=60)
        fetcher = SemanticScholarFetcher(api_key="", cache=cache)

        paper = PaperMetadata(title="Cached Paper", year=2023)
        cache.put("s2_paper:test123", paper)

        result = fetcher.get_paper("test123")
        assert result is not None
        assert result.title == "Cached Paper"
