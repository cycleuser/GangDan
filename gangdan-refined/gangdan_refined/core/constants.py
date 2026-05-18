"""Application constants and default values."""

from __future__ import annotations

# Default URLs and endpoints
OLLAMA_DEFAULT_URL = "http://localhost:11434"

# Default models
DEFAULT_CHAT_MODEL = "llama3.2"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"

# Default settings
DEFAULT_LANGUAGE = "en"
DEFAULT_TOP_K = 5
CHUNK_SIZE_DEFAULT = 1000
CHUNK_OVERLAP_DEFAULT = 200
MAX_CONTEXT_TOKENS_DEFAULT = 8192

# Knowledge base naming
KB_NAME_MIN_LENGTH = 3
KB_NAME_HASH_LENGTH = 8

# File upload limits
MAX_UPLOAD_SIZE_MB = 50

# API timeouts
API_TIMEOUT_SHORT = 10
API_TIMEOUT_MEDIUM = 30
API_TIMEOUT_LONG = 300

# Supported document extensions
DOC_EXTENSIONS = {".md", ".txt", ".rst", ".py", ".ipynb", ".html", ".texi", ".cpp"}

# Image extensions
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
