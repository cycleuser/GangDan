"""Storage layer for GangDan Refined.

Provides data persistence through:
- VectorDBBase: Abstraction over vector databases (ChromaDB, FAISS, InMemory)
- ChromaManager: ChromaDB client with auto-recovery
- KnowledgeBaseManager: KB CRUD, search, and indexing
- ConversationManager: Chat history with auto-save
"""

from .vector_db import (
    VectorDBBase,
    VectorDBType,
    ChromaVectorDB,
    FAISSVectorDB,
    InMemoryVectorDB,
    create_vector_db,
    create_vector_db_auto,
)
from .chroma_manager import ChromaManager
from .kb_manager import CustomKBManager, CustomKB, KBDocEntry
from .conversation import ConversationManager

__all__ = [
    "VectorDBBase",
    "VectorDBType",
    "ChromaVectorDB",
    "FAISSVectorDB",
    "InMemoryVectorDB",
    "create_vector_db",
    "create_vector_db_auto",
    "ChromaManager",
    "CustomKBManager",
    "CustomKB",
    "KBDocEntry",
    "ConversationManager",
]