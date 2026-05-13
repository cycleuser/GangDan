"""Custom knowledge base API routes.

Provides RESTful endpoints for:
- Create/list/update/delete custom KBs
- Add/remove documents to/from KBs
- Search within and across KBs
- Export KB content
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request, send_file

from gangdan.core.config import DATA_DIR
from gangdan.core.doc_manager import DOC_SOURCES

logger = logging.getLogger(__name__)

kb_bp = Blueprint("custom_kb", __name__, url_prefix="/api/kb")

_kb_manager = None


def _resolve_kb_name(internal_name: str) -> Optional[Dict[str, Any]]:
    """Resolve a KB name to its metadata, supporting both custom and built-in KBs.

    Parameters
    ----------
    internal_name : str
        KB internal name (e.g., "numpy", "user_mykb").

    Returns
    -------
    Dict or None
        KB metadata dict with at least 'internal_name' and 'display_name',
        or None if the KB does not exist.
    """
    # Check custom KBs first
    manager = get_kb_manager()
    kb = manager.get_kb(internal_name)
    if kb is not None:
        return {"internal_name": kb.internal_name, "display_name": kb.display_name, "type": "custom"}

    # Check built-in DOC_SOURCES
    if internal_name in DOC_SOURCES:
        return {"internal_name": internal_name, "display_name": DOC_SOURCES[internal_name]["name"], "type": "builtin"}

    # Check user KBs manifest
    from gangdan.core.config import CONFIG, load_user_kbs

    user_kbs = load_user_kbs()
    if internal_name in user_kbs:
        return {"internal_name": internal_name, "display_name": user_kbs[internal_name].get("display_name", internal_name), "type": "user"}

    # Check if ChromaDB collection exists for this name
    try:
        from gangdan.app import CHROMA
        if CHROMA and CHROMA.is_available and CHROMA.collection_exists(internal_name):
            return {"internal_name": internal_name, "display_name": internal_name, "type": "collection"}
    except Exception:
        pass

    return None


def get_kb_manager():
    """Get or create the CustomKBManager singleton."""
    global _kb_manager
    if _kb_manager is None:
        from gangdan.core.kb_manager import CustomKBManager

        _kb_manager = CustomKBManager()
    return _kb_manager


# =============================================================================
# KB CRUD
# =============================================================================


@kb_bp.route("/create", methods=["POST"])
def create_kb() -> Any:
    """Create a new custom knowledge base.

    Body: {"display_name": "...", "description": "...", "tags": ["..."]}
    """
    data = request.json or {}
    display_name = data.get("display_name", "")
    if not display_name:
        return jsonify({"error": "display_name is required"}), 400

    description = data.get("description", "")
    tags = data.get("tags", [])

    manager = get_kb_manager()
    kb = manager.create_kb(display_name, description, tags)

    return jsonify({"success": True, "kb": kb.to_dict()})


@kb_bp.route("/list", methods=["GET"])
def list_kbs() -> Any:
    """List all knowledge bases (built-in DOC_SOURCES + custom + other ChromaDB collections)."""
    from gangdan.app import CHROMA, OLLAMA
    from gangdan.core.config import CONFIG, load_user_kbs
    from gangdan.core.doc_manager import DOC_SOURCES

    stats = {}
    if CHROMA and CHROMA.is_available:
        try:
            stats = CHROMA.get_stats()
        except Exception:
            pass

    def get_collection_languages(coll_name: str) -> List[str]:
        if not CHROMA or not CHROMA.is_available:
            return []
        try:
            sample = CHROMA.get_documents(coll_name, limit=50, include=["metadatas"])
            langs = set()
            for meta in sample.get("metadatas", []):
                if meta and meta.get("language"):
                    langs.add(meta["language"])
            langs.discard("unknown")
            return sorted(list(langs))
        except Exception:
            return []

    user_kbs = load_user_kbs()
    result = []

    for key in DOC_SOURCES:
        if key in stats:
            result.append({
                "name": key,
                "display_name": DOC_SOURCES[key]["name"],
                "type": "builtin",
                "doc_count": stats.get(key, 0),
                "languages": get_collection_languages(key),
            })

    for internal_name, meta in user_kbs.items():
        result.append({
            "name": internal_name,
            "display_name": meta.get("display_name", internal_name),
            "type": "user",
            "doc_count": stats.get(internal_name, 0),
            "languages": meta.get("languages", []) or get_collection_languages(internal_name),
        })

    known = set(DOC_SOURCES.keys()) | set(user_kbs.keys())
    for coll_name in stats:
        if coll_name not in known:
            result.append({
                "name": coll_name,
                "display_name": coll_name,
                "type": "other",
                "doc_count": stats.get(coll_name, 0),
                "languages": get_collection_languages(coll_name),
            })

    current_embed_dim = 0
    if CONFIG.embedding_model and OLLAMA and stats:
        try:
            test_emb = OLLAMA.embed("test", CONFIG.embedding_model)
            if test_emb:
                current_embed_dim = len(test_emb)
        except Exception:
            pass

    if CHROMA and hasattr(CHROMA, "get_collection_info"):
        for kb_entry in result:
            coll_name = kb_entry["name"]
            try:
                coll_info = CHROMA.get_collection_info(coll_name)
            except Exception:
                coll_info = {}
            coll_model = coll_info.get("embedding_model", "")
            coll_dim = coll_info.get("dimension", 0)
            if coll_model:
                kb_entry["embedding_model"] = coll_model
            if coll_dim:
                kb_entry["embedding_dimension"] = coll_dim
            if current_embed_dim > 0 and coll_dim > 0 and coll_dim != current_embed_dim:
                kb_entry["dimension_mismatch"] = {
                    "collection_dim": coll_dim,
                    "expected_dim": current_embed_dim,
                    "current_model": CONFIG.embedding_model,
                    "collection_model": coll_model,
                }

    return jsonify({"kbs": result, "total": len(result)})


@kb_bp.route("/<internal_name>", methods=["GET"])
def get_kb(internal_name: str) -> Any:
    """Get a KB by internal name."""
    manager = get_kb_manager()
    kb = manager.get_kb(internal_name)
    if kb is None:
        return jsonify({"error": "KB not found"}), 404
    return jsonify({"kb": kb.to_dict()})


@kb_bp.route("/<internal_name>", methods=["PUT"])
def update_kb(internal_name: str) -> Any:
    """Update KB metadata.

    Body: {"display_name": "...", "description": "...", "tags": [...]}
    """
    data = request.json or {}
    manager = get_kb_manager()

    kb = manager.update_kb(
        internal_name,
        display_name=data.get("display_name"),
        description=data.get("description"),
        tags=data.get("tags"),
    )

    if kb is None:
        return jsonify({"error": "KB not found"}), 404

    return jsonify({"success": True, "kb": kb.to_dict()})


@kb_bp.route("/<internal_name>", methods=["DELETE"])
def delete_kb(internal_name: str) -> Any:
    """Delete a KB.

    Query: ?delete_files=true
    """
    delete_files = request.args.get("delete_files", "false").lower() == "true"
    manager = get_kb_manager()

    success = manager.delete_kb(internal_name, delete_files=delete_files)
    if not success:
        return jsonify({"error": "KB not found"}), 404

    return jsonify({"success": True, "message": f"Deleted KB '{internal_name}'"})


# =============================================================================
# Document Management
# =============================================================================


@kb_bp.route("/<internal_name>/documents", methods=["GET"])
def list_documents(internal_name: str) -> Any:
    """List all documents in a KB."""
    # Check user KBs first
    manager = get_kb_manager()
    kb = manager.get_kb(internal_name)
    
    # If not a user KB, check builtin KBs
    if kb is None:
        from gangdan.core.doc_manager import DOC_SOURCES
        if internal_name in DOC_SOURCES:
            # Return builtin KB documents (simplified list)
            source_info = DOC_SOURCES[internal_name]
            docs = source_info.get("docs", [])
            return jsonify({"documents": [d.to_dict() for d in docs], "total": len(docs)})
        logger.warning("[KB-API] KB not found: %s", internal_name)
        return jsonify({"error": "KB not found"}), 404

    docs = manager.get_documents(internal_name)
    logger.info("[KB-API] List documents for '%s': %d docs", internal_name, len(docs))
    return jsonify({"documents": [d.to_dict() for d in docs], "total": len(docs)})


@kb_bp.route("/<internal_name>/documents", methods=["POST"])
def add_document(internal_name: str) -> Any:
    """Add a document to a KB.

    Body: {
        "doc_id": "...",
        "title": "...",
        "source_type": "preprint|paper|markdown",
        "source_id": "...",
        "source_platform": "...",
        "markdown_path": "...",
        "content_preview": "...",
        "authors": [...],
        "published_date": "...",
        "url": "...",
        "tags": [...],
        "index_to_chroma": true
    }
    """
    data = request.json or {}
    doc_id = data.get("doc_id", "")
    title = data.get("title", "")

    if not doc_id or not title:
        return jsonify({"error": "doc_id and title are required"}), 400

    manager = get_kb_manager()
    kb = manager.get_kb(internal_name)
    if kb is None:
        return jsonify({"error": "KB not found"}), 404

    from gangdan.core.kb_manager import KBDocEntry
    from datetime import datetime

    doc = KBDocEntry(
        doc_id=doc_id,
        title=title,
        source_type=data.get("source_type", ""),
        source_id=data.get("source_id", ""),
        source_platform=data.get("source_platform", ""),
        markdown_path=data.get("markdown_path", ""),
        content_preview=data.get("content_preview", ""),
        authors=data.get("authors", []),
        published_date=data.get("published_date", ""),
        url=data.get("url", ""),
        tags=data.get("tags", []),
        added_at=datetime.now().isoformat(),
    )

    index_to_chroma = data.get("index_to_chroma", True)
    success = manager.add_document(internal_name, doc, index_to_chroma=index_to_chroma)

    if not success:
        return jsonify({"error": "Failed to add document"}), 500

    return jsonify({"success": True, "document": doc.to_dict()})


@kb_bp.route("/<internal_name>/documents/<doc_id>", methods=["DELETE"])
def remove_document(internal_name: str, doc_id: str) -> Any:
    """Remove a document from a KB."""
    manager = get_kb_manager()
    success = manager.remove_document(internal_name, doc_id)

    if not success:
        return jsonify({"error": "Document not found"}), 404

    return jsonify({"success": True, "message": f"Removed document '{doc_id}'"})


# =============================================================================
# Search
# =============================================================================


@kb_bp.route("/<internal_name>/search", methods=["POST"])
def search_kb(internal_name: str) -> Any:
    """Search within a specific KB with adaptive dimension handling.

    Body: {"query": "...", "limit": 20}
    """
    data = request.json or {}
    query = data.get("query", "")
    if not query:
        return jsonify({"error": "query is required"}), 400

    limit = data.get("limit", 20)

    manager = get_kb_manager()
    kb = manager.get_kb(internal_name)
    if kb is None:
        return jsonify({"error": "KB not found"}), 404

    results = manager.search_kb(internal_name, query, limit)

    adaptation_info = _get_adaptation_info(internal_name)
    response = {"results": results, "total": len(results)}
    if adaptation_info:
        response["dimension_info"] = adaptation_info
    return jsonify(response)


@kb_bp.route("/search", methods=["POST"])
def search_all_kbs() -> Any:
    """Search across multiple or all KBs with adaptive dimension handling.

    Body: {"query": "...", "kb_names": ["..."], "limit": 20}
    """
    data = request.json or {}
    query = data.get("query", "")
    if not query:
        return jsonify({"error": "query is required"}), 400

    kb_names = data.get("kb_names", None)
    limit = data.get("limit", 20)

    manager = get_kb_manager()
    results = manager.search_all_kbs(query, kb_names=kb_names, limit=limit)

    adaptation_info = {}
    target_kbs = kb_names or list(manager._manifest.keys()) if hasattr(manager, '_manifest') else []
    for kb_name in target_kbs:
        info = _get_adaptation_info(kb_name)
        if info:
            adaptation_info[kb_name] = info

    response = {"results": results, "total": len(results)}
    if adaptation_info:
        response["dimension_info"] = adaptation_info
    return jsonify(response)


def _get_adaptation_info(collection_name: str) -> Dict[str, Any]:
    """Get dimension adaptation info for a collection."""
    from gangdan.app import CHROMA
    from gangdan.core.config import CONFIG

    if not CHROMA or not hasattr(CHROMA, "get_collection_info"):
        return {}

    try:
        coll_info = CHROMA.get_collection_info(collection_name)
    except Exception:
        return {}

    if not coll_info:
        return {}

    coll_model = coll_info.get("embedding_model", "")
    coll_dim = coll_info.get("dimension", 0)
    if not coll_dim and not coll_model:
        return {}

    current_model = CONFIG.embedding_model
    return {
        "collection_model": coll_model,
        "collection_dimension": coll_dim,
        "current_model": current_model,
        "may_adapt": bool(coll_model and coll_model != current_model),
    }


# =============================================================================
# Export
# =============================================================================


@kb_bp.route("/<internal_name>/export", methods=["POST"])
def export_kb(internal_name: str) -> Any:
    """Export KB Markdown files to ZIP.

    Body: {"kb_name": "..."} (optional, defaults to internal_name)
    """
    data = request.json or {}
    kb_name = data.get("kb_name", internal_name)

    manager = get_kb_manager()
    kb = manager.get_kb(internal_name)
    if kb is None:
        return jsonify({"error": "KB not found"}), 404

    exported_paths = manager.export_kb_to_zip(internal_name)

    if not exported_paths:
        return jsonify({"error": "No documents to export"}), 404

    return jsonify({
        "success": True,
        "exported_files": exported_paths,
        "count": len(exported_paths),
    })


@kb_bp.route("/<internal_name>/download", methods=["GET"])
def download_kb_zip(internal_name: str) -> Any:
    """Download KB as ZIP file.

    Query: ?kb_name=...
    """
    kb_name = request.args.get("kb_name", internal_name)

    manager = get_kb_manager()
    kb = manager.get_kb(internal_name)
    if kb is None:
        return jsonify({"error": "KB not found"}), 404

    exported_paths = manager.export_kb_to_zip(internal_name)

    if not exported_paths:
        return jsonify({"error": "No documents to export"}), 404

    zip_path = manager.export_kb_to_zip(internal_name)
    if zip_path and Path(zip_path).exists():
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=f"{kb_name}.zip",
        )

    return jsonify({"error": "Failed to create ZIP"}), 500


# =============================================================================
# Batch Add Documents
# =============================================================================


@kb_bp.route("/<internal_name>/batch-add", methods=["POST"])
def batch_add_documents(internal_name: str) -> Any:
    """Batch add documents to a KB.

    Body: {
        "documents": [
            {
                "doc_id": "...",
                "title": "...",
                "source_type": "...",
                "markdown_path": "...",
                ...
            },
            ...
        ],
        "index_to_chroma": true
    }
    """
    data = request.json or {}
    documents = data.get("documents", [])

    if not documents:
        return jsonify({"error": "documents array is required"}), 400

    manager = get_kb_manager()
    kb = manager.get_kb(internal_name)
    if kb is None:
        return jsonify({"error": "KB not found"}), 404

    from gangdan.core.kb_manager import KBDocEntry
    from datetime import datetime

    index_to_chroma = data.get("index_to_chroma", True)
    added = 0
    failed = 0
    errors = []

    for doc_data in documents:
        doc_id = doc_data.get("doc_id", "")
        title = doc_data.get("title", "")

        if not doc_id or not title:
            failed += 1
            errors.append(f"Missing doc_id or title for item")
            continue

        doc = KBDocEntry(
            doc_id=doc_id,
            title=title,
            source_type=doc_data.get("source_type", ""),
            source_id=doc_data.get("source_id", ""),
            source_platform=doc_data.get("source_platform", ""),
            markdown_path=doc_data.get("markdown_path", ""),
            content_preview=doc_data.get("content_preview", ""),
            authors=doc_data.get("authors", []),
            published_date=doc_data.get("published_date", ""),
            url=doc_data.get("url", ""),
            tags=doc_data.get("tags", []),
            added_at=datetime.now().isoformat(),
        )

        if manager.add_document(internal_name, doc, index_to_chroma=index_to_chroma):
            added += 1
        else:
            failed += 1
            errors.append(f"Failed to add '{doc_id}'")

    return jsonify({
        "success": True,
        "added": added,
        "failed": failed,
        "errors": errors[:10],
    })


# =============================================================================
# Analytics & Strict Citation
# =============================================================================

_analytics = None


def get_analytics():
    """Get or create the KBAnalytics singleton."""
    global _analytics
    if _analytics is None:
        from gangdan.core.kb_analytics import KBAnalytics
        from gangdan.app import OLLAMA

        manager = get_kb_manager()
        _analytics = KBAnalytics(kb_manager=manager, ollama_client=OLLAMA)
    return _analytics


@kb_bp.route("/<internal_name>/analytics/topics", methods=["POST"])
def get_topic_clusters(internal_name: str) -> Any:
    """Get topic clusters for a KB.

    Body: {"n_clusters": 5, "method": "kmeans", "doc_ids": ["doc1", "doc2"]}
    """
    kb_info = _resolve_kb_name(internal_name)
    if kb_info is None:
        return jsonify({"error": "KB not found"}), 404

    data = request.json or {}
    n_clusters = data.get("n_clusters", None)
    method = data.get("method", "kmeans")
    doc_ids = data.get("doc_ids", None)

    analytics = get_analytics()
    clusters = analytics.get_topic_clusters(internal_name, n_clusters=n_clusters, method=method, doc_ids=doc_ids)

    return jsonify({
        "kb_name": internal_name,
        "kb_display": kb_info["display_name"],
        "clusters": [c.to_dict() for c in clusters],
        "total_clusters": len(clusters),
    })


@kb_bp.route("/<internal_name>/analytics/point-cloud", methods=["POST"])
def get_point_cloud(internal_name: str) -> Any:
    """Get point cloud data for KB visualization.

    Body: {"dimensions": 2, "method": "pca", "include_clusters": true, "doc_ids": ["doc1"]}
    """
    kb_info = _resolve_kb_name(internal_name)
    if kb_info is None:
        return jsonify({"error": "KB not found"}), 404

    data = request.json or {}
    dimensions = data.get("dimensions", 2)
    method = data.get("method", "pca")
    include_clusters = data.get("include_clusters", False)
    doc_ids = data.get("doc_ids", None)

    analytics = get_analytics()
    cluster_labels = None

    if include_clusters:
        clusters = analytics.get_topic_clusters(internal_name, doc_ids=doc_ids)
        label_map = {}
        for c in clusters:
            for did in c.doc_ids:
                label_map[did] = c.cluster_id
        cluster_labels = [label_map.get(did, 0) for did in analytics._get_embeddings_for_kb(internal_name, doc_ids_filter=doc_ids)[0]]

    cloud = analytics.get_point_cloud(
        internal_name,
        dimensions=dimensions,
        method=method,
        cluster_labels=cluster_labels,
        doc_ids=doc_ids,
    )

    return jsonify({
        "kb_name": internal_name,
        "kb_display": kb_info["display_name"],
        "point_cloud": cloud.to_dict(),
    })


@kb_bp.route("/<internal_name>/analytics/opinions", methods=["POST"])
def get_opinion_clusters(internal_name: str) -> Any:
    """Get opinion clusters for a KB.

    Body: {"topic": "...", "max_clusters": 5, "use_llm": true, "doc_ids": ["doc1"]}
    """
    kb_info = _resolve_kb_name(internal_name)
    if kb_info is None:
        return jsonify({"error": "KB not found"}), 404

    data = request.json or {}
    topic = data.get("topic", "")
    max_clusters = data.get("max_clusters", 5)
    use_llm = data.get("use_llm", True)
    doc_ids = data.get("doc_ids", None)

    analytics = get_analytics()
    clusters = analytics.get_opinion_clusters(
        internal_name,
        topic=topic,
        max_clusters=max_clusters,
        use_llm=use_llm,
        doc_ids=doc_ids,
    )

    return jsonify({
        "kb_name": internal_name,
        "kb_display": kb_info["display_name"],
        "topic": topic,
        "opinion_clusters": [c.to_dict() for c in clusters],
        "total_clusters": len(clusters),
    })


@kb_bp.route("/<internal_name>/analytics/review", methods=["POST"])
def generate_review(internal_name: str) -> Any:
    """Generate a literature review from selected documents.

    Body: {
        "doc_ids": ["doc1", "doc2"],
        "topic": "AI Safety",
        "style": "academic",
        "language": "zh"
    }
    """
    kb_info = _resolve_kb_name(internal_name)
    if kb_info is None:
        return jsonify({"error": "KB not found"}), 404

    data = request.json or {}
    doc_ids = data.get("doc_ids", [])

    if not doc_ids:
        return jsonify({"error": "doc_ids is required"}), 400

    topic = data.get("topic", "")
    style = data.get("style", "academic")
    language = data.get("language", "")
    mode = data.get("mode", "review")

    analytics = get_analytics()
    result = analytics.generate_review(
        kb_name=internal_name,
        doc_ids=doc_ids,
        topic=topic,
        style=style,
        language=language,
        mode=mode,
    )

    return jsonify(result)


@kb_bp.route("/<internal_name>/analytics/cite", methods=["POST"])
def generate_cited_response(internal_name: str) -> Any:
    """Generate a response that strictly cites specified articles.

    Body: {
        "query": "...",
        "required_doc_ids": ["doc1", "doc2"],
        "additional_context": "..."
    }
    """
    kb_info = _resolve_kb_name(internal_name)
    if kb_info is None:
        return jsonify({"error": "KB not found"}), 404

    data = request.json or {}
    query = data.get("query", "")
    required_doc_ids = data.get("required_doc_ids", [])

    if not query:
        return jsonify({"error": "query is required"}), 400
    if not required_doc_ids:
        return jsonify({"error": "required_doc_ids is required"}), 400

    additional_context = data.get("additional_context", "")

    analytics = get_analytics()
    result = analytics.generate_cited_response(
        query=query,
        required_doc_ids=required_doc_ids,
        kb_name=internal_name,
        additional_context=additional_context,
    )

    return jsonify(result)


@kb_bp.route("/<internal_name>/documents/<doc_id>/content", methods=["GET"])
def get_document_content(internal_name: str, doc_id: str) -> Any:
    """Get full content of a specific document.

    Query: ?max_length=5000
    """
    kb_info = _resolve_kb_name(internal_name)
    if kb_info is None:
        return jsonify({"error": "KB not found"}), 404

    max_length = request.args.get("max_length", 5000, type=int)

    analytics = get_analytics()
    content = analytics.get_document_content(internal_name, doc_id, max_length=max_length)

    if content is None:
        return jsonify({"error": "Document not found"}), 404

    return jsonify(content)


# =============================================================================
# Dimension Management & Compatibility
# =============================================================================


@kb_bp.route("/<internal_name>/dimension-info", methods=["GET"])
def get_dimension_info(internal_name: str) -> Any:
    """Get embedding dimension info for a KB.

    Returns embedding model, dimension, doc count, and compatibility with current model.
    """
    manager = get_kb_manager()
    kb = manager.get_kb(internal_name)
    if kb is None:
        return jsonify({"error": "KB not found"}), 404

    info = manager.get_collection_embedding_info(internal_name)
    return jsonify({
        "kb_name": internal_name,
        "kb_display": kb.display_name,
        **info,
    })


@kb_bp.route("/dimension-matrix", methods=["GET"])
def get_dimension_matrix() -> Any:
    """Get dimension compatibility matrix for all KBs.

    Shows each KB's embedding model, dimension, and whether it's compatible
    with the current embedding model.
    """
    from gangdan.core.config import CONFIG, load_user_kbs
    from gangdan.core.doc_manager import DOC_SOURCES
    from gangdan.app import CHROMA

    manager = get_kb_manager()
    user_kbs = load_user_kbs()

    all_kbs = []
    for kb_name in list(user_kbs.keys()):
        info = manager.get_collection_embedding_info(kb_name)
        all_kbs.append({
            "name": kb_name,
            "display_name": user_kbs.get(kb_name, {}).get("display_name", kb_name),
            "type": "user",
            **info,
        })

    for kb_name in DOC_SOURCES:
        if CHROMA and CHROMA.is_available:
            try:
                coll_info = CHROMA.get_collection_info(kb_name)
                all_kbs.append({
                    "name": kb_name,
                    "display_name": DOC_SOURCES[kb_name]["name"],
                    "type": "builtin",
                    "embedding_model": coll_info.get("embedding_model", ""),
                    "dimension": coll_info.get("dimension", 0),
                    "doc_count": coll_info.get("doc_count", 0),
                    "status": "indexed" if coll_info.get("doc_count", 0) > 0 else "empty",
                    "current_model": CONFIG.embedding_model or "",
                    "compatible": False,
                })
            except Exception:
                pass

    current_dim = 0
    if CONFIG.embedding_model:
        from gangdan.core.ollama_client import OllamaClient
        try:
            test_emb = OllamaClient().embed("test", CONFIG.embedding_model)
            if test_emb:
                current_dim = len(test_emb)
        except Exception:
            pass

    return jsonify({
        "current_model": CONFIG.embedding_model or "",
        "current_dimension": current_dim,
        "knowledge_bases": all_kbs,
        "total": len(all_kbs),
        "compatible_count": sum(1 for kb in all_kbs if kb.get("compatible")),
        "incompatible_count": sum(
            1 for kb in all_kbs
            if kb.get("dimension", 0) > 0 and not kb.get("compatible")
        ),
    })


@kb_bp.route("/<internal_name>/reindex", methods=["POST"])
def reindex_kb(internal_name: str) -> Any:
    """Re-index a KB with a different embedding model.

    Body: {"model": "nomic-embed-text"} (optional, defaults to current model)
    """
    manager = get_kb_manager()
    kb = manager.get_kb(internal_name)
    if kb is None:
        return jsonify({"error": "KB not found"}), 404

    data = request.json or {}
    new_model = data.get("model", None)

    result = manager.reindex_kb(internal_name, new_model=new_model)

    if result.get("success"):
        return jsonify({"success": True, **result})
    return jsonify({"success": False, **result}), 500
