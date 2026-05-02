"""Tests for preprint_fetcher module."""

import pytest
from unittest.mock import MagicMock, patch

from gangdan.core.preprint_fetcher import (
    ArxivPreprintFetcher,
    BioRxivPreprintFetcher,
    MedRxivPreprintFetcher,
    PreprintFetcher,
    PreprintMetadata,
)


class TestPreprintMetadata:
    """Test PreprintMetadata dataclass."""

    def test_defaults(self) -> None:
        meta = PreprintMetadata()
        assert meta.preprint_id == ""
        assert meta.title == ""
        assert meta.authors == []
        assert meta.has_html is False
        assert meta.has_tex is False
        assert meta.preferred_format == "pdf"

    def test_authors_str_empty(self) -> None:
        meta = PreprintMetadata(authors=[])
        assert meta.authors_str == "Unknown"

    def test_authors_str_single(self) -> None:
        meta = PreprintMetadata(authors=["Alice"])
        assert meta.authors_str == "Alice"

    def test_authors_str_multiple(self) -> None:
        meta = PreprintMetadata(authors=["Alice", "Bob", "Charlie", "Dave"])
        assert meta.authors_str == "Alice, Bob, Charlie et al."

    def test_authors_str_three(self) -> None:
        meta = PreprintMetadata(authors=["Alice", "Bob", "Charlie"])
        assert meta.authors_str == "Alice, Bob, Charlie"

    def test_short_title_short(self) -> None:
        meta = PreprintMetadata(title="Short Title")
        assert meta.short_title == "Short Title"

    def test_short_title_long(self) -> None:
        meta = PreprintMetadata(title="A" * 100)
        assert len(meta.short_title) == 80
        assert meta.short_title.endswith("...")

    def test_to_dict(self) -> None:
        meta = PreprintMetadata(
            preprint_id="2301.12345",
            title="Test Paper",
            authors=["Alice"],
            has_html=True,
        )
        d = meta.to_dict()
        assert d["preprint_id"] == "2301.12345"
        assert d["title"] == "Test Paper"
        assert d["has_html"] is True
        assert d["preferred_format"] == "html"

    def test_preferred_format_html(self) -> None:
        meta = PreprintMetadata(has_html=True, has_tex=True)
        assert meta.preferred_format == "html"

    def test_preferred_format_tex_only(self) -> None:
        meta = PreprintMetadata(has_html=False, has_tex=True)
        assert meta.preferred_format == "tex"


class TestArxivPreprintFetcher:
    """Test ArxivPreprintFetcher."""

    def test_normalize_id_standard(self) -> None:
        assert ArxivPreprintFetcher._normalize_id("2301.12345") == "2301.12345"

    def test_normalize_id_with_version(self) -> None:
        assert ArxivPreprintFetcher._normalize_id("2301.12345v1") == "2301.12345"

    def test_normalize_id_from_url(self) -> None:
        assert ArxivPreprintFetcher._normalize_id("https://arxiv.org/abs/2301.12345") == "2301.12345"

    def test_normalize_id_invalid(self) -> None:
        assert ArxivPreprintFetcher._normalize_id("invalid") == ""

    def test_extract_arxiv_id_abs_url(self) -> None:
        fetcher = ArxivPreprintFetcher()
        assert fetcher._extract_arxiv_id("https://arxiv.org/abs/2301.12345") == "2301.12345"

    def test_extract_arxiv_id_pdf_url(self) -> None:
        fetcher = ArxivPreprintFetcher()
        assert fetcher._extract_arxiv_id("https://arxiv.org/pdf/2301.12345.pdf") == "2301.12345"

    def test_extract_arxiv_id_raw(self) -> None:
        fetcher = ArxivPreprintFetcher()
        assert fetcher._extract_arxiv_id("2301.12345") == "2301.12345"

    def test_search_success(self) -> None:
        mock_resp = MagicMock()
        mock_resp.text = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
            <entry>
                <title>Test Paper</title>
                <summary>Test abstract</summary>
                <published>2023-01-15T00:00:00Z</published>
                <updated>2023-01-16T00:00:00Z</updated>
                <id>http://arxiv.org/abs/2301.12345</id>
                <author><name>Alice</name></author>
                <author><name>Bob</name></author>
                <category term="cs.AI"/>
                <link rel="alternate" href="https://arxiv.org/abs/2301.12345"/>
                <link title="pdf" href="https://arxiv.org/pdf/2301.12345"/>
            </entry>
        </feed>"""
        mock_resp.raise_for_status = MagicMock()

        fetcher = ArxivPreprintFetcher()
        with patch.object(fetcher._session, "get", return_value=mock_resp):
            with patch.object(fetcher, "_detect_source_formats"):
                results = fetcher.search("machine learning")

        assert len(results) == 1
        assert results[0].title == "Test Paper"
        assert results[0].preprint_id == "2301.12345"
        assert len(results[0].authors) == 2

    def test_search_failure(self) -> None:
        fetcher = ArxivPreprintFetcher()
        with patch.object(fetcher._session, "get", side_effect=Exception("Network error")):
            results = fetcher.search("test")
        assert results == []

    def test_detect_source_formats_html_available(self) -> None:
        fetcher = ArxivPreprintFetcher()
        paper = PreprintMetadata(preprint_id="2301.12345")

        with patch.object(fetcher._session, "head") as mock_head:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_head.return_value = mock_resp

            fetcher._detect_source_formats(paper)

        assert paper.has_html is True
        assert paper.has_tex is True
        assert paper.preferred_format == "html"

    def test_detect_source_formats_html_unavailable(self) -> None:
        fetcher = ArxivPreprintFetcher()
        paper = PreprintMetadata(preprint_id="2301.12345")

        with patch.object(fetcher._session, "head") as mock_head:
            mock_head.side_effect = Exception("404")

            fetcher._detect_source_formats(paper)

        assert paper.has_html is False
        assert paper.has_tex is True
        assert paper.preferred_format == "tex"


class TestBioRxivPreprintFetcher:
    """Test BioRxivPreprintFetcher."""

    def test_search_success(self) -> None:
        fetcher = BioRxivPreprintFetcher()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "collection": [
                {
                    "doi": "10.1101/2023.01.01.123456",
                    "title": "Genomics Study Paper",
                    "abstract": "Test abstract about genomics",
                    "authors": "Alice; Bob",
                    "date": "2023-01-01",
                    "category": "Genomics",
                    "link": "https://www.biorxiv.org/content/10.1101/2023.01.01.123456",
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(fetcher._session, "get", return_value=mock_resp):
            results = fetcher.search("genomics")

        assert len(results) == 1
        assert results[0].title == "Genomics Study Paper"
        assert results[0].source_platform == "biorxiv"

    def test_search_empty(self) -> None:
        fetcher = BioRxivPreprintFetcher()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"collection": []}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(fetcher._session, "get", return_value=mock_resp):
            results = fetcher.search("nonexistent")
        assert results == []


class TestMedRxivPreprintFetcher:
    """Test MedRxivPreprintFetcher."""

    def test_search_success(self) -> None:
        fetcher = MedRxivPreprintFetcher()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "collection": [
                {
                    "doi": "10.1101/2023.01.01.234567",
                    "title": "Epidemiology Research Paper",
                    "abstract": "Medical abstract about epidemiology",
                    "authors": "Doctor; Nurse",
                    "date": "2023-01-01",
                    "category": "Epidemiology",
                    "link": "https://www.medrxiv.org/content/10.1101/2023.01.01.234567",
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(fetcher._session, "get", return_value=mock_resp):
            results = fetcher.search("epidemiology")

        assert len(results) == 1
        assert results[0].source_platform == "medrxiv"


class TestPreprintFetcher:
    """Test unified PreprintFetcher."""

    def test_init_default_platforms(self) -> None:
        fetcher = PreprintFetcher()
        assert "arxiv" in fetcher.fetchers
        assert "biorxiv" in fetcher.fetchers
        assert "medrxiv" in fetcher.fetchers

    def test_init_custom_platforms(self) -> None:
        fetcher = PreprintFetcher(platforms=["arxiv"])
        assert "arxiv" in fetcher.fetchers
        assert "biorxiv" not in fetcher.fetchers

    def test_init_invalid_platform(self) -> None:
        fetcher = PreprintFetcher(platforms=["invalid"])
        assert len(fetcher.fetchers) == 0

    @patch("gangdan.core.preprint_fetcher.ArxivPreprintFetcher")
    @patch("gangdan.core.preprint_fetcher.BioRxivPreprintFetcher")
    def test_search_deduplication(self, mock_biorxiv: MagicMock, mock_arxiv: MagicMock) -> None:
        mock_arxiv_instance = MagicMock()
        mock_arxiv_instance.search.return_value = [
            PreprintMetadata(preprint_id="2301.12345", source_platform="arxiv", has_html=True),
        ]
        mock_arxiv.return_value = mock_arxiv_instance

        mock_biorxiv_instance = MagicMock()
        mock_biorxiv_instance.search.return_value = []
        mock_biorxiv.return_value = mock_biorxiv_instance

        fetcher = PreprintFetcher(platforms=["arxiv", "biorxiv"])
        fetcher.fetchers = {
            "arxiv": mock_arxiv_instance,
            "biorxiv": mock_biorxiv_instance,
        }

        results = fetcher.search("test")
        assert len(results) == 1

    def test_get_html_preprints(self) -> None:
        fetcher = PreprintFetcher()
        papers = [
            PreprintMetadata(preprint_id="1", has_html=True),
            PreprintMetadata(preprint_id="2", has_html=False),
            PreprintMetadata(preprint_id="3", has_html=True),
        ]
        html_papers = fetcher.get_html_preprints(papers)
        assert len(html_papers) == 2
        assert all(p.has_html for p in html_papers)

    def test_get_tex_preprints(self) -> None:
        fetcher = PreprintFetcher()
        papers = [
            PreprintMetadata(preprint_id="1", has_tex=True),
            PreprintMetadata(preprint_id="2", has_tex=False),
        ]
        tex_papers = fetcher.get_tex_preprints(papers)
        assert len(tex_papers) == 1

    def test_get_preferred_format_html(self) -> None:
        fetcher = PreprintFetcher()
        paper = PreprintMetadata(has_html=True, has_tex=True)
        assert fetcher.get_preferred_format(paper) == "html"

    def test_get_preferred_format_tex(self) -> None:
        fetcher = PreprintFetcher()
        paper = PreprintMetadata(has_html=False, has_tex=True)
        assert fetcher.get_preferred_format(paper) == "tex"

    def test_get_preferred_format_pdf(self) -> None:
        fetcher = PreprintFetcher()
        paper = PreprintMetadata(has_html=False, has_tex=False)
        assert fetcher.get_preferred_format(paper) == "pdf"
