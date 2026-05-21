"""Knowledge base route blueprint.

Provides all /api/kb/* endpoints expected by the frontend JS.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from flask import Blueprint, request, jsonify, send_file, abort

from ...core.config import CONFIG, DATA_DIR, DOCS_DIR, CHROMA_DIR
from ...core.errors import GangDanError, create_error_response

kb_bp = Blueprint("kb", __name__)


def _resolve_kb_dir(kb_name: str) -> tuple:
    from ...core.config import sanitize_kb_name
    from ...storage.kb_manager import CUSTOM_KBS_DIR

    candidates = [kb_name]
    if not kb_name.startswith("user_"):
        candidates.append(f"user_{kb_name}")

    for name in candidates:
        docs_path = DOCS_DIR / name
        if docs_path.exists():
            return (docs_path, name)
        custom_path = CUSTOM_KBS_DIR / name
        if custom_path.exists():
            return (custom_path, name)

    return (None, kb_name)


def _get_chroma():
    from ...storage.chroma_manager import ChromaManager
    from ...core.config import CHROMA_DIR
    try:
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        return chroma if chroma.client is not None else None
    except Exception:
        return None


# --- KB List & CRUD ---

@kb_bp.route("/list", methods=["GET"])
def kb_list():
    from ...storage.kb_manager import CustomKBManager
    try:
        mgr = CustomKBManager()
        kbs = mgr.list_kbs()
        return jsonify({"success": True, "kbs": [kb.to_dict() for kb in kbs]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@kb_bp.route("/create", methods=["POST"])
def kb_create():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    if not name:
        return jsonify({"success": False, "error": "Name is required"}), 400
    try:
        from ...storage.kb_manager import CustomKBManager
        mgr = CustomKBManager()
        kb = mgr.create_kb(
            display_name=name,
            description=data.get("description", ""),
            tags=data.get("tags", []),
        )
        return jsonify({"success": True, "kb": kb.to_dict()})
    except GangDanError as e:
        return jsonify(create_error_response(e)), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@kb_bp.route("/<internal_name>", methods=["GET"])
def kb_get(internal_name):
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
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    if not query:
        return jsonify({"success": False, "error": "Query is required"}), 400
    try:
        from ...storage.kb_manager import CustomKBManager
        mgr = CustomKBManager()
        results = mgr.search_kb(internal_name, query, limit=data.get("limit", 20))
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@kb_bp.route("/<internal_name>/documents", methods=["GET"])
def kb_documents(internal_name):
    chroma = _get_chroma()
    if not chroma:
        return jsonify({"success": False, "error": "Vector DB not available"}), 500
    try:
        files = chroma.get_collection_files(internal_name)
        return jsonify({"success": True, "name": internal_name, "files": files, "total_docs": sum(f.get("doc_count", 0) for f in files)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@kb_bp.route("/<internal_name>/documents", methods=["POST"])
def kb_add_document(internal_name):
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


# --- KB Reindex ---

@kb_bp.route("/<internal_name>/reindex", methods=["POST"])
@kb_bp.route("/reindex", methods=["POST"])
def kb_reindex(internal_name=None):
    if internal_name is None:
        data = request.get_json(silent=True) or {}
        internal_name = data.get("name", "")
    if not internal_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    source_dir, resolved_name = _resolve_kb_dir(internal_name)
    if source_dir is None:
        return jsonify({"success": False, "error": f"KB directory not found: {internal_name}"}), 404

    chroma = _get_chroma()
    if chroma:
        try:
            if chroma.collection_exists(resolved_name):
                chroma.delete_collection(resolved_name)
        except Exception:
            pass

    try:
        from ...storage.doc_manager import DocManager
        from ...llm.ollama import OllamaClient
        ollama = OllamaClient(CONFIG.llm.ollama_url)
        doc_mgr = DocManager(source_dir, chroma, ollama)
        files, chunks, images = doc_mgr.index_source(resolved_name)
        return jsonify({"success": True, "files": files, "chunks": chunks, "images": images})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- KB Files ---

@kb_bp.route("/files", methods=["GET"])
def kb_files():
    kb_name = request.args.get("name", "").strip()
    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    chroma = _get_chroma()
    if not chroma:
        return jsonify({"success": False, "error": "Vector database not available"}), 500

    if not chroma.collection_exists(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    try:
        files = chroma.get_collection_files(kb_name)
        kb_dir, resolved_name = _resolve_kb_dir(kb_name)
        if resolved_name != kb_name:
            kb_name = resolved_name

        SOURCE_EXTENSIONS = {".pdf", ".caj", ".html", ".htm", ".tex", ".latex", ".epub", ".docx"}
        indexed_names = {f["file"] for f in files}

        if kb_dir is not None and kb_dir.exists():
            for ext in SOURCE_EXTENSIONS:
                for src_file in sorted(kb_dir.rglob(f"*{ext}")):
                    fname = src_file.name
                    if fname not in indexed_names:
                        files.append({"file": fname, "doc_count": 0, "language": ext.lstrip("."), "is_source": True})
                        indexed_names.add(fname)

        return jsonify({"success": True, "name": kb_name, "files": files, "total_docs": sum(f.get("doc_count", 0) for f in files)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- KB Delete Files ---

@kb_bp.route("/delete-files", methods=["POST"])
def kb_delete_files():
    data = request.get_json(silent=True) or {}
    kb_name = data.get("name", "").strip()
    file_names = data.get("files", [])

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400
    if not file_names:
        return jsonify({"success": False, "error": "No files specified"}), 400

    chroma = _get_chroma()
    deleted = []
    errors = []

    if chroma and chroma.collection_exists(kb_name):
        for fname in file_names:
            try:
                chroma.delete_documents(kb_name, {"file": fname})
                deleted.append(fname)
            except Exception as e:
                errors.append({"file": fname, "error": str(e)})

    kb_dir, _ = _resolve_kb_dir(kb_name)
    if kb_dir and kb_dir.exists():
        for fname in file_names:
            for fpath in kb_dir.rglob(fname):
                try:
                    fpath.unlink()
                except Exception as e:
                    if fname not in [e2.get("file") for e2 in errors]:
                        errors.append({"file": fname, "error": str(e)})

    return jsonify({"success": True, "deleted": deleted, "errors": errors})


# --- KB Export Files ---

@kb_bp.route("/export-files", methods=["POST"])
def kb_export_files():
    data = request.get_json(silent=True) or {}
    kb_name = data.get("name", "").strip()
    file_names = data.get("files", [])
    export_format = data.get("format", "markdown")

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    kb_dir, _ = _resolve_kb_dir(kb_name)
    if kb_dir is None:
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    try:
        import zipfile
        import io
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in file_names:
                fpath = kb_dir / fname
                if fpath.exists():
                    zf.write(str(fpath), fname)
                else:
                    for p in kb_dir.rglob(fname):
                        zf.write(str(p), p.relative_to(kb_dir))
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype="application/zip", as_attachment=True, download_name=f"{kb_name}_export.zip")
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- KB Image ---

@kb_bp.route("/image/<kb_name>/<path:image_name>")
def kb_image(kb_name, image_name):
    kb_dir, _ = _resolve_kb_dir(kb_name)
    if kb_dir is None:
        abort(404)

    image_path = kb_dir / image_name
    if not image_path.exists():
        for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
            candidate = kb_dir / f"{image_name}{ext}"
            if candidate.exists():
                image_path = candidate
                break

    if not image_path.exists():
        abort(404)

    from flask import send_from_directory
    return send_from_directory(str(image_path.parent), image_path.name)


# --- KB Gallery ---

@kb_bp.route("/gallery", methods=["GET"])
def kb_gallery():
    from ...storage.image_handler import ImageHandler
    kb_name = request.args.get("name", "").strip()
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    if not kb_name:
        available = [d.name for d in DOCS_DIR.iterdir() if d.is_dir()] if DOCS_DIR.exists() else []
        return jsonify({"success": False, "error": "KB name is required", "available_kbs": available}), 400

    kb_dir, resolved_name = _resolve_kb_dir(kb_name)
    if kb_dir is None:
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    try:
        handler = ImageHandler()
        images = handler.list_images(kb_dir, limit=limit, offset=offset)
        return jsonify({"success": True, "images": images, "kb": resolved_name, "total": len(images)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- KB Image Search ---

@kb_bp.route("/images/search", methods=["GET"])
def kb_images_search():
    from ...storage.image_handler import ImageHandler
    kb_name = request.args.get("name", "").strip()
    query = request.args.get("query", "").lower()
    limit = int(request.args.get("limit", 50))

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    kb_dir, resolved_name = _resolve_kb_dir(kb_name)
    if kb_dir is None:
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    try:
        handler = ImageHandler()
        images = handler.search_images(kb_dir, query=query, limit=limit)
        return jsonify({"success": True, "images": images, "kb": resolved_name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@kb_bp.route("/images/search-advanced", methods=["POST"])
def kb_images_search_advanced():
    from ...storage.image_handler import ImageHandler
    data = request.get_json(silent=True) or {}
    kb_name = data.get("name", "").strip()
    query = data.get("query", "").lower()
    filters = data.get("filters", {})
    limit = data.get("limit", 50)

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    kb_dir, resolved_name = _resolve_kb_dir(kb_name)
    if kb_dir is None:
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    try:
        handler = ImageHandler()
        images = handler.search_images(kb_dir, query=query, filters=filters, limit=limit)
        return jsonify({"success": True, "images": images, "kb": resolved_name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- KB Literature Review ---

@kb_bp.route("/literature-review", methods=["POST"])
def kb_literature_review():
    data = request.get_json(silent=True) or {}
    kb_name = data.get("kb_name", data.get("name", "")).strip()
    topic = data.get("topic", "").strip()
    model = data.get("model", "")

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    chroma = _get_chroma()
    if not chroma or not chroma.collection_exists(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    try:
        from ...llm.factory import create_chat_client
        client = create_chat_client()
        model_name = model or CONFIG.llm.chat_model

        results = chroma.search(kb_name, topic or "overview", n_results=20)
        context = "\n".join(r.get("content", "") for r in results if r.get("content"))

        prompt = f"Write a literature review based on the following documents about '{topic}':\n\n{context}"
        review = client.chat(messages=[{"role": "user", "content": prompt}], model=model_name)
        return jsonify({"success": True, "review": review})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- KB Paper ---

@kb_bp.route("/paper", methods=["POST"])
def kb_paper():
    data = request.get_json(silent=True) or {}
    kb_name = data.get("kb_name", data.get("name", "")).strip()
    topic = data.get("topic", "").strip()
    paper_type = data.get("type", "review")
    model = data.get("model", "")

    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    chroma = _get_chroma()
    if not chroma or not chroma.collection_exists(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    try:
        from ...llm.factory import create_chat_client
        client = create_chat_client()
        model_name = model or CONFIG.llm.chat_model

        results = chroma.search(kb_name, topic, n_results=20)
        context = "\n".join(r.get("content", "") for r in results if r.get("content"))

        type_prompts = {
            "review": "Write an academic review paper",
            "survey": "Write a survey paper",
            "report": "Write a research report",
        }
        prompt = f"{type_prompts.get(paper_type, 'Write an academic paper')} about '{topic}' based on:\n\n{context}"
        paper = client.chat(messages=[{"role": "user", "content": prompt}], model=model_name)
        return jsonify({"success": True, "paper": paper})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- KB Update ---

@kb_bp.route("/update", methods=["POST"])
def kb_update():
    data = request.get_json(silent=True) or {}
    kb_name = data.get("name", "").strip()
    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400
    try:
        from ...storage.kb_manager import CustomKBManager
        mgr = CustomKBManager()
        updates = {k: v for k, v in data.items() if k not in ("name",)}
        mgr.update_kb(kb_name, **updates)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- KB Detailed Stats ---

@kb_bp.route("/detailed-stats", methods=["GET"])
def kb_detailed_stats():
    kb_name = request.args.get("name", "").strip()
    if not kb_name:
        all_stats = {}
        chroma = _get_chroma()
        if chroma:
            for collection in chroma.list_collections():
                count = chroma.get_collection_count(collection)
                all_stats[collection] = {"document_count": count}
        return jsonify({"success": True, "stats": all_stats})

    chroma = _get_chroma()
    if not chroma or not chroma.collection_exists(kb_name):
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    try:
        count = chroma.get_collection_count(kb_name)
        files = chroma.get_collection_files(kb_name)
        return jsonify({"success": True, "stats": {"document_count": count, "files": len(files), "details": files}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- KB Annotate Dimensions ---

@kb_bp.route("/annotate-dimensions", methods=["POST"])
def kb_annotate_dimensions():
    data = request.get_json(silent=True) or {}
    kb_name = data.get("kb_name", data.get("name", "")).strip()
    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400
    return jsonify({"success": True, "message": "Dimension annotation not yet implemented in refined version"})


# --- KB Analytics ---

@kb_bp.route("/<internal_name>/analytics/topics", methods=["POST"])
def kb_analytics_topics(internal_name):
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "topics": [], "message": "Analytics not yet implemented"})


@kb_bp.route("/<internal_name>/analytics/point-cloud", methods=["POST"])
def kb_analytics_point_cloud(internal_name):
    return jsonify({"success": True, "points": [], "message": "Analytics not yet implemented"})


@kb_bp.route("/<internal_name>/analytics/opinions", methods=["POST"])
def kb_analytics_opinions(internal_name):
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "opinions": [], "message": "Analytics not yet implemented"})


@kb_bp.route("/<internal_name>/analytics/review", methods=["POST"])
def kb_analytics_review(internal_name):
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "review": "", "message": "Analytics not yet implemented"})


@kb_bp.route("/<internal_name>/analytics/cite", methods=["POST"])
def kb_analytics_cite(internal_name):
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "citations": [], "message": "Analytics not yet implemented"})


@kb_bp.route("/<internal_name>/dimension-info", methods=["GET"])
def kb_dimension_info(internal_name):
    return jsonify({"success": True, "dimensions": {}, "message": "Dimension info not yet implemented"})


@kb_bp.route("/dimension-matrix", methods=["GET"])
def kb_dimension_matrix():
    return jsonify({"success": True, "matrix": {}, "message": "Dimension matrix not yet implemented"})


# --- KB Refine Query ---

@kb_bp.route("/refine-query", methods=["POST"])
def kb_refine_query():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    kb_name = data.get("kb_name", "")
    from ...search.query_expander import QueryExpander
    from ...llm.factory import create_chat_client
    try:
        client = create_chat_client()
        expander = QueryExpander(client)
        expanded = expander.expand(query)
        return jsonify({"success": True, "original": query, "expanded": expanded.expanded_query, "terms": expanded.search_terms})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- KB Translate ---

@kb_bp.route("/translate", methods=["POST"])
def kb_translate():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    target = data.get("target_language", "en")
    source = data.get("source_language", "auto")
    from ...llm.factory import create_chat_client
    try:
        client = create_chat_client()
        result = client.translate(text, target_language=target, source_language=source)
        return jsonify({"success": True, "translation": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500