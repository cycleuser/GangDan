"""Tests for arXiv full-text fetcher."""

from unittest.mock import MagicMock, patch

import pytest

from gangdan.core.arxiv_fetcher import ArxivFullTextFetcher
from gangdan.core.research_models import ArxivFullText


class TestArxivFullTextFetcher:
    """Test arXiv full-text fetching with fallback."""

    def test_normalize_id_valid(self):
        assert ArxivFullTextFetcher._normalize_id("2301.12345") == "2301.12345"
        assert ArxivFullTextFetcher._normalize_id("arxiv.org/abs/2301.12345") == "2301.12345"
        assert ArxivFullTextFetcher._normalize_id("https://arxiv.org/abs/2301.12345v1") == "2301.12345"

    def test_normalize_id_invalid(self):
        assert ArxivFullTextFetcher._normalize_id("") == ""
        assert ArxivFullTextFetcher._normalize_id("invalid") == ""

    def test_fetch_full_text_invalid_id(self):
        fetcher = ArxivFullTextFetcher()
        result = fetcher.fetch_full_text("")
        assert not result.arxiv_id
        assert result.error == "Invalid arXiv ID"

    @patch("gangdan.core.arxiv_fetcher.requests.Session.get")
    def test_fetch_full_text_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = "# Test Paper\n\nThis is the abstract content." * 10
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        fetcher = ArxivFullTextFetcher()
        result = fetcher.fetch_full_text("2301.12345")

        assert result.arxiv_id == "2301.12345"
        assert result.source in ("alphaxiv_overview", "alphaxiv_full", "arxiv_html", "ar5iv_labs", "ar5iv", "arxiv_abstract")
        assert result.content

    @patch("gangdan.core.arxiv_fetcher.requests.Session.get")
    def test_fetch_full_text_all_fail(self, mock_get):
        mock_get.side_effect = Exception("Network error")

        fetcher = ArxivFullTextFetcher()
        result = fetcher.fetch_full_text("2301.12345")

        assert result.source == "none"
        assert result.error == "All sources failed"

    def test_clean_markdown(self):
        content = "## Title\n\n<!-- comment -->\n\nSome text\n\n"
        cleaned = ArxivFullTextFetcher._clean_markdown(content)
        assert "<!--" not in cleaned
        assert "## Title" in cleaned

    def test_extract_abstract_html(self):
        html = '<html><body><abstract>This is the abstract text.</abstract></body></html>'
        result = ArxivFullTextFetcher._extract_abstract_html(html)
        assert result == "This is the abstract text."

    def test_extract_abstract_html_no_abstract(self):
        html = "<html><body>No abstract here</body></html>"
        result = ArxivFullTextFetcher._extract_abstract_html(html)
        assert result == ""
