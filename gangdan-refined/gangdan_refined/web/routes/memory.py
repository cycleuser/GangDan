"""Memory store API routes for GangDan Refined."""

from flask import Blueprint, jsonify, request
from ...core.config import DATA_DIR
from ...storage.memory_store import MemoryStore

memory_bp = Blueprint("memory", __name__, url_prefix="/api/memory")

def _store():
    return MemoryStore(DATA_DIR)


@memory_bp.route("/remember", methods=["POST"])
def api_memory_remember():
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"success": False, "error": "Content is required"}), 400
    store = _store()
    entry = store.remember(
        content=content,
        memory_type=data.get("memory_type", "fact"),
        importance=float(data.get("importance", 0.5)),
        metadata=data.get("metadata"),
    )
    return jsonify({"success": True, "entry": entry})


@memory_bp.route("/list")
def api_memory_list():
    store = _store()
    mem_type = request.args.get("type")
    limit = min(int(request.args.get("limit", 50)), 200)
    entries = store.list_memories(memory_type=mem_type, limit=limit)
    return jsonify({"results": entries})


@memory_bp.route("/search")
def api_memory_search():
    q = (request.args.get("q") or "").strip()
    if not q: return jsonify({"results": []})
    store = _store()
    limit = min(int(request.args.get("limit", 10)), 100)
    results = store.search_memories(q, limit=limit)
    return jsonify({"results": results})


@memory_bp.route("/forget", methods=["POST"])
def api_memory_forget():
    data = request.get_json(silent=True) or {}
    memory_id = (data.get("memory_id") or "").strip()
    if not memory_id:
        return jsonify({"success": False, "error": "memory_id is required"}), 400
    store = _store()
    ok = store.forget(memory_id)
    return jsonify({"success": ok})
