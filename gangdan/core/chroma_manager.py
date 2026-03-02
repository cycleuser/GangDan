"""ChromaDB vector database manager."""

import sys
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

import chromadb
from chromadb.config import Settings


class ChromaManager:
    """Manager for ChromaDB vector database with auto-recovery."""
    
    def __init__(self, persist_dir: str):
        self.persist_dir = persist_dir
        self.client = None
        
        # Tier 1: Try normal initialization
        try:
            self.client = chromadb.PersistentClient(path=persist_dir)
            print(f"[ChromaDB] Initialized successfully: {persist_dir}", file=sys.stderr)
            return
        except BaseException as e:
            print(f"[ChromaDB] ERROR: Initialization failed: {type(e).__name__}: {e}", file=sys.stderr)
        
        # Tier 2: Backup corrupted database and retry
        try:
            backup_name = f"chroma_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_path = str(Path(persist_dir).parent / backup_name)
            print(f"[ChromaDB] RECOVERY: Backing up corrupted database to: {backup_path}", file=sys.stderr)
            shutil.move(persist_dir, backup_path)
            Path(persist_dir).mkdir(parents=True, exist_ok=True)
            # Clear ChromaDB's internal shared system cache (poisoned by failed init)
            try:
                from chromadb.api.shared_system_client import SharedSystemClient
                SharedSystemClient.clear_system_cache()
            except Exception:
                pass
            self.client = chromadb.PersistentClient(path=persist_dir)
            print(f"[ChromaDB] RECOVERY: Success - created fresh database", file=sys.stderr)
            return
        except BaseException as e2:
            print(f"[ChromaDB] RECOVERY: Failed: {type(e2).__name__}: {e2}", file=sys.stderr)
        
        # Tier 3: Give up, run without ChromaDB
        print(f"[ChromaDB] WARNING: Running without ChromaDB - knowledge base features disabled", file=sys.stderr)
    
    def get_or_create_collection(self, name: str):
        """Get or create a collection by name."""
        if self.client is None:
            return None
        try:
            return self.client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
        except Exception as e:
            print(f"[ChromaDB] Error getting collection '{name}': {e}", file=sys.stderr)
            return None
    
    def add_documents(self, collection_name: str, documents: List[str], embeddings: List[List[float]], 
                      metadatas: List[Dict], ids: List[str]):
        """Add documents to a collection."""
        if self.client is None:
            return
        coll = self.get_or_create_collection(collection_name)
        if coll is None:
            return
        coll.add(documents=documents, embeddings=embeddings, metadatas=metadatas, ids=ids)
    
    def search(self, collection_name: str, query_embedding: List[float], top_k: int = 10) -> List[Dict]:
        """Search a collection for similar documents."""
        if self.client is None:
            return []
        try:
            coll = self.client.get_collection(collection_name)
            results = coll.query(query_embeddings=[query_embedding], n_results=top_k)
            items = []
            for i in range(len(results["ids"][0])):
                items.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                })
            return items
        except Exception as e:
            print(f"[ChromaDB] Search error in '{collection_name}': {e}", file=sys.stderr)
            return []
    
    def list_collections(self) -> List[str]:
        """List all collection names."""
        if self.client is None:
            return []
        try:
            return [c.name for c in self.client.list_collections()]
        except Exception as e:
            print(f"[ChromaDB] Error listing collections: {e}", file=sys.stderr)
            return []
    
    def get_stats(self) -> Dict[str, int]:
        """Get document counts for all collections."""
        if self.client is None:
            return {}
        try:
            stats = {}
            for coll in self.client.list_collections():
                stats[coll.name] = coll.count()
            return stats
        except Exception as e:
            print(f"[ChromaDB] Error getting stats: {e}", file=sys.stderr)
            return {}
