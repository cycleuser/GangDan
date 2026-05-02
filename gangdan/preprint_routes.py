"""Flask Blueprint for preprint intelligence routes.

Provides API endpoints for:
- Preprint search across arXiv, bioRxiv, medRxiv
- Scheduler management (start/stop/status)
- Subscription management (add/remove/list)
- Knowledge base search and matching
- Preprint conversion and indexing
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from gangdan.core.config import CONFIG, DATA_DIR

logger = logging.getLogger(__name__)

preprint_bp = Blueprint("preprint", __name__, url_prefix="/api/preprint")

_scheduler = None
_kb_manager = None


def get_scheduler():
    """Get or create the preprint scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        from gangdan.core.preprint_scheduler import PreprintScheduler

        state_file = DATA_DIR / "preprint_state.json"
        _scheduler = PreprintScheduler(state_file=state_file)
    return _scheduler


def get_kb_manager():
    """Get or create the preprint KB manager singleton."""
    global _kb_manager
    if _kb_manager is None:
        from gangdan.core.preprint_kb_manager import PreprintKBManager

        kb_file = DATA_DIR / "preprint_kb.json"
        _kb_manager = PreprintKBManager(kb_file=kb_file)
    return _kb_manager


@preprint_bp.route("/search", methods=["POST"])
def search_preprints() -> Any:
    """Search for preprints across platforms.

    Request JSON:
        query (str): Search query
        platforms (list): Platforms to search (arxiv, biorxiv, medrxiv)
        max_results (int): Max results per platform
        categories (list): arXiv categories to filter
        strict_mode (bool): If True, only return papers matching categories
        ai_refine (bool): If True, use AI to refine query before search
        model (str): Ollama model for AI refinement

    Returns:
        JSON with preprint list and metadata
    """
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    platforms = data.get("platforms", ["arxiv", "biorxiv", "medrxiv"])
    max_results = data.get("max_results", CONFIG.preprint_max_results)
    categories = data.get("categories", [])
    strict_mode = data.get("strict_mode", False)
    ai_refine = data.get("ai_refine", False)
    model = data.get("model", "")

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        from gangdan.core.preprint_fetcher import PreprintFetcher

        fetcher = PreprintFetcher(
            platforms=platforms,
            max_results=max_results,
        )

        if categories or ai_refine:
            result = fetcher.search_with_categories(
                query=query,
                categories=categories,
                strict_mode=strict_mode,
                ai_refine=ai_refine,
                platforms=platforms,
                max_results=max_results,
                model=model,
            )
            papers = result["results"]
            refined_query = result["refined_query"]
            query_refined = result["query_refined"]
            category_counts = result["category_counts"]
        else:
            papers = fetcher.search(query, categories=None)
            refined_query = query
            query_refined = False
            category_counts = {}

        results = [p.to_dict() for p in papers]
        html_count = sum(1 for p in papers if p.has_html)
        tex_count = sum(1 for p in papers if p.has_tex)

        return jsonify({
            "success": True,
            "query": query,
            "refined_query": refined_query,
            "query_refined": query_refined,
            "total": len(results),
            "html_available": html_count,
            "tex_available": tex_count,
            "category_counts": category_counts,
            "strict_mode": strict_mode,
            "preprints": results,
        })
    except Exception as e:
        logger.error("[PreprintAPI] Search failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/categories", methods=["GET"])
def get_categories() -> Any:
    """Get all preprint platform categories.

    Query params:
        platform (str): Filter by platform (arxiv, biorxiv, medrxiv)
        search (str): Search categories by name/code

    Returns:
        JSON with category tree
    """
    platform = request.args.get("platform")
    search_query = request.args.get("search")

    try:
        from gangdan.core.preprint_categories import (
            get_all_categories,
            get_platform_categories,
            search_categories,
        )

        if search_query:
            results = search_categories(search_query, platform=platform)
            return jsonify({"success": True, "categories": results, "total": len(results)})

        if platform:
            cats = get_platform_categories(platform)
            return jsonify({
                "success": True,
                "platform": platform,
                "categories": [c.to_dict() for c in cats],
                "total": len(cats),
            })

        return jsonify({"success": True, "platforms": get_all_categories()})
    except Exception as e:
        logger.error("[PreprintAPI] Categories failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/refine-query", methods=["POST"])
def refine_query() -> Any:
    """Use AI to refine a search query.

    Request JSON:
        query (str): Original search query
        categories (list): Selected category codes
        platform (str): Target platform
        model (str): Ollama model to use

    Returns:
        JSON with refined query
    """
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    categories = data.get("categories", [])
    platform = data.get("platform", "arxiv")
    model = data.get("model", "")

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        from gangdan.core.preprint_fetcher import PreprintFetcher

        refined = PreprintFetcher.refine_query_with_ai(
            query, categories=categories, platform=platform, model=model
        )

        return jsonify({
            "success": True,
            "original_query": query,
            "refined_query": refined,
            "was_refined": refined != query,
        })
    except Exception as e:
        logger.error("[PreprintAPI] Refine query failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/fetch-by-id", methods=["POST"])
def fetch_by_id() -> Any:
    """Fetch a single preprint by ID with full source detection.

    Request JSON:
        preprint_id (str): Preprint identifier
        platform (str): Platform (arxiv, biorxiv, medrxiv)

    Returns:
        JSON with preprint metadata
    """
    data = request.get_json(silent=True) or {}
    preprint_id = data.get("preprint_id", "")
    platform = data.get("platform", "arxiv")

    if not preprint_id:
        return jsonify({"error": "preprint_id is required"}), 400

    try:
        from gangdan.core.preprint_fetcher import PreprintFetcher

        fetcher = PreprintFetcher(platforms=[platform])
        paper = fetcher.fetch_by_id(preprint_id, platform=platform)

        if paper is None:
            return jsonify({"error": "Preprint not found"}), 404

        return jsonify({
            "success": True,
            "preprint": paper.to_dict(),
        })
    except Exception as e:
        logger.error("[PreprintAPI] Fetch by ID failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/convert", methods=["POST"])
def convert_preprint() -> Any:
    """Convert a preprint to Markdown.

    Request JSON:
        url (str): Content URL (HTML, TeX, or PDF)
        content_type (str): html, tex, xml, or pdf
        preprint_id (str): Preprint identifier

    Returns:
        JSON with conversion result
    """
    data = request.get_json(silent=True) or {}
    url = data.get("url", "")
    content_type = data.get("content_type", "html")
    preprint_id = data.get("preprint_id", "")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        from gangdan.core.preprint_converter import PreprintConverter

        import tempfile

        output_dir = Path(tempfile.mkdtemp(prefix=f"gangdan_{preprint_id}_"))
        converter = PreprintConverter(fallback_to_pdf=True)
        result = converter.convert_from_url(
            url, content_type=content_type, output_dir=output_dir, preprint_id=preprint_id
        )

        if result.success:
            md_content = ""
            md_path = Path(result.markdown_path)
            if md_path.exists():
                md_content = md_path.read_text(encoding="utf-8")

            return jsonify({
                "success": True,
                "engine": result.engine,
                "markdown_path": result.markdown_path,
                "markdown_content": md_content[:10000],
            })
        else:
            return jsonify({"error": result.error}), 500
    except Exception as e:
        logger.error("[PreprintAPI] Convert failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/scheduler/status", methods=["GET"])
def scheduler_status() -> Any:
    """Get scheduler status.

    Returns:
        JSON with scheduler status, subscriptions, and recent jobs
    """
    try:
        scheduler = get_scheduler()
        status = scheduler.get_status()
        return jsonify({"success": True, "status": status})
    except Exception as e:
        logger.error("[PreprintAPI] Status failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/scheduler/start", methods=["POST"])
def scheduler_start() -> Any:
    """Start the background scheduler.

    Returns:
        JSON with success status
    """
    try:
        scheduler = get_scheduler()
        started = scheduler.start()
        return jsonify({
            "success": True,
            "started": started,
            "message": "Scheduler started" if started else "Scheduler already running",
        })
    except Exception as e:
        logger.error("[PreprintAPI] Start failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/scheduler/stop", methods=["POST"])
def scheduler_stop() -> Any:
    """Stop the background scheduler.

    Returns:
        JSON with success status
    """
    try:
        scheduler = get_scheduler()
        stopped = scheduler.stop()
        return jsonify({
            "success": True,
            "stopped": stopped,
            "message": "Scheduler stopped" if stopped else "Scheduler not running",
        })
    except Exception as e:
        logger.error("[PreprintAPI] Stop failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/scheduler/run-now", methods=["POST"])
def scheduler_run_now() -> Any:
    """Run a fetch cycle immediately.

    Returns:
        JSON with fetch cycle summary
    """
    try:
        scheduler = get_scheduler()
        summary = scheduler.run_once()
        return jsonify({"success": True, "summary": summary})
    except Exception as e:
        logger.error("[PreprintAPI] Run now failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/scheduler/interval", methods=["POST"])
def set_interval() -> Any:
    """Set the scheduler interval.

    Request JSON:
        hours (int): Hours between runs

    Returns:
        JSON with success status
    """
    data = request.get_json(silent=True) or {}
    hours = data.get("hours", 24)

    try:
        scheduler = get_scheduler()
        scheduler.set_interval(hours)
        return jsonify({"success": True, "interval_hours": hours})
    except Exception as e:
        logger.error("[PreprintAPI] Set interval failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/subscriptions", methods=["GET"])
def list_subscriptions() -> Any:
    """List all subscriptions.

    Returns:
        JSON with subscription list
    """
    try:
        scheduler = get_scheduler()
        subs = [s.to_dict() for s in scheduler.subscriptions]
        return jsonify({"success": True, "subscriptions": subs})
    except Exception as e:
        logger.error("[PreprintAPI] List subscriptions failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/subscriptions", methods=["POST"])
def add_subscription() -> Any:
    """Add a new subscription.

    Request JSON:
        name (str): Subscription name
        keywords (list): Keywords to search
        platforms (list): Platforms to search
        categories (list): arXiv categories
        max_results (int): Max results per keyword

    Returns:
        JSON with created subscription
    """
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    keywords = data.get("keywords", [])
    platforms = data.get("platforms", ["arxiv"])
    categories = data.get("categories", [])
    max_results = data.get("max_results", 10)

    if not name or not keywords:
        return jsonify({"error": "name and keywords are required"}), 400

    try:
        scheduler = get_scheduler()
        sub = scheduler.add_subscription(
            name=name,
            keywords=keywords,
            platforms=platforms,
            categories=categories,
            max_results=max_results,
        )
        return jsonify({"success": True, "subscription": sub.to_dict()})
    except Exception as e:
        logger.error("[PreprintAPI] Add subscription failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/subscriptions/<name>", methods=["DELETE"])
def remove_subscription(name: str) -> Any:
    """Remove a subscription.

    Returns:
        JSON with success status
    """
    try:
        scheduler = get_scheduler()
        removed = scheduler.remove_subscription(name)
        if removed:
            return jsonify({"success": True, "message": f"Removed '{name}'"})
        else:
            return jsonify({"error": f"Subscription '{name}' not found"}), 404
    except Exception as e:
        logger.error("[PreprintAPI] Remove subscription failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/kb/search", methods=["POST"])
def kb_search() -> Any:
    """Search the preprint knowledge base.

    Request JSON:
        query (str): Search query
        mode (str): keyword, semantic, or combined
        platform (str): Filter by platform
        category (str): Filter by category
        date_from (str): Filter by date from
        date_to (str): Filter by date to
        limit (int): Max results

    Returns:
        JSON with search results
    """
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    mode = data.get("mode", "keyword")
    platform = data.get("platform")
    category = data.get("category")
    date_from = data.get("date_from")
    date_to = data.get("date_to")
    limit = data.get("limit", 20)

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        kb_manager = get_kb_manager()
        results = kb_manager.search(
            query=query,
            mode=mode,
            platform=platform,
            category=category,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )

        return jsonify({
            "success": True,
            "query": query,
            "total": len(results),
            "results": [r.to_dict() for r in results],
        })
    except Exception as e:
        logger.error("[PreprintAPI] KB search failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/kb/stats", methods=["GET"])
def kb_stats() -> Any:
    """Get preprint KB statistics.

    Returns:
        JSON with KB statistics
    """
    try:
        kb_manager = get_kb_manager()
        stats = kb_manager.get_statistics()
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        logger.error("[PreprintAPI] KB stats failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/kb/recent", methods=["GET"])
def kb_recent() -> Any:
    """Get recently indexed preprints.

    Query params:
        days (int): Days to look back (default 30)
        limit (int): Max results (default 50)

    Returns:
        JSON with recent preprints
    """
    try:
        days = request.args.get("days", 30, type=int)
        limit = request.args.get("limit", 50, type=int)

        kb_manager = get_kb_manager()
        entries = kb_manager.get_recent(days=days, limit=limit)

        return jsonify({
            "success": True,
            "total": len(entries),
            "entries": [e.to_dict() for e in entries],
        })
    except Exception as e:
        logger.error("[PreprintAPI] KB recent failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/kb/index", methods=["POST"])
def kb_index() -> Any:
    """Index a preprint's Markdown content for semantic search.

    Request JSON:
        preprint_id (str): Preprint identifier
        markdown_path (str): Path to Markdown file

    Returns:
        JSON with success status
    """
    data = request.get_json(silent=True) or {}
    preprint_id = data.get("preprint_id", "")
    markdown_path = data.get("markdown_path", "")

    if not preprint_id or not markdown_path:
        return jsonify({"error": "preprint_id and markdown_path are required"}), 400

    try:
        kb_manager = get_kb_manager()
        success = kb_manager.index_markdown_content(preprint_id, markdown_path)

        if success:
            return jsonify({"success": True, "message": "Indexed successfully"})
        else:
            return jsonify({"error": "Indexing failed"}), 500
    except Exception as e:
        logger.error("[PreprintAPI] KB index failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/recent", methods=["GET"])
def fetch_recent() -> Any:
    """Fetch recent preprints from all platforms.

    Query params:
        days (int): Days to look back (default 7)
        platforms (str): Comma-separated platform list

    Returns:
        JSON with recent preprints
    """
    try:
        days = request.args.get("days", 7, type=int)
        platforms_str = request.args.get("platforms", "arxiv,biorxiv,medrxiv")
        platforms = [p.strip() for p in platforms_str.split(",")]

        from gangdan.core.preprint_fetcher import PreprintFetcher

        fetcher = PreprintFetcher(platforms=platforms)
        papers = fetcher.fetch_recent(days=days)

        return jsonify({
            "success": True,
            "total": len(papers),
            "preprints": [p.to_dict() for p in papers],
        })
    except Exception as e:
        logger.error("[PreprintAPI] Fetch recent failed: %s", e)
        return jsonify({"error": str(e)}), 500
