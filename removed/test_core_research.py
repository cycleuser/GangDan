"""Tests for the research search module: query expander, models, searchers."""

import json
import pytest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

from gangdan.core.query_expander import QueryExpander, ExpandedQuery, QUERY_EXPANSION_PROMPT
from gangdan.core.research_models import (
    PaperMetadata,
    SearchResult,
    DownloadResult,
    ConversionResult,
    PaperRecord,
)
from gangdan.core.research_searcher import (
    ArxivFetcher,
    SemanticScholarFetcher,
    CrossRefFetcher,
    PubMedFetcher,
    GitHubFetcher,
    ResearchSearcher,
)
from gangdan.core.pdf_downloader import PDFDownloadManager
from gangdan.core.pdf_renamer import PDFRenamer
from gangdan.core.pdf_converter import PDFConverter


# =============================================================================
# QueryExpander Tests
# =============================================================================


class TestExpandedQuery:
    """Tests for the ExpandedQuery dataclass."""

    def test_default_values(self):
        eq = ExpandedQuery(original="test query")
        assert eq.original == "test query"
        assert eq.expanded == []
        assert eq.precise == []
        assert eq.broad == []
        assert eq.domain == ""
        assert eq.recommended_sources == []

    def test_all_queries_deduplication(self):
        eq = ExpandedQuery(
            original="test",
            expanded=["query A", "query B", "Query a", "query C"],
        )
        result = eq.all_queries()
        assert len(result) == 3
        assert "query A" in result
        assert "query B" in result
        assert "query C" in result

    def test_all_queries_empty(self):
        eq = ExpandedQuery(original="test")
        assert eq.all_queries() == []

    def test_all_queries_whitespace(self):
        eq = ExpandedQuery(original="test", expanded=["  ", "query A", ""])
        result = eq.all_queries()
        assert len(result) == 1
        assert "query A" in result


class TestQueryExpander:
    """Tests for the QueryExpander class."""

    def test_disabled_returns_original(self):
        """When disabled, expander should return original query."""
        mock_client = MagicMock()
        expander = QueryExpander(llm_client=mock_client, enabled=False)
        result = expander.expand("transformer attention")
        assert result.original == "transformer attention"
        assert result.expanded == ["transformer attention"]
        assert result.recommended_sources == ["arxiv", "semantic_scholar", "crossref"]
        mock_client.chat_complete.assert_not_called()

    def test_empty_query(self):
        """Empty query should return empty result."""
        mock_client = MagicMock()
        expander = QueryExpander(llm_client=mock_client, enabled=True)
        result = expander.expand("")
        assert result.original == ""
        assert result.expanded == []

    def test_enabled_calls_llm(self):
        """When enabled, expander should call the LLM."""
        mock_response = json.dumps({
            "domain": "machine learning",
            "precise": ["transformer attention mechanism", "self-attention neural network"],
            "broad": ["deep learning architectures", "sequence modeling"],
            "synonyms": ["attention mechanism", "sequence-to-sequence models"],
            "preprint": ["transformer attention arXiv"],
            "github": ["transformer implementation"],
            "recommended_sources": ["arxiv", "semantic_scholar", "github"],
        })
        mock_client = MagicMock()
        mock_client.chat_complete.return_value = mock_response

        expander = QueryExpander(llm_client=mock_client, enabled=True, model="test-model")
        result = expander.expand("transformer attention")

        assert result.original == "transformer attention"
        assert len(result.precise) >= 1
        assert len(result.broad) >= 1
        assert result.domain == "machine learning"
        mock_client.chat_complete.assert_called_once()

    def test_llm_error_fallback(self):
        """When LLM fails, should fall back to original query."""
        mock_client = MagicMock()
        mock_client.chat_complete.return_value = "[Error: connection failed]"

        expander = QueryExpander(llm_client=mock_client, enabled=True)
        result = expander.expand("test query")
        assert result.original == "test query"
        assert result.expanded == ["test query"]
        assert result.metadata.get("fallback") is True

    def test_llm_malformed_json_fallback(self):
        """When LLM returns invalid JSON, should fall back."""
        mock_client = MagicMock()
        mock_client.chat_complete.return_value = "This is not JSON at all"

        expander = QueryExpander(llm_client=mock_client, enabled=True)
        result = expander.expand("test query")
        assert result.expanded == ["test query"]

    def test_custom_model_passed_to_llm(self):
        """Custom model should be passed to the LLM client."""
        mock_response = json.dumps({
            "domain": "", "precise": [], "broad": [],
            "synonyms": [], "preprint": [], "github": [],
            "recommended_sources": [],
        })
        mock_client = MagicMock()
        mock_client.chat_complete.return_value = mock_response

        expander = QueryExpander(llm_client=mock_client, enabled=True, model="qwen2:7b")
        expander.expand("test")

        call_kwargs = mock_client.chat_complete.call_args
        assert call_kwargs[1].get("model") == "qwen2:7b" or "model" in str(call_kwargs)


# =============================================================================
# PaperMetadata Tests
# =============================================================================


class TestPaperMetadata:
    """Tests for PaperMetadata dataclass."""

    def test_authors_str_single(self):
        p = PaperMetadata(authors=["Smith"])
        assert p.authors_str == "Smith"

    def test_authors_str_multiple(self):
        p = PaperMetadata(authors=["Smith", "Jones", "Brown", "Lee"])
        assert p.authors_str == "Smith, Jones, Brown et al."

    def test_authors_str_empty(self):
        p = PaperMetadata(authors=[])
        assert p.authors_str == "Unknown"

    def test_short_title_short(self):
        p = PaperMetadata(title="Short Title")
        assert p.short_title == "Short Title"

    def test_short_title_long(self):
        p = PaperMetadata(title="A" * 100)
        assert len(p.short_title) <= 83
        assert p.short_title.endswith("...")

    def test_to_dict(self):
        p = PaperMetadata(title="Test", authors=["A"], year=2023, doi="10.1234/test")
        d = p.to_dict()
        assert d["title"] == "Test"
        assert d["authors"] == ["A"]
        assert d["year"] == 2023
        assert d["doi"] == "10.1234/test"


class TestPaperRecord:
    """Tests for PaperRecord dataclass."""

    def test_paper_id_from_doi(self):
        meta = PaperMetadata(doi="10.1234/test")
        record = PaperRecord(metadata=meta)
        assert len(record.paper_id) == 12

    def test_paper_id_from_arxiv(self):
        meta = PaperMetadata(arxiv_id="2301.12345")
        record = PaperRecord(metadata=meta)
        assert len(record.paper_id) == 12

    def test_to_dict_roundtrip(self):
        meta = PaperMetadata(title="Test Paper", authors=["Author A"], year=2024)
        record = PaperRecord(metadata=meta, local_pdf="/path/to/paper.pdf", tags=["ml"])
        d = record.to_dict()
        restored = PaperRecord.from_dict(d)
        assert restored.metadata.title == "Test Paper"
        assert restored.local_pdf == "/path/to/paper.pdf"
        assert restored.tags == ["ml"]


class TestDownloadResult:
    """Tests for DownloadResult dataclass."""

    def test_default_failure(self):
        r = DownloadResult()
        assert r.success is False
        assert r.error == ""

    def test_success(self):
        r = DownloadResult(success=True, pdf_path="/tmp/paper.pdf", file_size=1024)
        assert r.success is True
        assert r.file_size == 1024


class TestConversionResult:
    """Tests for ConversionResult dataclass."""

    def test_default_failure(self):
        r = ConversionResult()
        assert r.success is False
        assert r.page_count == 0

    def test_success(self):
        r = ConversionResult(success=True, markdown_path="/tmp/paper.md", engine="pymupdf4llm", page_count=10)
        assert r.success is True
        assert r.engine == "pymupdf4llm"


# =============================================================================
# ArxivFetcher Tests
# =============================================================================


class TestArxivFetcher:
    """Tests for ArxivFetcher."""

    def test_extract_arxiv_id_from_url(self):
        assert ArxivFetcher._extract_arxiv_id("https://arxiv.org/abs/2301.12345") == "2301.12345"
        assert ArxivFetcher._extract_arxiv_id("https://arxiv.org/abs/2301.12345v1") == "2301.12345"
        assert ArxivFetcher._extract_arxiv_id("https://arxiv.org/pdf/2301.12345.pdf") == "2301.12345"
        assert ArxivFetcher._extract_arxiv_id("2301.12345") == "2301.12345"

    def test_parse_atom_response(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.12345v1</id>
    <title>Test Paper Title</title>
    <summary>Test abstract content</summary>
    <published>2023-01-15T00:00:00Z</published>
    <author><name>Smith, John</name></author>
    <author><name>Jones, Mary</name></author>
    <link rel="alternate" href="http://arxiv.org/abs/2301.12345v1"/>
    <link rel="related" title="pdf" href="http://arxiv.org/pdf/2301.12345v1"/>
  </entry>
</feed>"""
        fetcher = ArxivFetcher()
        papers = fetcher._parse_atom_response(xml)
        assert len(papers) == 1
        assert papers[0].title == "Test Paper Title"
        assert papers[0].year == 2023
        assert papers[0].arxiv_id == "2301.12345"
        assert len(papers[0].authors) == 2


class TestSemanticScholarFetcher:
    """Tests for SemanticScholarFetcher."""

    def test_parse_response(self):
        fetcher = SemanticScholarFetcher()
        items = [
            {
                "title": "Attention Is All You Need",
                "authors": [{"name": "Vaswani"}],
                "year": 2017,
                "abstract": "We propose a new network architecture.",
                "externalIds": {"DOI": "10.5555/3295222.3295349", "ArXiv": "1706.03762"},
                "url": "https://semanticscholar.org/paper/abc",
                "citationCount": 50000,
                "isOpenAccess": True,
                "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762.pdf"},
                "venue": "NeurIPS",
            }
        ]
        papers = fetcher._parse_response(items)
        assert len(papers) == 1
        assert papers[0].title == "Attention Is All You Need"
        assert papers[0].doi == "10.5555/3295222.3295349"
        assert papers[0].arxiv_id == "1706.03762"
        assert papers[0].citations == 50000
        assert papers[0].pdf_url == "https://arxiv.org/pdf/1706.03762.pdf"


class TestCrossRefFetcher:
    """Tests for CrossRefFetcher."""

    def test_parse_response(self):
        fetcher = CrossRefFetcher()
        items = [
            {
                "title": ["Deep Learning"],
                "author": [{"given": "Ian", "family": "Goodfellow"}],
                "published-print": {"date-parts": [[2016, 1, 1]]},
                "DOI": "10.5555/3086952",
                "is-referenced-by-count": 100000,
                "container-title": ["Nature"],
                "link": [{"content-type": "application/pdf", "URL": "https://example.com/paper.pdf"}],
            }
        ]
        papers = fetcher._parse_response(items)
        assert len(papers) == 1
        assert papers[0].title == "Deep Learning"
        assert papers[0].year == 2016
        assert papers[0].doi == "10.5555/3086952"


# =============================================================================
# ResearchSearcher Tests
# =============================================================================


class TestResearchSearcher:
    """Tests for ResearchSearcher orchestrator."""

    def test_valid_sources(self):
        assert ResearchSearcher.VALID_SOURCES == {"arxiv", "semantic_scholar", "crossref", "pubmed", "github", "openalex", "dblp"}

    def test_init_default_sources(self):
        searcher = ResearchSearcher()
        assert "arxiv" in searcher.fetchers
        assert "semantic_scholar" in searcher.fetchers
        assert "crossref" in searcher.fetchers

    def test_init_github_source(self):
        searcher = ResearchSearcher(sources=["github"])
        assert "github" in searcher.fetchers

    def test_init_openalex_source(self):
        searcher = ResearchSearcher(sources=["openalex"])
        assert "openalex" in searcher.fetchers

    def test_init_dblp_source(self):
        searcher = ResearchSearcher(sources=["dblp"])
        assert "dblp" in searcher.fetchers

    def test_init_all_sources(self):
        searcher = ResearchSearcher(
            sources=["arxiv", "semantic_scholar", "crossref", "pubmed", "github", "openalex", "dblp"]
        )
        assert len(searcher.fetchers) == 7

    def test_dedup_key_doi(self):
        searcher = ResearchSearcher()
        paper = PaperMetadata(doi="10.1234/test")
        key = searcher._dedup_key(paper)
        assert key == "doi:10.1234/test"

    def test_dedup_key_arxiv(self):
        searcher = ResearchSearcher()
        paper = PaperMetadata(arxiv_id="2301.12345")
        key = searcher._dedup_key(paper)
        assert key == "arxiv:2301.12345"

    def test_dedup_key_title(self):
        searcher = ResearchSearcher()
        paper = PaperMetadata(title="Attention Is All You Need")
        key = searcher._dedup_key(paper)
        assert key.startswith("title:")

    def test_dedup_key_empty(self):
        searcher = ResearchSearcher()
        paper = PaperMetadata()
        key = searcher._dedup_key(paper)
        assert key == ""

    def test_score_paper(self):
        searcher = ResearchSearcher()
        paper = PaperMetadata(
            citations=500,
            abstract="Test abstract",
            pdf_url="https://example.com/paper.pdf",
            doi="10.1234/test",
            source="semantic_scholar",
        )
        score = searcher._score_paper(paper)
        assert score > 0

    def test_score_paper_no_metadata(self):
        searcher = ResearchSearcher()
        paper = PaperMetadata(source="unknown")
        score = searcher._score_paper(paper)
        assert score >= 0


# =============================================================================
# PDFRenamer Tests
# =============================================================================


class TestPDFRenamer:
    """Tests for PDFRenamer."""

    def test_generate_filename_first_surname(self):
        renamer = PDFRenamer(author_format="first_surname")
        meta = PaperMetadata(
            title="Attention Is All You Need",
            authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
            year=2017,
        )
        filename = renamer._generate_filename(meta)
        assert "Vaswani" in filename
        assert "2017" in filename
        assert "Attention Is All You Need" in filename
        assert filename.endswith(".pdf")

    def test_generate_filename_single_author(self):
        renamer = PDFRenamer(author_format="first_surname")
        meta = PaperMetadata(title="Test Paper", authors=["Smith"], year=2023)
        filename = renamer._generate_filename(meta)
        assert "Smith" in filename
        assert "(2023)" in filename

    def test_generate_filename_no_authors(self):
        renamer = PDFRenamer(author_format="first_surname")
        meta = PaperMetadata(title="Unknown Paper", year=2023)
        filename = renamer._generate_filename(meta)
        assert "2023" in filename

    def test_generate_filename_no_year(self):
        renamer = PDFRenamer(author_format="first_surname")
        meta = PaperMetadata(title="Test Paper", authors=["Smith"])
        filename = renamer._generate_filename(meta)
        assert "Smith" in filename

    def test_sanitize_filename(self):
        result = PDFRenamer._sanitize_filename('Test: A/B "Paper" <draft>')
        assert ":" not in result
        assert "/" not in result
        assert '"' not in result
        assert "<" not in result

    def test_generate_filename_long_title(self):
        renamer = PDFRenamer(author_format="first_surname", abbreviate_title=True)
        meta = PaperMetadata(
            title="A" * 200,
            authors=["Smith"],
            year=2023,
        )
        filename = renamer._generate_filename(meta)
        assert len(filename) <= 210


# =============================================================================
# PDFConverter Tests
# =============================================================================


class TestPDFConverter:
    """Tests for PDFConverter."""

    def test_resolve_engine_auto(self):
        converter = PDFConverter(engine="auto")
        engine = converter._resolve_engine()
        assert engine in ("marker", "pymupdf", "pdfplumber", "basic")

    def test_resolve_engine_explicit(self):
        converter = PDFConverter(engine="pymupdf")
        assert converter._resolve_engine() == "pymupdf"

    def test_convert_nonexistent_file(self):
        converter = PDFConverter()
        result = converter.convert(Path("/nonexistent/file.pdf"))
        assert result.success is False
        assert "not found" in result.error.lower() or "PDF" in result.error


# =============================================================================
# PDFDownloadManager Tests
# =============================================================================


class TestPDFDownloadManager:
    """Tests for PDFDownloadManager."""

    def test_init_creates_directory(self, tmp_path):
        papers_dir = tmp_path / "papers"
        manager = PDFDownloadManager(papers_dir=papers_dir)
        assert papers_dir.exists()

    def test_list_papers_empty(self, tmp_path):
        manager = PDFDownloadManager(papers_dir=tmp_path)
        assert manager.list_papers() == []

    def test_list_papers_with_files(self, tmp_path):
        (tmp_path / "test.pdf").write_bytes(b"%PDF-1.4 test")
        manager = PDFDownloadManager(papers_dir=tmp_path)
        papers = manager.list_papers()
        assert len(papers) == 1
        assert papers[0].name == "test.pdf"

    def test_discover_oa_urls_arxiv(self):
        manager = PDFDownloadManager()
        paper = PaperMetadata(arxiv_id="2301.12345")
        urls = manager.discover_oa_urls(paper)
        pdf_urls = [u["url"] for u in urls]
        assert any("arxiv.org/pdf/2301.12345" in u for u in pdf_urls)

    def test_discover_oa_urls_pdf_url(self):
        manager = PDFDownloadManager()
        paper = PaperMetadata(
            pdf_url="https://example.com/paper.pdf",
            source="semantic_scholar",
        )
        urls = manager.discover_oa_urls(paper)
        assert any(u["url"] == "https://example.com/paper.pdf" for u in urls)