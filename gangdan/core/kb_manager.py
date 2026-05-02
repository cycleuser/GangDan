"""Unified custom knowledge base manager.

Manages user-created knowledge bases with:
- Create/delete/list custom KBs
- Add/remove documents (Markdown, text, preprints, papers)
- Index content into ChromaDB for semantic search
- Search within and across KBs
- Export KB content

Each custom KB has:
- A unique internal name (sanitized with user_ prefix)
- A display name
- Metadata (description, tags, creation date)
- A ChromaDB collection for embeddings
- A JSON manifest tracking documents
- A directory for stored Markdown files
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from gangdan.core.config import CONFIG, DATA_DIR, sanitize_kb_name

logger = logging.getLogger(__name__)

CUSTOM_KBS_DIR = DATA_DIR / "custom_kbs"
CUSTOM_KBS_MANIFEST = DATA_DIR / "custom_kbs_manifest.json"


@dataclass
class KBDocEntry:
    """A single document entry in a custom knowledge base.

    Attributes
    ----------
    doc_id : str
        Unique document identifier.
    title : str
        Document title.
    source_type : str
        Type: 'preprint', 'paper', 'markdown', 'text', 'url'.
    source_id : str
        Original source ID (arXiv ID, DOI, etc.).
    source_platform : str
        Platform: 'arxiv', 'biorxiv', 'medrxiv', 'semantic_scholar', etc.
    markdown_path : str
        Path to local Markdown file.
    content_preview : str
        First 500 chars of content for preview.
    authors : List[str]
        Author names (for papers/preprints).
    published_date : str
        Publication date.
    url : str
        Original URL.
    tags : List[str]
        User-assigned tags.
    added_at : str
        ISO timestamp when added.
    """

    doc_id: str = ""
    title: str = ""
    source_type: str = ""
    source_id: str = ""
    source_platform: str = ""
    markdown_path: str = ""
    content_preview: str = ""
    authors: List[str] = field(default_factory=list)
    published_date: str = ""
    url: str = ""
    tags: List[str] = field(default_factory=list)
    added_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_platform": self.source_platform,
            "markdown_path": self.markdown_path,
            "content_preview": self.content_preview,
            "authors": self.authors,
            "published_date": self.published_date,
            "url": self.url,
            "tags": self.tags,
            "added_at": self.added_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KBDocEntry":
        """Create from dictionary."""
        return cls(
            doc_id=data.get("doc_id", ""),
            title=data.get("title", ""),
            source_type=data.get("source_type", ""),
            source_id=data.get("source_id", ""),
            source_platform=data.get("source_platform", ""),
            markdown_path=data.get("markdown_path", ""),
            content_preview=data.get("content_preview", ""),
            authors=data.get("authors", []),
            published_date=data.get("published_date", ""),
            url=data.get("url", ""),
            tags=data.get("tags", []),
            added_at=data.get("added_at", ""),
        )


@dataclass
class CustomKB:
    """A custom knowledge base.

    Attributes
    ----------
    kb_id : str
        Unique KB identifier (UUID).
    internal_name : str
        Sanitized internal name (user_xxx).
    display_name : str
        User-facing display name.
    description : str
        KB description.
    created_at : str
        ISO timestamp of creation.
    updated_at : str
        ISO timestamp of last update.
    tags : List[str]
        KB-level tags.
    chroma_collection : str
        ChromaDB collection name.
    doc_count : int
        Number of documents.
    """

    kb_id: str = ""
    internal_name: str = ""
    display_name: str = ""
    description: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: List[str] = field(default_factory=list)
    chroma_collection: str = ""
    doc_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "kb_id": self.kb_id,
            "internal_name": self.internal_name,
            "display_name": self.display_name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
            "chroma_collection": self.chroma_collection,
            "doc_count": self.doc_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CustomKB":
        """Create from dictionary."""
        return cls(
            kb_id=data.get("kb_id", ""),
            internal_name=data.get("internal_name", ""),
            display_name=data.get("display_name", ""),
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            tags=data.get("tags", []),
            chroma_collection=data.get("chroma_collection", ""),
            doc_count=data.get("doc_count", 0),
        )


class CustomKBManager:
    """Manager for custom knowledge bases.

    Provides CRUD operations for custom KBs, document management,
    and ChromaDB indexing.

    Parameters
    ----------
    kbs_dir : Path
        Base directory for custom KBs.
    """

    def __init__(self, kbs_dir: Optional[Path] = None) -> None:
        self.kbs_dir = kbs_dir or CUSTOM_KBS_DIR
        self.kbs_dir.mkdir(parents=True, exist_ok=True)
        self._manifest = self._load_manifest()
        self._chroma_client = None

    def create_kb(
        self,
        display_name: str,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> CustomKB:
        """Create a new custom knowledge base.

        Parameters
        ----------
        display_name : str
            User-facing name.
        description : str
            KB description.
        tags : List[str] or None
            KB-level tags.

        Returns
        -------
        CustomKB
            The created knowledge base.
        """
        internal_name = sanitize_kb_name(display_name)
        now = datetime.now().isoformat()

        kb = CustomKB(
            kb_id=str(uuid.uuid4())[:8],
            internal_name=internal_name,
            display_name=display_name,
            description=description,
            created_at=now,
            updated_at=now,
            tags=tags or [],
            chroma_collection=internal_name,
            doc_count=0,
        )

        kb_dir = self.kbs_dir / internal_name
        kb_dir.mkdir(parents=True, exist_ok=True)

        self._manifest[kb.internal_name] = kb.to_dict()
        self._save_manifest()

        doc_manifest = {
            "kb_id": kb.kb_id,
            "internal_name": kb.internal_name,
            "documents": {},
            "created_at": now,
            "updated_at": now,
        }
        doc_file = kb_dir / "documents.json"
        doc_file.write_text(
            json.dumps(doc_manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info("[CustomKB] Created KB '%s' (%s)", display_name, internal_name)
        return kb

    def delete_kb(self, internal_name: str, delete_files: bool = False) -> bool:
        """Delete a custom knowledge base.

        Parameters
        ----------
        internal_name : str
            Internal KB name.
        delete_files : bool
            If True, also delete local files.

        Returns
        -------
        bool
            True if deleted.
        """
        if internal_name not in self._manifest:
            return False

        del self._manifest[internal_name]
        self._save_manifest()

        if delete_files:
            kb_dir = self.kbs_dir / internal_name
            if kb_dir.exists():
                import shutil
                shutil.rmtree(kb_dir, ignore_errors=True)

        try:
            self._delete_chroma_collection(internal_name)
        except Exception as e:
            logger.warning("[CustomKB] Chroma collection delete failed: %s", e)

        logger.info("[CustomKB] Deleted KB '%s'", internal_name)
        return True

    def list_kbs(self) -> List[CustomKB]:
        """List all custom knowledge bases.

        Returns
        -------
        List[CustomKB]
            All custom KBs.
        """
        return [CustomKB.from_dict(v) for v in self._manifest.values()]

    def get_kb(self, internal_name: str) -> Optional[CustomKB]:
        """Get a KB by internal name.

        Parameters
        ----------
        internal_name : str
            Internal KB name.

        Returns
        -------
        CustomKB or None
            The KB if found.
        """
        data = self._manifest.get(internal_name)
        return CustomKB.from_dict(data) if data else None

    def update_kb(
        self,
        internal_name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[CustomKB]:
        """Update KB metadata.

        Parameters
        ----------
        internal_name : str
            Internal KB name.
        display_name : str or None
            New display name.
        description : str or None
            New description.
        tags : List[str] or None
            New tags.

        Returns
        -------
        CustomKB or None
            Updated KB, or None if not found.
        """
        if internal_name not in self._manifest:
            return None

        kb_data = self._manifest[internal_name]
        if display_name is not None:
            kb_data["display_name"] = display_name
        if description is not None:
            kb_data["description"] = description
        if tags is not None:
            kb_data["tags"] = tags
        kb_data["updated_at"] = datetime.now().isoformat()

        self._manifest[internal_name] = kb_data
        self._save_manifest()
        return CustomKB.from_dict(kb_data)

    def add_document(
        self,
        internal_name: str,
        doc: KBDocEntry,
        index_to_chroma: bool = True,
    ) -> bool:
        """Add a document to a KB.

        Parameters
        ----------
        internal_name : str
            Internal KB name.
        doc : KBDocEntry
            Document entry.
        index_to_chroma : bool
            Whether to index content into ChromaDB.

        Returns
        -------
        bool
            True if added successfully.
        """
        kb_dir = self.kbs_dir / internal_name
        doc_file = kb_dir / "documents.json"

        if not doc_file.exists():
            return False

        try:
            data = json.loads(doc_file.read_text(encoding="utf-8"))
            data["documents"][doc.doc_id] = doc.to_dict()
            data["updated_at"] = datetime.now().isoformat()
            doc_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            if internal_name in self._manifest:
                self._manifest[internal_name]["doc_count"] = len(data["documents"])
                self._manifest[internal_name]["updated_at"] = datetime.now().isoformat()
                self._save_manifest()

            if index_to_chroma and doc.markdown_path:
                self._index_document_to_chroma(internal_name, doc)

            logger.info("[CustomKB] Added doc '%s' to KB '%s'", doc.doc_id, internal_name)
            return True
        except Exception as e:
            logger.error("[CustomKB] Add document failed: %s", e)
            return False

    def remove_document(self, internal_name: str, doc_id: str) -> bool:
        """Remove a document from a KB.

        Parameters
        ----------
        internal_name : str
            Internal KB name.
        doc_id : str
            Document ID.

        Returns
        -------
        bool
            True if removed.
        """
        kb_dir = self.kbs_dir / internal_name
        doc_file = kb_dir / "documents.json"

        if not doc_file.exists():
            return False

        try:
            data = json.loads(doc_file.read_text(encoding="utf-8"))
            if doc_id in data["documents"]:
                del data["documents"][doc_id]
                data["updated_at"] = datetime.now().isoformat()
                doc_file.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

                if internal_name in self._manifest:
                    self._manifest[internal_name]["doc_count"] = len(data["documents"])
                    self._save_manifest()

                self._remove_doc_from_chroma(internal_name, doc_id)
                return True
            return False
        except Exception as e:
            logger.error("[CustomKB] Remove document failed: %s", e)
            return False

    def get_documents(self, internal_name: str) -> List[KBDocEntry]:
        """Get all documents in a KB.

        Parameters
        ----------
        internal_name : str
            Internal KB name.

        Returns
        -------
        List[KBDocEntry]
            All documents.
        """
        kb_dir = self.kbs_dir / internal_name
        doc_file = kb_dir / "documents.json"

        if not doc_file.exists():
            return []

        try:
            data = json.loads(doc_file.read_text(encoding="utf-8"))
            return [
                KBDocEntry.from_dict(v)
                for v in data.get("documents", {}).values()
            ]
        except Exception as e:
            logger.error("[CustomKB] Get documents failed: %s", e)
            return []

    def search_kb(
        self,
        internal_name: str,
        query: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search within a KB.

        Parameters
        ----------
        internal_name : str
            Internal KB name.
        query : str
            Search query.
        limit : int
            Max results.

        Returns
        -------
        List[Dict]
            Search results with docs and scores.
        """
        results = []

        keyword_results = self._keyword_search(internal_name, query)
        results.extend(keyword_results)

        semantic_results = self._semantic_search(internal_name, query, limit)
        results.extend(semantic_results)

        results = self._dedup_search_results(results)
        results.sort(key=lambda r: r.get("score", 0), reverse=True)
        return results[:limit]

    def search_all_kbs(
        self,
        query: str,
        kb_names: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search across multiple or all KBs.

        Parameters
        ----------
        query : str
            Search query.
        kb_names : List[str] or None
            Specific KBs to search. None = all.
        limit : int
            Max results.

        Returns
        -------
        List[Dict]
            Combined search results.
        """
        all_results = []
        target_kbs = kb_names or list(self._manifest.keys())

        for kb_name in target_kbs:
            if kb_name in self._manifest:
                kb_results = self.search_kb(kb_name, query, limit)
                for r in kb_results:
                    r["kb_name"] = kb_name
                    r["kb_display"] = self._manifest[kb_name].get("display_name", kb_name)
                all_results.extend(kb_results)

        all_results = self._dedup_search_results(all_results)
        all_results.sort(key=lambda r: r.get("score", 0), reverse=True)
        return all_results[:limit]

    def export_kb_markdown(
        self,
        internal_name: str,
        output_dir: Optional[Path] = None,
    ) -> List[str]:
        """Export all KB documents as Markdown files.

        Parameters
        ----------
        internal_name : str
            Internal KB name.
        output_dir : Path or None
            Output directory. If None, uses KB's docs directory.

        Returns
        -------
        List[str]
            Paths to exported Markdown files.
        """
        if output_dir is None:
            output_dir = self.kbs_dir / internal_name / "export"
        output_dir.mkdir(parents=True, exist_ok=True)

        docs = self.get_documents(internal_name)
        exported = []

        for doc in docs:
            if doc.markdown_path and Path(doc.markdown_path).exists():
                import shutil
                dest = output_dir / f"{doc.doc_id}.md"
                shutil.copy2(doc.markdown_path, dest)
                exported.append(str(dest))
            elif doc.content_preview:
                md_path = output_dir / f"{doc.doc_id}.md"
                md_path.write_text(
                    f"# {doc.title}\n\n{doc.content_preview}\n",
                    encoding="utf-8",
                )
                exported.append(str(md_path))

        logger.info("[CustomKB] Exported %d docs from '%s'", len(exported), internal_name)
        return exported

    def _keyword_search(
        self,
        internal_name: str,
        query: str,
    ) -> List[Dict[str, Any]]:
        """Keyword search within a KB."""
        import re

        docs = self.get_documents(internal_name)
        query_lower = query.lower()
        query_terms = set(re.findall(r"\b\w+\b", query_lower))
        results = []

        for doc in docs:
            score = 0.0
            title_lower = doc.title.lower()
            preview_lower = doc.content_preview.lower()

            title_matches = sum(1 for term in query_terms if term in title_lower)
            if title_matches > 0:
                score += title_matches * 3.0

            preview_matches = sum(1 for term in query_terms if term in preview_lower)
            if preview_matches > 0:
                score += preview_matches * 1.0

            if score > 0:
                normalized = min(score / (len(query_terms) * 3.0), 1.0)
                results.append({
                    "doc": doc.to_dict(),
                    "score": normalized,
                    "match_type": "keyword",
                })

        return results

    def _semantic_search(
        self,
        internal_name: str,
        query: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Semantic search via ChromaDB."""
        collection = self._get_chroma_collection(internal_name)
        if collection is None:
            return []

        try:
            embedding = self._get_embedding(query)
            if embedding is None:
                return []

            query_results = collection.query(
                query_embeddings=[embedding],
                n_results=limit,
                include=["metadatas", "documents", "distances"],
            )

            results = []
            if query_results and query_results.get("ids"):
                for i, doc_id in enumerate(query_results["ids"][0]):
                    distance = query_results["distances"][0][i] if query_results.get("distances") else 1.0
                    score = max(0, 1.0 - distance)
                    metadata = query_results["metadatas"][0][i] if query_results.get("metadatas") else {}

                    results.append({
                        "doc": {"doc_id": doc_id, **metadata},
                        "score": score,
                        "match_type": "semantic",
                    })

            return results
        except Exception as e:
            logger.debug("[CustomKB] Semantic search failed: %s", e)
            return []

    def _index_document_to_chroma(
        self,
        internal_name: str,
        doc: KBDocEntry,
    ) -> None:
        """Index a document's Markdown content into ChromaDB."""
        try:
            md_path = Path(doc.markdown_path)
            if not md_path.exists():
                return

            content = md_path.read_text(encoding="utf-8")
            chunks = self._chunk_text(content)

            collection = self._get_or_create_chroma_collection(internal_name)
            if collection is None:
                return

            ids = [f"{doc.doc_id}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "source_type": doc.source_type,
                    "chunk_index": i,
                }
                for i in range(len(chunks))
            ]

            embeddings = []
            valid_chunks = []
            valid_ids = []
            valid_metadatas = []

            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) < 50:
                    continue
                embedding = self._get_embedding(chunk)
                if embedding:
                    embeddings.append(embedding)
                    valid_chunks.append(chunk)
                    valid_ids.append(ids[i])
                    valid_metadatas.append(metadatas[i])

            if valid_chunks:
                collection.add(
                    ids=valid_ids,
                    embeddings=embeddings,
                    metadatas=valid_metadatas,
                    documents=valid_chunks,
                )
        except Exception as e:
            logger.debug("[CustomKB] Chroma index failed for '%s': %s", doc.doc_id, e)

    def _remove_doc_from_chroma(
        self,
        internal_name: str,
        doc_id: str,
    ) -> None:
        """Remove a document's chunks from ChromaDB."""
        try:
            collection = self._get_chroma_collection(internal_name)
            if collection is None:
                return

            existing = collection.get(
                where={"doc_id": doc_id},
                include=[],
            )
            if existing and existing.get("ids"):
                collection.delete(ids=existing["ids"])
        except Exception as e:
            logger.debug("[CustomKB] Chroma remove failed: %s", e)

    def _delete_chroma_collection(self, internal_name: str) -> None:
        """Delete a ChromaDB collection."""
        try:
            from gangdan.core.chroma_manager import ChromaManager

            chroma_dir = str(DATA_DIR / "custom_kb_chroma")
            manager = ChromaManager(persist_dir=chroma_dir)

            if manager.client:
                manager.client.delete_collection(name=internal_name)
        except Exception as e:
            logger.debug("[CustomKB] Delete chroma collection failed: %s", e)

    def _get_or_create_chroma_collection(self, internal_name: str):
        """Get or create ChromaDB collection for a KB."""
        collection = self._get_chroma_collection(internal_name)
        if collection is None:
            try:
                from gangdan.core.chroma_manager import ChromaManager

                chroma_dir = str(DATA_DIR / "custom_kb_chroma")
                manager = ChromaManager(persist_dir=chroma_dir)

                if manager.client:
                    collection = manager.client.get_or_create_collection(
                        name=internal_name,
                        metadata={"hnsw:space": "cosine"},
                    )
                    self._chroma_client = manager.client
            except Exception as e:
                logger.debug("[CustomKB] Create chroma collection failed: %s", e)
                return None
        return collection

    def _get_chroma_collection(self, internal_name: str):
        """Get existing ChromaDB collection."""
        if self._chroma_client is None:
            try:
                from gangdan.core.chroma_manager import ChromaManager

                chroma_dir = str(DATA_DIR / "custom_kb_chroma")
                manager = ChromaManager(persist_dir=chroma_dir)
                self._chroma_client = manager.client
            except Exception:
                return None

        if self._chroma_client is None:
            return None

        try:
            return self._chroma_client.get_collection(name=internal_name)
        except Exception:
            return None

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding via Ollama."""
        try:
            from gangdan.core.ollama_client import get_embedding

            result = get_embedding(text)
            if result and result.get("embedding"):
                return result["embedding"]
        except Exception as e:
            logger.debug("[CustomKB] Embedding failed: %s", e)
        return None

    @staticmethod
    def _chunk_text(text: str, max_chunk_size: int = 2000) -> List[str]:
        """Split text into chunks."""
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
            for i in range(0, len(text), max_chunk_size):
                chunked.append(text[i:i + max_chunk_size])
            return chunked

        return chunks if chunks else [text]

    @staticmethod
    def _dedup_search_results(results: List[Dict]) -> List[Dict]:
        """Deduplicate search results by doc_id."""
        best: Dict[str, Dict] = {}
        for r in results:
            doc = r.get("doc", {})
            doc_id = doc.get("doc_id", "")
            if doc_id and (doc_id not in best or r.get("score", 0) > best[doc_id].get("score", 0)):
                best[doc_id] = r
        return list(best.values())

    def _load_manifest(self) -> Dict[str, Any]:
        """Load KB manifest."""
        if CUSTOM_KBS_MANIFEST.exists():
            try:
                return json.loads(CUSTOM_KBS_MANIFEST.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_manifest(self) -> None:
        """Save KB manifest."""
        try:
            CUSTOM_KBS_MANIFEST.write_text(
                json.dumps(self._manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            logger.error("[CustomKB] Save manifest failed: %s", e)
