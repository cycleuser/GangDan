"""Research API routes for GangDan.

Provides RESTful endpoints for:
- Paper search (with optional LLM query expansion)
- Paper details and related papers (citations, references, recommendations)
- Autocomplete suggestions
- PDF download and processing
- Paper management (list, delete)
- Configuration
- SSE streaming for search progress
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Generator, List, Optional

from flask import Blueprint, Response, jsonify, request, stream_with_context

from gangdan.core.config import CONFIG, save_config
from gangdan.core.research_models import PaperMetadata

logger = logging.getLogger(__name__)

research_bp = Blueprint("research", __name__, url_prefix="/api/research")

_pipeline = None


def get_pipeline():
    """Get or create the ResearchPipeline singleton."""
    global _pipeline
    if _pipeline is None:
        from gangdan.core.research_pipeline import ResearchPipeline

        _pipeline = ResearchPipeline()
    return _pipeline


@research_bp.route("/search", methods=["POST"])
def search() -> Response:
    """Search for papers.

    Body: {"query": "...", "expand_query": true, "sources": ["arxiv", "semantic_scholar"], "max_results": 20}
    """
    data = request.json or {}
    query = data.get("query", "")
    if not query:
        return jsonify({"error": "query is required"}), 400

    expand_query = data.get("expand_query", None)
    sources = data.get("sources", None)
    max_results = data.get("max_results", None)

    pipeline = get_pipeline()
    results = pipeline.search(
        query,
        expand_query=expand_query,
        sources=sources,
        max_results=max_results,
    )

    expanded_query = None
    if expand_query and pipeline.expander:
        eq = pipeline.expander.expand(query)
        expanded_query = {
            "original": eq.original,
            "expanded": eq.all_queries(),
            "domain": eq.domain,
            "recommended_sources": eq.recommended_sources,
        }

    return jsonify({
        "results": [r.to_dict() for r in results],
        "expanded_query": expanded_query,
    })


@research_bp.route("/search/stream", methods=["GET"])
def search_stream() -> Response:
    """SSE streaming search.

    Query: ?query=...&expand_query=true
    """
    query = request.args.get("query", "")
    if not query:
        return jsonify({"error": "query is required"}), 400

    expand_query = request.args.get("expand_query", "false").lower() == "true"

    def generate() -> Generator[str, None, None]:
        """Generate SSE events."""
        pipeline = get_pipeline()

        if expand_query and pipeline.expander is None:
            from gangdan.app import get_research_client

            client = get_research_client()
            from gangdan.core.query_expander import QueryExpander

            pipeline.expander = QueryExpander(
                llm_client=client,
                enabled=True,
                model=CONFIG.query_expansion_model or "",
            )

        if expand_query and pipeline.expander:
            eq = pipeline.expander.expand(query)
            yield f"event: expanded_query\ndata: {json.dumps({'original': eq.original, 'expanded': eq.all_queries(), 'domain': eq.domain})}\n\n"

        results = pipeline.search(query, expand_query=expand_query)

        source_counts: Dict[str, int] = {}
        for r in results:
            src = r.paper.source
            source_counts[src] = source_counts.get(src, 0) + 1

        for src, count in source_counts.items():
            yield f"event: search_progress\ndata: {json.dumps({'source': src, 'count': count})}\n\n"

        deduped = len(results)
        yield f"event: search_complete\ndata: {json.dumps({'total': deduped})}\n\n"
        yield f"event: results\ndata: {json.dumps([r.to_dict() for r in results])}\n\n"
        yield "event: done\ndata: {}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@research_bp.route("/paper/<paper_id>", methods=["GET"])
def get_paper(paper_id: str) -> Response:
    """Get paper details by ID."""
    pipeline = get_pipeline()
    paper = pipeline.get_paper_details(paper_id)
    if paper is None:
        return jsonify({"error": "Paper not found"}), 404
    return jsonify(paper.to_dict())


@research_bp.route("/paper/<paper_id>/citations", methods=["GET"])
def get_citations(paper_id: str) -> Response:
    """Get papers citing this paper."""
    limit = request.args.get("limit", 20, type=int)
    pipeline = get_pipeline()
    papers = pipeline.get_related_papers(paper_id, relation="citations", limit=limit)
    return jsonify({"papers": [p.to_dict() for p in papers]})


@research_bp.route("/paper/<paper_id>/references", methods=["GET"])
def get_references(paper_id: str) -> Response:
    """Get papers cited by this paper."""
    limit = request.args.get("limit", 20, type=int)
    pipeline = get_pipeline()
    papers = pipeline.get_related_papers(paper_id, relation="references", limit=limit)
    return jsonify({"papers": [p.to_dict() for p in papers]})


@research_bp.route("/paper/<paper_id>/recommendations", methods=["GET"])
def get_recommendations(paper_id: str) -> Response:
    """Get recommended similar papers."""
    limit = request.args.get("limit", 10, type=int)
    pipeline = get_pipeline()
    papers = pipeline.get_related_papers(paper_id, relation="recommendations", limit=limit)
    return jsonify({"papers": [p.to_dict() for p in papers]})


@research_bp.route("/autocomplete", methods=["GET"])
def autocomplete() -> Response:
    """Get paper title autocomplete suggestions."""
    query = request.args.get("q", "")
    limit = request.args.get("limit", 5, type=int)

    from gangdan.core.research_searcher import SemanticScholarFetcher

    fetcher = SemanticScholarFetcher(api_key=CONFIG.semantic_scholar_api_key)
    suggestions = fetcher.autocomplete(query, limit=limit)
    return jsonify({"suggestions": suggestions})


@research_bp.route("/download", methods=["POST"])
def download() -> Response:
    """Download and process a single paper.

    Body: {"paper": {...}, "rename": true, "convert": true}
    """
    data = request.json or {}
    paper_data = data.get("paper", {})
    if not paper_data:
        return jsonify({"error": "paper is required"}), 400

    paper = PaperMetadata(**paper_data)
    rename = data.get("rename", None)
    convert = data.get("convert", None)
    index_to_kb = data.get("index_to_kb", None)

    pipeline = get_pipeline()
    record = pipeline.download_and_process(
        paper, rename=rename, convert=convert, index_to_kb=index_to_kb
    )

    if not record.local_pdf:
        return jsonify({"error": record.notes or "Download failed"}), 500

    pipeline.save_manifest([record])
    return jsonify({"record": record.to_dict()})


@research_bp.route("/download/batch", methods=["POST"])
def download_batch() -> Response:
    """Download and process multiple papers.

    Body: {"papers": [{...}, ...], "rename": true, "convert": true}
    """
    data = request.json or {}
    papers_data = data.get("papers", [])
    if not papers_data:
        return jsonify({"error": "papers is required"}), 400

    rename = data.get("rename", None)
    convert = data.get("convert", None)
    index_to_kb = data.get("index_to_kb", None)

    pipeline = get_pipeline()
    records = []

    for paper_data in papers_data:
        paper = PaperMetadata(**paper_data)
        record = pipeline.download_and_process(
            paper, rename=rename, convert=convert, index_to_kb=index_to_kb
        )
        records.append(record)

    pipeline.save_manifest(records)
    return jsonify({"records": [r.to_dict() for r in records]})


@research_bp.route("/papers", methods=["GET"])
def list_papers() -> Response:
    """List all downloaded papers."""
    pipeline = get_pipeline()
    records = pipeline.load_manifest()
    return jsonify({"papers": [r.to_dict() for r in records], "total": len(records)})


@research_bp.route("/papers/<paper_id>", methods=["DELETE"])
def delete_paper(paper_id: str) -> Response:
    """Delete a paper record and its local files."""
    pipeline = get_pipeline()
    success = pipeline.delete_paper(paper_id)
    if success:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Paper not found"}), 404


@research_bp.route("/config", methods=["GET"])
def get_config() -> Response:
    """Get research configuration."""
    return jsonify({
        "query_expansion_enabled": CONFIG.query_expansion_enabled,
        "query_expansion_model": CONFIG.query_expansion_model,
        "research_search_sources": CONFIG.research_search_sources,
        "research_max_results": CONFIG.research_max_results,
        "research_search_timeout": CONFIG.research_search_timeout,
        "semantic_scholar_api_key": "****" if CONFIG.semantic_scholar_api_key else "",
        "crossref_email": CONFIG.crossref_email,
        "pubmed_api_key": "****" if CONFIG.pubmed_api_key else "",
        "github_token": "****" if CONFIG.github_token else "",
        "openalex_email": CONFIG.openalex_email,
        "pdf_rename_enabled": CONFIG.pdf_rename_enabled,
        "pdf_convert_enabled": CONFIG.pdf_convert_enabled,
        "pdf_convert_engine": CONFIG.pdf_convert_engine,
        "unpaywall_email": CONFIG.unpaywall_email,
        "web_search_engine": CONFIG.web_search_engine,
        "serper_api_key": "****" if CONFIG.serper_api_key else "",
        "brave_api_key": "****" if CONFIG.brave_api_key else "",
        "research_pipeline_convert": CONFIG.research_pipeline_convert,
        "research_pipeline_index": CONFIG.research_pipeline_index,
        "research_pipeline_rename": CONFIG.research_pipeline_rename,
    })


@research_bp.route("/config", methods=["PUT"])
def update_config() -> Response:
    """Update research configuration."""
    data = request.json or {}

    if "query_expansion_enabled" in data:
        CONFIG.query_expansion_enabled = bool(data["query_expansion_enabled"])
    if "query_expansion_model" in data:
        CONFIG.query_expansion_model = str(data["query_expansion_model"])
    if "research_search_sources" in data:
        CONFIG.research_search_sources = str(data["research_search_sources"])
    if "research_max_results" in data:
        CONFIG.research_max_results = int(data["research_max_results"])
    if "research_search_timeout" in data:
        CONFIG.research_search_timeout = int(data["research_search_timeout"])
    if "semantic_scholar_api_key" in data:
        CONFIG.semantic_scholar_api_key = str(data["semantic_scholar_api_key"])
    if "crossref_email" in data:
        CONFIG.crossref_email = str(data["crossref_email"])
    if "pubmed_api_key" in data:
        CONFIG.pubmed_api_key = str(data["pubmed_api_key"])
    if "github_token" in data:
        CONFIG.github_token = str(data["github_token"])
    if "openalex_email" in data:
        CONFIG.openalex_email = str(data["openalex_email"])
    if "pdf_rename_enabled" in data:
        CONFIG.pdf_rename_enabled = bool(data["pdf_rename_enabled"])
    if "pdf_convert_enabled" in data:
        CONFIG.pdf_convert_enabled = bool(data["pdf_convert_enabled"])
    if "pdf_convert_engine" in data:
        CONFIG.pdf_convert_engine = str(data["pdf_convert_engine"])
    if "unpaywall_email" in data:
        CONFIG.unpaywall_email = str(data["unpaywall_email"])
    if "web_search_engine" in data:
        CONFIG.web_search_engine = str(data["web_search_engine"])
    if "serper_api_key" in data:
        CONFIG.serper_api_key = str(data["serper_api_key"])
    if "brave_api_key" in data:
        CONFIG.brave_api_key = str(data["brave_api_key"])
    if "research_pipeline_convert" in data:
        CONFIG.research_pipeline_convert = bool(data["research_pipeline_convert"])
    if "research_pipeline_index" in data:
        CONFIG.research_pipeline_index = bool(data["research_pipeline_index"])
    if "research_pipeline_rename" in data:
        CONFIG.research_pipeline_rename = bool(data["research_pipeline_rename"])

    save_config()
    return jsonify({"success": True})


# =============================================================================
# Batch Convert & KB Integration
# =============================================================================


@research_bp.route("/batch-convert", methods=["POST"])
def batch_convert_papers() -> Response:
    """Batch convert research papers (PDF) to Markdown.

    Body: {
        "items": [{"item_id": "...", "title": "...", "pdf_path": "..."}],
        "create_zip": true,
        "kb_name": "..." (optional)
    }
    """
    data = request.json or {}
    items = data.get("items", [])

    if not items:
        return jsonify({"error": "items array is required"}), 400

    create_zip = data.get("create_zip", True)
    kb_name = data.get("kb_name", "")

    from gangdan.core.export_manager import ExportManager

    manager = ExportManager()
    report = manager.batch_convert_papers(items, create_zip=create_zip)

    result = report.to_dict()

    if kb_name and report.success_count > 0:
        result["kb_result"] = _add_papers_to_kb(kb_name, report.results)

    return jsonify(result)


@research_bp.route("/add-to-kb", methods=["POST"])
def add_papers_to_kb() -> Response:
    """Add papers to a custom knowledge base.

    Body: {
        "kb_name": "...",
        "papers": [{"doc_id": "...", "title": "...", "markdown_path": "...", ...}],
        "index_to_chroma": true
    }
    """
    data = request.json or {}
    kb_name = data.get("kb_name", "")
    papers = data.get("papers", [])
    index_to_chroma = data.get("index_to_chroma", True)

    if not kb_name or not papers:
        return jsonify({"error": "kb_name and papers are required"}), 400

    try:
        result = _add_papers_to_kb_direct(kb_name, papers, index_to_chroma)
        return jsonify(result)
    except Exception as e:
        logger.error("[ResearchAPI] Add to KB failed: %s", e)
        return jsonify({"error": str(e)}), 500


def _add_papers_to_kb(kb_name: str, results: list) -> dict:
    """Add batch convert results to a KB."""
    paper_items = []
    for r in results:
        if r.get("success") and r.get("markdown_path"):
            paper_items.append({
                "doc_id": r.get("item_id", ""),
                "title": r.get("title", ""),
                "source_type": "paper",
                "markdown_path": r.get("markdown_path", ""),
                "content_preview": r.get("markdown_content", "")[:500],
            })
    return _add_papers_to_kb_direct(kb_name, paper_items, index_to_chroma=True)


def _add_papers_to_kb_direct(kb_name: str, papers: list, index_to_chroma: bool = True) -> dict:
    """Add paper items to a custom KB."""
    from gangdan.core.kb_manager import CustomKBManager, KBDocEntry
    from datetime import datetime

    manager = CustomKBManager()

    kb = manager.get_kb(kb_name)
    if kb is None:
        kb = manager.create_kb(kb_name, f"Paper collection: {kb_name}")

    added = 0
    failed = 0

    for p in papers:
        doc_id = p.get("doc_id", "")
        title = p.get("title", "")

        if not doc_id or not title:
            failed += 1
            continue

        doc = KBDocEntry(
            doc_id=doc_id,
            title=title,
            source_type=p.get("source_type", "paper"),
            source_id=p.get("doi", "") or p.get("arxiv_id", doc_id),
            source_platform=p.get("source", ""),
            markdown_path=p.get("markdown_path", ""),
            content_preview=p.get("content_preview", "")[:500],
            authors=p.get("authors", []),
            published_date=p.get("year", ""),
            url=p.get("url", ""),
            tags=p.get("tags", []),
            added_at=datetime.now().isoformat(),
        )

        if manager.add_document(kb.internal_name, doc, index_to_chroma=index_to_chroma):
            added += 1
        else:
            failed += 1

    return {
        "kb_name": kb.internal_name,
        "kb_display": kb.display_name,
        "added": added,
        "failed": failed,
    }
