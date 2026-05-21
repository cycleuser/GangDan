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
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return getattr(self._config, name)
        except AttributeError:
            pass
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

    # Register all API blueprints
    from .routes.api import api_bp
    app.register_blueprint(api_bp)

    from .routes.settings import settings_bp
    app.register_blueprint(settings_bp, url_prefix="/api/settings")

    from .routes.kb import kb_bp
    app.register_blueprint(kb_bp, url_prefix="/api/kb")

    from .routes.docs import docs_bp
    app.register_blueprint(docs_bp, url_prefix="/api/docs")

    from .routes.learning import learning_bp
    app.register_blueprint(learning_bp, url_prefix="/api/learning")

    from .routes.research import research_bp
    app.register_blueprint(research_bp, url_prefix="/api/research")

    from .routes.preprint import preprint_bp
    app.register_blueprint(preprint_bp, url_prefix="/api/preprint")

    from .routes.export import export_bp
    app.register_blueprint(export_bp, url_prefix="/api/export")

    from .routes.chat import chat_bp
    app.register_blueprint(chat_bp, url_prefix="/api/chat")

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