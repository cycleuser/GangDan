"""Vector Database Abstraction Layer.

Supports multiple backends: ChromaDB, FAISS, and InMemory (numpy).
"""

import hashlib
import json
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class VectorDBType(Enum):
    """Supported vector database types."""
    CHROMA = "chroma"
    FAISS = "faiss"
    MEMORY = "memory"


class VectorDBBase(ABC):
    """Abstract base class for vector database backends."""

    @property
    @abstractmethod
    def db_type(self) -> VectorDBType:
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def get_or_create_collection(self, name: str) -> Any:
        pass

    @abstractmethod
    def collection_exists(self, name: str) -> bool:
        pass

    @abstractmethod
    def add_documents(self, collection_name: str, documents: List[str],
                      embeddings: List[List[float]], metadatas: List[Dict],
                      ids: List[str]) -> bool:
        pass

    @abstractmethod
    def search(self, collection_name: str, query_embedding: List[float],
               top_k: int = 10) -> List[Dict]:
        pass

    @abstractmethod
    def list_collections(self) -> List[str]:
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, int]:
        pass

    @abstractmethod
    def delete_collection(self, name: str) -> bool:
        pass

    @abstractmethod
    def get_documents(self, collection_name: str, limit: int = 0,
                      include: List[str] = None) -> Dict:
        pass

    @abstractmethod
    def delete_documents(self, collection_name: str, doc_ids: List[str]) -> bool:
        pass

    @abstractmethod
    def get_collection_files(self, collection_name: str) -> List[Dict]:
        pass

    @abstractmethod
    def get_collection_dimension(self, collection_name: str) -> int:
        pass

    @abstractmethod
    def check_dimension_mismatch(self, collection_name: str, expected_dim: int) -> Optional[int]:
        pass

    def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        return {}

    def set_collection_embedding_model(self, collection_name: str, model_name: str, dimension: int) -> bool:
        return True


class ChromaVectorDB(VectorDBBase):
    """ChromaDB vector database backend with auto-recovery."""

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
        try:
            import chromadb
        except ImportError:
            print("[ChromaDB] ERROR: chromadb package not installed", file=sys.stderr)
            return

        try:
            self.client = chromadb.PersistentClient(path=self.persist_dir)
            return
        except BaseException as e:
            print(f"[ChromaDB] Init failed: {e}", file=sys.stderr)

        try:
            import shutil
            backup_name = f"chroma_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_path = str(Path(self.persist_dir).parent / backup_name)
            print(f"[ChromaDB] Backing up corrupted DB to: {backup_path}", file=sys.stderr)
            shutil.move(self.persist_dir, backup_path)
            Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
            try:
                from chromadb.api.shared_system_client import SharedSystemClient
                SharedSystemClient.clear_system_cache()
            except Exception:
                pass
            self.client = chromadb.PersistentClient(path=self.persist_dir)
            print("[ChromaDB] Recovery successful", file=sys.stderr)
        except BaseException as e2:
            print(f"[ChromaDB] Recovery failed: {e2}", file=sys.stderr)

    def get_or_create_collection(self, name: str) -> Any:
        if self.client is None:
            return None
        try:
            return self.client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
        except Exception as e:
            print(f"[ChromaDB] Error: {e}", file=sys.stderr)
            return None

    def collection_exists(self, name: str) -> bool:
        if self.client is None:
            return False
        try:
            return name in [c.name for c in self.client.list_collections()]
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
            print(f"[ChromaDB] Add error: {e}", file=sys.stderr)
            return False

    def search(self, collection_name: str, query_embedding: List[float],
               top_k: int = 10) -> List[Dict]:
        if self.client is None or not self.collection_exists(collection_name):
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
            print(f"[ChromaDB] Search error: {e}", file=sys.stderr)
            return []

    def list_collections(self) -> List[str]:
        if self.client is None:
            return []
        try:
            return [c.name for c in self.client.list_collections()]
        except Exception:
            return []

    def get_stats(self) -> Dict[str, int]:
        if self.client is None:
            return {}
        try:
            return {coll.name: coll.count() for coll in self.client.list_collections()}
        except Exception:
            return {}

    def delete_collection(self, name: str) -> bool:
        if self.client is None:
            return False
        try:
            self.client.delete_collection(name)
            return True
        except Exception:
            return False

    def get_collection_dimension(self, collection_name: str) -> int:
        if self.client is None:
            return 0
        try:
            collection = self.client.get_collection(collection_name)
            metadata = collection.metadata or {}
            dim = metadata.get("dimension", 0)
            if dim and isinstance(dim, (int, float)) and dim > 0:
                return int(dim)
            peek = collection.peek()
            embeddings = peek.get("embeddings")
            if embeddings and len(embeddings) > 0:
                return len(embeddings[0])
        except Exception:
            pass
        return 0

    def check_dimension_mismatch(self, collection_name: str, expected_dim: int) -> Optional[int]:
        coll_dim = self.get_collection_dimension(collection_name)
        if coll_dim == 0 or coll_dim == expected_dim:
            return None
        return coll_dim

    def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        if self.client is None:
            return {}
        try:
            collection = self.client.get_collection(collection_name)
            metadata = collection.metadata or {}
            dim = metadata.get("dimension", 0) or self.get_collection_dimension(collection_name)
            return {
                "dimension": dim,
                "embedding_model": metadata.get("embedding_model", ""),
                "doc_count": collection.count(),
            }
        except Exception:
            return {}

    def set_collection_embedding_model(self, collection_name: str, model_name: str, dimension: int) -> bool:
        if self.client is None:
            return False
        try:
            collection = self.client.get_collection(collection_name)
            existing_meta = dict(collection.metadata or {})
            existing_meta.pop("hnsw:space", None)
            existing_meta["embedding_model"] = model_name
            existing_meta["dimension"] = dimension
            collection.modify(metadata=existing_meta)
            return True
        except Exception:
            return False

    def get_documents(self, collection_name: str, limit: int = 0,
                      include: List[str] = None) -> Dict:
        if self.client is None or not self.collection_exists(collection_name):
            return {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
        try:
            coll = self.client.get_collection(collection_name)
            if include is None:
                include = ["documents", "metadatas", "ids"]
            chroma_include = [f for f in include if f in ("documents", "metadatas", "embeddings")]
            kwargs = {}
            if chroma_include:
                kwargs["include"] = chroma_include
            if limit > 0:
                kwargs["limit"] = limit
            data = coll.get(**kwargs)
            return {
                "ids": data.get("ids", []),
                "documents": data.get("documents", []) if "documents" in include else [],
                "metadatas": data.get("metadatas", []) if "metadatas" in include else [],
                "embeddings": data.get("embeddings", []) if "embeddings" in include else [],
            }
        except Exception:
            return {"ids": [], "documents": [], "metadatas": [], "embeddings": []}

    def delete_documents(self, collection_name: str, doc_ids: List[str]) -> bool:
        if self.client is None or not doc_ids:
            return False
        try:
            coll = self.client.get_collection(collection_name)
            coll.delete(ids=doc_ids)
            return True
        except Exception:
            return False

    def get_collection_files(self, collection_name: str) -> List[Dict]:
        if self.client is None:
            return []
        try:
            coll = self.client.get_collection(collection_name)
            data = coll.get(include=["metadatas"])
            file_stats = {}
            for meta in data.get("metadatas", []):
                if not meta:
                    continue
                filename = meta.get("file") or meta.get("doc_id") or meta.get("title") or "unknown"
                if filename not in file_stats:
                    file_stats[filename] = {"file": filename, "doc_count": 0, "language": meta.get("language", "unknown")}
                file_stats[filename]["doc_count"] += 1
            return sorted(file_stats.values(), key=lambda x: x["file"])
        except Exception:
            return []


class InMemoryVectorDB(VectorDBBase):
    """Simple in-memory vector database using numpy."""

    def __init__(self, persist_dir: str):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._collections: Dict[str, Dict] = {}
        self._load_all_collections()

    @property
    def db_type(self) -> VectorDBType:
        return VectorDBType.MEMORY

    @property
    def is_available(self) -> bool:
        return True

    def _get_collection_path(self, name: str) -> Path:
        return self.persist_dir / f"{name}.json"

    def _load_all_collections(self):
        for path in self.persist_dir.glob("*.json"):
            self._load_collection(path.stem)

    def _load_collection(self, name: str) -> bool:
        path = self._get_collection_path(name)
        if not path.exists():
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._collections[name] = {
                "embeddings": np.array(data.get("embeddings", []), dtype=np.float32),
                "documents": data.get("documents", []),
                "metadatas": data.get("metadatas", []),
                "ids": data.get("ids", []),
                "embedding_model": data.get("embedding_model", ""),
            }
            return True
        except Exception:
            return False

    def _save_collection(self, name: str) -> bool:
        if name not in self._collections:
            return False
        coll = self._collections[name]
        path = self._get_collection_path(name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "embeddings": coll["embeddings"].tolist(),
                    "documents": coll["documents"],
                    "metadatas": coll["metadatas"],
                    "ids": coll["ids"],
                    "embedding_model": coll.get("embedding_model", ""),
                }, f, ensure_ascii=False)
            return True
        except Exception:
            return False

    def get_or_create_collection(self, name: str) -> Any:
        if name not in self._collections:
            self._collections[name] = {
                "embeddings": np.array([], dtype=np.float32).reshape(0, 0),
                "documents": [],
                "metadatas": [],
                "ids": [],
                "embedding_model": "",
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
                "distance": float(1 - similarities[idx]),
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
        new_indices = [i for i, doc_id in enumerate(coll["ids"]) if doc_id not in ids_set]
        if len(new_indices) == len(coll["ids"]):
            return True
        try:
            coll["embeddings"] = coll["embeddings"][new_indices] if coll["embeddings"].size > 0 else np.array([], dtype=np.float32).reshape(0, 0)
            coll["documents"] = [coll["documents"][i] for i in new_indices]
            coll["metadatas"] = [coll["metadatas"][i] for i in new_indices]
            coll["ids"] = [coll["ids"][i] for i in new_indices]
            return self._save_collection(collection_name)
        except Exception:
            return False

    def get_collection_files(self, collection_name: str) -> List[Dict]:
        if collection_name not in self._collections:
            return []
        coll = self._collections[collection_name]
        file_stats = {}
        for meta in coll["metadatas"]:
            if not meta:
                continue
            filename = meta.get("file") or meta.get("doc_id") or meta.get("title") or "unknown"
            if filename not in file_stats:
                file_stats[filename] = {"file": filename, "doc_count": 0, "language": meta.get("language", "unknown")}
            file_stats[filename]["doc_count"] += 1
        return sorted(file_stats.values(), key=lambda x: x["file"])

    def get_collection_dimension(self, collection_name: str) -> int:
        if collection_name not in self._collections:
            return 0
        coll = self._collections[collection_name]
        embeddings = coll.get("embeddings", [])
        if embeddings is not None and embeddings.size > 0:
            return embeddings.shape[1] if len(embeddings.shape) > 1 else 0
        return 0

    def check_dimension_mismatch(self, collection_name: str, expected_dim: int) -> Optional[int]:
        coll_dim = self.get_collection_dimension(collection_name)
        if coll_dim == 0 or coll_dim == expected_dim:
            return None
        return coll_dim

    def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        if collection_name not in self._collections:
            return {}
        coll = self._collections[collection_name]
        embeddings = coll.get("embeddings", [])
        dim = embeddings.shape[1] if embeddings.size > 0 and len(embeddings.shape) > 1 else 0
        return {
            "dimension": dim,
            "embedding_model": coll.get("embedding_model", ""),
            "doc_count": len(coll.get("ids", [])),
        }

    def set_collection_embedding_model(self, collection_name: str, model_name: str, dimension: int) -> bool:
        if collection_name not in self._collections:
            return False
        self._collections[collection_name]["embedding_model"] = model_name
        return self._save_collection(collection_name)


def create_vector_db(db_type: VectorDBType, persist_dir: str) -> VectorDBBase:
    """Factory function to create a vector database instance."""
    if db_type == VectorDBType.CHROMA:
        return ChromaVectorDB(persist_dir)
    elif db_type == VectorDBType.FAISS:
        try:
            import faiss  # noqa: F401
            from gangdan_refined.core.vector_db import FAISSVectorDB
            return FAISSVectorDB(persist_dir)
        except ImportError:
            print("[VectorDB] FAISS not available, falling back to memory", file=sys.stderr)
            return InMemoryVectorDB(persist_dir)
    return InMemoryVectorDB(persist_dir)


def create_vector_db_auto(persist_dir: str, preferred: str = "chroma") -> VectorDBBase:
    """Create vector database with automatic fallback."""
    type_map = {"chroma": VectorDBType.CHROMA, "faiss": VectorDBType.FAISS, "memory": VectorDBType.MEMORY}
    preferred_type = type_map.get(preferred.lower(), VectorDBType.CHROMA)
    db = create_vector_db(preferred_type, persist_dir)
    if db.is_available:
        return db
    for fallback_type in [VectorDBType.CHROMA, VectorDBType.FAISS, VectorDBType.MEMORY]:
        if fallback_type == preferred_type:
            continue
        db = create_vector_db(fallback_type, persist_dir)
        if db.is_available:
            return db
    return InMemoryVectorDB(persist_dir)
