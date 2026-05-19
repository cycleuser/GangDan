"""Documentation route blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

from ...core.config import CONFIG

docs_bp = Blueprint("docs", __name__)


@docs_bp.route("/sources", methods=["GET"])
def docs_sources():
    """List available documentation sources."""
    from ...storage.doc_manager import DOC_SOURCES
    return jsonify({"success": True, "sources": DOC_SOURCES})


@docs_bp.route("/download/<source_name>", methods=["POST"])
def docs_download(source_name):
    """Download and index a documentation source."""
    from ...storage.doc_manager import DocManager
    from ...storage.chroma_manager import ChromaManager
    from ...llm.ollama import OllamaClient

    try:
        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager(str(CONFIG.storage.chroma_size) if hasattr(CONFIG.storage, 'chroma_size') else "")
        doc_mgr = DocManager(CONFIG.docs_dir, chroma, ollama)
        count, errors = doc_mgr.download_source(source_name)
        return jsonify({"success": True, "count": count, "errors": errors})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@docs_bp.route("/index/<source_name>", methods=["POST"])
def docs_index(source_name):
    """Index a downloaded documentation source."""
    from ...storage.doc_manager import DocManager
    from ...storage.chroma_manager import ChromaManager
    from ...llm.ollama import OllamaClient

    try:
        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager()
        doc_mgr = DocManager(CONFIG.docs_dir, chroma, ollama)
        files, chunks, images = doc_mgr.index_source(
            source_name,
            process_images=request.json.get("process_images", True) if request.json else True,
        )
        return jsonify({"success": True, "files": files, "chunks": chunks, "images": images})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500