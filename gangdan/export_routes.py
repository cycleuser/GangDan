"""Batch conversion and export API routes.

Provides endpoints for:
- Batch convert preprints to Markdown
- Batch convert papers to Markdown
- Mixed batch conversion (preprints + papers + existing Markdown)
- Download ZIP exports
- Add converted results directly to custom KBs
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request, send_file

logger = logging.getLogger(__name__)

export_bp = Blueprint("export", __name__, url_prefix="/api/export")

_export_manager = None


def get_export_manager():
    """Get or create the ExportManager singleton."""
    global _export_manager
    if _export_manager is None:
        from gangdan.core.export_manager import ExportManager

        _export_manager = ExportManager()
    return _export_manager


# =============================================================================
# Batch Convert Preprints
# =============================================================================


@export_bp.route("/preprints/batch-convert", methods=["POST"])
def batch_convert_preprints() -> Any:
    """Batch convert preprints to Markdown.

    Body: {
        "items": [
            {
                "item_id": "...",
                "title": "...",
                "url": "https://ar5iv.labs.arxiv.org/html/...",
                "content_type": "html|tex|xml",
                "preprint_id": "..."
            },
            ...
        ],
        "create_zip": true,
        "kb_name": "..." (optional: add to KB after conversion)
    }
    """
    data = request.json or {}
    items = data.get("items", [])

    if not items:
        return jsonify({"error": "items array is required"}), 400

    create_zip = data.get("create_zip", True)
    kb_name = data.get("kb_name", "")

    manager = get_export_manager()
    report = manager.batch_convert_preprints(items, create_zip=create_zip)

    result = report.to_dict()

    if kb_name and report.success_count > 0:
        kb_result = _add_to_kb(kb_name, report.results)
        result["kb_result"] = kb_result

    return jsonify(result)


# =============================================================================
# Batch Convert Papers
# =============================================================================


@export_bp.route("/papers/batch-convert", methods=["POST"])
def batch_convert_papers() -> Any:
    """Batch convert research papers (PDF) to Markdown.

    Body: {
        "items": [
            {
                "item_id": "...",
                "title": "...",
                "pdf_path": "/path/to/paper.pdf"
            },
            ...
        ],
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

    manager = get_export_manager()
    report = manager.batch_convert_papers(items, create_zip=create_zip)

    result = report.to_dict()

    if kb_name and report.success_count > 0:
        kb_result = _add_to_kb(kb_name, report.results)
        result["kb_result"] = kb_result

    return jsonify(result)


# =============================================================================
# Mixed Batch Convert
# =============================================================================


@export_bp.route("/mixed/batch-convert", methods=["POST"])
def batch_convert_mixed() -> Any:
    """Batch convert mixed sources to Markdown.

    Body: {
        "preprint_items": [...],
        "paper_items": [...],
        "markdown_items": [
            {"item_id": "...", "title": "...", "md_path": "..."}
        ],
        "create_zip": true,
        "kb_name": "..." (optional)
    }
    """
    data = request.json or {}

    preprint_items = data.get("preprint_items")
    paper_items = data.get("paper_items")
    markdown_items = data.get("markdown_items")

    if not any([preprint_items, paper_items, markdown_items]):
        return jsonify({"error": "At least one of preprint_items, paper_items, or markdown_items is required"}), 400

    create_zip = data.get("create_zip", True)
    kb_name = data.get("kb_name", "")

    manager = get_export_manager()
    report = manager.batch_convert_mixed(
        preprint_items=preprint_items,
        paper_items=paper_items,
        markdown_items=markdown_items,
        create_zip=create_zip,
    )

    result = report.to_dict()

    if kb_name and report.success_count > 0:
        kb_result = _add_to_kb(kb_name, report.results)
        result["kb_result"] = kb_result

    return jsonify(result)


# =============================================================================
# Download ZIP
# =============================================================================


@export_bp.route("/download/<zip_path>", methods=["GET"])
def download_zip(zip_path: str) -> Any:
    """Download a ZIP export file.

    Note: zip_path is relative to export directory.
    """
    manager = get_export_manager()
    full_path = manager.output_dir / zip_path

    if not full_path.exists():
        return jsonify({"error": "File not found"}), 404

    return send_file(
        str(full_path),
        as_attachment=True,
        download_name=full_path.name,
    )


@export_bp.route("/latest-zip", methods=["GET"])
def download_latest_zip() -> Any:
    """Download the most recently created ZIP export.

    Query: ?prefix=preprints|papers|mixed
    """
    prefix = request.args.get("prefix", "")

    manager = get_export_manager()
    zip_dir = manager.output_dir / "zip_exports"

    if not zip_dir.exists():
        return jsonify({"error": "No exports found"}), 404

    zip_files = sorted(zip_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)

    if prefix:
        zip_files = [f for f in zip_files if f.name.startswith(prefix)]

    if not zip_files:
        return jsonify({"error": "No matching exports found"}), 404

    latest = zip_files[0]
    return send_file(
        str(latest),
        as_attachment=True,
        download_name=latest.name,
    )


# =============================================================================
# Export Status
# =============================================================================


@export_bp.route("/status", methods=["GET"])
def export_status() -> Any:
    """Get export manager status and available exports."""
    manager = get_export_manager()
    zip_dir = manager.output_dir / "zip_exports"

    exports = []
    if zip_dir.exists():
        for f in sorted(zip_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
            exports.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "created": f.stat().st_mtime,
                "path": str(f.relative_to(manager.output_dir)),
            })

    return jsonify({
        "output_dir": str(manager.output_dir),
        "exports": exports,
        "total_exports": len(exports),
    })


# =============================================================================
# Helper Functions
# =============================================================================


def _add_to_kb(kb_name: str, results: list) -> dict:
    """Add successful conversion results to a custom KB.

    Parameters
    ----------
    kb_name : str
        KB display name or internal name.
    results : list
        BatchConvertResult list.

    Returns
    -------
    dict
        Result of the KB add operation.
    """
    from gangdan.core.kb_manager import CustomKBManager, KBDocEntry
    from datetime import datetime

    manager = get_kb_manager()

    kb = manager.get_kb(kb_name)
    if kb is None:
        kb = manager.create_kb(kb_name, f"Auto-created from batch export")

    added = 0
    failed = 0

    for r in results:
        if not r.success or not r.markdown_path:
            failed += 1
            continue

        doc = KBDocEntry(
            doc_id=r.item_id,
            title=r.title,
            source_type="converted",
            source_id=r.item_id,
            markdown_path=r.markdown_path,
            content_preview=r.markdown_content[:500],
            added_at=datetime.now().isoformat(),
        )

        if manager.add_document(kb.internal_name, doc, index_to_chroma=True):
            added += 1
        else:
            failed += 1

    return {
        "kb_name": kb.internal_name,
        "kb_display": kb.display_name,
        "added": added,
        "failed": failed,
    }


def get_kb_manager():
    """Get the CustomKBManager singleton."""
    from gangdan.kb_routes import get_kb_manager as _get_kb_manager
    return _get_kb_manager()
