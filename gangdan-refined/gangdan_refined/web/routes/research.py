"""Research route blueprint.

Provides all /api/research/* endpoints expected by the frontend JS.
"""

from __future__ import annotations

import json

from flask import Blueprint, request, jsonify, Response, stream_with_context

from ...core.config import CONFIG, DATA_DIR

research_bp = Blueprint("research", __name__)


@research_bp.route("/search", methods=["POST"])
def research_search():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    sources = data.get("sources")
    max_results = data.get("max_results", 10)

    if not query:
        return jsonify({"success": False, "error": "Query is required"}), 400

    try:
        from ...search.research_searcher import ResearchSearcher
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


@research_bp.route("/search/stream", methods=["GET"])
def research_search_stream():
    query = request.args.get("query", "")
    if not query:
        return jsonify({"success": False, "error": "Query is required"}), 400

    try:
        from ...search.research_searcher import ResearchSearcher

        def gen():
            searcher = ResearchSearcher(
                timeout=CONFIG.search.research_search_timeout,
                semantic_scholar_api_key=CONFIG.search.semantic_scholar_api_key,
            )
            for event in searcher.search_stream(query):
                yield f"data: {json.dumps(event)}\n\n"
            yield 'data: {"type": "done"}\n\n'

        return Response(gen(), mimetype="text/event-stream")
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/autocomplete", methods=["GET"])
def research_autocomplete():
    query = request.args.get("query", "")
    if not query:
        return jsonify({"success": True, "suggestions": []})
    try:
        from ...search.research_searcher import ResearchSearcher
        searcher = ResearchSearcher(
            semantic_scholar_api_key=CONFIG.search.semantic_scholar_api_key,
        )
        suggestions = searcher.autocomplete(query)
        return jsonify({"success": True, "suggestions": suggestions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/download", methods=["POST"])
def research_download():
    data = request.get_json(silent=True) or {}
    paper_id = data.get("paper_id", "")
    title = data.get("title", "")
    source = data.get("source", "arxiv")
    try:
        from ...research.pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        result = pipeline.download_paper(paper_id=paper_id, title=title, source=source)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/download/batch", methods=["POST"])
def research_download_batch():
    data = request.get_json(silent=True) or {}
    papers = data.get("papers", [])
    try:
        from ...research.pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        results = pipeline.download_papers(papers)
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/papers", methods=["GET"])
def research_papers():
    try:
        from ...research.pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        papers = pipeline.list_papers()
        return jsonify({"success": True, "papers": papers})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/papers/<paper_id>", methods=["DELETE"])
def research_papers_delete(paper_id):
    try:
        from ...research.pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        pipeline.delete_paper(paper_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/papers/<paper_id>/markdown", methods=["GET"])
def research_papers_markdown(paper_id):
    try:
        from ...research.pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        markdown = pipeline.get_paper_markdown(paper_id)
        return jsonify({"success": True, "markdown": markdown})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/paper/<paper_id>/<relation>", methods=["GET"])
def research_paper_relation(paper_id, relation):
    try:
        from ...research.pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        if relation == "citations":
            result = pipeline.get_citations(paper_id)
        elif relation == "references":
            result = pipeline.get_references(paper_id)
        elif relation == "recommendations":
            result = pipeline.get_recommendations(paper_id)
        else:
            return jsonify({"success": False, "error": f"Unknown relation: {relation}"}), 400
        return jsonify({"success": True, "results": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/config", methods=["GET"])
def research_config_get():
    return jsonify({
        "success": True,
        "config": {
            "search_timeout": CONFIG.search.research_search_timeout,
            "semantic_scholar_api_key": bool(CONFIG.search.semantic_scholar_api_key),
            "crossref_email": CONFIG.search.crossref_email,
        },
    })


@research_bp.route("/config", methods=["PUT"])
def research_config_set():
    data = request.get_json(silent=True) or {}
    if "search_timeout" in data:
        CONFIG.search.research_search_timeout = data["search_timeout"]
    if "crossref_email" in data:
        CONFIG.search.crossref_email = data["crossref_email"]
    from ...core.config import save_config
    save_config()
    return jsonify({"success": True})


@research_bp.route("/batch-convert", methods=["POST"])
def research_batch_convert():
    data = request.get_json(silent=True) or {}
    papers = data.get("papers", [])
    try:
        from ...research.export import ExportManager
        from pathlib import Path
        mgr = ExportManager(output_dir=Path(DATA_DIR) / "exports")
        report = mgr.batch_convert_papers(papers)
        return jsonify({"success": True, "report": report.to_dict() if hasattr(report, "to_dict") else str(report)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/add-to-kb", methods=["POST"])
def research_add_to_kb():
    data = request.get_json(silent=True) or {}
    paper_id = data.get("paper_id", "")
    kb_name = data.get("kb_name", "research")
    try:
        from ...research.pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        result = pipeline.add_paper_to_kb(paper_id, kb_name)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/pipeline", methods=["POST"])
def research_pipeline():
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