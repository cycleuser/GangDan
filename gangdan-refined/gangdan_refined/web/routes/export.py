"""Export route blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify, send_file

from ...core.config import DATA_DIR

export_bp = Blueprint("export", __name__)


@export_bp.route("/batch", methods=["POST"])
def export_batch():
    """Batch convert and export documents."""
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    export_type = data.get("type", "preprint")

    try:
        from ...research.export import ExportManager
        from pathlib import Path

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

        return jsonify({"success": True, "report": report.to_dict()})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@export_bp.route("/download/<path:filename>", methods=["GET"])
def export_download(filename):
    """Download an exported file."""
    from pathlib import Path
    from flask import abort

    filepath = Path(DATA_DIR) / "exports" / filename
    if not filepath.exists():
        abort(404)
    return send_file(str(filepath), as_attachment=True)