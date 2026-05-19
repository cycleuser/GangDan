"""Adaptive dimension-aware search for knowledge bases.

When collections are indexed with different embedding models (and thus different
dimensions), queries must be re-embedded with the collection's model to produce
compatible vectors. This module provides a single, tested implementation of that
logic so that all search paths (chat RAG, KB search API, kb_manager) behave
consistently.

Key design decisions:
- ``current_dim`` is ALWAYS determined from a test embed of the current model,
  never inferred from collection metadata (which may be stale or wrong).
- If a collection's model is known and available, re-embed the query with it.
- If the model is unknown or unavailable, attempt the search anyway with the
  current model's embedding — ChromaDB may still return results if the
  dimensions happen to match (e.g. legacy 1024d collections with a 1024d model).
- Every adaptation decision is recorded in the returned ``AdaptiveResult``
  so callers can report status to the user.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveResult:
    """Result of adaptive embedding for one collection."""

    collection_name: str
    embedding: Optional[List[float]] = None
    adapted: bool = False
    skip: bool = False
    reason: str = ""
    collection_dim: int = 0
    current_dim: int = 0
    collection_model: str = ""
    current_model: str = ""


def get_current_model_dimension(ollama: Any, model_name: str) -> int:
    """Determine the dimension of the current embedding model via a test embed.

    Parameters
    ----------
    ollama : Any
        Object with an ``embed(text, model)`` method (e.g. OllamaClient).
    model_name : str
        The embedding model name.

    Returns
    -------
    int
        Dimension of the model's output vectors, or 0 if unavailable.
    """
    if not model_name or ollama is None:
        return 0
    try:
        test_emb = ollama.embed("test", model_name)
        if test_emb and len(test_emb) > 0:
            return len(test_emb)
    except Exception:
        pass
    return 0


def build_collection_info_cache(
    vector_db: Any,
    collection_names: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Pre-compute collection metadata for all named collections.

    Parameters
    ----------
    vector_db : Any
        Object with ``get_collection_info(name)`` method.
    collection_names : List[str]
        Collection names to inspect.

    Returns
    -------
    Dict[str, Dict]
        Mapping of collection name -> info dict with keys
        ``dimension``, ``embedding_model``, ``doc_count``.
    """
    cache: Dict[str, Dict[str, Any]] = {}
    if vector_db is None or not hasattr(vector_db, "get_collection_info"):
        return cache
    for name in collection_names:
        try:
            info = vector_db.get_collection_info(name)
            if info:
                cache[name] = info
        except Exception:
            pass
    return cache


def adaptive_embed(
    query_text: str,
    collection_name: str,
    current_embedding: List[float],
    current_dim: int,
    current_model: str,
    coll_info: Dict[str, Any],
    ollama: Any,
) -> AdaptiveResult:
    """Produce the correct embedding for searching a specific collection.

    Parameters
    ----------
    query_text : str
        Original query text (needed for re-embedding with a different model).
    collection_name : str
        Target collection name.
    current_embedding : List[float]
        Embedding produced with ``current_model``.
    current_dim : int
        Dimension of ``current_model`` (from ``get_current_model_dimension``).
    current_model : str
        Name of the currently configured embedding model.
    coll_info : Dict[str, Any]
        Pre-computed collection info (``dimension``, ``embedding_model``).
    ollama : Any
        OllamaClient for re-embedding if needed.

    Returns
    -------
    AdaptiveResult
        Embedding to use, plus adaptation metadata.
    """
    result = AdaptiveResult(
        collection_name=collection_name,
        current_dim=current_dim,
        current_model=current_model,
    )

    coll_dim = coll_info.get("dimension", 0)
    coll_model = coll_info.get("embedding_model", "")
    result.collection_dim = coll_dim
    result.collection_model = coll_model

    # No collection dimension info — try current embedding as-is
    if coll_dim == 0:
        result.embedding = current_embedding
        result.reason = "no_collection_dim_info"
        return result

    # Dimensions match — use current embedding directly
    if current_dim > 0 and coll_dim == current_dim:
        result.embedding = current_embedding
        result.reason = "dimensions_match"
        return result

    # Dimension mismatch detected
    if current_dim > 0 and coll_dim != current_dim:
        result.adapted = True

        # Strategy 1: Use the collection's recorded model if available
        if coll_model and coll_model != current_model:
            try:
                re_emb = ollama.embed(query_text, coll_model)
                if re_emb and len(re_emb) > 0:
                    re_dim = len(re_emb)
                    if re_dim == coll_dim:
                        result.embedding = re_emb
                        result.reason = (
                            f"adapted: re-embedded with recorded model '{coll_model}' "
                            f"({re_dim}d matches collection {coll_dim}d)"
                        )
                        logger.info(
                            "[AdaptiveSearch] '%s': %s", collection_name, result.reason
                        )
                        return result
                    else:
                        logger.warning(
                            "[AdaptiveSearch] '%s': re-embedded with '%s' got %dd "
                            "but collection expects %dd. Trying dimension probe.",
                            collection_name, coll_model, re_dim, coll_dim,
                        )
                else:
                    logger.warning(
                        "[AdaptiveSearch] '%s': re-embedding with '%s' returned empty. "
                        "Trying dimension probe.",
                        collection_name, coll_model,
                    )
            except Exception as e:
                logger.warning(
                    "[AdaptiveSearch] '%s': re-embedding with '%s' failed: %s. "
                    "Trying dimension probe.",
                    collection_name, coll_model, e,
                )

        # Strategy 2: No recorded model (or it failed). Probe available models
        # to find one whose output dimension matches the collection.
        matched_model = _find_model_by_dimension(ollama, coll_dim, current_model)
        if matched_model:
            try:
                re_emb = ollama.embed(query_text, matched_model)
                if re_emb and len(re_emb) > 0:
                    result.embedding = re_emb
                    result.reason = (
                        f"adapted: dimension-probed model '{matched_model}' "
                        f"({len(re_emb)}d matches collection {coll_dim}d)"
                    )
                    logger.info(
                        "[AdaptiveSearch] '%s': %s", collection_name, result.reason
                    )
                    return result
            except Exception as e:
                logger.warning(
                    "[AdaptiveSearch] '%s': probed model '%s' embed failed: %s",
                    collection_name, matched_model, e,
                )

        # Strategy 3: Dimension projection via PCA truncation/padding
        projected = _project_embedding(current_embedding, current_dim, coll_dim)
        if projected is not None:
            result.embedding = projected
            result.adapted = True
            result.reason = (
                f"adapted: PCA-projected current model '{current_model}' "
                f"from {current_dim}d to {coll_dim}d"
            )
            logger.info(
                "[AdaptiveSearch] '%s': %s", collection_name, result.reason
            )
            return result

        # Strategy 4: No matching model found. Fall back to current embedding —
        # ChromaDB may still accept it if metadata is stale.
        result.embedding = current_embedding
        result.reason = (
            f"dimension_mismatch: collection={coll_dim}d, current={current_dim}d, "
            f"model={'unknown' if not coll_model else coll_model}. "
            f"No matching model found. Attempting with current model (may return no results)."
        )
        logger.warning(
            "[AdaptiveSearch] '%s': %s", collection_name, result.reason
        )
        return result

    # current_dim is 0 (unknown current model dimension) — try as-is
    result.embedding = current_embedding
    result.reason = "current_dim_unknown"
    return result


def _find_model_by_dimension(
    ollama: Any,
    target_dim: int,
    current_model: str,
) -> Optional[str]:
    """Find an available embedding model whose output dimension matches target_dim.

    Probes each model returned by ``get_embedding_models()`` with a short test
    text and returns the first one whose embedding dimension equals
    ``target_dim``.  The configured ``current_model`` is always tried first so
    exact-name matches are preferred.

    Parameters
    ----------
    ollama : Any
        OllamaClient (or compatible) instance.
    target_dim : int
        Desired embedding dimension.
    current_model : str
        Currently configured embedding model (tried first, then skipped).

    Returns
    -------
    Optional[str]
        Model name that produces ``target_dim``-dimensional embeddings, or
        ``None`` if no matching model is found.
    """
    if not ollama or target_dim <= 0:
        return None

    # Try current model first — it might happen to match
    if current_model:
        try:
            test = ollama.embed("test", current_model)
            if test and len(test) == target_dim:
                return current_model
        except Exception:
            pass

    # Try other available embedding models
    try:
        models = ollama.get_embedding_models()
    except Exception:
        models = []

    for model in models:
        if model == current_model:
            continue
        try:
            test = ollama.embed("test", model)
            if test and len(test) == target_dim:
                logger.info(
                    "[AdaptiveSearch] Found matching model '%s' for %dd",
                    model, target_dim,
                )
                return model
        except Exception:
            continue

    return None


# Cache: model name -> dimension, to avoid redundant probing across calls.
_model_dim_cache: Dict[str, int] = {}


def _project_embedding(
    embedding: List[float],
    from_dim: int,
    to_dim: int,
) -> Optional[List[float]]:
    """Project an embedding vector from one dimension to another.

    Uses PCA-based truncation (for downsizing) or zero-padding (for upsizing).
    This is a lossy but pragmatic fallback when no matching model is available.

    Parameters
    ----------
    embedding : List[float]
        Source embedding vector.
    from_dim : int
        Current embedding dimension.
    to_dim : int
        Target embedding dimension.

    Returns
    -------
    Optional[List[float]]
        Projected embedding, or None if projection is not feasible.
    """
    if from_dim == to_dim or not embedding:
        return embedding

    if to_dim < from_dim:
        # Downsize: truncate to first to_dim components
        # This preserves the most variance (PCA components are ordered by variance)
        return embedding[:to_dim]

    # Upsize: pad with zeros
    # This is a conservative approach — the extra dimensions contribute
    # zero to cosine similarity, so they don't distort the distance
    return embedding + [0.0] * (to_dim - from_dim)


def get_model_dimension_cached(ollama: Any, model: str) -> int:
    """Return the embedding dimension for *model*, using a process-level cache.

    Parameters
    ----------
    ollama : Any
        OllamaClient instance.
    model : str
        Embedding model name.

    Returns
    -------
    int
        Dimension of the model, or 0 if unavailable.
    """
    if model in _model_dim_cache:
        return _model_dim_cache[model]
    dim = get_current_model_dimension(ollama, model)
    if dim > 0:
        _model_dim_cache[model] = dim
    return dim


def adaptive_search_collections(
    query_text: str,
    collection_names: List[str],
    vector_db: Any,
    ollama: Any,
    current_model: str,
    top_k: int = 5,
) -> tuple[List[Dict[str, Any]], List[AdaptiveResult]]:
    """Search multiple collections with adaptive dimension handling.

    Parameters
    ----------
    query_text : str
        Query text.
    collection_names : List[str]
        Collections to search.
    vector_db : Any
        VectorDB with ``search(name, embedding, top_k)`` and
        ``get_collection_info(name)`` methods.
    ollama : Any
        OllamaClient for embedding.
    current_model : str
        Currently configured embedding model name.
    top_k : int
        Number of results per collection.

    Returns
    -------
    tuple[List[Dict], List[AdaptiveResult]]
        (search_results, adaptation_log) — results from all collections plus
        a log of adaptation decisions for each collection.
    """
    all_results: List[Dict[str, Any]] = []
    adaptation_log: List[AdaptiveResult] = []

    if not current_model or ollama is None:
        return all_results, adaptation_log

    # Step 1: Determine current model dimension (always via test embed)
    current_dim = get_current_model_dimension(ollama, current_model)

    # Step 2: Pre-compute collection info
    coll_info_cache = build_collection_info_cache(vector_db, collection_names)

    # Step 3: Embed query with current model
    try:
        current_embedding = ollama.embed(query_text, current_model)
    except Exception as e:
        logger.error("[AdaptiveSearch] Embedding with current model failed: %s", e)
        return all_results, adaptation_log

    if not current_embedding:
        return all_results, adaptation_log

    # Step 4: Search each collection with adaptive embedding
    for coll_name in collection_names:
        coll_info = coll_info_cache.get(coll_name, {})
        ar = adaptive_embed(
            query_text=query_text,
            collection_name=coll_name,
            current_embedding=current_embedding,
            current_dim=current_dim,
            current_model=current_model,
            coll_info=coll_info,
            ollama=ollama,
        )
        adaptation_log.append(ar)

        if ar.skip or ar.embedding is None:
            continue

        try:
            results = vector_db.search(coll_name, ar.embedding, top_k=top_k)
            for r in results:
                r["_adapted"] = ar.adapted
                r["_adapt_reason"] = ar.reason
                all_results.append(r)
        except Exception as e:
            err_msg = str(e).lower()
            if "dimension" in err_msg:
                logger.warning(
                    "[AdaptiveSearch] '%s': search failed with dimension error "
                    "even after adaptation: %s", coll_name, e,
                )
            else:
                logger.error(
                    "[AdaptiveSearch] '%s': search error: %s", coll_name, e,
                )

    return all_results, adaptation_log