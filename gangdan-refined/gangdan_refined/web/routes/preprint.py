"""Preprint route blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

from ...core.config import CONFIG

preprint_bp = Blueprint("preprint", __name__)


@preprint_bp.route("/search", methods=["POST"])
def preprint_search():
    """Search preprints from configured platforms."""
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    platform = data.get("platform", "arxiv")
    max_results = data.get("max_results", 20)

    try:
        from ...document.preprint.fetcher import PreprintFetcher
        fetcher = PreprintFetcher()
        results = fetcher.search(
            query=query,
            platform=platform,
            max_results=max_results,
        )
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@preprint_bp.route("/scheduler/status", methods=["GET"])
def preprint_scheduler_status():
    """Get preprint scheduler status."""
    return jsonify({"success": True, "status": "ready"})


@preprint_bp.route("/categories", methods=["GET"])
def preprint_categories():
    """List available preprint categories."""
    from ...document.preprint.categories import PREPRINT_CATEGORIES
    return jsonify({"success": True, "categories": PREPRINT_CATEGORIES})