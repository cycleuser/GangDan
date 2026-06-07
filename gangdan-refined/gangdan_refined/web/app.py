"""Flask application factory for GangDan Refined.

Creates the Flask app with all blueprints and page routes.
Templates receive a flat config proxy for backwards compatibility
with the original template JS code.
"""

from __future__ import annotations

import json
import sys as _sys
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

    def _register_safe(flask_app, bp, name=None):
        """Register blueprint, ignoring duplicate name errors."""
        try:
            flask_app.register_blueprint(bp, name=name)
        except ValueError:
            _sys.stderr.write(f"[App] Blueprint '{bp.name}' already registered, skipping\n")

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

    from .routes.graph import graph_bp
    from .routes.memory import memory_bp
    from .routes.cron import cron_bp

    # Register new blueprints — skip already-registered in test replay
    _register_safe(app, graph_bp, 'graph_ext')
    _register_safe(app, memory_bp, 'memory_ext')
    _register_safe(app, cron_bp, 'cron_ext')

    flat_config = FlatConfigProxy(CONFIG)

    # --- Setup wizard route ---
    @app.route("/setup")
    def setup_wizard():
        """First-run setup wizard page."""
        from ..core.setup_wizard import get_setup_status
        from ..llm.models import PROVIDER_CONFIGS
        
        lang = CONFIG.ui.language
        translations_json = json.dumps(TRANSLATIONS, ensure_ascii=False)
        providers = [
            {
                "name": p.name,
                "display_name": p.display_name,
                "requires_key": p.requires_key,
                "base_url": p.base_url,
                "default_model": p.default_model,
                "help": p.help,
                "key_url": p.key_url,
            }
            for p in PROVIDER_CONFIGS.values()
        ]
        
        return render_template(
            "setup.html",
            lang=lang,
            languages=LANGUAGES,
            t=t,
            config=flat_config,
            translations_json=translations_json,
            providers=providers,
            setup_status=get_setup_status(),
        )

    # --- Middleware: redirect to /setup if first run ---
    from flask import redirect, url_for
    
    @app.before_request
    def check_first_run():
        """Redirect to setup wizard on first run."""
        from ..core.setup_wizard import is_first_run
        
        # Don't redirect to setup for these paths
        allowed_paths = ['/setup', '/api/health', '/api/set-language', '/api/test-connection', '/api/test-provider', '/api/provider/models', '/api/setup', '/static/']
        if request.path.startswith(tuple(allowed_paths)):
            return None
        
        if is_first_run():
            return redirect(url_for('setup_wizard'))
        
        return None

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