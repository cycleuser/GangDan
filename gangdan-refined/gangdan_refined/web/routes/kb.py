"""Knowledge base route blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

from ...core.config import CONFIG, CHROMA_DIR, sanitize_kb_name
from ...core.errors import GangDanError, ValidationError, create_error_response

kb_bp = Blueprint("kb", __name__)


@kb_bp.route("/list", methods=["GET"])
def kb_list():
    """List all knowledge bases."""
    from ...storage.kb_manager import CustomKBManager
    try:
        mgr = CustomKBManager()
        kbs = mgr.list_kbs()
        return jsonify({"success": True, "kbs": [kb.to_dict() for kb in kbs]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@kb_bp.route("/create", methods=["POST"])
def kb_create():
    """Create a new knowledge base."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    description = data.get("description", "")
    tags = data.get("tags", [])

    if not name:
        return jsonify({"success": False, "error": "Name is required"}), 400

    try:
        from ...storage.kb_manager import CustomKBManager
        mgr = CustomKBManager()
        kb = mgr.create_kb(display_name=name, description=description, tags=tags)
        return jsonify({"success": True, "kb": kb.to_dict()})
    except GangDanError as e:
        return jsonify(create_error_response(e)), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@kb_bp.route("/<internal_name>", methods=["GET"])
def kb_get(internal_name):
    """Get knowledge base details."""
    from ...storage.kb_manager import CustomKBManager
    try:
        mgr = CustomKBManager()
        kb = mgr.get_kb(internal_name)
        if kb is None:
            return jsonify({"success": False, "error": "KB not found"}), 404
        return jsonify({"success": True, "kb": kb.to_dict()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@kb_bp.route("/<internal_name>", methods=["DELETE"])
def kb_delete(internal_name):
    """Delete a knowledge base."""
    data = request.get_json(silent=True) or {}
    delete_files = data.get("delete_files", False)

    try:
        from ...storage.kb_manager import CustomKBManager
        mgr = CustomKBManager()
        success = mgr.delete_kb(internal_name, delete_files=delete_files)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@kb_bp.route("/<internal_name>/search", methods=["POST"])
def kb_search(internal_name):
    """Search within a knowledge base."""
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    limit = data.get("limit", 20)

    if not query:
        return jsonify({"success": False, "error": "Query is required"}), 400

    try:
        from ...storage.kb_manager import CustomKBManager
        mgr = CustomKBManager()
        results = mgr.search_kb(internal_name, query, limit=limit)
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@kb_bp.route("/<internal_name>/documents", methods=["POST"])
def kb_add_document(internal_name):
    """Add a document to a knowledge base."""
    data = request.get_json(silent=True) or {}

    try:
        from ...storage.kb_manager import CustomKBManager, KBDocEntry
        mgr = CustomKBManager()
        doc = KBDocEntry.from_dict(data) if "doc_id" in data else KBDocEntry(
            doc_id=data.get("doc_id", ""),
            title=data.get("title", ""),
            source_type=data.get("source_type", "upload"),
            content_preview=data.get("content_preview", ""),
        )
        success = mgr.add_document(internal_name, doc)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500