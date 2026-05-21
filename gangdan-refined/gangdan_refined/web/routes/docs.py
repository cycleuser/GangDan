"""Documentation route blueprint.

Provides all /api/docs/* endpoints expected by the frontend JS.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from flask import Blueprint, request, jsonify

from ...core.config import CONFIG, DATA_DIR, DOCS_DIR, CHROMA_DIR

docs_bp = Blueprint("docs", __name__)


# --- Sources ---

@docs_bp.route("/list", methods=["GET"])
@docs_bp.route("/sources", methods=["GET"])
def docs_list():
    from ...storage.doc_manager import DOC_SOURCES
    return jsonify({"success": True, "sources": DOC_SOURCES})


# --- Download (single) ---

@docs_bp.route("/download", methods=["POST"])
@docs_bp.route("/download/<source_name>", methods=["POST"])
def docs_download(source_name=None):
    data = request.get_json(silent=True) or {}
    source = source_name or data.get("source", "")
    from ...storage.doc_manager import DocManager
    from ...storage.chroma_manager import ChromaManager
    from ...llm.ollama import OllamaClient
    try:
        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        doc_mgr = DocManager(DOCS_DIR, chroma, ollama)
        count, errors = doc_mgr.download_source(source)
        return jsonify({"success": True, "count": count, "errors": errors})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Index (single) ---

@docs_bp.route("/index", methods=["POST"])
@docs_bp.route("/index/<source_name>", methods=["POST"])
def docs_index(source_name=None):
    data = request.get_json(silent=True) or {}
    source = source_name or data.get("source", "")
    process_images = data.get("process_images", True) if request.json else True
    from ...storage.doc_manager import DocManager
    from ...storage.chroma_manager import ChromaManager
    from ...llm.ollama import OllamaClient
    try:
        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        doc_mgr = DocManager(DOCS_DIR, chroma, ollama)
        files, chunks, images = doc_mgr.index_source(source, process_images=process_images)
        return jsonify({"success": True, "files": files, "chunks": chunks, "images": images})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Batch Download ---

@docs_bp.route("/batch-download", methods=["POST"])
def docs_batch_download():
    data = request.get_json(silent=True) or {}
    sources = data.get("sources", [])
    results = []
    from ...storage.doc_manager import DocManager
    from ...storage.chroma_manager import ChromaManager
    from ...llm.ollama import OllamaClient
    ollama = OllamaClient(CONFIG.llm.ollama_url)
    chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
    doc_mgr = DocManager(DOCS_DIR, chroma, ollama)
    for source in sources:
        try:
            count, errors = doc_mgr.download_source(source)
            results.append({"source": source, "count": count, "errors": errors})
        except Exception as e:
            results.append({"source": source, "error": str(e)})
    return jsonify({"success": True, "results": results})


# --- Batch Index ---

@docs_bp.route("/batch-index", methods=["POST"])
def docs_batch_index():
    data = request.get_json(silent=True) or {}
    sources = data.get("sources", [])
    results = []
    from ...storage.doc_manager import DocManager
    from ...storage.chroma_manager import ChromaManager
    from ...llm.ollama import OllamaClient
    ollama = OllamaClient(CONFIG.llm.ollama_url)
    chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
    doc_mgr = DocManager(DOCS_DIR, chroma, ollama)
    for source in sources:
        try:
            files, chunks, images = doc_mgr.index_source(source)
            results.append({"source": source, "files": files, "chunks": chunks, "images": images})
        except Exception as e:
            results.append({"source": source, "error": str(e)})
    return jsonify({"success": True, "results": results})


# --- Web Search to KB ---

@docs_bp.route("/web-search-to-kb", methods=["POST"])
def docs_web_search_to_kb():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    kb_name = data.get("kb_name", "")
    max_results = data.get("max_results", 10)

    if not query:
        return jsonify({"success": False, "error": "Query is required"}), 400

    try:
        from ...search.web_searcher import WebSearcher
        from ...storage.chroma_manager import ChromaManager

        searcher = WebSearcher()
        search_results = searcher.search(query, max_results=max_results)

        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        indexed = 0
        for result in search_results:
            try:
                if hasattr(result, "to_dict"):
                    doc = result.to_dict()
                else:
                    doc = {"content": str(result), "metadata": {}}
                chroma.add_documents(kb_name or "web_search", [doc])
                indexed += 1
            except Exception:
                pass

        return jsonify({"success": True, "search_results": len(search_results), "indexed": indexed})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Upload ---

@docs_bp.route("/upload", methods=["POST"])
def docs_upload():
    kb_name = request.form.get("kb_name", "uploads")
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"success": False, "error": "No filename"}), 400

    try:
        from ...storage.kb_manager import CustomKBManager
        from ...core.config import sanitize_kb_name
        internal_name = sanitize_kb_name(kb_name)
        kb_dir = DOCS_DIR / internal_name
        kb_dir.mkdir(parents=True, exist_ok=True)

        save_path = kb_dir / uploaded.filename
        uploaded.save(str(save_path))

        ext = Path(uploaded.filename).suffix.lower()
        if ext in (".pdf", ".caj"):
            try:
                from ...document.pdf_converter import PDFConverter
                converter = PDFConverter()
                md_content = converter.convert(str(save_path))
                md_path = save_path.with_suffix(".md")
                md_path.write_text(md_content, encoding="utf-8")
            except Exception:
                pass

        return jsonify({"success": True, "filename": uploaded.filename, "path": str(save_path)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Import Directory ---

@docs_bp.route("/import-directory", methods=["POST"])
def docs_import_directory():
    data = request.get_json(silent=True) or {}
    directory = data.get("directory", "")
    kb_name = data.get("kb_name", "imports")
    recursive = data.get("recursive", True)

    if not directory:
        return jsonify({"success": False, "error": "Directory path is required"}), 400

    dir_path = Path(directory)
    if not dir_path.exists():
        return jsonify({"success": False, "error": f"Directory not found: {directory}"}), 404

    import glob
    from ...core.config import sanitize_kb_name
    SUPPORTED_EXT = {".md", ".txt", ".pdf", ".html", ".htm", ".tex", ".epub", ".docx", ".caj"}
    internal_name = sanitize_kb_name(kb_name)
    kb_dir = DOCS_DIR / internal_name
    kb_dir.mkdir(parents=True, exist_ok=True)

    imported = 0
    errors = []
    pattern = "**/*" if recursive else "*"
    for fpath in dir_path.glob(pattern):
        if fpath.is_file() and fpath.suffix.lower() in SUPPORTED_EXT:
            try:
                dest = kb_dir / fpath.name
                shutil.copy2(str(fpath), str(dest))
                imported += 1
            except Exception as e:
                errors.append({"file": str(fpath), "error": str(e)})

    return jsonify({"success": True, "imported": imported, "errors": errors})


# --- Check Duplicates ---

@docs_bp.route("/check-duplicates", methods=["POST"])
def docs_check_duplicates():
    data = request.get_json(silent=True) or {}
    kb_name = data.get("kb_name", "")
    source = data.get("source", "")
    url = data.get("url", "")

    if not kb_name and not source:
        return jsonify({"success": False, "error": "KB name or source required"}), 400

    try:
        from ...storage.chroma_manager import ChromaManager
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))

        if kb_name and chroma.collection_exists(kb_name):
            files = chroma.get_collection_files(kb_name)
            existing = [f["file"] for f in files]
            if source and source in existing:
                return jsonify({"success": True, "duplicate": True, "existing_file": source})
            return jsonify({"success": True, "duplicate": False, "existing_files": existing})

        return jsonify({"success": True, "duplicate": False})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500