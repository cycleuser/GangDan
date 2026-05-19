"""Flask application factory for GangDan Refined.

Creates the Flask app with all blueprints and page routes.
Templates receive a flat config proxy for backwards compatibility
with the original template JS code.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

from ..core.config import CONFIG, DATA_DIR, LANGUAGES, TRANSLATIONS, t
from ..storage.doc_manager import DOC_SOURCES


class FlatConfigProxy:
    """Flat config proxy that provides attribute access matching original templates.

    The original templates use config.ollama_url, config.proxy_mode, etc.
    The refined config uses grouped fields: config.llm.ollama_url, config.proxy.mode.
    This proxy flattens the groups so templates work without modification.
    """

    def __init__(self, config):
        self._config = config

    def __getattr__(self, name):
        # Try direct attribute first (for convenience aliases)
        try:
            return getattr(self._config, name)
        except AttributeError:
            pass
        # Search in grouped configs
        for group_name in ("proxy", "llm", "storage", "search", "document", "preprint", "research", "adaptive", "ui"):
            group = getattr(self._config, group_name, None)
            if group is not None:
                try:
                    return getattr(group, name)
                except AttributeError:
                    continue
        raise AttributeError(f"Config has no attribute {name!r}")

    def __setattr__(self, name, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
            return
        # Try direct setter first
        try:
            setattr(self._config, name, value)
            return
        except AttributeError:
            pass
        for group_name in ("proxy", "llm", "storage", "search", "document", "preprint", "research", "adaptive", "ui"):
            group = getattr(self._config, group_name, None)
            if group is not None:
                try:
                    setattr(group, name, value)
                    return
                except AttributeError:
                    continue
        setattr(self._config, name, value)


def create_app(config: dict | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    app.config["SECRET_KEY"] = "gangdan-refined-secret-key"
    app.config["DATA_DIR"] = str(DATA_DIR)

    if config:
        app.config.update(config)

    CORS(app)

    # Register compatibility API blueprint (matches original GangDan URL patterns)
    from .routes.api import api_bp
    app.register_blueprint(api_bp)

    # Register additional modular API blueprints for new features
    from .routes.settings import settings_bp
    app.register_blueprint(settings_bp, url_prefix="/api/settings")

    # Flat config for template compatibility
    flat_config = FlatConfigProxy(CONFIG)

    # --- Page routes ---

    @app.route("/")
    def index():
        lang = request.args.get("lang", CONFIG.ui.language)
        CONFIG.ui.language = lang
        from ..core.config import save_config
        save_config()
        translations_json = json.dumps(TRANSLATIONS, ensure_ascii=False)
        return render_template(
            "index.html",
            lang=lang,
            languages=LANGUAGES,
            t=t,
            config=flat_config,
            doc_sources=DOC_SOURCES,
            translations_json=translations_json,
        )

    @app.route("/research")
    def research_page():
        lang = request.args.get("lang", CONFIG.ui.language)
        translations_json = json.dumps(TRANSLATIONS, ensure_ascii=False)
        return render_template(
            "research.html",
            lang=lang,
            languages=LANGUAGES,
            t=t,
            config=flat_config,
            translations_json=translations_json,
        )

    @app.route("/question")
    def question_page():
        lang = request.args.get("lang", CONFIG.ui.language)
        translations_json = json.dumps(TRANSLATIONS, ensure_ascii=False)
        return render_template(
            "question.html",
            lang=lang,
            languages=LANGUAGES,
            t=t,
            config=flat_config,
            translations_json=translations_json,
        )

    @app.route("/guide")
    def guide_page():
        lang = request.args.get("lang", CONFIG.ui.language)
        translations_json = json.dumps(TRANSLATIONS, ensure_ascii=False)
        return render_template(
            "guide.html",
            lang=lang,
            languages=LANGUAGES,
            t=t,
            config=flat_config,
            translations_json=translations_json,
        )

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app