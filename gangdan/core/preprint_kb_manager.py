"""Preprint knowledge base manager with search and matching.

Manages preprint metadata storage, indexing, and retrieval with multiple
matching strategies:
1. Keyword matching - fast text-based search
2. Semantic matching - embedding-based similarity (if Ollama available)
3. Metadata filtering - by platform, date, category, author

Integrates with the existing ChromaDB infrastructure for embedding-based
search while maintaining a local JSON index for fast keyword lookups.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from gangdan.core.config import DATA_DIR

logger = logging.getLogger(__name__)

PREPRINT_KB_FILE = DATA_DIR / "preprint_kb.json"


@dataclass
class PreprintKBEntry:
    """A single entry in the preprint knowledge base.

    Attributes
    ----------
    preprint_id : str
        Unique preprint identifier.
    title : str
        Paper title.
    authors : List[str]
        Author names.
    abstract : str
        Paper abstract.
    published_date : str
        Publication date.
    source_platform : str
        Platform: 'arxiv', 'biorxiv', 'medrxiv'.
    category : str
        Subject category.
    markdown_path : str
        Path to converted Markdown file.
    source_format : str
        Source format: 'html', 'tex', 'pdf'.
    html_url : str
        HTML version URL.
    tex_source_url : str
        TeX source URL.
    pdf_url : str
        PDF URL.
    url : str
        Abstract page URL.
    indexed_at : str
        ISO timestamp when indexed.
    embedding_id : str
        ChromaDB document ID if embedded.
    tags : List[str]
        User-assigned tags.
    """

    preprint_id: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    published_date: str = ""
    source_platform: str = ""
    category: str = ""
    markdown_path: str = ""
    source_format: str = ""
    html_url: str = ""
    tex_source_url: str = ""
    pdf_url: str = ""
    url: str = ""
    indexed_at: str = ""
    embedding_id: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "preprint_id": self.preprint_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "published_date": self.published_date,
            "source_platform": self.source_platform,
            "category": self.category,
            "markdown_path": self.markdown_path,
            "source_format": self.source_format,
            "html_url": self.html_url,
            "tex_source_url": self.tex_source_url,
            "pdf_url": self.pdf_url,
            "url": self.url,
            "indexed_at": self.indexed_at,
            "embedding_id": self.embedding_id,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PreprintKBEntry":
        """Create from dictionary."""
        return cls(
            preprint_id=data.get("preprint_id", ""),
            title=data.get("title", ""),
            authors=data.get("authors", []),
            abstract=data.get("abstract", ""),
            published_date=data.get("published_date", ""),
            source_platform=data.get("source_platform", ""),
            category=data.get("category", ""),
            markdown_path=data.get("markdown_path", ""),
            source_format=data.get("source_format", ""),
            html_url=data.get("html_url", ""),
            tex_source_url=data.get("tex_source_url", ""),
            pdf_url=data.get("pdf_url", ""),
            url=data.get("url", ""),
            indexed_at=data.get("indexed_at", ""),
            embedding_id=data.get("embedding_id", ""),
            tags=data.get("tags", []),
        )

    @property
    def authors_str(self) -> str:
        """Format authors as string."""
        if not self.authors:
            return "Unknown"
        if len(self.authors) == 1:
            return self.authors[0]
        return ", ".join(self.authors[:3]) + (" et al." if len(self.authors) > 3 else "")

    @property
    def short_title(self) -> str:
        """Truncated title."""
        if len(self.title) <= 80:
            return self.title
        return self.title[:77] + "..."


@dataclass
class KBSearchResult:
    """A search result from the preprint knowledge base.

    Attributes
    ----------
    entry : PreprintKBEntry
        The matched preprint entry.
    score : float
        Relevance score (0-1).
    match_type : str
        How it matched: 'keyword', 'semantic', 'metadata'.
    matched_fields : List[str]
        Which fields matched the query.
    """

    entry: PreprintKBEntry
    score: float = 0.0
    match_type: str = "keyword"
    matched_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entry": self.entry.to_dict(),
            "score": self.score,
            "match_type": self.match_type,
            "matched_fields": self.matched_fields,
        }


class PreprintKBManager:
    """Manager for the preprint knowledge base.

    Provides storage, indexing, and search capabilities for preprints.
    Supports keyword matching, semantic matching (via embeddings),
    and metadata filtering.

    Parameters
    ----------
    kb_file : Path
        Path to the JSON knowledge base file.
    """

    def __init__(self, kb_file: Optional[Path] = None) -> None:
        self.kb_file = kb_file or PREPRINT_KB_FILE
        self.entries: Dict[str, PreprintKBEntry] = {}
        self._chroma_collection = None
        self._load()

    def add_entry(
        self,
        preprint_id: str,
        title: str,
        abstract: str,
        authors: Optional[List[str]] = None,
        published_date: str = "",
        source_platform: str = "",
        category: str = "",
        markdown_path: str = "",
        source_format: str = "",
        html_url: str = "",
        tex_source_url: str = "",
        pdf_url: str = "",
        url: str = "",
        tags: Optional[List[str]] = None,
    ) -> PreprintKBEntry:
        """Add a preprint to the knowledge base.

        Parameters
        ----------
        preprint_id : str
            Unique preprint identifier.
        title : str
            Paper title.
        abstract : str
            Paper abstract.
        authors : List[str] or None
            Author names.
        published_date : str
            Publication date.
        source_platform : str
            Platform name.
        category : str
            Subject category.
        markdown_path : str
            Path to converted Markdown.
        source_format : str
            Source format.
        html_url : str
            HTML URL.
        tex_source_url : str
            TeX source URL.
        pdf_url : str
            PDF URL.
        url : str
            Abstract page URL.
        tags : List[str] or None
            User tags.

        Returns
        -------
        PreprintKBEntry
            The created entry.
        """
        entry = PreprintKBEntry(
            preprint_id=preprint_id,
            title=title,
            authors=authors or [],
            abstract=abstract,
            published_date=published_date,
            source_platform=source_platform,
            category=category,
            markdown_path=markdown_path,
            source_format=source_format,
            html_url=html_url,
            tex_source_url=tex_source_url,
            pdf_url=pdf_url,
            url=url,
            indexed_at=datetime.now().isoformat(),
            tags=tags or [],
        )
        self.entries[preprint_id] = entry
        self._save()
        return entry

    def add_from_metadata(self, paper, markdown_path: str = "", source_format: str = "") -> PreprintKBEntry:
        """Add a preprint from PreprintMetadata object.

        Parameters
        ----------
        paper : PreprintMetadata
            Preprint metadata from fetcher.
        markdown_path : str
            Path to converted Markdown.
        source_format : str
            Source format used.

        Returns
        -------
        PreprintKBEntry
            The created entry.
        """
        return self.add_entry(
            preprint_id=paper.preprint_id,
            title=paper.title,
            abstract=paper.abstract,
            authors=paper.authors,
            published_date=paper.published_date,
            source_platform=paper.source_platform,
            category=paper.category,
            markdown_path=markdown_path,
            source_format=source_format,
            html_url=paper.html_url,
            tex_source_url=paper.tex_source_url,
            pdf_url=paper.pdf_url,
            url=paper.url,
        )

    def remove_entry(self, preprint_id: str) -> bool:
        """Remove a preprint from the knowledge base.

        Parameters
        ----------
        preprint_id : str
            Preprint identifier to remove.

        Returns
        -------
        bool
            True if removed, False if not found.
        """
        if preprint_id in self.entries:
            del self.entries[preprint_id]
            self._save()
            return True
        return False

    def get_entry(self, preprint_id: str) -> Optional[PreprintKBEntry]:
        """Get a preprint entry by ID.

        Parameters
        ----------
        preprint_id : str
            Preprint identifier.

        Returns
        -------
        PreprintKBEntry or None
            The entry, or None if not found.
        """
        return self.entries.get(preprint_id)

    def search(
        self,
        query: str,
        mode: str = "keyword",
        platform: Optional[str] = None,
        category: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 20,
    ) -> List[KBSearchResult]:
        """Search the preprint knowledge base.

        Parameters
        ----------
        query : str
            Search query string.
        mode : str
            Search mode: 'keyword', 'semantic', 'combined'.
        platform : str or None
            Filter by platform.
        category : str or None
            Filter by category.
        date_from : str or None
            Filter by date from (ISO format).
        date_to : str or None
            Filter by date to (ISO format).
        limit : int
            Maximum results to return.

        Returns
        -------
        List[KBSearchResult]
            Ranked search results.
        """
        results = []

        if mode in ("keyword", "combined"):
            keyword_results = self._keyword_search(query)
            results.extend(keyword_results)

        if mode in ("semantic", "combined"):
            semantic_results = self._semantic_search(query)
            results.extend(semantic_results)

        results = self._deduplicate_results(results)

        results = self._filter_results(
            results,
            platform=platform,
            category=category,
            date_from=date_from,
            date_to=date_to,
        )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def _keyword_search(self, query: str) -> List[KBSearchResult]:
        """Perform keyword-based search.

        Parameters
        ----------
        query : str
            Search query.

        Returns
        -------
        List[KBSearchResult]
            Keyword-matched results.
        """
        results = []
        query_lower = query.lower()
        query_terms = set(re.findall(r"\b\w+\b", query_lower))

        for entry in self.entries.values():
            score = 0.0
            matched_fields = []

            title_lower = entry.title.lower()
            abstract_lower = entry.abstract.lower()
            authors_lower = " ".join(entry.authors).lower()
            category_lower = entry.category.lower()

            title_matches = sum(1 for term in query_terms if term in title_lower)
            if title_matches > 0:
                score += title_matches * 3.0
                matched_fields.append("title")

            abstract_matches = sum(1 for term in query_terms if term in abstract_lower)
            if abstract_matches > 0:
                score += abstract_matches * 1.0
                matched_fields.append("abstract")

            author_matches = sum(1 for term in query_terms if term in authors_lower)
            if author_matches > 0:
                score += author_matches * 2.0
                matched_fields.append("authors")

            if query_lower in category_lower:
                score += 1.5
                matched_fields.append("category")

            if score > 0:
                normalized_score = min(score / (len(query_terms) * 3.0), 1.0)
                results.append(
                    KBSearchResult(
                        entry=entry,
                        score=normalized_score,
                        match_type="keyword",
                        matched_fields=matched_fields,
                    )
                )

        return results

    def _semantic_search(self, query: str) -> List[KBSearchResult]:
        """Perform semantic search using embeddings.

        Falls back to keyword search if embeddings are not available.

        Parameters
        ----------
        query : str
            Search query.

        Returns
        -------
        List[KBSearchResult]
            Semantically-matched results.
        """
        if self._chroma_collection is None:
            return []

        try:
            query_embedding = self._get_embedding(query)
            if query_embedding is None:
                return []

            query_results = self._chroma_collection.query(
                query_embeddings=[query_embedding],
                n_results=20,
                include=["metadatas", "documents", "distances"],
            )

            results = []
            if query_results and query_results.get("ids"):
                for i, doc_id in enumerate(query_results["ids"][0]):
                    entry = self.entries.get(doc_id)
                    if entry is None:
                        continue

                    distance = query_results["distances"][0][i] if query_results.get("distances") else 1.0
                    score = max(0, 1.0 - distance)

                    results.append(
                        KBSearchResult(
                            entry=entry,
                            score=score,
                            match_type="semantic",
                            matched_fields=["embedding"],
                        )
                    )

            return results
        except Exception as e:
            logger.error("[PreprintKBManager] Semantic search failed: %s", e)
            return []

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for text using Ollama.

        Parameters
        ----------
        text : str
            Text to embed.

        Returns
        -------
        List[float] or None
            Embedding vector, or None if unavailable.
        """
        try:
            from gangdan.core.ollama_client import get_embedding

            result = get_embedding(text)
            if result and result.get("embedding"):
                return result["embedding"]
        except Exception as e:
            logger.debug("[PreprintKBManager] Embedding failed: %s", e)

        return None

    def _deduplicate_results(self, results: List[KBSearchResult]) -> List[KBSearchResult]:
        """Deduplicate results by preprint_id, keeping highest score.

        Parameters
        ----------
        results : List[KBSearchResult]
            Raw search results.

        Returns
        -------
        List[KBSearchResult]
            Deduplicated results.
        """
        best: Dict[str, KBSearchResult] = {}
        for result in results:
            pid = result.entry.preprint_id
            if pid not in best or result.score > best[pid].score:
                best[pid] = result
        return list(best.values())

    def _filter_results(
        self,
        results: List[KBSearchResult],
        platform: Optional[str] = None,
        category: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[KBSearchResult]:
        """Filter results by metadata.

        Parameters
        ----------
        results : List[KBSearchResult]
            Search results to filter.
        platform : str or None
            Filter by platform.
        category : str or None
            Filter by category.
        date_from : str or None
            Filter by date from.
        date_to : str or None
            Filter by date to.

        Returns
        -------
        List[KBSearchResult]
            Filtered results.
        """
        filtered = results

        if platform:
            filtered = [r for r in filtered if r.entry.source_platform == platform]

        if category:
            cat_lower = category.lower()
            filtered = [r for r in filtered if cat_lower in r.entry.category.lower()]

        if date_from:
            filtered = [r for r in filtered if r.entry.published_date >= date_from]

        if date_to:
            filtered = [r for r in filtered if r.entry.published_date <= date_to]

        return filtered

    def get_recent(self, days: int = 30, limit: int = 50) -> List[PreprintKBEntry]:
        """Get recently indexed preprints.

        Parameters
        ----------
        days : int
            Number of days to look back.
        limit : int
            Maximum results.

        Returns
        -------
        List[PreprintKBEntry]
            Recent preprints sorted by index date.
        """
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        recent = []
        for entry in self.entries.values():
            if entry.indexed_at >= cutoff:
                recent.append(entry)

        recent.sort(key=lambda e: e.indexed_at, reverse=True)
        return recent[:limit]

    def get_by_platform(self, platform: str, limit: int = 50) -> List[PreprintKBEntry]:
        """Get preprints by platform.

        Parameters
        ----------
        platform : str
            Platform name.
        limit : int
            Maximum results.

        Returns
        -------
        List[PreprintKBEntry]
            Preprints from the specified platform.
        """
        entries = [e for e in self.entries.values() if e.source_platform == platform]
        entries.sort(key=lambda e: e.published_date, reverse=True)
        return entries[:limit]

    def get_statistics(self) -> Dict[str, Any]:
        """Get knowledge base statistics.

        Returns
        -------
        Dict
            Statistics about the knowledge base.
        """
        platforms = {}
        formats = {}
        total = len(self.entries)

        for entry in self.entries.values():
            platforms[entry.source_platform] = platforms.get(entry.source_platform, 0) + 1
            formats[entry.source_format] = formats.get(entry.source_format, 0) + 1

        return {
            "total_entries": total,
            "by_platform": platforms,
            "by_format": formats,
            "has_markdown": sum(1 for e in self.entries.values() if e.markdown_path),
            "has_html": sum(1 for e in self.entries.values() if e.html_url),
            "has_tex": sum(1 for e in self.entries.values() if e.tex_source_url),
        }

    def index_markdown_content(self, preprint_id: str, markdown_path: str) -> bool:
        """Index Markdown content for semantic search.

        Parameters
        ----------
        preprint_id : str
            Preprint identifier.
        markdown_path : str
            Path to Markdown file.

        Returns
        -------
        bool
            True if indexed successfully.
        """
        try:
            path = Path(markdown_path)
            if not path.exists():
                return False

            content = path.read_text(encoding="utf-8")
            chunks = self._chunk_text(content, max_chunk_size=2000)

            if self._chroma_collection is None:
                self._init_chroma_collection()

            if self._chroma_collection is None:
                return False

            ids = [f"{preprint_id}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [
                {"preprint_id": preprint_id, "chunk_index": i, "source": "preprint"}
                for i in range(len(chunks))
            ]

            embeddings = []
            for chunk in chunks:
                embedding = self._get_embedding(chunk)
                if embedding:
                    embeddings.append(embedding)

            if embeddings:
                self._chroma_collection.add(
                    ids=ids[:len(embeddings)],
                    embeddings=embeddings,
                    metadatas=metadatas[:len(embeddings)],
                    documents=chunks[:len(embeddings)],
                )

            if preprint_id in self.entries:
                self.entries[preprint_id].embedding_id = ids[0] if ids else ""
                self._save()

            return True
        except Exception as e:
            logger.error("[PreprintKBManager] Index failed: %s", e)
            return False

    def _chunk_text(self, text: str, max_chunk_size: int = 2000) -> List[str]:
        """Split text into chunks for embedding.

        Parameters
        ----------
        text : str
            Text to chunk.
        max_chunk_size : int
            Maximum chunk size in characters.

        Returns
        -------
        List[str]
            Text chunks.
        """
        if len(text) <= max_chunk_size:
            return [text]

        chunks = []
        current = ""

        for line in text.split("\n"):
            if len(current) + len(line) > max_chunk_size and current:
                chunks.append(current.strip())
                current = line
            else:
                current += "\n" + line if current else line

        if current.strip():
            chunks.append(current.strip())

        if len(chunks) == 1 and len(chunks[0]) > max_chunk_size:
            chunked = []
            text = chunks[0]
            for i in range(0, len(text), max_chunk_size):
                chunked.append(text[i:i + max_chunk_size])
            return chunked

        return chunks if chunks else [text]

    def _init_chroma_collection(self) -> None:
        """Initialize ChromaDB collection for preprints."""
        try:
            from gangdan.core.chroma_manager import ChromaManager

            chroma_dir = str(DATA_DIR / "preprint_chroma")
            manager = ChromaManager(persist_dir=chroma_dir)

            if manager.client:
                self._chroma_collection = manager.client.get_or_create_collection(
                    name="preprints",
                    metadata={"hnsw:space": "cosine"},
                )
        except Exception as e:
            logger.error("[PreprintKBManager] ChromaDB init failed: %s", e)
            self._chroma_collection = None

    def _load(self) -> None:
        """Load knowledge base from disk."""
        if not self.kb_file.exists():
            return

        try:
            data = json.loads(self.kb_file.read_text(encoding="utf-8"))
            entries_data = data.get("entries", {})
            self.entries = {
                pid: PreprintKBEntry.from_dict(entry_data)
                for pid, entry_data in entries_data.items()
            }
        except Exception as e:
            logger.error("[PreprintKBManager] Failed to load KB: %s", e)

    def _save(self) -> None:
        """Save knowledge base to disk."""
        try:
            self.kb_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "entries": {
                    pid: entry.to_dict()
                    for pid, entry in self.entries.items()
                },
                "updated_at": datetime.now().isoformat(),
            }
            self.kb_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.error("[PreprintKBManager] Failed to save KB: %s", e)

    def clear(self) -> None:
        """Clear all entries from the knowledge base."""
        self.entries.clear()
        self._save()
