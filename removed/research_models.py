"""Data models for academic paper search and management.

This module defines the core data structures used throughout the research
search pipeline: paper metadata, search results, download status, etc.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class PaperMetadata:
    """Standardized paper metadata from any search source.

    Attributes
    ----------
    title : str
        Paper title.
    authors : List[str]
        Author names.
    year : int
        Publication year (0 if unknown).
    abstract : str
        Paper abstract.
    doi : str
        Digital Object Identifier.
    arxiv_id : str
        arXiv identifier (e.g., '2301.12345').
    url : str
        Paper URL (abstract page or landing page).
    pdf_url : str
        Direct PDF download URL.
    source : str
        Source identifier (arxiv, semantic_scholar, crossref, pubmed, github).
    citations : int
        Citation count.
    journal : str
        Journal or venue name.
    venue : str
        Conference or journal venue.
    raw_data : Dict
        Original response data from the source API.
    """

    title: str = ""
    authors: List[str] = field(default_factory=list)
    year: int = 0
    abstract: str = ""
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""
    pdf_url: str = ""
    source: str = ""
    citations: int = 0
    journal: str = ""
    venue: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def authors_str(self) -> str:
        """Format authors as a comma-separated string."""
        if not self.authors:
            return "Unknown"
        if len(self.authors) == 1:
            return self.authors[0]
        return ", ".join(self.authors[:3]) + (" et al." if len(self.authors) > 3 else "")

    @property
    def short_title(self) -> str:
        """Truncated title for display (max 80 chars)."""
        if len(self.title) <= 80:
            return self.title
        return self.title[:77] + "..."

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "abstract": self.abstract,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "url": self.url,
            "pdf_url": self.pdf_url,
            "source": self.source,
            "citations": self.citations,
            "journal": self.journal,
            "venue": self.venue,
        }


@dataclass
class SearchResult:
    """A single paper search result with ranking info.

    Attributes
    ----------
    paper : PaperMetadata
        Paper metadata.
    score : float
        Relevance score (higher = more relevant).
    matched_query : str
        Which expanded query matched this result.
    """

    paper: PaperMetadata
    score: float = 0.0
    matched_query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "paper": self.paper.to_dict(),
            "score": self.score,
            "matched_query": self.matched_query,
        }


@dataclass
class DownloadResult:
    """Result of a PDF download operation.

    Attributes
    ----------
    success : bool
        Whether the download succeeded.
    pdf_path : str
        Local path to the downloaded PDF.
    source : str
        Which OA source provided the PDF.
    error : str
        Error message if download failed.
    file_size : int
        File size in bytes.
    sha256 : str
        SHA-256 hash of the PDF file.
    """

    success: bool = False
    pdf_path: str = ""
    source: str = ""
    error: str = ""
    file_size: int = 0
    sha256: str = ""


@dataclass
class ConversionResult:
    """Result of a PDF-to-Markdown conversion.

    Attributes
    ----------
    success : bool
        Whether the conversion succeeded.
    markdown_path : str
        Path to the output Markdown file.
    images_dir : str
        Directory containing extracted images.
    engine : str
        Which engine performed the conversion.
    error : str
        Error message if conversion failed.
    page_count : int
        Number of pages in the PDF.
    """

    success: bool = False
    markdown_path: str = ""
    images_dir: str = ""
    engine: str = ""
    error: str = ""
    page_count: int = 0


@dataclass
class PaperRecord:
    """Complete record of a downloaded paper with local file info.

    This is stored in the papers/manifest.json file.

    Attributes
    ----------
    metadata : PaperMetadata
        Paper metadata from search.
    local_pdf : str
        Local path to the PDF file.
    citation_filename : str
        Citation-style filename (e.g., 'Author et al. (2023) - Title.pdf').
    markdown_path : str
        Path to converted Markdown (empty if not converted).
    download_date : str
        ISO timestamp of download.
    kb_collection : str
        ChromaDB collection name if indexed.
    tags : List[str]
        User-assigned tags.
    notes : str
        User notes about the paper.
    """

    metadata: PaperMetadata
    local_pdf: str = ""
    citation_filename: str = ""
    markdown_path: str = ""
    download_date: str = ""
    kb_collection: str = ""
    tags: List[str] = field(default_factory=list)
    notes: str = ""

    @property
    def paper_id(self) -> str:
        """Generate a unique ID for this paper record."""
        key = self.metadata.doi or self.metadata.arxiv_id or self.metadata.title
        return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "paper_id": self.paper_id,
            "metadata": self.metadata.to_dict(),
            "local_pdf": self.local_pdf,
            "citation_filename": self.citation_filename,
            "markdown_path": self.markdown_path,
            "download_date": self.download_date,
            "kb_collection": self.kb_collection,
            "tags": self.tags,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaperRecord":
        """Create a PaperRecord from a dictionary."""
        metadata = PaperMetadata(**data.get("metadata", {}))
        return cls(
            metadata=metadata,
            local_pdf=data.get("local_pdf", ""),
            citation_filename=data.get("citation_filename", ""),
            markdown_path=data.get("markdown_path", ""),
            download_date=data.get("download_date", ""),
            kb_collection=data.get("kb_collection", ""),
            tags=data.get("tags", []),
            notes=data.get("notes", ""),
        )
