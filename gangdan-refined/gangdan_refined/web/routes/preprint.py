"""Preprint route blueprint.

Provides all /api/preprint/* endpoints expected by the frontend JS.
"""

from __future__ import annotations

import json

from flask import Blueprint, request, jsonify, Response, stream_with_context

from ...core.config import CONFIG, DATA_DIR

preprint_bp = Blueprint("preprint", __name__)


@preprint_bp.route("/search", methods=["POST"])
def preprint_search():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    platform = data.get("platform", "arxiv")
    max_results = data.get("max_results", 20)
    try:
        from ...document.preprint.fetcher import PreprintFetcher
        fetcher = PreprintFetcher()
        results = fetcher.search(query=query, platform=platform, max_results=max_results)
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@preprint_bp.route("/categories", methods=["GET"])
def preprint_categories():
    try:
        from ...document.preprint.categories import PREPRINT_CATEGORIES
        return jsonify({"success": True, "categories": PREPRINT_CATEGORIES})
    except ImportError:
        return jsonify({"success": True, "categories": []})


@preprint_bp.route("/recent", methods=["GET"])
def preprint_recent():
    try:
        from ...document.preprint.fetcher import PreprintFetcher
        fetcher = PreprintFetcher()
        results = fetcher.get_recent()
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@preprint_bp.route("/convert", methods=["POST"])
def preprint_convert():
    data = request.get_json(silent=True) or {}
    paper_id = data.get("paper_id", "")
    source_url = data.get("source_url", "")
    if not paper_id and not source_url:
        return jsonify({"success": False, "error": "paper_id or source_url required"}), 400
    try:
        from ...document.preprint.converter import PreprintConverter
        converter = PreprintConverter()
        result = converter.convert(paper_id=paper_id, source_url=source_url)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@preprint_bp.route("/kb/index", methods=["POST"])
def preprint_kb_index():
    data = request.get_json(silent=True) or {}
    paper_id = data.get("paper_id", "")
    kb_name = data.get("kb_name", "preprints")
    try:
        from ...document.preprint.kb_manager import PreprintKBManager
        mgr = PreprintKBManager()
        result = mgr.index_paper(paper_id=paper_id, kb_name=kb_name)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@preprint_bp.route("/batch-convert-stream", methods=["POST"])
def preprint_batch_convert_stream():
    data = request.get_json(silent=True) or {}
    paper_ids = data.get("paper_ids", [])
    try:
        from ...document.preprint.batch import BatchConverter

        def gen():
            converter = BatchConverter()
            for event in converter.convert_stream(paper_ids):
                yield f"data: {json.dumps(event)}\n\n"
            yield 'data: {"type": "done"}\n\n'

        return Response(gen(), mimetype="text/event-stream")
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@preprint_bp.route("/add-to-kb", methods=["POST"])
def preprint_add_to_kb():
    data = request.get_json(silent=True) or {}
    paper_id = data.get("paper_id", "")
    kb_name = data.get("kb_name", "preprints")
    try:
        from ...document.preprint.kb_manager import PreprintKBManager
        mgr = PreprintKBManager()
        result = mgr.add_to_kb(paper_id=paper_id, kb_name=kb_name)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Scheduler ---

@preprint_bp.route("/scheduler/status", methods=["GET"])
def preprint_scheduler_status():
    try:
        from ...document.preprint.scheduler import PreprintScheduler
        scheduler = PreprintScheduler()
        return jsonify({"success": True, "status": scheduler.get_status()})
    except Exception:
        return jsonify({"success": True, "status": "inactive", "running": False})


@preprint_bp.route("/scheduler/start", methods=["POST"])
def preprint_scheduler_start():
    data = request.get_json(silent=True) or {}
    interval = data.get("interval", 3600)
    try:
        from ...document.preprint.scheduler import PreprintScheduler
        scheduler = PreprintScheduler()
        scheduler.start(interval=interval)
        return jsonify({"success": True, "interval": interval})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@preprint_bp.route("/scheduler/stop", methods=["POST"])
def preprint_scheduler_stop():
    try:
        from ...document.preprint.scheduler import PreprintScheduler
        scheduler = PreprintScheduler()
        scheduler.stop()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@preprint_bp.route("/scheduler/interval", methods=["POST"])
def preprint_scheduler_interval():
    data = request.get_json(silent=True) or {}
    interval = data.get("interval", 3600)
    try:
        from ...document.preprint.scheduler import PreprintScheduler
        scheduler = PreprintScheduler()
        scheduler.set_interval(interval)
        return jsonify({"success": True, "interval": interval})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Subscriptions ---

@preprint_bp.route("/subscriptions", methods=["GET"])
def preprint_subscriptions_get():
    try:
        from ...document.preprint.scheduler import PreprintScheduler
        scheduler = PreprintScheduler()
        subs = scheduler.get_subscriptions()
        return jsonify({"success": True, "subscriptions": subs})
    except ImportError:
        return jsonify({"success": True, "subscriptions": []})
    except Exception as e:
        return jsonify({"success": True, "subscriptions": [], "error": str(e)})


@preprint_bp.route("/subscriptions", methods=["POST"])
def preprint_subscriptions_create():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    query = data.get("query", "")
    platform = data.get("platform", "arxiv")
    try:
        from ...document.preprint.scheduler import PreprintScheduler
        scheduler = PreprintScheduler()
        scheduler.add_subscription(name=name, query=query, platform=platform)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@preprint_bp.route("/subscriptions/<name>", methods=["DELETE"])
def preprint_subscriptions_delete(name):
    try:
        from ...document.preprint.scheduler import PreprintScheduler
        scheduler = PreprintScheduler()
        scheduler.remove_subscription(name)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500