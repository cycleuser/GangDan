"""Cron job API routes."""
from flask import Blueprint, jsonify, request

cron_bp = Blueprint("cron_service", __name__, url_prefix="/api/cron")


def _get_cron():
    from gangdan_refined.core.cron_service import get_cron_service
    return get_cron_service()


@cron_bp.route("/list")
def cron_list():
    return jsonify({"jobs": _get_cron().list_jobs()})


@cron_bp.route("/add", methods=["POST"])
def cron_add():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    job = _get_cron().add_job(
        name=name,
        kind=data.get("kind", "every"),
        schedule_value=data.get("schedule_value", "3600"),
        action=data.get("action", ""),
        enabled=data.get("enabled", True),
    )
    return jsonify({"job": job.__dict__ if hasattr(job, '__dict__') else str(job)})


@cron_bp.route("/<job_id>/toggle", methods=["POST"])
def cron_toggle(job_id):
    data = request.get_json(silent=True) or {}
    ok = _get_cron().toggle_job(job_id, data.get("enabled", True))
    return jsonify({"success": ok})


@cron_bp.route("/<job_id>/delete", methods=["POST"])
def cron_delete(job_id):
    ok = _get_cron().remove_job(job_id)
    return jsonify({"success": ok})
