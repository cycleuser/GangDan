"""Route blueprints for web interface."""

from .chat import chat_bp
from .kb import kb_bp
from .docs import docs_bp
from .learning import learning_bp
from .research import research_bp
from .preprint import preprint_bp
from .export import export_bp
from .settings import settings_bp

__all__ = [
    "chat_bp",
    "kb_bp",
    "docs_bp",
    "learning_bp",
    "research_bp",
    "preprint_bp",
    "export_bp",
    "settings_bp",
]