"""Hybrid search: combines vector similarity and full-text search with RRF fusion.

Implements Reciprocal Rank Fusion (RRF) to merge ranked results from multiple
retrieval strategies into a single relevance-ordered list.

Reference: "Reciprocal Rank Fusion outperforms Condorcet and individual rank
learning methods" (Cormack et al., 2009, SIGIR).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from gangdan.core.chroma_manager import ChromaManager
    from gangdan.core.fts import FullTextSearch

logger = logging.getLogger(__name__)

# RRF constant: higher values give more weight to lower-ranked items.
# k=60 is the standard recommendation from Cormack et al.
RRF_K = 60


class HybridSearcher:
    """Combine vector search and full-text search via RRF.

    The searcher queries both backends independently, assigns RRF scores
    to each result based on its rank position in each list, then returns
    the top-k results sorted by fused score.

    Attributes
    ----------
    chroma : ChromaManager
        Vector database manager.
    fts : FullTextSearch or None
        Full-text search engine (can be None for vector-only fallback).
    """

    def __init__(
        self,
        chroma: ChromaManager,
        fts: Optional[FullTextSearch] = None,
    ) -> None:
        """Initialize hybrid searcher.

        Parameters
        ----------
        chroma : ChromaManager
            Vector database manager.
        fts : FullTextSearch, optional
            Full-text search engine. When None, falls back to vector-only.
        """
        self.chroma = chroma
        self.fts = fts

    def search(
        self,
        collection: str,
        query_text: str,
        query_embedding: List[float],
        top_k: int = 10,
        strategy: str = "hybrid",
    ) -> List[Dict[str, Any]]:
        """Search a collection using the specified strategy.

        Parameters
        ----------
        collection : str
            Collection name.
        query_text : str
            Original text query (for full-text search).
        query_embedding : List[float]
            Query embedding vector (for vector search).
        top_k : int
            Maximum number of results (default: 10).
        strategy : str
            Retrieval strategy:
            - "vector": vector similarity search only
            - "fts": full-text search only
            - "hybrid": RRF fusion of both (default)

        Returns
        -------
        List[Dict[str, Any]]
            Results with keys: id, document, metadata, distance, score, sources.
        """
        if strategy == "vector":
            return self._vector_search(collection, query_embedding, top_k)
        elif strategy == "fts":
            return self._fts_search(collection, query_text, top_k)
        else:
            return self._hybrid_search(
                collection, query_text, query_embedding, top_k
            )

    def _vector_search(
        self,
        collection: str,
        query_embedding: List[float],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Vector-only search."""
        results = self.chroma.search(collection, query_embedding, top_k=top_k)
        for r in results:
            r["sources"] = ["vector"]
            r["score"] = 1.0 - r.get("distance", 0.0)
        return results

    def _fts_search(
        self,
        collection: str,
        query_text: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Full-text-only search."""
        if not self.fts:
            return []
        results = self.fts.search(query_text, collection, top_k=top_k)
        for r in results:
            r["sources"] = ["fts"]
            # Normalize raw BM25/tf score to [0, 1] range approximately
            raw_score = r.get("score", 0.0)
            r["score"] = min(raw_score / max(1.0, raw_score + 1.0), 1.0)
            r["distance"] = 1.0 - r["score"]
            if "metadata" not in r:
                r["metadata"] = {}
        return results

    def _hybrid_search(
        self,
        collection: str,
        query_text: str,
        query_embedding: List[float],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """RRF fusion of vector and full-text search results.

        Uses a larger retrieval pool (top_k * 2) from each backend to
        give RRF more candidates to re-rank.
        """
        # Retrieve from both backends
        vector_results = self._vector_search(
            collection, query_embedding, top_k * 2
        )
        fts_results = self._fts_search(collection, query_text, top_k * 2)

        # If only one backend returned results, return those directly
        if not vector_results and not fts_results:
            return []
        if not vector_results:
            for r in fts_results:
                r.setdefault("sources", []).append("fts")
            return fts_results[:top_k]
        if not fts_results:
            for r in vector_results:
                r.setdefault("sources", []).append("vector")
            return vector_results[:top_k]

        # RRF scoring
        rrf_scores: Dict[str, float] = {}
        docs: Dict[str, Dict[str, Any]] = {}
        sources_map: Dict[str, List[str]] = {}

        # Score from vector results
        for rank, result in enumerate(vector_results):
            doc_id = result.get("id", "")
            if not doc_id:
                continue
            rrf = 1.0 / (RRF_K + rank + 1)
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + rrf
            docs[doc_id] = result
            sources_map.setdefault(doc_id, []).append("vector")

        # Score from FTS results
        for rank, result in enumerate(fts_results):
            doc_id = result.get("id", "")
            if not doc_id:
                continue
            rrf = 1.0 / (RRF_K + rank + 1)
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + rrf
            if doc_id not in docs:
                docs[doc_id] = result
            sources_map.setdefault(doc_id, []).append("fts")

        # Sort by RRF score descending
        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        # Build final result list
        fused: List[Dict[str, Any]] = []
        for doc_id, rrf_score in ranked:
            if doc_id not in docs:
                continue
            result = docs[doc_id]
            result["rrf_score"] = rrf_score
            result["sources"] = sources_map.get(doc_id, [])
            result["score"] = rrf_score  # unified score
            result["distance"] = 1.0 - rrf_score  # approximate distance
            fused.append(result)

        return fused[:top_k]

    def search_multi_collection(
        self,
        collections: List[str],
        query_text: str,
        query_embedding: List[float],
        top_k: int = 10,
        strategy: str = "hybrid",
    ) -> List[Dict[str, Any]]:
        """Search across multiple collections and merge results.

        Parameters
        ----------
        collections : List[str]
            List of collection names to search.
        query_text : str
            Original text query.
        query_embedding : List[float]
            Query embedding vector.
        top_k : int
            Maximum results per collection.
        strategy : str
            Retrieval strategy.

        Returns
        -------
        List[Dict[str, Any]]
            Merged and re-ranked results across all collections, capped at top_k.
        """
        all_results: List[Dict[str, Any]] = []
        seen_ids: set = set()

        for coll_name in collections:
            if not self.chroma.collection_exists(coll_name):
                continue
            results = self.search(
                coll_name, query_text, query_embedding,
                top_k=top_k, strategy=strategy,
            )
            for r in results:
                doc_id = r.get("id", "")
                if doc_id and doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    r["collection"] = coll_name
                    all_results.append(r)

        # Re-sort by score descending across collections
        all_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return all_results[:top_k]
