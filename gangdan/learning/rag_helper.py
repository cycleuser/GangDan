"""Shared RAG retrieval helper for the learning module.

Supports both vector-only and hybrid (vector + full-text) retrieval strategies.
"""

from __future__ import annotations

import hashlib
import os as _os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from gangdan.core.ollama_client import OllamaClient
    from gangdan.core.chroma_manager import ChromaManager
    from gangdan.core.config import Config
    from gangdan.core.fts import FullTextSearch


# Module-level FTS instance for full-text search
_fts_instance: Optional[FullTextSearch] = None


def get_fts() -> Optional[FullTextSearch]:
    """Get or create the shared FullTextSearch instance.

    Returns
    -------
    FullTextSearch or None
        FTS instance, or None if no data directory is configured.
    """
    global _fts_instance
    if _fts_instance is None:
        try:
            # Try env var first (works in all contexts)
            data_dir = _os.environ.get("GANGDAN_DATA_DIR")
            if not data_dir:
                from gangdan.core.config import DATA_DIR
                data_dir = str(DATA_DIR)
            fts_path = Path(data_dir) / "fts" / "fts.db"
            from gangdan.core.fts import FullTextSearch as FTS
            _fts_instance = FTS(str(fts_path))
        except Exception as e:
            print(f"[RAG Helper] FTS init failed: {e}", file=sys.stderr)
            return None
    return _fts_instance


def retrieve_context(
    query: str,
    kb_names: List[str],
    ollama: OllamaClient,
    chroma: ChromaManager,
    config: Config,
    max_chars: int = 3000,
    top_k: int = 10,
    strategy: str = "hybrid",
) -> Tuple[str, List[str]]:
    """Retrieve relevant context from knowledge bases via RAG.

    Parameters
    ----------
    query : str
        Search query.
    kb_names : List[str]
        List of knowledge base collection names to search.
    ollama : OllamaClient
        Ollama client for embeddings.
    chroma : ChromaManager
        ChromaDB client for vector search.
    config : Config
        Application configuration.
    max_chars : int
        Maximum characters in returned context.
    top_k : int
        Number of results to retrieve per collection.
    strategy : str
        Retrieval strategy: "vector", "fts", or "hybrid" (default).

    Returns
    -------
    Tuple[str, List[str]]
        Context string and list of source filenames.
    """
    if not query or not kb_names or not ollama or not chroma:
        return "", []

    if not config.embedding_model:
        print("[RAG Helper] No embedding model configured", file=sys.stderr)
        return "", []

    try:
        query_emb = ollama.embed(query, config.embedding_model)
    except Exception as e:
        print(f"[RAG Helper] Embedding error: {e}", file=sys.stderr)
        return "", []

    collections = chroma.list_collections()
    collections = [c for c in collections if c in kb_names]

    if not collections:
        print(
            f"[RAG Helper] No matching collections for: {kb_names}",
            file=sys.stderr,
        )
        return "", []

    # Try hybrid search first if strategy is "hybrid"
    all_results: List[Dict] = []
    if strategy == "hybrid":
        try:
            from gangdan.core.hybrid_search import HybridSearcher

            fts = get_fts()
            searcher = HybridSearcher(chroma=chroma, fts=fts)
            results = searcher.search_multi_collection(
                collections=collections,
                query_text=query,
                query_embedding=query_emb,
                top_k=top_k,
                strategy="hybrid",
            )
            for r in results:
                dist = r.get("distance", 1.0)
                meta = r.get("metadata", {})
                coll = r.get("collection", "unknown")
                doc_id = r.get("id", hashlib.md5(r["document"][:100].encode()).hexdigest())
                all_results.append({
                    "coll": coll,
                    "doc": r["document"],
                    "dist": dist,
                    "id": doc_id,
                    "file": meta.get("file", "unknown"),
                    "source": meta.get("source", coll),
                    "sources": r.get("sources", ["hybrid"]),
                })
            print(
                f"[RAG Helper] Hybrid search returned {len(results)} results "
                f"(strategy=hybrid)",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"[RAG Helper] Hybrid search error: {e}, falling back to vector", file=sys.stderr)
            strategy = "vector"  # fallback

    # Vector search fallback
    if strategy != "hybrid" or not all_results:
        # Adaptive distance threshold based on embedding model
        embedding_model = getattr(config, 'embedding_model', '') or ''
        is_large_model = any(m in embedding_model.lower() for m in ['text-embedding', 'embedding-3', 'e5-large', 'bge-large'])
        distance_threshold = 2.0 if is_large_model else 1.5

        for coll_name in collections:
            try:
                results = chroma.search(coll_name, query_emb, top_k=top_k)
                for r in results:
                    dist = r.get("distance", 1)
                    meta = r.get("metadata", {})
                    all_results.append(
                        {
                            "coll": coll_name,
                            "doc": r["document"],
                            "dist": dist,
                            "id": r.get(
                                "id",
                                hashlib.md5(r["document"][:100].encode()).hexdigest(),
                            ),
                            "file": meta.get("file", "unknown"),
                            "source": meta.get("source", coll_name),
                        }
                    )
            except Exception as e:
                print(
                    f"[RAG Helper] Search error in '{coll_name}': {e}",
                    file=sys.stderr,
                )

    # Fallback: if vector search returns nothing (dimension mismatch etc),
    # fetch documents directly from collections
    if not all_results:
        print("[RAG Helper] Vector search returned 0 results, trying direct document fetch", file=sys.stderr)
        for coll_name in collections:
            try:
                docs_data = chroma.get_documents(coll_name, limit=top_k, include=["documents", "metadatas", "ids"])
                if docs_data and docs_data.get("documents"):
                    for i in range(len(docs_data["documents"])):
                        meta = docs_data["metadatas"][i] if docs_data.get("metadatas") and i < len(docs_data.get("metadatas", [])) else {}
                        doc_id = docs_data.get("ids", [f"doc_{i}" for _ in range(len(docs_data["documents"]))])[i] if docs_data.get("ids") and i < len(docs_data.get("ids", [])) else f"doc_{i}"
                        all_results.append({
                            "coll": coll_name,
                            "doc": docs_data["documents"][i],
                            "dist": 2.0,
                            "id": doc_id,
                            "file": meta.get("file", "unknown"),
                            "source": meta.get("source", coll_name),
                        })
            except Exception as e:
                print(f"[RAG Helper] Direct fetch error in '{coll_name}': {e}", file=sys.stderr)

    # Adaptive distance threshold based on embedding model
    embedding_model = getattr(config, 'embedding_model', '') or ''
    is_large_model = any(m in embedding_model.lower() for m in ['text-embedding', 'embedding-3', 'e5-large', 'bge-large'])
    distance_threshold = 2.0 if is_large_model else 1.5

    # First pass: use strict threshold
    filtered = [r for r in all_results if r["dist"] < distance_threshold]

    # Fallback: if strict threshold yields too few, relax to include top-k by distance
    if len(filtered) < 3:
        all_results_sorted = sorted(all_results, key=lambda x: x["dist"])
        relaxed_threshold = min(all_results_sorted[0]["dist"] + 1.0, 3.0) if all_results_sorted else distance_threshold
        filtered = [r for r in all_results if r["dist"] < relaxed_threshold]
        if len(filtered) < len(all_results_sorted):
            filtered = all_results_sorted[:max(top_k, 5)]
        print(
            f"[RAG Helper] Relaxed threshold from {distance_threshold:.2f} to {relaxed_threshold:.2f}, "
            f"results: {len(filtered)}",
            file=sys.stderr,
        )

    seen: Dict[str, Dict] = {}
    for r in filtered:
        if r["id"] not in seen or r["dist"] < seen[r["id"]]["dist"]:
            seen[r["id"]] = r

    merged = sorted(seen.values(), key=lambda x: x["dist"])

    context = ""
    sources_used = set()
    for r in merged:
        snippet = f"\n[Source: {r['file']}]\n{r['doc'][:500]}\n"
        if len(context) + len(snippet) > max_chars:
            break
        context += snippet
        sources_used.add(r["file"])

    sources = sorted(list(sources_used))
    print(
        f"[RAG Helper] Found {len(merged)} results, using {len(sources)} sources",
        file=sys.stderr,
    )
    return context, sources


def collect_kb_documents(
    kb_names: List[str],
    docs_dir: Path,
    max_total_chars: int = 8000,
) -> str:
    """Read raw document files from KB directories.

    Parameters
    ----------
    kb_names : List[str]
        List of knowledge base names.
    docs_dir : Path
        Base directory containing KB subdirectories.
    max_total_chars : int
        Maximum total characters to return.

    Returns
    -------
    str
        Concatenated and truncated document content.
    """
    all_text = ""

    for kb_name in kb_names:
        kb_dir = docs_dir / kb_name
        if not kb_dir.exists():
            continue

        for filepath in list(kb_dir.glob("*.md")) + list(kb_dir.glob("*.txt")):
            try:
                content = filepath.read_text(encoding="utf-8")
                header = f"\n--- {filepath.name} ---\n"
                snippet = content[:2000]

                remaining = max_total_chars - len(all_text) - len(header)
                if remaining <= 0:
                    all_text += header + snippet[: max(0, remaining)]
                    break

                all_text += header + snippet
            except (OSError, UnicodeDecodeError):
                continue

    return all_text


def compress_rag_notes(
    context: str,
    query: str,
    ollama: OllamaClient,
    config: Config,
    max_output_chars: int = 800,
) -> str:
    """Compress raw RAG context into focused notes.

    Applies the DeepTutor NoteAgent pattern: compress RAG results into
    concise summaries retaining only query-relevant information.

    Parameters
    ----------
    context : str
        Raw RAG context string with source attributions.
    query : str
        The query/topic to focus notes on.
    ollama : OllamaClient
        Ollama client for LLM calls.
    config : Config
        Application configuration.
    max_output_chars : int
        Maximum output length.

    Returns
    -------
    str
        Compressed notes string, or original context if compression fails.
    """
    if not context or not context.strip():
        return context

    if len(context) < 500:
        return context

    from gangdan.learning.prompts import get_prompt
    from gangdan.learning.utils import llm_call_with_retry

    lang = config.language if config.language in ("zh", "en") else "en"
    prompt_template = get_prompt("rag_compress", lang)
    prompt = prompt_template.format(query=query, context=context[:3000])

    messages = [{"role": "user", "content": prompt}]
    result = llm_call_with_retry(
        ollama,
        config,
        messages,
        temperature=0.3,
        max_retries=1,
        parse_json_response=False,
        label="rag_compress",
    )

    if result and len(result.strip()) > 50:
        return result[:max_output_chars]

    return context[:max_output_chars]


def check_kb_sufficiency(
    topic: str,
    kb_names: List[str],
    ollama: OllamaClient,
    chroma: ChromaManager,
    config: Config,
) -> Dict[str, "Any"]:
    """Check if the knowledge bases have enough content for research.

    Parameters
    ----------
    topic : str
        Research topic to test against.
    kb_names : List[str]
        Knowledge base names to check.
    ollama : OllamaClient
        Ollama client for embeddings.
    chroma : ChromaManager
        ChromaDB client.
    config : Config
        Application configuration.

    Returns
    -------
    Dict[str, Any]
        Dictionary with keys:
        - sufficient (bool): Whether KB has enough content
        - total_docs (int): Total document count across KBs
        - total_chars (int): Total character count
        - relevant_results (int): Number of relevant search results
        - kb_details (list): Per-KB details
        - suggestion (str): User-friendly suggestion
    """
    from typing import Any as AnyType

    if not kb_names:
        return {
            "sufficient": False,
            "total_docs": 0,
            "total_chars": 0,
            "relevant_results": 0,
            "kb_details": [],
            "suggestion": "no_kb_selected",
        }

    kb_details = []
    total_docs = 0
    total_chars = 0

    collections = chroma.list_collections()
    matching = [c for c in collections if c in kb_names]

    for coll_name in matching:
        try:
            coll_info = chroma.get_collection_info(coll_name)
            doc_count = coll_info.get("count", 0) if isinstance(coll_info, dict) else 0
            total_docs += doc_count
            kb_details.append({
                "name": coll_name,
                "doc_count": doc_count,
            })
        except Exception:
            try:
                count = chroma.count(coll_name)
                total_docs += count
                kb_details.append({"name": coll_name, "doc_count": count})
            except Exception:
                kb_details.append({"name": coll_name, "doc_count": 0})

    # Try a probe search to see how many relevant results we get
    relevant_results = 0
    if topic and ollama and config.embedding_model:
        try:
            query_emb = ollama.embed(topic, config.embedding_model)
            embedding_model = getattr(config, 'embedding_model', '') or ''
            is_large_model = any(m in embedding_model.lower() for m in ['text-embedding', 'embedding-3', 'e5-large', 'bge-large'])
            distance_threshold = 3.0  # More lenient: get more results

            for coll_name in matching:
                try:
                    results = chroma.search(coll_name, query_emb, top_k=5)
                    for r in results:
                        if r.get("distance", 1) < distance_threshold:
                            relevant_results += 1
                            total_chars += len(r.get("document", ""))
                except Exception:
                    pass
        except Exception:
            pass

    # Determine sufficiency
    sufficient = True
    suggestion = ""

    if total_docs == 0:
        sufficient = False
        suggestion = "kb_empty"
    elif total_docs < 3:
        sufficient = False
        suggestion = "kb_too_small"
    elif relevant_results == 0 and total_chars == 0:
        sufficient = False
        suggestion = "kb_not_relevant"
    elif relevant_results < 2 and total_chars < 500:
        sufficient = False
        suggestion = "kb_limited_relevance"
    elif relevant_results < 3:
        sufficient = False
        suggestion = "kb_marginal"

    return {
        "sufficient": sufficient,
        "total_docs": total_docs,
        "total_chars": total_chars,
        "relevant_results": relevant_results,
        "kb_details": kb_details,
        "suggestion": suggestion,
    }
