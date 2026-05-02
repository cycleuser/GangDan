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

logger = logging.getLogger(__name__)

kb_bp = Blueprint("custom_kb", __name__, url_prefix="/api/kb")

_kb_manager = None


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
    from gangdan.app import CHROMA
    from gangdan.core.doc_manager import DOC_SOURCES
    from gangdan.core.config import load_user_kbs

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
    manager = get_kb_manager()
    kb = manager.get_kb(internal_name)
    if kb is None:
        return jsonify({"error": "KB not found"}), 404

    docs = manager.get_documents(internal_name)
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
    """Search within a specific KB.

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
    return jsonify({"results": results, "total": len(results)})


@kb_bp.route("/search", methods=["POST"])
def search_all_kbs() -> Any:
    """Search across multiple or all KBs.

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
    return jsonify({"results": results, "total": len(results)})


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
