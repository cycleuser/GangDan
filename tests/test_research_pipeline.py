"""Tests for research pipeline (end-to-end orchestration)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gangdan.core.research_models import PaperMetadata, PaperRecord
from gangdan.core.research_pipeline import ResearchPipeline


class TestResearchPipeline:
    """Test ResearchPipeline orchestration."""

    def test_parse_sources(self):
        sources = ResearchPipeline._parse_sources("arxiv,semantic_scholar,crossref")
        assert sources == ["arxiv", "semantic_scholar", "crossref"]

    def test_parse_sources_empty(self):
        sources = ResearchPipeline._parse_sources("")
        assert sources == ["arxiv", "semantic_scholar", "crossref"]

    def test_parse_sources_with_spaces(self):
        sources = ResearchPipeline._parse_sources("arxiv, semantic_scholar , crossref")
        assert sources == ["arxiv", "semantic_scholar", "crossref"]

    def test_chunk_text(self):
        text = "A" * 100
        chunks = ResearchPipeline._chunk_text(text, chunk_size=30, overlap=10)
        assert len(chunks) > 1
        assert all(len(c) <= 30 for c in chunks)

    def test_chunk_text_overlap(self):
        text = "ABCDEFGHIJ"
        chunks = ResearchPipeline._chunk_text(text, chunk_size=5, overlap=2)
        assert len(chunks) > 1
        assert chunks[0] == "ABCDE"

    @patch("gangdan.core.research_pipeline.ResearchSearcher")
    @patch("gangdan.core.research_pipeline.PDFDownloadManager")
    @patch("gangdan.core.research_pipeline.PDFRenamer")
    @patch("gangdan.core.research_pipeline.PDFConverter")
    def test_download_and_process_success(self, mock_converter_cls, mock_renamer_cls, mock_downloader_cls, mock_searcher_cls):
        from gangdan.core.research_models import ConversionResult, DownloadResult

        mock_downloader = MagicMock()
        mock_downloader.download_pdf.return_value = DownloadResult(
            success=True,
            pdf_path="/tmp/test.pdf",
            source="arxiv",
            file_size=1000,
            sha256="abc123",
        )
        mock_downloader_cls.return_value = mock_downloader

        mock_renamer = MagicMock()
        mock_renamer.rename.return_value = Path("/tmp/Author et al. (2023) - Test.pdf")
        mock_renamer_cls.return_value = mock_renamer

        mock_converter = MagicMock()
        mock_converter.convert.return_value = ConversionResult(
            success=True,
            markdown_path="/tmp/test.md",
            engine="pymupdf4llm",
            page_count=10,
        )
        mock_converter_cls.return_value = mock_converter

        paper = PaperMetadata(
            title="Test Paper",
            authors=["Author One"],
            year=2023,
            source="arxiv",
            arxiv_id="2301.12345",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = ResearchPipeline()
            pipeline.papers_dir = Path(tmpdir)
            pipeline.downloader = mock_downloader
            pipeline.renamer = mock_renamer
            pipeline.converter = mock_converter

            record = pipeline.download_and_process(paper, rename=True, convert=True)

            assert record.local_pdf != ""
            assert record.citation_filename != ""
            assert record.markdown_path != ""

    @patch("gangdan.core.research_pipeline.ResearchSearcher")
    @patch("gangdan.core.research_pipeline.PDFDownloadManager")
    @patch("gangdan.core.research_pipeline.PDFRenamer")
    @patch("gangdan.core.research_pipeline.PDFConverter")
    def test_download_and_process_download_failure(self, mock_converter_cls, mock_renamer_cls, mock_downloader_cls, mock_searcher_cls):
        from gangdan.core.research_models import DownloadResult

        mock_downloader = MagicMock()
        mock_downloader.download_pdf.return_value = DownloadResult(
            success=False,
            error="No OA PDF sources found",
        )
        mock_downloader_cls.return_value = mock_downloader

        paper = PaperMetadata(title="Test Paper", authors=["Author"], year=2023)

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = ResearchPipeline()
            pipeline.papers_dir = Path(tmpdir)
            pipeline.downloader = mock_downloader

            record = pipeline.download_and_process(paper)

            assert record.local_pdf == ""
            assert "No OA PDF" in (record.notes or "")

    def test_save_and_load_manifest(self):
        paper = PaperMetadata(
            title="Test Paper",
            authors=["Author One", "Author Two"],
            year=2023,
            doi="10.1234/test",
            source="crossref",
        )
        record = PaperRecord(
            metadata=paper,
            local_pdf="/tmp/test.pdf",
            citation_filename="Author One et al. (2023) - Test Paper.pdf",
            markdown_path="/tmp/test.md",
            download_date="2026-05-01T10:00:00",
            tags=["test"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = ResearchPipeline()
            pipeline.papers_dir = Path(tmpdir)

            pipeline.save_manifest([record])
            loaded = pipeline.load_manifest()

            assert len(loaded) == 1
            assert loaded[0].metadata.title == "Test Paper"
            assert loaded[0].tags == ["test"]

    def test_delete_paper(self):
        paper = PaperMetadata(
            title="Test Paper",
            authors=["Author"],
            year=2023,
            doi="10.1234/test",
        )
        record = PaperRecord(
            metadata=paper,
            local_pdf="/tmp/test.pdf",
            download_date="2026-05-01T10:00:00",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = ResearchPipeline()
            pipeline.papers_dir = Path(tmpdir)

            pipeline.save_manifest([record])
            paper_id = record.paper_id

            loaded_before = pipeline.load_manifest()
            assert len(loaded_before) == 1

            result = pipeline.delete_paper(paper_id)
            assert result is True

            loaded_after = pipeline.load_manifest()
            assert len(loaded_after) == 0

    def test_delete_paper_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = ResearchPipeline()
            pipeline.papers_dir = Path(tmpdir)

            result = pipeline.delete_paper("nonexistent")
            assert result is False
