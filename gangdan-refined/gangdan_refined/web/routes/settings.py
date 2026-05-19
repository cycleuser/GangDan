"""Settings route blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

from ...core.config import CONFIG, save_config, load_config

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/", methods=["GET"])
def settings_get():
    """Get current settings (excluding sensitive data)."""
    import dataclasses

    settings = dataclasses.asdict(CONFIG)

    # Remove sensitive keys
    sensitive_keys = [
        "chat_api_key", "research_api_key", "serper_api_key", "brave_api_key",
        "semantic_scholar_api_key", "pubmed_api_key", "github_token",
        "crossref_email", "openalex_email",
    ]
    for key in sensitive_keys:
        if key in settings:
            val = settings[key]
            settings[key] = val[:4] + "****" if val else ""

    return jsonify({"success": True, "settings": settings})


@settings_bp.route("/", methods=["POST"])
def settings_update():
    """Update settings."""
    data = request.get_json(silent=True) or {}

    try:
        for key, value in data.items():
            if hasattr(CONFIG, key):
                setattr(CONFIG, key, value)

        save_config()
        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@settings_bp.route("/providers", methods=["GET"])
def settings_providers():
    """List available LLM providers."""
    from ...llm.factory import list_providers
    return jsonify({"success": True, "providers": list_providers()})


@settings_bp.route("/models", methods=["GET"])
def settings_models():
    """List available models for the current provider."""
    provider = request.args.get("provider", "ollama")
    api_key = request.args.get("api_key", "")
    base_url = request.args.get("base_url", "")

    try:
        from ...llm.factory import create_client
        client = create_client(provider, api_key=api_key, base_url=base_url)
        models = client.get_models()
        return jsonify({"success": True, "models": models})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500