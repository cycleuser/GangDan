"""Full-text search engine using SQLite FTS5 with fallback to in-memory index.

Provides keyword-based document retrieval as a complement to vector search.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FullTextSearch:
    """Full-text search engine backed by SQLite FTS5.

    Each collection gets its own virtual FTS5 table. Documents are indexed
    alongside their chunk metadata, enabling keyword-driven retrieval with
    BM25 scoring.

    Attributes
    ----------
    db_path : str
        Path to the SQLite database file.
    _conn : sqlite3.Connection
        Thread-local database connection.
    _lock : threading.Lock
        Lock for write operations.
    """

    def __init__(self, db_path: str) -> None:
        """Initialize FTS engine.

        Parameters
        ----------
        db_path : str
            Path to the SQLite database file.
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = threading.Lock()

    @property
    def conn(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _table_name(self, collection: str) -> str:
        """Map a collection name to a safe FTS table name."""
        safe = collection.replace("-", "_").replace(".", "_")
        return f"fts_{safe}"

    def index_documents(
        self,
        collection: str,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
    ) -> None:
        """Index documents for full-text search.

        Parameters
        ----------
        collection : str
            Collection name.
        documents : List[str]
            Document texts to index.
        metadatas : List[Dict[str, Any]]
            Metadata for each document.
        ids : List[str]
            Unique IDs for each document.
        """
        table = self._table_name(collection)
        with self._lock:
            try:
                self.conn.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} "
                    "USING fts5(id, document, source, file, tokenize='unicode61')"
                )
                rows = []
                for i, (doc, meta, doc_id) in enumerate(zip(documents, metadatas, ids)):
                    source = meta.get("source", collection) if meta else collection
                    file_name = meta.get("file", "unknown") if meta else "unknown"
                    rows.append((doc_id, doc, source, file_name))
                self.conn.executemany(
                    f"INSERT INTO {table} (id, document, source, file) VALUES (?, ?, ?, ?)",
                    rows,
                )
                self.conn.commit()
                logger.info(
                    "FTS: indexed %d documents in collection '%s'", len(rows), collection
                )
            except sqlite3.Error as e:
                logger.error("FTS index error in '%s': %s", collection, e)

    def remove_documents(self, collection: str, ids: List[str]) -> None:
        """Remove documents from the FTS index.

        Parameters
        ----------
        collection : str
            Collection name.
        ids : List[str]
            Document IDs to remove.
        """
        table = self._table_name(collection)
        with self._lock:
            try:
                for doc_id in ids:
                    self.conn.execute(f"DELETE FROM {table} WHERE id = ?", (doc_id,))
                self.conn.commit()
            except sqlite3.Error:
                pass  # Table may not exist

    def delete_collection(self, collection: str) -> None:
        """Drop the FTS table for a collection.

        Parameters
        ----------
        collection : str
            Collection name to drop.
        """
        table = self._table_name(collection)
        with self._lock:
            try:
                self.conn.execute(f"DROP TABLE IF EXISTS {table}")
                self.conn.commit()
                logger.info("FTS: dropped table for '%s'", collection)
            except sqlite3.Error as e:
                logger.warning("FTS drop error for '%s': %s", collection, e)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        collection: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Full-text search a collection.

        Uses FTS5 BM25 ranking. Falls back to simple LIKE search if
        the FTS table does not exist.

        Parameters
        ----------
        query : str
            Search query string.
        collection : str
            Collection to search.
        top_k : int
            Maximum number of results.

        Returns
        -------
        List[Dict[str, Any]]
            Results with keys: id, document, metadata, score.
        """
        table = self._table_name(collection)
        results: List[Dict[str, Any]] = []

        # Check if FTS table exists
        try:
            cursor = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if cursor.fetchone() is None:
                # Fallback: token-based search over an in-memory structure
                return self._fallback_search(query, collection, top_k)
        except sqlite3.Error:
            return self._fallback_search(query, collection, top_k)

        # Sanitize query for FTS5: escape special chars, prepend * for prefix match
        safe_query = self._sanitize_fts_query(query)
        if not safe_query:
            return results

        try:
            # FTS5 search with snippet
            rows = self.conn.execute(
                f"SELECT id, document, source, file, rank "
                f"FROM {table} WHERE {table} MATCH ? "
                f"ORDER BY rank LIMIT ?",
                (safe_query, top_k),
            ).fetchall()

            for row in rows:
                doc_id, doc_text, source, file_name, rank = row
                results.append({
                    "id": doc_id,
                    "document": doc_text,
                    "metadata": {"source": source, "file": file_name},
                    "score": float(rank) if rank else 0.0,
                    "source": "fts",
                })
        except sqlite3.Error as e:
            logger.warning("FTS search error: %s, falling back", e)
            return self._fallback_search(query, collection, top_k)

        return results

    def _sanitize_fts_query(self, query: str) -> str:
        """Sanitize a user query for FTS5 MATCH.

        FTS5 has special meaning for: * " ( ) + - and column specifiers.
        We strip most of these and add prefix wildcards for partial matching.
        """
        if not query or not query.strip():
            return ""

        # Remove special FTS5 characters
        sanitized = query.replace('"', "").replace("(", "").replace(")", "")
        sanitized = sanitized.replace("+", "").replace(":", " ")

        # Tokenize and add prefix matching
        tokens = sanitized.strip().split()
        if not tokens:
            return ""

        # Build FTS5 query: each token gets a trailing * for prefix match
        fts_tokens = []
        for token in tokens:
            if len(token) > 1:
                # Quote tokens with hyphens
                if "-" in token and not token.startswith("-"):
                    fts_tokens.append(f'"{token}"*')
                else:
                    fts_tokens.append(f"{token}*")
            else:
                fts_tokens.append(token)

        return " AND ".join(fts_tokens) if len(fts_tokens) > 1 else fts_tokens[0]

    def _fallback_search(
        self,
        query: str,
        collection: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Simple keyword match when FTS5 is unavailable.

        Uses SQLite LIKE with scored term frequency ranking.
        """
        table = self._table_name(collection)
        results: List[Dict[str, Any]] = []
        query_lower = query.lower()
        tokens = [t for t in query_lower.split() if len(t) > 1]

        if not tokens:
            return results

        try:
            # Build LIKE conditions scoped to this collection
            like_clauses = " OR ".join(
                [f"LOWER(document) LIKE '%' || ? || '%'"] * len(tokens)
            )
            params = tuple(tokens) + (top_k,)
            rows = self.conn.execute(
                f"SELECT id, document, source, file FROM {table} "
                f"WHERE {like_clauses} LIMIT ?",
                params,
            ).fetchall()
        except sqlite3.Error:
            # Table might not exist at all
            return results

        seen: Dict[str, Tuple[str, str, str, str]] = {}
        for row in rows:
            doc_id, doc_text, source, file_name = row
            if doc_id not in seen:
                seen[doc_id] = (doc_id, doc_text, source or collection, file_name or "unknown")

        # Score by token frequency
        scored: List[Tuple[float, str, str, str, str]] = []
        for doc_id, doc_text, source, file_name in seen.values():
            score = sum(doc_text.lower().count(t) for t in tokens)
            scored.append((float(score), doc_id, doc_text, source, file_name))

        scored.sort(key=lambda x: x[0], reverse=True)
        for score, doc_id, doc_text, source, file_name in scored[:top_k]:
            results.append({
                "id": doc_id,
                "document": doc_text,
                "metadata": {"source": source, "file": file_name},
                "score": score,
                "source": "fts_fallback",
            })

        return results

    def collection_has_index(self, collection: str) -> bool:
        """Check if a collection has an FTS index."""
        table = self._table_name(collection)
        try:
            cursor = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            return cursor.fetchone() is not None
        except sqlite3.Error:
            return False

    def close(self) -> None:
        """Close the database connection."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except sqlite3.Error:
                pass
            self._local.conn = None
