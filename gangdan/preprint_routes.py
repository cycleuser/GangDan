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
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request, Response

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
    provider = data.get("provider", "")
    api_key = data.get("api_key", "")
    base_url = data.get("base_url", "")

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        from gangdan.core.preprint_fetcher import PreprintFetcher

        fetcher = PreprintFetcher(
            platforms=platforms,
            max_results=max_results,
        )

        llm_client = None
        if ai_refine:
            if provider and provider != "ollama":
                from gangdan.core.llm_client import create_client
                llm_client = create_client(
                    provider=provider,
                    api_key=api_key or CONFIG.chat_api_key,
                    base_url=base_url or CONFIG.chat_api_base_url,
                )
                model = model or CONFIG.chat_model_name or CONFIG.chat_model
            elif provider == "ollama":
                from gangdan.core.ollama_client import OllamaClient
                llm_client = OllamaClient(CONFIG.ollama_url)
                model = model or CONFIG.chat_model or CONFIG.embedding_model
            elif ai_refine:
                from gangdan.app import get_chat_client
                llm_client = get_chat_client()
                model = model or CONFIG.chat_model_name or CONFIG.chat_model or CONFIG.embedding_model

        if categories or ai_refine:
            result = fetcher.search_with_categories(
                query=query,
                categories=categories,
                strict_mode=strict_mode,
                ai_refine=ai_refine,
                platforms=platforms,
                max_results=max_results,
                model=model,
                llm_client=llm_client,
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


@preprint_bp.route("/search-and-convert", methods=["POST"])
def search_and_convert() -> Any:
    """Search preprints, download full articles, convert to Markdown, and create a KB.

    Request JSON:
        query (str): Search query (e.g. "vector calculus")
        kb_name (str): Knowledge base display name
        platforms (list): Platforms to search (default: ["arxiv"])
        max_results (int): Max papers to process (default: 10)
        categories (list): arXiv categories to filter

    This endpoint searches for papers, then for each paper:
    1. Tries HTML first (from ar5iv) for best quality
    2. Falls back to TeX source if HTML fails
    3. Falls back to PDF if both fail
    Converts to Markdown and adds to the specified knowledge base.
    """
    import json
    import shutil
    import time

    from gangdan.core.config import DOCS_DIR, sanitize_kb_name, save_user_kb
    from gangdan.core.preprint_converter import PreprintConverter
    from gangdan.core.preprint_fetcher import PreprintFetcher

    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    kb_name = data.get("kb_name", "") or query
    platforms = data.get("platforms", ["arxiv"])
    max_results = min(data.get("max_results", 10), 50)
    categories = data.get("categories", [])

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        fetcher = PreprintFetcher(platforms=platforms, max_results=max_results)
        papers = fetcher.search(query, categories=categories if categories else None)

        if not papers:
            return jsonify({
                "success": True,
                "query": query,
                "total": 0,
                "converted": 0,
                "kb_name": kb_name,
                "message": "No papers found",
            })

        internal_name = sanitize_kb_name(kb_name)
        kb_dir = DOCS_DIR / internal_name
        if kb_dir.exists():
            shutil.rmtree(kb_dir, ignore_errors=True)
        kb_dir.mkdir(parents=True, exist_ok=True)

        converter = PreprintConverter(fallback_to_pdf=True)
        converted_count = 0
        failed_ids = []
        documents = {}

        for i, paper in enumerate(papers):
            logger.info(
                "[SearchAndConvert] [%d/%d] %s: %s (html=%s, tex=%s)",
                i + 1, len(papers), paper.preprint_id,
                paper.title[:50], paper.has_html, paper.has_tex,
            )

            safe_id = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', paper.preprint_id) if paper.preprint_id else "unknown"
            paper_dir = kb_dir / safe_id
            paper_dir.mkdir(parents=True, exist_ok=True)
            success = False
            source_formats_saved = []

            # Step 1: Download ALL available source formats (HTML, TeX, PDF)
            all_formats = []
            if paper.html_url:
                all_formats.append(("html", paper.html_url))
            if paper.tex_source_url:
                all_formats.append(("tex", paper.tex_source_url))
            if paper.pdf_url:
                all_formats.append(("pdf", paper.pdf_url))

            for fmt, url in all_formats:
                try:
                    dl_result = converter.download_source(
                        url, content_type=fmt, output_dir=paper_dir, preprint_id=paper.preprint_id,
                    )
                    if dl_result.success and dl_result.source_path:
                        source_formats_saved.append(fmt)
                        logger.info("[SearchAndConvert]   %s source saved (format=%s)", paper.preprint_id, fmt)
                except Exception as e:
                    logger.warning("[SearchAndConvert]   %s source download format=%s failed: %s", paper.preprint_id, fmt, e)

            # Step 2: Convert to Markdown using priority chain (HTML > TeX > PDF)
            format_chain = []
            if paper.has_html and paper.html_url:
                format_chain.append(("html", paper.html_url))
            if paper.has_tex and paper.tex_source_url:
                format_chain.append(("tex", paper.tex_source_url))
            if paper.pdf_url:
                format_chain.append(("pdf", paper.pdf_url))

            for fmt, url in format_chain:
                try:
                    safe_preid = re.sub(r'[<>:"/\\|?*\x00-\x1f()]', '_', paper.preprint_id) if paper.preprint_id else "preprint"
                    source_file = None
                    ext_map = {"html": "_source.html", "tex": "_source.tar.gz", "pdf": "_source.pdf"}
                    possible_source = paper_dir / f"{safe_preid}{ext_map.get(fmt, '')}"
                    if possible_source.exists():
                        source_file = possible_source
                    result = converter.convert_from_url(
                        url,
                        content_type=fmt,
                        output_dir=paper_dir,
                        preprint_id=paper.preprint_id,
                    )
                    if result.success and result.markdown_path and Path(result.markdown_path).exists():
                        md_content = Path(result.markdown_path).read_text(encoding="utf-8")
                        header = f"# {paper.title}\n\n"
                        header += f"**Authors:** {paper.authors_str}\n\n"
                        header += f"**arXiv ID:** [{paper.preprint_id}]({paper.url})\n\n"
                        header += f"**Published:** {paper.published_date}\n\n"
                        header += f"**Abstract:** {paper.abstract}\n\n"
                        header += "---\n\n"

                        dest_path = paper_dir / f"{paper.preprint_id}.md"
                        dest_path.write_text(header + md_content, encoding="utf-8")

                        doc_id = paper.preprint_id
                        documents[doc_id] = {
                            "doc_id": doc_id,
                            "title": paper.title,
                            "source_type": "paper",
                            "source_id": paper.preprint_id,
                            "source_platform": paper.source_platform,
                            "markdown_path": str(dest_path),
                            "content_preview": paper.abstract[:500] if paper.abstract else "",
                            "authors": paper.authors,
                            "published_date": paper.published_date,
                            "url": paper.url,
                            "tags": [],
                            "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "source_format": fmt,
                            "source_formats_saved": source_formats_saved,
                            "source_path": getattr(result, "source_path", None),
                        }
                        converted_count += 1
                        success = True
                        logger.info(
                            "[SearchAndConvert]   %s -> Markdown (format=%s), sources=%s",
                            paper.preprint_id, fmt, source_formats_saved,
                        )
                        break
                except Exception as e:
                    logger.warning(
                        "[SearchAndConvert]   %s format=%s failed: %s",
                        paper.preprint_id, fmt, e,
                    )

            if not success:
                failed_ids.append(paper.preprint_id)
                logger.warning(
                    "[SearchAndConvert]   All formats failed for %s",
                    paper.preprint_id,
                )

        manifest = {
            "kb_id": internal_name,
            "internal_name": internal_name,
            "documents": documents,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        (kb_dir / "documents.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        save_user_kb(internal_name, kb_name, converted_count, languages=["en"])

        return jsonify({
            "success": True,
            "query": query,
            "kb_name": kb_name,
            "internal_name": internal_name,
            "total": len(papers),
            "converted": converted_count,
            "failed": failed_ids,
            "message": f"Converted {converted_count}/{len(papers)} papers to KB '{kb_name}'",
        })
    except Exception as e:
        logger.error("[PreprintAPI] Search-and-convert failed: %s", e)
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

    Uses the chat model by default (supports Ollama and online providers).
    Optionally accepts provider/model overrides.

    Request JSON:
        query (str): Original search query
        categories (list): Selected category codes
        platform (str): Target platform
        model (str): Model name to use
        provider (str): LLM provider (e.g. 'ollama', 'minimax')
        api_key (str): API key for the provider
        base_url (str): Base URL for the provider

    Returns:
        JSON with refined query
    """
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    categories = data.get("categories", [])
    platform = data.get("platform", "arxiv")
    model_name = data.get("model", "")
    provider = data.get("provider", "")
    api_key = data.get("api_key", "")
    base_url = data.get("base_url", "")

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        from gangdan.core.preprint_fetcher import PreprintFetcher
        from gangdan.core.config import CONFIG

        if provider and provider != "ollama":
            from gangdan.core.llm_client import create_client
            llm_client = create_client(
                provider=provider,
                api_key=api_key or CONFIG.chat_api_key,
                base_url=base_url or CONFIG.chat_api_base_url,
            )
            target_model = model_name or CONFIG.chat_model_name or CONFIG.chat_model
        elif provider == "ollama":
            from gangdan.core.ollama_client import OllamaClient
            llm_client = OllamaClient(CONFIG.ollama_url)
            target_model = model_name or CONFIG.chat_model or CONFIG.embedding_model
        else:
            from gangdan.app import get_chat_client
            llm_client = get_chat_client()
            target_model = model_name or CONFIG.chat_model_name or CONFIG.chat_model or CONFIG.embedding_model

        refined = PreprintFetcher.refine_query_with_ai(
            query, categories=categories, platform=platform, model=target_model, llm_client=llm_client
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


# =============================================================================
# Batch Convert & KB Integration
# =============================================================================


@preprint_bp.route("/batch-convert", methods=["POST"])
def batch_convert_preprints() -> Any:
    """Batch convert multiple preprints to Markdown.

    Request JSON:
        items (list): List of {item_id, title, url, content_type, preprint_id}
        create_zip (bool): Whether to create ZIP export (default true)
        kb_name (str): Optional KB name to add results to

    Returns:
        JSON with conversion report
    """
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])

    if not items:
        return jsonify({"error": "items array is required"}), 400

    create_zip = data.get("create_zip", True)
    kb_name = data.get("kb_name", "")

    try:
        from gangdan.core.export_manager import ExportManager

        manager = ExportManager()
        report = manager.batch_convert_preprints(items, create_zip=create_zip)

        result = report.to_dict()

        if kb_name and report.success_count > 0:
            result["kb_result"] = _add_preprints_to_kb(kb_name, report.results)

        return jsonify(result)
    except Exception as e:
        logger.error("[PreprintAPI] Batch convert failed: %s", e)
        return jsonify({"error": str(e)}), 500


@preprint_bp.route("/batch-convert-stream", methods=["POST"])
def batch_convert_stream() -> Any:
    """Batch convert preprints with SSE progress updates.

    Downloads HTML, TeX, and PDF sources locally first, then converts
    using format priority: HTML > TeX > PDF.

    Request JSON:
        items (list): List of {item_id, title, url, content_type, preprint_id,
                       html_url, tex_source_url, pdf_url, has_html, has_tex}
        create_zip (bool): Whether to create ZIP export (default false)
        kb_name (str): Optional KB name to add results to

    Returns:
        Server-Sent Events stream with per-item progress
    """
    import json as _json
    import time
    import tempfile
    from pathlib import Path

    data = request.get_json(silent=True) or {}
    items = data.get("items", [])

    if not items:
        return jsonify({"error": "items array is required"}), 400

    create_zip = data.get("create_zip", False)
    kb_name = data.get("kb_name", "")

    def generate():
        from gangdan.core.config import DATA_DIR
        from gangdan.core.preprint_converter import PreprintConverter
        from gangdan.core.export_manager import ExportManager

        export_dir = DATA_DIR / "preprint_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        manager = ExportManager(output_dir=export_dir)
        converter = PreprintConverter(fallback_to_pdf=True)
        total = len(items)
        success_count = 0
        fail_count = 0
        results = []

        yield f"data: {_json.dumps({'type': 'start', 'total': total})}\n\n"

        for i, item_data in enumerate(items):
            item_id = item_data.get("item_id", "")
            title = item_data.get("title", "")
            preprint_id = item_data.get("preprint_id", "") or item_id
            authors = item_data.get("authors", []) if isinstance(item_data.get("authors"), list) else []
            year = item_data.get("year", "") or item_data.get("published_date", "")

            yield f"data: {_json.dumps({'type': 'downloading', 'index': i + 1, 'total': total, 'item_id': item_id})}\n\n"

            # Collect all available source URLs
            all_sources = []
            html_url = item_data.get("html_url")
            has_html = item_data.get("has_html", False)
            if html_url:
                all_sources.append(("html", html_url, has_html))

            tex_url = item_data.get("tex_source_url")
            has_tex = item_data.get("has_tex", False)
            if tex_url:
                all_sources.append(("tex", tex_url, has_tex))

            pdf_url = item_data.get("pdf_url")
            if pdf_url:
                all_sources.append(("pdf", pdf_url, True))

            if not all_sources:
                url = item_data.get("url", "")
                content_type = item_data.get("content_type", "html")
                if url:
                    all_sources.append((content_type, url, True))

            if not all_sources:
                result = type("R", (), {"success": False, "error": "No URLs available", "markdown_path": None, "markdown_content": None, "engine": ""})()
                results.append(result)
                fail_count += 1
                progress = {
                    "type": "progress", "index": i + 1, "total": total,
                    "item_id": item_id, "success": False,
                    "success_count": success_count, "fail_count": fail_count,
                    "markdown_path": None, "error": "No URLs available",
                }
                yield f"data: {_json.dumps(progress)}\n\n"
                continue

            # Create persistent output dir for this item
            clean_name = manager._make_clean_filename(title, authors, year, preprint_id or item_id)
            item_dir = manager.output_dir / "preprints" / clean_name
            item_dir.mkdir(parents=True, exist_ok=True)

            # Step 1: Download ALL source formats (best effort)
            source_formats_saved = []
            for fmt, url, available in all_sources:
                try:
                    dl_result = converter.download_source(
                        url, content_type=fmt, output_dir=item_dir, preprint_id=preprint_id,
                    )
                    if dl_result.success:
                        source_formats_saved.append(fmt)
                except Exception as e:
                    logger.warning("[BatchConvert] %s source download %s failed: %s", preprint_id, fmt, e)

            # Step 2: Convert to Markdown using priority chain (HTML > TeX > PDF)
            convert_chain = []
            if has_html and html_url:
                convert_chain.append(("html", html_url))
            if has_tex and tex_url:
                convert_chain.append(("tex", tex_url))
            if pdf_url:
                convert_chain.append(("pdf", pdf_url))
            if not convert_chain:
                for fmt, url, _ in all_sources:
                    convert_chain.append((fmt, url))

            result = None
            for fmt, url in convert_chain:
                try:
                    conv_result = converter.convert_from_url(
                        url, content_type=fmt, output_dir=item_dir, preprint_id=preprint_id,
                    )
                    if conv_result.success and conv_result.markdown_path and Path(conv_result.markdown_path).exists():
                        result = type("R", (), {
                            "success": True,
                            "markdown_path": conv_result.markdown_path,
                            "markdown_content": Path(conv_result.markdown_path).read_text(encoding="utf-8")[:500],
                            "engine": getattr(conv_result, "engine", fmt),
                            "source_path": getattr(conv_result, "source_path", None),
                            "source_format": fmt,
                            "source_formats_saved": source_formats_saved,
                            "error": None,
                            "item_id": item_id,
                            "title": title,
                            "authors": authors,
                            "year": year,
                        })()
                        break
                    else:
                        logger.info("[BatchConvert] %s format=%s failed: %s", preprint_id, fmt, getattr(conv_result, "error", "unknown"))
                except Exception as e:
                    logger.warning("[BatchConvert] %s format=%s exception: %s", preprint_id, fmt, e)

            if result is None:
                result = type("R", (), {"success": False, "error": f"All formats failed for {preprint_id}", "markdown_path": None, "markdown_content": None, "engine": "", "item_id": item_id})()
                fail_count += 1
            else:
                success_count += 1

            results.append(result)

            progress = {
                "type": "progress", "index": i + 1, "total": total,
                "item_id": item_id, "success": result.success,
                "success_count": success_count, "fail_count": fail_count,
                "markdown_path": getattr(result, "markdown_path", None),
                "error": getattr(result, "error", None),
            }
            yield f"data: {_json.dumps(progress)}\n\n"

        kb_result = None
        if kb_name and success_count > 0:
            try:
                kb_result = _add_preprints_to_kb(kb_name, results)
            except Exception as e:
                logger.error("[PreprintAPI] KB add failed in stream: %s", e)
                kb_result = {"success": False, "error": str(e)}

        done = {
            "type": "done",
            "total": total,
            "success_count": success_count,
            "fail_count": fail_count,
            "kb_result": kb_result,
        }
        yield f"data: {_json.dumps(done)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@preprint_bp.route("/add-to-kb", methods=["POST"])
def add_preprints_to_kb() -> Any:
    """Add preprints to a custom knowledge base.

    Request JSON:
        kb_name (str): KB display name (creates if not exists)
        preprints (list): List of preprint dicts with id, title, markdown_path, etc.
        index_to_chroma (bool): Whether to index content (default true)

    Returns:
        JSON with add result
    """
    data = request.get_json(silent=True) or {}
    kb_name = data.get("kb_name", "")
    preprints = data.get("preprints", [])
    index_to_chroma = data.get("index_to_chroma", True)

    if not kb_name or not preprints:
        return jsonify({"error": "kb_name and preprints are required"}), 400

    try:
        result = _add_preprints_to_kb_direct(kb_name, preprints, index_to_chroma)
        return jsonify(result)
    except Exception as e:
        logger.error("[PreprintAPI] Add to KB failed: %s", e)
        return jsonify({"error": str(e)}), 500


def _add_preprints_to_kb(kb_name: str, results: list) -> dict:
    """Add batch convert results to a KB."""
    preprint_items = []
    for r in results:
        if r.get("success") and r.get("markdown_path"):
            preprint_items.append({
                "doc_id": r.get("item_id", ""),
                "title": r.get("title", ""),
                "authors": r.get("authors", []),
                "published_date": r.get("year", ""),
                "source_type": "preprint",
                "source_platform": "arxiv",
                "markdown_path": r.get("markdown_path", ""),
                "content_preview": r.get("markdown_content", ""),
                "source_path": r.get("source_path"),
                "source_format": r.get("source_format", ""),
                "source_formats_saved": r.get("source_formats_saved", []),
                "url": r.get("url", ""),
            })
    return _add_preprints_to_kb_direct(kb_name, preprint_items, index_to_chroma=True)


def _add_preprints_to_kb_direct(kb_name: str, preprints: list, index_to_chroma: bool = True) -> dict:
    """Add preprint items to a custom KB."""
    from gangdan.kb_routes import get_kb_manager
    from gangdan.core.kb_manager import KBDocEntry
    from gangdan.core.config import DATA_DIR, sanitize_kb_name
    from datetime import datetime
    import re as _re
    from pathlib import Path

    manager = get_kb_manager()

    # Find KB by display_name or internal_name
    kb = None
    existing_kb = False
    sanitized = sanitize_kb_name(kb_name)
    all_kbs = manager.list_kbs()
    for k in all_kbs:
        if k.internal_name == kb_name or k.internal_name == sanitized or k.display_name == kb_name:
            kb = k
            existing_kb = True
            break
    if kb is None:
        kb = manager.get_kb(kb_name) or manager.get_kb(sanitized)

    if kb is None:
        kb = manager.create_kb(kb_name, f"Preprint collection: {kb_name}")
        if kb is None:
            return {"success": False, "error": f"Failed to create KB: {kb_name}"}

    # Get existing doc IDs for duplicate detection
    existing_docs = set()
    try:
        for doc in manager.get_documents(kb.internal_name):
            existing_docs.add(doc.doc_id)
    except Exception:
        pass

    added = 0
    failed = 0
    skipped = 0

    for p in preprints:
        preprint_id = p.get("preprint_id", "") or p.get("doc_id", "")
        title = p.get("title", "")

        if not preprint_id or not title:
            logger.warning("[PreprintAPI] Skipping item without ID or title: %s", preprint_id or title)
            failed += 1
            continue

        authors = p.get("authors", [])
        year = p.get("published_date", "") or p.get("year", "")
        if year:
            year = re.sub(r'\D', '', str(year))[:4]

        doc_id = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', preprint_id)
        if not doc_id.strip('_') or len(doc_id.strip('_')) < 2:
            clean = re.sub(r'[^a-zA-Z0-9._-]', '_', title[:80]).strip('_')
            doc_id = clean if clean else doc_id

        # Check duplicate
        if doc_id in existing_docs:
            logger.info("[PreprintAPI] Skipping duplicate doc: %s", doc_id)
            skipped += 1
            continue

        source_format = p.get("source_format", "")
        source_formats_saved = p.get("source_formats_saved", [])
        source_path = p.get("source_path", "")

        doc = KBDocEntry(
            doc_id=doc_id,
            title=title,
            source_type=p.get("source_type", "preprint"),
            source_id=preprint_id,
            source_platform=p.get("source_platform", "arxiv"),
            markdown_path=p.get("markdown_path", ""),
            content_preview=p.get("content_preview", ""),
            authors=authors,
            published_date=year or p.get("published_date", ""),
            url=p.get("url", ""),
            tags=p.get("tags", []),
            added_at=datetime.now().isoformat(),
        )

        # Write full-text markdown to KB directory
        kb_dir = DATA_DIR / "custom_kbs" / kb.internal_name
        kb_dir.mkdir(parents=True, exist_ok=True)

        # Generate Chou-style clean name: Author et al. (Year) - Title
        def _clean_for_filename(s):
            return _re.sub(r'[<>:"/\\|?*]', '', s).strip()
        def _make_chou_name(title, authors, year):
            t = _clean_for_filename(title)
            prefix = ""
            if authors and len(authors) > 0:
                fa = str(authors[0]).strip()
                parts = fa.split()
                surname = parts[-1] if parts else fa
                prefix = f"{surname} et al." if len(authors) > 1 else surname
            ystr = str(year).strip()[:4] if year else ""
            if prefix and ystr:
                return f"{prefix} ({ystr}) - {t}"
            elif ystr:
                return f"({ystr}) - {t}"
            elif prefix:
                return f"{prefix} - {t}"
            return t if t else doc_id

        chou_name = _make_chou_name(title, authors, year)
        safe_name = _re.sub(r'[^a-zA-Z0-9._\-() ]', '', chou_name)[:180].strip()
        md_filename = safe_name + ".md" if safe_name else doc_id + ".md"
        md_path = kb_dir / md_filename

        # Resolve full-text markdown content
        # Priority: 1) markdown_path points to existing file  2) search preprint_exports  3) fallback to abstract
        md_content = ""
        resolved_md_path = None
        existing_md = p.get("markdown_path", "")
        if existing_md and Path(existing_md).exists():
            resolved_md_path = Path(existing_md)
        else:
            # Search for full-text MD in preprint_exports by arXiv ID
            exports_dir = DATA_DIR / "preprint_exports" / "preprints"
            safe_pid = re.sub(r'[<>:"/\\|?*\x00-\x1f()]', '_', preprint_id)
            if exports_dir.exists():
                # Try: {arxiv_id}.md inside any subdirectory
                for subdir in exports_dir.iterdir():
                    if not subdir.is_dir():
                        continue
                    candidate = subdir / f"{safe_pid}.md"
                    if not candidate.exists():
                        # Also try preprint_id without sanitization or with different sanitization
                        alt_candidates = list(subdir.glob(f"{preprint_id}.md")) + list(subdir.glob("*.md"))
                        for ac in alt_candidates:
                            if ac.stem.replace('_', '.').replace('..', '.') == safe_pid:
                                candidate = ac
                                break
                    if candidate.exists() and candidate.stat().st_size > 500:
                        resolved_md_path = candidate
                        logger.info("[PreprintAPI] Found full-text MD for %s: %s", preprint_id, candidate)
                        break

        if resolved_md_path and resolved_md_path.exists():
            md_content = resolved_md_path.read_text(encoding="utf-8")
            md_path.write_text(md_content, encoding="utf-8")
            logger.info("[PreprintAPI] Wrote full-text MD for %s (%d chars)", preprint_id, len(md_content))
        else:
            md_content = p.get("content_preview", "") or p.get("abstract", "") or ""
            if len(md_content.strip()) < 50 and title:
                md_content = f"# {title}\n\nAuthors: {', '.join(authors) if authors else 'Unknown'}\n\n{md_content}"
            if not md_content.strip():
                md_content = f"# {title}\n\nAuthors: {', '.join(authors) if authors else 'Unknown'}"
            md_path.write_text(md_content, encoding="utf-8")
            logger.warning("[PreprintAPI] No full-text MD found for %s, wrote abstract (%d chars)", preprint_id, len(md_content))

        doc.markdown_path = str(md_path)
        doc.content_preview = md_content

        # Copy ALL source files (HTML, TeX, PDF) to the KB directory for persistence
        import shutil as _shutil
        ext_map = {"html": ".html", "tex": ".tar.gz", "pdf": ".pdf", "xml": ".xml"}
        actual_source_formats = list(source_formats_saved) if source_formats_saved else []
        source_dirs_searched = set()

        # 1. Copy the primary source file (from the format that succeeded in conversion)
        if source_path and Path(source_path).exists():
            src_file = Path(source_path)
            src_ext = ext_map.get(source_format, src_file.suffix or ".bin")
            dest_src = kb_dir / f"{doc_id}_source{src_ext}"
            try:
                _shutil.copy2(src_file, dest_src)
                logger.info("[PreprintAPI] Copied primary source %s -> %s", src_file.name, dest_src.name)
                if source_format and source_format not in actual_source_formats:
                    actual_source_formats.append(source_format)
            except Exception as e:
                logger.warning("[PreprintAPI] Failed to copy source file: %s", e)

        # 2. Copy source files from preprint_exports directory (even without markdown_path)
        #    Searches by arXiv ID pattern: {safe_pid}_source.{ext}
        exports_dir = DATA_DIR / "preprint_exports" / "preprints"
        safe_pid = re.sub(r'[<>:"/\\|?*\x00-\x1f()]', '_', preprint_id)
        if exports_dir.exists():
            for subdir in exports_dir.iterdir():
                if not subdir.is_dir() or str(subdir) in source_dirs_searched:
                    continue
                source_dirs_searched.add(str(subdir))
                # Check if this subdir contains files for our preprint_id
                has_our_files = False
                for fmt, ext in ext_map.items():
                    candidate = subdir / f"{safe_pid}_source{ext}"
                    if candidate.exists():
                        has_our_files = True
                        break
                if not has_our_files:
                    # Also try glob for any *_source files and check by preprint_id
                    pid_variants = [safe_pid, preprint_id]
                    for src_file in subdir.glob("*_source.*"):
                        src_stem = src_file.stem.replace("_source", "")
                        if any(v == src_stem for v in pid_variants):
                            has_our_files = True
                            break
                if not has_our_files:
                    continue

                for fmt, ext in ext_map.items():
                    # Try safe_pid first, then glob
                    src_candidate = subdir / f"{safe_pid}_source{ext}"
                    if not src_candidate.exists():
                        alt_srcs = list(subdir.glob(f"*_source{ext}"))
                        for alt in alt_srcs:
                            alt_stem = alt.stem.replace("_source", "")
                            if alt_stem == safe_pid or alt_stem == preprint_id:
                                src_candidate = alt
                                break
                        if not src_candidate.exists() and alt_srcs:
                            src_candidate = alt_srcs[0]
                    if src_candidate.exists():
                        dest_name = f"{doc_id}_source{ext}"
                        dest_path = kb_dir / dest_name
                        if dest_path.exists():
                            continue
                        try:
                            _shutil.copy2(src_candidate, dest_path)
                            logger.info("[PreprintAPI] Copied source %s -> %s", src_candidate.name, dest_path.name)
                            if fmt not in actual_source_formats:
                                actual_source_formats.append(fmt)
                        except Exception as e:
                            logger.warning("[PreprintAPI] Failed to copy source: %s", e)

        # Also copy from markdown_path's parent dir if available
        if existing_md and Path(existing_md).exists():
            item_dir = Path(existing_md).parent
            if str(item_dir) not in source_dirs_searched:
                for fmt, ext in ext_map.items():
                    src_candidate = item_dir / f"{safe_pid}_source{ext}"
                    if not src_candidate.exists():
                        alt_srcs = list(item_dir.glob(f"*_source{ext}"))
                        src_candidate = alt_srcs[0] if alt_srcs else src_candidate
                    if src_candidate.exists():
                        dest_name = f"{doc_id}_source{ext}"
                        dest_path = kb_dir / dest_name
                        if dest_path.exists():
                            continue
                        try:
                            _shutil.copy2(src_candidate, dest_path)
                            logger.info("[PreprintAPI] Copied source from md dir %s -> %s", src_candidate.name, dest_path.name)
                            if fmt not in actual_source_formats:
                                actual_source_formats.append(fmt)
                        except Exception as e:
                            logger.warning("[PreprintAPI] Failed to copy source from md dir: %s", e)

        # Store source_formats as doc metadata for export
        if actual_source_formats:
            doc.tags = list(set(list(doc.tags or []) + [f"source_formats:{','.join(actual_source_formats)}"]))
        doc.source_format = source_format or (actual_source_formats[0] if actual_source_formats else "")
        doc.source_formats_saved = actual_source_formats

        if manager.add_document(kb.internal_name, doc, index_to_chroma=index_to_chroma):
            added += 1
            existing_docs.add(doc_id)
        else:
            failed += 1

    # Also index full text into main ChromaDB (used by chat system)
    if index_to_chroma and added > 0:
        try:
            from gangdan.app import CHROMA as main_chroma
            if main_chroma and main_chroma.is_available:
                for p in preprints:
                    pid = p.get("preprint_id", "") or p.get("doc_id", "")
                    title = p.get("title", "")
                    # Read full markdown content from the KB file for indexing
                    existing_md = p.get("markdown_path", "")
                    if existing_md and Path(existing_md).exists():
                        full_content = Path(existing_md).read_text(encoding="utf-8")
                    else:
                        full_content = p.get("content_preview", "") or p.get("abstract", "")
                    if not full_content or len(full_content.strip()) < 50:
                        continue
                    try:
                        main_chroma.add_documents(
                            kb.internal_name,
                            [full_content],
                            [{"title": title, "doc_id": pid, "chunk_index": 0}],
                            [pid],
                        )
                    except Exception:
                        pass
        except ImportError:
            pass
        except Exception as e:
            logger.warning("[PreprintAPI] Main ChromaDB index failed: %s", e)
    try:
        from gangdan.core.config import save_user_kb
        doc_count = len(existing_docs)
        existed_before = existing_kb
        if not existed_before:
            # New KB: register with empty languages (auto-detection will fill)
            save_user_kb(kb.internal_name, kb.display_name, doc_count, languages=[])
        else:
            save_user_kb(kb.internal_name, kb.display_name, doc_count, languages=[])
    except Exception as e:
        logger.warning("[PreprintAPI] Failed to register KB in manifest: %s", e)

    return {
        "success": True,
        "kb_name": kb.internal_name,
        "kb_display": kb.display_name,
        "existing_kb": existing_kb,
        "added": added,
        "failed": failed,
        "skipped": skipped,
    }
