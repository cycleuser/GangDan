# Changelog

All notable changes to GangDan will be documented in this file.

## [1.0.36] - Unreleased

### Changed
- **Refactor**: Extracted i18n translation strings (~5000 lines) from `config.py` into separate `core/i18n.py` module
- **Refactor**: Simplified `load_config()` and `save_config()` using `dataclasses.asdict()` and field iteration (reduced ~150 lines)
- **Refactor**: Eliminated code duplication in `app.py`:
  - Replaced embedded `DOC_SOURCES` dict with import from `core/doc_manager.py`
  - Replaced minimal `ConversationManager` stub with import from `core/conversation.py`
- **Refactor**: Merged `openai_client.py` functionality into `llm_client.py` and removed dead code:
  - Ported provider model presets into `ProviderConfig` dataclass
  - Added `is_available()`, `get_chat_models()`, `get_embedding_models()` to `llm_client.OpenAIClient`
  - Added `OpenAIClient.list_providers()` classmethod
  - Removed self-referential import in `llm_client.get_models()`

### Fixed
- Version mismatch: `constants.py` APP_VERSION updated from "1.0.14" to "1.0.35"
- Duplicate `import argparse` in `cli_app.py`
- Missing `numpy>=1.24` dependency in `pyproject.toml`
- Removed reference to non-existent `removed/` directory in README.md
- Root-level `errors` log file added to `.gitignore`
- Missing overlap guard in `app.py` DocManager `_chunk_text()` method

### Removed
- Dead `core/openai_client.py` module (functionality merged into `llm_client.py`)

## [1.0.35] - 2026-03-11

- Preprint intelligence: arXiv/bioRxiv/medRxiv search with AI refinement
- PDF batch download, smart rename, and convert to Markdown
- LLM-generated Wiki with cross-KB concept linking
- Image gallery with multiple search modes
- Multi-provider LLM support (DashScope, MiniMax, Bailian, OpenAI, DeepSeek, etc.)
- Literature review and paper writer
- Lecture maker and exam generator
- Export manager for batch conversion

## [1.0.14] - 2025-2026

- Stable release with RAG chat, document management, and teaching assistant features
- 10-language UI support
- CLI with Rich terminal interface
- ChromaDB vector database with auto-recovery
- DuckDuckGo web search integration
- Conversation save/load
