"""ChromaDB vector database manager with auto-recovery.

This module provides persistent vector storage with automatic recovery
from database corruption.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb

logger = logging.getLogger(__name__)


class ChromaManager:
    """Manager for ChromaDB vector database with auto-recovery on corruption.

    Attributes
    ----------
    persist_dir : str
        Directory for persistent storage.
    client : chromadb.ClientAPI or None
        ChromaDB client instance.
    """

    def __init__(self, persist_dir: str) -> None:
        """Initialize ChromaDB manager.

        Parameters
        ----------
        persist_dir : str
            Directory for persistent database storage.
        """
        self.persist_dir = persist_dir
        self.client: Optional[chromadb.ClientAPI] = None

        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize ChromaDB client with automatic recovery."""
        try:
            self.client = chromadb.PersistentClient(path=self.persist_dir)
            logger.info("Initialized successfully: %s", self.persist_dir)
            return
        except BaseException as e:
            logger.error("Initialization failed: %s: %s", type(e).__name__, str(e))

        self._recover_and_initialize()

    def _recover_and_initialize(self) -> None:
        """Attempt to recover from corrupted database and reinitialize."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"chroma_backup_{timestamp}"
            backup_path = str(Path(self.persist_dir).parent / backup_name)

            logger.info("RECOVERY: Backing up corrupted database to: %s", backup_path)
            shutil.move(self.persist_dir, backup_path)
            Path(self.persist_dir).mkdir(parents=True, exist_ok=True)

            self._clear_system_cache()

            self.client = chromadb.PersistentClient(path=self.persist_dir)
            logger.info("RECOVERY: Success - created fresh database")
        except BaseException as e:
            logger.error("RECOVERY: Failed: %s: %s", type(e).__name__, str(e))

        logger.warning("Running without ChromaDB - knowledge base features disabled")

    def _clear_system_cache(self) -> None:
        """Clear ChromaDB's internal shared system cache."""
        try:
            from chromadb.api.shared_system_client import SharedSystemClient

            SharedSystemClient.clear_system_cache()
        except (ImportError, AttributeError):
            # Ignore if SharedSystemClient is not available
            pass

    def get_or_create_collection(self, name: str) -> Optional[Any]:
        """Get or create a collection by name.

        Parameters
        ----------
        name : str
            Collection name.

        Returns
        -------
        chromadb.Collection or None
            Collection instance, or None if unavailable.
        """
        if self.client is None:
            return None
        try:
            return self.client.get_or_create_collection(
                name=name, metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.error("Error getting collection '%s': %s", name, str(e))
            return None

    def add_documents(
        self,
        collection_name: str,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
    ) -> None:
        """Add documents to a collection.

        Parameters
        ----------
        collection_name : str
            Target collection name.
        documents : List[str]
            List of document texts.
        embeddings : List[List[float]]
            List of embedding vectors.
        metadatas : List[Dict[str, Any]]
            List of metadata dicts.
        ids : List[str]
            List of unique document IDs.
        """
        if self.client is None:
            return

        collection = self.get_or_create_collection(collection_name)
        if collection is None:
            return

        collection.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )

    def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists."""
        if self.client is None:
            return False
        try:
            names = [c.name for c in self.client.list_collections()]
            return collection_name in names
        except Exception:
            return False

    def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search a collection for similar documents.

        Parameters
        ----------
        collection_name : str
            Collection to search.
        query_embedding : List[float]
            Query embedding vector.
        top_k : int
            Number of results to return (default: 10).

        Returns
        -------
        List[Dict[str, Any]]
            List of matching documents with metadata and distances.
        """
        if self.client is None:
            return []

        if not self.collection_exists(collection_name):
            return []

        try:
            collection = self.client.get_collection(collection_name)
            results = collection.query(
                query_embeddings=[query_embedding], n_results=top_k
            )

            items: List[Dict[str, Any]] = []
            for i in range(len(results["ids"][0])):
                items.append(
                    {
                        "id": results["ids"][0][i],
                        "document": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i]
                        if results["metadatas"]
                        else {},
                        "distance": results["distances"][0][i]
                        if results["distances"]
                        else 0.0,
                    }
                )
            return items
        except Exception as e:
            logger.error("Search error in '%s': %s", collection_name, str(e))
            return []

    def list_collections(self) -> List[str]:
        """List all collection names.

        Returns
        -------
        List[str]
            List of collection names.
        """
        if self.client is None:
            return []
        try:
            return [c.name for c in self.client.list_collections()]
        except Exception as e:
            logger.error("Error listing collections: %s", str(e))
            return []

    def get_stats(self) -> Dict[str, int]:
        """Get document counts for all collections.

        Returns
        -------
        Dict[str, int]
            Dictionary mapping collection names to document counts.
        """
        if self.client is None:
            return {}
        try:
            stats = {}
            for collection in self.client.list_collections():
                stats[collection.name] = collection.count()
            return stats
        except Exception as e:
            logger.error("Error getting stats: %s", str(e))
            return {}
