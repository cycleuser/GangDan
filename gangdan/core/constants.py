"""
Constants for GangDan application.

This module centralizes all magic numbers, default values, and constants
used throughout the codebase for better maintainability.
"""

from typing import Dict, List


# =============================================================================
# Timeout Values (in seconds)
# =============================================================================
HTTP_TIMEOUT_SHORT = 10
HTTP_TIMEOUT_MEDIUM = 30
HTTP_TIMEOUT_LONG = 300
HTTP_TIMEOUT_EXTRA_LONG = 600

# Request retry configuration
MAX_REQUEST_RETRIES = 3
REQUEST_RETRY_DELAY = 1.0  # Base delay in seconds
REQUEST_BACKOFF_FACTOR = 2.0

# =============================================================================
# Text Processing Defaults
# =============================================================================
CHUNK_SIZE_DEFAULT = 800
CHUNK_OVERLAP_DEFAULT = 150
CHUNK_SIZE_MIN = 100
CHUNK_SIZE_MAX = 2000

MAX_EMBED_TEXT_LENGTH = 500
MAX_CONTEXT_TOKENS_DEFAULT = 3000
MAX_CONTEXT_TOKENS_MAX = 8000

# Token estimation
TOKENS_PER_CHAR_ESTIMATE = 0.25  # Rough estimate: 1 token ≈ 4 chars

# =============================================================================
# Vector Database Configuration
# =============================================================================
DEFAULT_TOP_K = 15
TOP_K_MIN = 1
TOP_K_MAX = 100

MAX_BATCH_SIZE = 100
BATCH_SIZE_DEFAULT = 32

# =============================================================================
# Knowledge Base Validation
# =============================================================================
KB_NAME_MIN_LENGTH = 3
KB_NAME_MAX_LENGTH = 50
KB_NAME_HASH_LENGTH = 8
KB_NAME_PATTERN = r"^[a-zA-Z0-9_-]+$"

MAX_USER_KBS = 50  # Maximum number of user knowledge bases

# =============================================================================
# File and Document Processing
# =============================================================================
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

SUPPORTED_IMAGE_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
SUPPORTED_DOC_EXTENSIONS: List[str] = [
    ".pdf",
    ".txt",
    ".md",
    ".markdown",
    ".html",
    ".htm",
    ".docx",
    ".pptx",
]

# Image processing
IMAGE_MAX_DIMENSION = 2048
IMAGE_QUALITY = 85
IMAGE_THUMBNAIL_SIZE = (200, 200)

# =============================================================================
# LLM and Model Configuration
# =============================================================================
DEFAULT_CHAT_MODEL = "qwen2.5:7b"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_RERANKER_MODEL = "bge-reranker"

OLLAMA_DEFAULT_URL = "http://localhost:11434"
OLLAMA_DEFAULT_PORT = 11434

# Model response parameters
DEFAULT_TEMPERATURE = 0.7
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0

DEFAULT_MAX_TOKENS = 2048
DEFAULT_TOP_P = 0.9

# =============================================================================
# Conversation History
# =============================================================================
DEFAULT_MAX_HISTORY = 20
HISTORY_MIN = 1
HISTORY_MAX = 100

# Auto-save interval in seconds
CONVERSATION_SAVE_INTERVAL = 60

# =============================================================================
# Web Search Configuration
# =============================================================================
DEFAULT_SEARCH_RESULTS = 10
MAX_SEARCH_RESULTS = 50

# Search engine URLs
DUCKDUCKGO_URL = "https://duckduckgo.com/html/"
SEARXNG_DEFAULT_URL = "http://localhost:8080"

# =============================================================================
# Learning Module Defaults
# =============================================================================
DEFAULT_QUESTION_COUNT = 5
QUESTION_COUNT_MIN = 1
QUESTION_COUNT_MAX = 20

DEFAULT_GUIDED_SESSIONS = 5
GUIDED_SESSIONS_MIN = 1
GUIDED_SESSIONS_MAX = 10

RESEARCH_MAX_PHASES = 5
RESEARCH_MIN_PHASES = 1

# =============================================================================
# Port and Network Configuration
# =============================================================================
DEFAULT_WEB_PORT = 5000
DEFAULT_WEB_HOST = "127.0.0.1"

PORT_CHECK_TIMEOUT = 5
MAX_PORT_RETRY_ATTEMPTS = 10

# =============================================================================
# Cache and Performance
# =============================================================================
CACHE_TTL_DEFAULT = 3600  # 1 hour
CACHE_MAX_SIZE = 1000

# Thread pool settings
MAX_WORKERS_DEFAULT = 4
MAX_WORKERS_MIN = 1
MAX_WORKERS_MAX = 16

# =============================================================================
# UI and Display
# =============================================================================
DEFAULT_LANGUAGE = "zh"
SUPPORTED_LANGUAGES: List[str] = [
    "zh",
    "en",
    "es",
    "fr",
    "de",
    "ja",
    "ko",
    "pt",
    "ru",
    "ar",
]

# Streaming configuration
STREAM_CHUNK_SIZE = 1
STREAM_FLUSH_INTERVAL = 0.1  # seconds

# =============================================================================
# Error Messages
# =============================================================================
ERROR_MESSAGES: Dict[str, str] = {
    "MODEL_NOT_FOUND": "Model '{model}' not found. Please pull it first with 'ollama pull {model}'",
    "CONNECTION_FAILED": "Failed to connect to {service}. Is it running?",
    "FILE_NOT_FOUND": "File not found: {path}",
    "INVALID_FORMAT": "Invalid format: {detail}",
    "TIMEOUT": "Operation timed out after {timeout} seconds",
    "PERMISSION_DENIED": "Permission denied: {path}",
    "DISK_FULL": "Insufficient disk space",
    "CORRUPTED_DATA": "Data corruption detected in {component}",
}

# =============================================================================
# Research Search Configuration
# =============================================================================
RESEARCH_SEARCH_SOURCES: List[str] = ["arxiv", "semantic_scholar", "crossref", "openalex", "dblp"]
RESEARCH_MAX_RESULTS_PER_SOURCE = 10
RESEARCH_SEARCH_TIMEOUT = 15

# PDF Download configuration
PAPERS_DIR_NAME = "papers"
PDF_DOWNLOAD_TIMEOUT = 120
PDF_MAX_SIZE_MB = 250
PDF_SHA256_BLOCK_SIZE = 65536

# Academic search API URLs
ARXIV_API_URL = "http://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1"
CROSSREF_API_URL = "https://api.crossref.org/works"
PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
OPENALEX_API_URL = "https://api.openalex.org/works"
DBLP_API_URL = "https://dblp.org/search/publ/api"

# OA PDF discovery URLs
UNPAYWALL_API_URL = "https://api.unpaywall.org/v2"
EUROPE_PMC_API_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
PMC_ID_CONVERTER_URL = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"

# =============================================================================
# Feature Flags
# =============================================================================
FEATURE_ENABLE_WEB_SEARCH = True
FEATURE_ENABLE_IMAGE_PROCESSING = True
FEATURE_ENABLE_LEARNING_MODULE = True
FEATURE_ENABLE_STREAMING = True
FEATURE_ENABLE_RESEARCH_SEARCH = True

# =============================================================================
# Metadata
# =============================================================================
APP_NAME = "GangDan"
APP_VERSION = "1.0.14"
APP_DESCRIPTION = "LLM-powered knowledge management and teaching assistant"
