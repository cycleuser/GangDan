"""PDF renaming using Chou-style citation filename format.

Integrates the Chou library for extracting paper metadata from PDFs
and renaming them to citation-style filenames like:
  Author et al. (2023) - Attention Is All You Need.pdf

When Chou is not installed, falls back to a basic filename generator
using available metadata (title, authors, year from search results).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from gangdan.core.research_models import PaperMetadata

logger = logging.getLogger(__name__)


class PDFRenamer:
    """Rename PDFs to citation-style filenames.

    Uses Chou library when available for precise metadata extraction
    from PDF content. Falls back to search-result metadata otherwise.

    Parameters
    ----------
    author_format : str
        Author name format: first_surname, first_full, all_surnames,
        all_full, n_surnames, n_full.
    include_journal : bool
        Whether to include journal name in filename.
    abbreviate_title : bool
        Whether to truncate long titles.
    """

    def __init__(
        self,
        author_format: str = "first_surname",
        include_journal: bool = False,
        abbreviate_title: bool = False,
    ) -> None:
        self.author_format = author_format
        self.include_journal = include_journal
        self.abbreviate_title = abbreviate_title

    def rename(
        self,
        pdf_path: Path,
        metadata: Optional[PaperMetadata] = None,
        dry_run: bool = False,
    ) -> Path:
        """Rename a PDF file to citation-style filename.

        Parameters
        ----------
        pdf_path : Path
            Path to the PDF file.
        metadata : PaperMetadata or None
            Pre-existing metadata from search results.
        dry_run : bool
            If True, only return the new path without renaming.

        Returns
        -------
        Path
            New path (or would-be path in dry_run mode).
        """
        if metadata is None:
            metadata = self._extract_metadata_from_pdf(pdf_path)
            if metadata is None:
                logger.warning("[PDFRenamer] Could not extract metadata, keeping original name")
                return pdf_path

        new_filename = self._generate_filename(metadata)
        new_path = pdf_path.parent / new_filename

        if pdf_path == new_path:
            return pdf_path

        if dry_run:
            return new_path

        try:
            pdf_path.rename(new_path)
            logger.info("[PDFRenamer] %s -> %s", pdf_path.name, new_filename)
            return new_path
        except OSError as e:
            logger.error("[PDFRenamer] Rename failed: %s", e)
            return pdf_path

    def _extract_metadata_from_pdf(self, pdf_path: Path) -> Optional[PaperMetadata]:
        """Extract paper metadata from PDF using Chou if available.

        Parameters
        ----------
        pdf_path : Path
            Path to the PDF file.

        Returns
        -------
        PaperMetadata or None
            Extracted metadata, or None if extraction fails.
        """
        try:
            from chou.core.processor import PaperProcessor
            from chou.core.models import AuthorFormat

            format_map = {
                "first_surname": AuthorFormat.FIRST_SURNAME,
                "first_full": AuthorFormat.FIRST_FULL,
                "all_surnames": AuthorFormat.ALL_SURNAMES,
                "all_full": AuthorFormat.ALL_FULL,
                "n_surnames": AuthorFormat.N_SURNAMES,
                "n_full": AuthorFormat.N_FULL,
            }
            author_fmt = format_map.get(self.author_format, AuthorFormat.FIRST_SURNAME)

            processor = PaperProcessor(author_format=author_fmt)
            result = processor.process_single(str(pdf_path))

            if result and result.new_filename:
                return PaperMetadata(
                    title=result.title or "",
                    authors=[a.name for a in (result.authors or [])],
                    year=result.year or 0,
                )
        except ImportError:
            logger.debug("[PDFRenamer] Chou not installed, using search metadata")
        except Exception as e:
            logger.debug("[PDFRenamer] Chou extraction failed: %s", e)

        return None

    def _generate_filename(self, metadata: PaperMetadata) -> str:
        """Generate a citation-style filename from PaperMetadata.

        Parameters
        ----------
        metadata : PaperMetadata
            Paper metadata.

        Returns
        -------
        str
            Generated filename (safe for filesystem).
        """
        author_str = self._format_authors(metadata.authors)
        year_str = f"({metadata.year})" if metadata.year else ""
        title = metadata.title or "Untitled"

        if self.abbreviate_title and len(title) > 80:
            title = title[:77] + "..."

        title = self._sanitize_filename(title)

        parts = []
        if author_str:
            parts.append(author_str)
        if year_str:
            parts.append(year_str)
        if title:
            if parts:
                parts.append(f"- {title}")
            else:
                parts.append(title)

        filename = " ".join(parts) + ".pdf"
        filename = re.sub(r"\s+", " ", filename).strip()

        if len(filename) > 200:
            filename = filename[:197] + "...pdf"

        return filename

    def _format_authors(self, authors: list) -> str:
        """Format author names according to the selected format.

        Parameters
        ----------
        authors : list
            List of author name strings.

        Returns
        -------
        str
            Formatted author string.
        """
        if not authors:
            return ""

        if self.author_format in ("first_surname", "first_full"):
            name = authors[0]
            if self.author_format == "first_surname" and " " in name:
                name = name.split()[-1]
            if len(authors) > 1:
                return f"{name} et al."
            return name

        if self.author_format in ("all_surnames", "all_full"):
            formatted = []
            for a in authors[:5]:
                if self.author_format == "all_surnames" and " " in a:
                    formatted.append(a.split()[-1])
                else:
                    formatted.append(a)
            result = ", ".join(formatted)
            if len(authors) > 5:
                result += " et al."
            return result

        if self.author_format in ("n_surnames", "n_full"):
            formatted = []
            for a in authors[:3]:
                if self.author_format == "n_surnames" and " " in a:
                    formatted.append(a.split()[-1])
                else:
                    formatted.append(a)
            result = ", ".join(formatted[:2])
            if len(authors) > 2:
                result += " et al."
            return result

        return authors[0] if authors else ""

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Remove characters that are unsafe for filenames.

        Parameters
        ----------
        name : str
            Raw name string.

        Returns
        -------
        str
            Sanitized filename-safe string.
        """
        name = re.sub(r'[<>:"/\\|?*]', '', name)
        name = re.sub(r'\s+', ' ', name)
        return name.strip()