"""
Vector Database Abstraction Layer

Supports multiple vector database backends:
- ChromaDB (default, persistent)
- FAISS (high-performance, requires faiss-cpu/faiss-gpu)
- InMemory (numpy-based fallback, no external dependencies)

Usage:
    from gangdan.core.vector_db import create_vector_db, VectorDBType
    
    # Create with specific type
    db = create_vector_db(VectorDBType.CHROMA, persist_dir="/path/to/data")
    
    # Or use config
    db = create_vector_db_from_config()
"""

import sys
import json
import hashlib
import numpy as np
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum


class VectorDBType(Enum):
    """Supported vector database types."""
    CHROMA = "chroma"
    FAISS = "faiss"
    MEMORY = "memory"  # numpy-based in-memory fallback


class VectorDBBase(ABC):
    """Abstract base class for vector database backends."""
    
    @property
    @abstractmethod
    def db_type(self) -> VectorDBType:
        """Return the type of this vector database."""
        pass
    
    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available and initialized."""
        pass
    
    @abstractmethod
    def get_or_create_collection(self, name: str) -> Any:
        """Get or create a collection/index by name."""
        pass
    
    @abstractmethod
    def collection_exists(self, name: str) -> bool:
        """Check if a collection exists."""
        pass
    
    @abstractmethod
    def add_documents(self, collection_name: str, documents: List[str], 
                      embeddings: List[List[float]], metadatas: List[Dict], 
                      ids: List[str]) -> bool:
        """Add documents with their embeddings to a collection."""
        pass
    
    @abstractmethod
    def search(self, collection_name: str, query_embedding: List[float], 
               top_k: int = 10) -> List[Dict]:
        """Search for similar documents. Returns list of {id, document, metadata, distance}."""
        pass
    
    @abstractmethod
    def list_collections(self) -> List[str]:
        """List all collection names."""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, int]:
        """Get document counts for all collections."""
        pass
    
    @abstractmethod
    def delete_collection(self, name: str) -> bool:
        """Delete a collection."""
        pass
    
    @abstractmethod
    def get_documents(self, collection_name: str, limit: int = 0,
                      include: List[str] = None) -> Dict:
        """Get documents from a collection.
        
        Args:
            collection_name: Name of the collection
            limit: Max documents to return. 0 = all.
            include: Fields to include, subset of ["documents", "metadatas", "embeddings", "ids"].
                     Default: ["documents", "metadatas", "ids"]
        
        Returns:
            Dict with keys: ids, documents, metadatas, embeddings (each a list)
        """
        pass
    
    @abstractmethod
    def delete_documents(self, collection_name: str, doc_ids: List[str]) -> bool:
        """Delete specific documents from a collection by their IDs.
        
        Args:
            collection_name: Name of the collection
            doc_ids: List of document IDs to delete
        
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def get_collection_files(self, collection_name: str) -> List[Dict]:
        """Get unique files in a collection with their document counts.
        
        Args:
            collection_name: Name of the collection
        
        Returns:
            List of dicts with keys: file, doc_count, language
        """
        pass


class ChromaVectorDB(VectorDBBase):
    """ChromaDB vector database backend."""
    
    def __init__(self, persist_dir: str):
        self.persist_dir = persist_dir
        self.client = None
        self._init_client()
    
    @property
    def db_type(self) -> VectorDBType:
        return VectorDBType.CHROMA
    
    @property
    def is_available(self) -> bool:
        return self.client is not None
    
    def _init_client(self):
        """Initialize ChromaDB client with auto-recovery."""
        try:
            import chromadb
        except ImportError:
            print("[ChromaDB] ERROR: chromadb package not installed", file=sys.stderr)
            return
        
        # Tier 1: Try normal initialization
        try:
            self.client = chromadb.PersistentClient(path=self.persist_dir)
            print(f"[ChromaDB] Initialized successfully: {self.persist_dir}", file=sys.stderr)
            return
        except BaseException as e:
            print(f"[ChromaDB] ERROR: Initialization failed: {type(e).__name__}: {e}", file=sys.stderr)
        
        # Tier 2: Backup corrupted database and retry
        try:
            import shutil
            backup_name = f"chroma_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_path = str(Path(self.persist_dir).parent / backup_name)
            print(f"[ChromaDB] RECOVERY: Backing up corrupted database to: {backup_path}", file=sys.stderr)
            shutil.move(self.persist_dir, backup_path)
            Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
            try:
                from chromadb.api.shared_system_client import SharedSystemClient
                SharedSystemClient.clear_system_cache()
            except Exception:
                pass
            self.client = chromadb.PersistentClient(path=self.persist_dir)
            print(f"[ChromaDB] RECOVERY: Success - created fresh database", file=sys.stderr)
            return
        except BaseException as e2:
            print(f"[ChromaDB] RECOVERY: Failed: {type(e2).__name__}: {e2}", file=sys.stderr)
        
        print(f"[ChromaDB] WARNING: Running without ChromaDB", file=sys.stderr)
    
    def get_or_create_collection(self, name: str) -> Any:
        if self.client is None:
            return None
        try:
            return self.client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
        except Exception as e:
            print(f"[ChromaDB] Error getting collection '{name}': {e}", file=sys.stderr)
            return None
    
    def collection_exists(self, name: str) -> bool:
        if self.client is None:
            return False
        try:
            names = [c.name for c in self.client.list_collections()]
            return name in names
        except Exception:
            return False
    
    def add_documents(self, collection_name: str, documents: List[str], 
                      embeddings: List[List[float]], metadatas: List[Dict], 
                      ids: List[str]) -> bool:
        if self.client is None:
            return False
        coll = self.get_or_create_collection(collection_name)
        if coll is None:
            return False
        try:
            coll.add(documents=documents, embeddings=embeddings, metadatas=metadatas, ids=ids)
            return True
        except Exception as e:
            print(f"[ChromaDB] Error adding documents: {e}", file=sys.stderr)
            return False
    
    def search(self, collection_name: str, query_embedding: List[float], 
               top_k: int = 10) -> List[Dict]:
        if self.client is None:
            return []
        if not self.collection_exists(collection_name):
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
        if self.client is None:
            return []
        try:
            return [c.name for c in self.client.list_collections()]
        except Exception as e:
            print(f"[ChromaDB] Error listing collections: {e}", file=sys.stderr)
            return []
    
    def get_stats(self) -> Dict[str, int]:
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
    
    def delete_collection(self, name: str) -> bool:
        if self.client is None:
            return False
        try:
            self.client.delete_collection(name)
            return True
        except Exception as e:
            print(f"[ChromaDB] Error deleting collection '{name}': {e}", file=sys.stderr)
            return False
    
    def get_documents(self, collection_name: str, limit: int = 0,
                      include: List[str] = None) -> Dict:
        if self.client is None:
            return {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
        if not self.collection_exists(collection_name):
            return {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
        try:
            coll = self.client.get_collection(collection_name)
            # Build include list for ChromaDB (it doesn't accept "ids" in include)
            chroma_include = []
            if include is None:
                include = ["documents", "metadatas", "ids"]
            for field in include:
                if field in ("documents", "metadatas", "embeddings"):
                    chroma_include.append(field)
            
            kwargs = {}
            if chroma_include:
                kwargs["include"] = chroma_include
            if limit > 0:
                kwargs["limit"] = limit
            
            data = coll.get(**kwargs)
            
            result = {
                "ids": data.get("ids", []),
                "documents": data.get("documents", []) if "documents" in include else [],
                "metadatas": data.get("metadatas", []) if "metadatas" in include else [],
                "embeddings": data.get("embeddings", []) if "embeddings" in include else [],
            }
            return result
        except Exception as e:
            print(f"[ChromaDB] Error getting documents from '{collection_name}': {e}", file=sys.stderr)
            return {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
    
    def delete_documents(self, collection_name: str, doc_ids: List[str]) -> bool:
        if self.client is None or not doc_ids:
            return False
        try:
            coll = self.client.get_collection(collection_name)
            coll.delete(ids=doc_ids)
            return True
        except Exception as e:
            print(f"[ChromaDB] Error deleting documents from '{collection_name}': {e}", file=sys.stderr)
            return False
    
    def get_collection_files(self, collection_name: str) -> List[Dict]:
        if self.client is None:
            return []
        try:
            coll = self.client.get_collection(collection_name)
            data = coll.get(include=["metadatas"])
            
            file_stats = {}
            for meta in data.get("metadatas", []):
                if meta and "file" in meta:
                    filename = meta["file"]
                    if filename not in file_stats:
                        file_stats[filename] = {"file": filename, "doc_count": 0, "language": meta.get("language", "unknown")}
                    file_stats[filename]["doc_count"] += 1
            
            return sorted(file_stats.values(), key=lambda x: x["file"])
        except Exception as e:
            print(f"[ChromaDB] Error getting files from '{collection_name}': {e}", file=sys.stderr)
            return []


class FAISSVectorDB(VectorDBBase):
    """FAISS vector database backend."""
    
    def __init__(self, persist_dir: str):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._faiss = None
        self._collections: Dict[str, Dict] = {}  # name -> {index, documents, metadatas, ids}
        self._init_faiss()
        self._load_all_collections()
    
    @property
    def db_type(self) -> VectorDBType:
        return VectorDBType.FAISS
    
    @property
    def is_available(self) -> bool:
        return self._faiss is not None
    
    def _init_faiss(self):
        """Initialize FAISS library."""
        try:
            import faiss
            self._faiss = faiss
            print(f"[FAISS] Initialized successfully: {self.persist_dir}", file=sys.stderr)
        except ImportError:
            print("[FAISS] ERROR: faiss package not installed. Install with: pip install faiss-cpu", file=sys.stderr)
    
    def _get_collection_path(self, name: str) -> Path:
        """Get path to collection directory."""
        return self.persist_dir / name
    
    def _load_all_collections(self):
        """Load all existing collections from disk."""
        if self._faiss is None:
            return
        for path in self.persist_dir.iterdir():
            if path.is_dir():
                self._load_collection(path.name)
    
    def _load_collection(self, name: str) -> bool:
        """Load a collection from disk."""
        if self._faiss is None:
            return False
        coll_path = self._get_collection_path(name)
        index_path = coll_path / "index.faiss"
        meta_path = coll_path / "metadata.json"
        
        if not index_path.exists() or not meta_path.exists():
            return False
        
        try:
            index = self._faiss.read_index(str(index_path))
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            
            self._collections[name] = {
                "index": index,
                "documents": meta.get("documents", []),
                "metadatas": meta.get("metadatas", []),
                "ids": meta.get("ids", []),
                "dimension": meta.get("dimension", 0)
            }
            return True
        except Exception as e:
            print(f"[FAISS] Error loading collection '{name}': {e}", file=sys.stderr)
            return False
    
    def _save_collection(self, name: str) -> bool:
        """Save a collection to disk."""
        if self._faiss is None or name not in self._collections:
            return False
        
        coll = self._collections[name]
        coll_path = self._get_collection_path(name)
        coll_path.mkdir(parents=True, exist_ok=True)
        
        try:
            self._faiss.write_index(coll["index"], str(coll_path / "index.faiss"))
            with open(coll_path / "metadata.json", 'w', encoding='utf-8') as f:
                json.dump({
                    "documents": coll["documents"],
                    "metadatas": coll["metadatas"],
                    "ids": coll["ids"],
                    "dimension": coll["dimension"]
                }, f, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[FAISS] Error saving collection '{name}': {e}", file=sys.stderr)
            return False
    
    def get_or_create_collection(self, name: str) -> Any:
        if self._faiss is None:
            return None
        if name in self._collections:
            return self._collections[name]
        # Return placeholder - will be created on first add
        return {"name": name, "pending": True}
    
    def collection_exists(self, name: str) -> bool:
        return name in self._collections
    
    def add_documents(self, collection_name: str, documents: List[str], 
                      embeddings: List[List[float]], metadatas: List[Dict], 
                      ids: List[str]) -> bool:
        if self._faiss is None or not embeddings:
            return False
        
        dimension = len(embeddings[0])
        vectors = np.array(embeddings, dtype=np.float32)
        
        if collection_name not in self._collections:
            # Create new index with cosine similarity (normalize + L2)
            index = self._faiss.IndexFlatIP(dimension)  # Inner product for cosine
            self._collections[collection_name] = {
                "index": index,
                "documents": [],
                "metadatas": [],
                "ids": [],
                "dimension": dimension
            }
        
        coll = self._collections[collection_name]
        
        # Normalize vectors for cosine similarity
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1  # Avoid division by zero
        normalized = vectors / norms
        
        # Add to index
        coll["index"].add(normalized)
        coll["documents"].extend(documents)
        coll["metadatas"].extend(metadatas)
        coll["ids"].extend(ids)
        
        # Persist
        return self._save_collection(collection_name)
    
    def search(self, collection_name: str, query_embedding: List[float], 
               top_k: int = 10) -> List[Dict]:
        if self._faiss is None:
            return []
        if not self.collection_exists(collection_name):
            return []
        
        coll = self._collections[collection_name]
        if coll["index"].ntotal == 0:
            return []
        
        # Normalize query for cosine similarity
        query = np.array([query_embedding], dtype=np.float32)
        norm = np.linalg.norm(query)
        if norm > 0:
            query = query / norm
        
        # Search
        k = min(top_k, coll["index"].ntotal)
        scores, indices = coll["index"].search(query, k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= 0 and idx < len(coll["documents"]):
                # Convert similarity score to distance (1 - similarity for cosine)
                distance = 1 - scores[0][i]
                results.append({
                    "id": coll["ids"][idx],
                    "document": coll["documents"][idx],
                    "metadata": coll["metadatas"][idx],
                    "distance": float(distance)
                })
        
        return results
    
    def list_collections(self) -> List[str]:
        return list(self._collections.keys())
    
    def get_stats(self) -> Dict[str, int]:
        return {name: coll["index"].ntotal for name, coll in self._collections.items()}
    
    def delete_collection(self, name: str) -> bool:
        if name not in self._collections:
            return False
        
        del self._collections[name]
        coll_path = self._get_collection_path(name)
        if coll_path.exists():
            import shutil
            shutil.rmtree(coll_path)
        return True
    
    def get_documents(self, collection_name: str, limit: int = 0,
                      include: List[str] = None) -> Dict:
        if self._faiss is None or collection_name not in self._collections:
            return {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
        
        if include is None:
            include = ["documents", "metadatas", "ids"]
        
        coll = self._collections[collection_name]
        total = len(coll["ids"])
        end = total if limit <= 0 else min(limit, total)
        
        result = {"ids": coll["ids"][:end]}
        result["documents"] = coll["documents"][:end] if "documents" in include else []
        result["metadatas"] = coll["metadatas"][:end] if "metadatas" in include else []
        if "embeddings" in include:
            # Reconstruct embeddings from FAISS index
            try:
                n = min(end, coll["index"].ntotal)
                if n > 0:
                    vectors = np.array([coll["index"].reconstruct(i) for i in range(n)])
                    result["embeddings"] = vectors.tolist()
                else:
                    result["embeddings"] = []
            except Exception:
                result["embeddings"] = []
        else:
            result["embeddings"] = []
        
        return result
    
    def delete_documents(self, collection_name: str, doc_ids: List[str]) -> bool:
        if self._faiss is None or collection_name not in self._collections or not doc_ids:
            return False
        
        coll = self._collections[collection_name]
        ids_set = set(doc_ids)
        
        new_indices = []
        for i, doc_id in enumerate(coll["ids"]):
            if doc_id not in ids_set:
                new_indices.append(i)
        
        if len(new_indices) == len(coll["ids"]):
            return True
        
        try:
            new_embeddings = coll["embeddings"][new_indices] if hasattr(coll["embeddings"], '__getitem__') else np.array([])
            new_documents = [coll["documents"][i] for i in new_indices]
            new_metadatas = [coll["metadatas"][i] for i in new_indices]
            new_ids = [coll["ids"][i] for i in new_indices]
            
            dimension = coll["dimension"]
            new_index = self._faiss.IndexFlatIP(dimension)
            if len(new_embeddings) > 0:
                norms = np.linalg.norm(new_embeddings, axis=1, keepdims=True)
                norms[norms == 0] = 1
                normalized = new_embeddings / norms
                new_index.add(normalized)
            
            coll["index"] = new_index
            coll["documents"] = new_documents
            coll["metadatas"] = new_metadatas
            coll["ids"] = new_ids
            coll["embeddings"] = new_embeddings
            
            return self._save_collection(collection_name)
        except Exception as e:
            print(f"[FAISS] Error deleting documents: {e}", file=sys.stderr)
            return False
    
    def get_collection_files(self, collection_name: str) -> List[Dict]:
        if self._faiss is None or collection_name not in self._collections:
            return []
        
        coll = self._collections[collection_name]
        file_stats = {}
        
        for meta in coll["metadatas"]:
            if meta and "file" in meta:
                filename = meta["file"]
                if filename not in file_stats:
                    file_stats[filename] = {"file": filename, "doc_count": 0, "language": meta.get("language", "unknown")}
                file_stats[filename]["doc_count"] += 1
        
        return sorted(file_stats.values(), key=lambda x: x["file"])


class InMemoryVectorDB(VectorDBBase):
    """Simple in-memory vector database using numpy (no external dependencies)."""
    
    def __init__(self, persist_dir: str):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._collections: Dict[str, Dict] = {}
        self._load_all_collections()
        print(f"[MemoryDB] Initialized: {self.persist_dir}", file=sys.stderr)
    
    @property
    def db_type(self) -> VectorDBType:
        return VectorDBType.MEMORY
    
    @property
    def is_available(self) -> bool:
        return True  # Always available
    
    def _get_collection_path(self, name: str) -> Path:
        return self.persist_dir / f"{name}.json"
    
    def _load_all_collections(self):
        """Load all collections from disk."""
        for path in self.persist_dir.glob("*.json"):
            name = path.stem
            self._load_collection(name)
    
    def _load_collection(self, name: str) -> bool:
        """Load a collection from disk."""
        path = self._get_collection_path(name)
        if not path.exists():
            return False
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._collections[name] = {
                "embeddings": np.array(data.get("embeddings", []), dtype=np.float32),
                "documents": data.get("documents", []),
                "metadatas": data.get("metadatas", []),
                "ids": data.get("ids", [])
            }
            return True
        except Exception as e:
            print(f"[MemoryDB] Error loading '{name}': {e}", file=sys.stderr)
            return False
    
    def _save_collection(self, name: str) -> bool:
        """Save a collection to disk."""
        if name not in self._collections:
            return False
        coll = self._collections[name]
        path = self._get_collection_path(name)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({
                    "embeddings": coll["embeddings"].tolist(),
                    "documents": coll["documents"],
                    "metadatas": coll["metadatas"],
                    "ids": coll["ids"]
                }, f, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[MemoryDB] Error saving '{name}': {e}", file=sys.stderr)
            return False
    
    def get_or_create_collection(self, name: str) -> Any:
        if name not in self._collections:
            self._collections[name] = {
                "embeddings": np.array([], dtype=np.float32).reshape(0, 0),
                "documents": [],
                "metadatas": [],
                "ids": []
            }
        return self._collections[name]
    
    def collection_exists(self, name: str) -> bool:
        return name in self._collections
    
    def add_documents(self, collection_name: str, documents: List[str], 
                      embeddings: List[List[float]], metadatas: List[Dict], 
                      ids: List[str]) -> bool:
        if not embeddings:
            return False
        
        coll = self.get_or_create_collection(collection_name)
        new_embeddings = np.array(embeddings, dtype=np.float32)
        
        if coll["embeddings"].size == 0:
            coll["embeddings"] = new_embeddings
        else:
            coll["embeddings"] = np.vstack([coll["embeddings"], new_embeddings])
        
        coll["documents"].extend(documents)
        coll["metadatas"].extend(metadatas)
        coll["ids"].extend(ids)
        
        return self._save_collection(collection_name)
    
    def search(self, collection_name: str, query_embedding: List[float], 
               top_k: int = 10) -> List[Dict]:
        if not self.collection_exists(collection_name):
            return []
        
        coll = self._collections[collection_name]
        if coll["embeddings"].size == 0:
            return []
        
        # Cosine similarity
        query = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []
        query = query / query_norm
        
        embeddings = coll["embeddings"]
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1
        normalized = embeddings / norms
        
        similarities = np.dot(normalized, query)
        k = min(top_k, len(similarities))
        top_indices = np.argsort(similarities)[-k:][::-1]
        
        results = []
        for idx in top_indices:
            results.append({
                "id": coll["ids"][idx],
                "document": coll["documents"][idx],
                "metadata": coll["metadatas"][idx],
                "distance": float(1 - similarities[idx])  # Convert to distance
            })
        
        return results
    
    def list_collections(self) -> List[str]:
        return list(self._collections.keys())
    
    def get_stats(self) -> Dict[str, int]:
        return {name: len(coll["documents"]) for name, coll in self._collections.items()}
    
    def delete_collection(self, name: str) -> bool:
        if name not in self._collections:
            return False
        del self._collections[name]
        path = self._get_collection_path(name)
        if path.exists():
            path.unlink()
        return True
    
    def get_documents(self, collection_name: str, limit: int = 0,
                      include: List[str] = None) -> Dict:
        if collection_name not in self._collections:
            return {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
        
        if include is None:
            include = ["documents", "metadatas", "ids"]
        
        coll = self._collections[collection_name]
        total = len(coll["ids"])
        end = total if limit <= 0 else min(limit, total)
        
        result = {"ids": coll["ids"][:end]}
        result["documents"] = coll["documents"][:end] if "documents" in include else []
        result["metadatas"] = coll["metadatas"][:end] if "metadatas" in include else []
        if "embeddings" in include and coll["embeddings"].size > 0:
            result["embeddings"] = coll["embeddings"][:end].tolist()
        else:
            result["embeddings"] = []
        
        return result
    
    def delete_documents(self, collection_name: str, doc_ids: List[str]) -> bool:
        if collection_name not in self._collections or not doc_ids:
            return False
        
        coll = self._collections[collection_name]
        ids_set = set(doc_ids)
        
        new_indices = []
        for i, doc_id in enumerate(coll["ids"]):
            if doc_id not in ids_set:
                new_indices.append(i)
        
        if len(new_indices) == len(coll["ids"]):
            return True
        
        try:
            new_embeddings = coll["embeddings"][new_indices] if coll["embeddings"].size > 0 else np.array([], dtype=np.float32).reshape(0, 0)
            new_documents = [coll["documents"][i] for i in new_indices]
            new_metadatas = [coll["metadatas"][i] for i in new_indices]
            new_ids = [coll["ids"][i] for i in new_indices]
            
            coll["embeddings"] = new_embeddings
            coll["documents"] = new_documents
            coll["metadatas"] = new_metadatas
            coll["ids"] = new_ids
            
            return self._save_collection(collection_name)
        except Exception as e:
            print(f"[MemoryDB] Error deleting documents: {e}", file=sys.stderr)
            return False
    
    def get_collection_files(self, collection_name: str) -> List[Dict]:
        if collection_name not in self._collections:
            return []
        
        coll = self._collections[collection_name]
        file_stats = {}
        
        for meta in coll["metadatas"]:
            if meta and "file" in meta:
                filename = meta["file"]
                if filename not in file_stats:
                    file_stats[filename] = {"file": filename, "doc_count": 0, "language": meta.get("language", "unknown")}
                file_stats[filename]["doc_count"] += 1
        
        return sorted(file_stats.values(), key=lambda x: x["file"])


def create_vector_db(db_type: VectorDBType, persist_dir: str) -> VectorDBBase:
    """
    Factory function to create a vector database instance.
    
    Args:
        db_type: Type of vector database to create
        persist_dir: Directory for persistent storage
    
    Returns:
        VectorDBBase instance
    """
    if db_type == VectorDBType.CHROMA:
        return ChromaVectorDB(persist_dir)
    elif db_type == VectorDBType.FAISS:
        db = FAISSVectorDB(persist_dir)
        if not db.is_available:
            print("[VectorDB] FAISS not available, falling back to in-memory DB", file=sys.stderr)
            return InMemoryVectorDB(persist_dir)
        return db
    elif db_type == VectorDBType.MEMORY:
        return InMemoryVectorDB(persist_dir)
    else:
        raise ValueError(f"Unsupported vector database type: {db_type}")


def create_vector_db_auto(persist_dir: str, preferred: str = "chroma") -> VectorDBBase:
    """
    Create vector database with automatic fallback.
    
    Tries backends in order: preferred -> chroma -> faiss -> memory
    
    Args:
        persist_dir: Directory for persistent storage
        preferred: Preferred backend type (chroma, faiss, memory)
    
    Returns:
        VectorDBBase instance
    """
    type_map = {
        "chroma": VectorDBType.CHROMA,
        "faiss": VectorDBType.FAISS,
        "memory": VectorDBType.MEMORY
    }
    
    preferred_type = type_map.get(preferred.lower(), VectorDBType.CHROMA)
    
    # Try preferred first
    db = create_vector_db(preferred_type, persist_dir)
    if db.is_available:
        return db
    
    # Fallback chain
    for fallback_type in [VectorDBType.CHROMA, VectorDBType.FAISS, VectorDBType.MEMORY]:
        if fallback_type == preferred_type:
            continue
        db = create_vector_db(fallback_type, persist_dir)
        if db.is_available:
            print(f"[VectorDB] Using fallback: {fallback_type.value}", file=sys.stderr)
            return db
    
    # Memory is always available
    return InMemoryVectorDB(persist_dir)
