"""Research route blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify, Response, stream_with_context

from ...core.config import CONFIG

research_bp = Blueprint("research", __name__)


@research_bp.route("/search", methods=["POST"])
def research_search():
    """Search for academic papers across multiple sources."""
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    sources = data.get("sources")
    max_results = data.get("max_results", 10)

    if not query:
        return jsonify({"success": False, "error": "Query is required"}), 400

    try:
        from ...search.research_searcher import ResearchSearcher
        from ...core.config import CONFIG

        searcher = ResearchSearcher(
            sources=sources,
            max_results=max_results,
            timeout=CONFIG.search.research_search_timeout,
            semantic_scholar_api_key=CONFIG.search.semantic_scholar_api_key,
            crossref_email=CONFIG.search.crossref_email,
            pubmed_api_key=CONFIG.search.pubmed_api_key,
            github_token=CONFIG.search.github_token,
            openalex_email=CONFIG.search.openalex_email,
        )

        results = searcher.search(query, max_results=max_results)

        return jsonify({
            "success": True,
            "results": [r.to_dict() if hasattr(r, "to_dict") else str(r) for r in results],
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/pipeline", methods=["POST"])
def research_pipeline():
    """Run the full research pipeline."""
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")

    if not query:
        return jsonify({"success": False, "error": "Query is required"}), 400

    try:
        from ...research.pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        results = pipeline.search(query)
        return jsonify({
            "success": True,
            "results": [r.to_dict() if hasattr(r, "to_dict") else str(r) for r in results],
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500