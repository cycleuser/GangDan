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
                "source_type": "preprint",
                "markdown_path": r.get("markdown_path", ""),
                "content_preview": r.get("markdown_content", "")[:500],
            })
    return _add_preprints_to_kb_direct(kb_name, preprint_items, index_to_chroma=True)


def _add_preprints_to_kb_direct(kb_name: str, preprints: list, index_to_chroma: bool = True) -> dict:
    """Add preprint items to a custom KB."""
    from gangdan.core.kb_manager import CustomKBManager, KBDocEntry
    from gangdan.core.config import DATA_DIR, sanitize_kb_name
    from datetime import datetime
    import re as _re
    from pathlib import Path

    manager = CustomKBManager()

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
            import re as _re
            year = _re.sub(r'\D', '', str(year))[:4]

        doc_id = preprint_id
        if not doc_id.replace('-', '').replace('.', '').replace('_', '').isalnum():
            import re as _re2
            clean = _re2.sub(r'[^a-zA-Z0-9._-]', '_', title[:80]).strip('_')
            doc_id = clean if clean else preprint_id

        # Check duplicate
        if doc_id in existing_docs:
            logger.info("[PreprintAPI] Skipping duplicate doc: %s", doc_id)
            skipped += 1
            continue

        doc = KBDocEntry(
            doc_id=doc_id,
            title=title,
            source_type=p.get("source_type", "preprint"),
            source_id=preprint_id,
            source_platform=p.get("source_platform", "arxiv"),
            markdown_path=p.get("markdown_path", ""),
            content_preview=p.get("content_preview", "")[:500],
            authors=authors,
            published_date=year or p.get("published_date", ""),
            url=p.get("url", ""),
            tags=p.get("tags", []),
            added_at=datetime.now().isoformat(),
        )

        # Write abstract/preview as a markdown file for ChromaDB indexing
        kb_dir = DATA_DIR / "custom_kbs" / kb.internal_name
        kb_dir.mkdir(parents=True, exist_ok=True)

        # Generate Chou-style clean name: Author et al. (Year) - Title
        def _clean_for_filename(s):
            return _re.sub(r'[<>:\"/\\|?*]', '', s).strip()
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

        # Write or use existing markdown for ChromaDB indexing
        existing_md = p.get("markdown_path", "")
        if existing_md and Path(existing_md).exists():
            md_path = Path(existing_md)
            md_content = md_path.read_text(encoding="utf-8")[:500]
        else:
            md_content = p.get("content_preview", "") or p.get("abstract", "") or ""
            if len(md_content.strip()) < 50 and title:
                md_content = f"# {title}\n\nAuthors: {', '.join(authors) if authors else 'Unknown'}\n\n{md_content}"
            if not md_content.strip():
                md_content = f"# {title}\n\nAuthors: {', '.join(authors) if authors else 'Unknown'}"
            md_path.write_text(md_content, encoding="utf-8")
        doc.markdown_path = str(md_path)
        doc.content_preview = md_content[:500]

        if manager.add_document(kb.internal_name, doc, index_to_chroma=index_to_chroma):
            added += 1
            existing_docs.add(doc_id)
        else:
            failed += 1

    # Also index into main ChromaDB (used by chat system)
    if index_to_chroma and added > 0:
        try:
            from gangdan.app import CHROMA as main_chroma
            if main_chroma and main_chroma.is_available:
                for p in preprints:
                    pid = p.get("preprint_id", "") or p.get("doc_id", "")
                    title = p.get("title", "")
                    abstract = p.get("abstract", "") or p.get("content_preview", "")
                    if not abstract or len(abstract) < 50:
                        continue
                    content = f"# {title}\n\n{abstract}"
                    try:
                        main_chroma.add_documents(
                            kb.internal_name,
                            [content],
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
