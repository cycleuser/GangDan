"""Export/Import route blueprint.

Provides /api/export/*, /api/export-raw-files, /api/import-raw-files,
/api/export-kb, /api/import-kb endpoints.
"""

from __future__ import annotations

import json
import os
import shutil
import zipfile
import io
from pathlib import Path

from flask import Blueprint, request, jsonify, send_file, abort

from ...core.config import CONFIG, DATA_DIR, DOCS_DIR, CHROMA_DIR

export_bp = Blueprint("export", __name__)


# --- Batch convert ---

@export_bp.route("/batch", methods=["POST"])
def export_batch():
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    export_type = data.get("type", "preprint")
    try:
        from ...research.export import ExportManager
        mgr = ExportManager(output_dir=Path(DATA_DIR) / "exports")
        if export_type == "preprint":
            report = mgr.batch_convert_preprints(items)
        elif export_type == "paper":
            report = mgr.batch_convert_papers(items)
        else:
            report = mgr.batch_convert_mixed(
                preprint_items=[i for i in items if i.get("type") == "preprint"],
                paper_items=[i for i in items if i.get("type") == "paper"],
            )
        return jsonify({"success": True, "report": report.to_dict() if hasattr(report, "to_dict") else str(report)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@export_bp.route("/download/<path:filename>", methods=["GET"])
def export_download(filename):
    filepath = Path(DATA_DIR) / "exports" / filename
    if not filepath.exists():
        abort(404)
    return send_file(str(filepath), as_attachment=True)


# --- Export Raw Files ---

@export_bp.route("/raw-files", methods=["GET"])
def export_raw_files():
    kb_name = request.args.get("name", "").strip()
    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    kb_dir = DOCS_DIR / kb_name
    if not kb_dir.exists():
        kb_dir = DOCS_DIR / f"user_{kb_name}"
    if not kb_dir.exists():
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in kb_dir.rglob("*"):
                if fpath.is_file():
                    zf.write(str(fpath), fpath.relative_to(kb_dir))
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype="application/zip", as_attachment=True, download_name=f"{kb_name}_raw.zip")
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Import Raw Files ---

@export_bp.route("/import-raw-files", methods=["POST"])
def import_raw_files():
    if "file" not in request.files:
        data = request.get_json(silent=True) or {}
        kb_name = data.get("kb_name", "imports")
    else:
        kb_name = request.form.get("kb_name", "imports")

    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400

    uploaded = request.files["file"]
    try:
        from ...core.config import sanitize_kb_name
        internal_name = sanitize_kb_name(kb_name)
        kb_dir = DOCS_DIR / internal_name
        kb_dir.mkdir(parents=True, exist_ok=True)

        zip_buffer = io.BytesIO(uploaded.read())
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            zf.extractall(str(kb_dir))

        return jsonify({"success": True, "kb_name": kb_name, "extracted_to": str(kb_dir)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Export KB ---

@export_bp.route("/kb", methods=["GET"])
def export_kb():
    kb_name = request.args.get("name", "").strip()
    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400

    try:
        from ...storage.chroma_manager import ChromaManager
        from ...storage.kb_manager import CustomKBManager

        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        if not chroma.collection_exists(kb_name):
            return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404

        documents = chroma.get_all_documents(kb_name)

        export_data = json.dumps({"kb_name": kb_name, "documents": documents}, ensure_ascii=False, indent=2)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("kb_data.json", export_data)
            kb_dir = DOCS_DIR / kb_name
            if kb_dir.exists():
                for fpath in kb_dir.rglob("*.md"):
                    zf.write(str(fpath), f"docs/{fpath.relative_to(kb_dir)}")
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype="application/zip", as_attachment=True, download_name=f"{kb_name}_kb.zip")
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Import KB ---

@export_bp.route("/import-kb", methods=["POST"])
def import_kb():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400

    uploaded = request.files["file"]
    kb_name = request.form.get("kb_name", "imported_kb")

    try:
        from ...storage.chroma_manager import ChromaManager
        from ...core.config import sanitize_kb_name

        internal_name = sanitize_kb_name(kb_name)
        kb_dir = DOCS_DIR / internal_name
        kb_dir.mkdir(parents=True, exist_ok=True)

        zip_buffer = io.BytesIO(uploaded.read())
        imported_docs = 0
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            for name in zf.namelist():
                if name == "kb_data.json":
                    data = json.loads(zf.read(name))
                    documents = data.get("documents", [])
                    chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
                    for doc in documents:
                        chroma.add_documents(internal_name, [doc])
                        imported_docs += 1
                elif name.startswith("docs/"):
                    zf.extract(name, str(kb_dir))

        return jsonify({"success": True, "kb_name": kb_name, "imported_docs": imported_docs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500