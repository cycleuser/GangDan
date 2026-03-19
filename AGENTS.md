# GangDan - Agent Guidelines

## Build & Test Commands

### Installation
```bash
pip install -e .                    # Install in development mode
pip install pytest pytest-cov       # Test dependencies
```

### Running Tests
```bash
pytest                              # Run all tests
pytest -v                           # Verbose output
pytest tests/test_core_config.py    # Run single test file
pytest -k "test_config_defaults"    # Run test by name pattern
pytest --cov=gangdan                # With coverage report
pytest --maxfail=3                  # Stop after 3 failures
pytest -x                           # Stop on first failure
```

### Single Test Execution
```bash
pytest tests/test_core_config.py::TestConfigDataclass::test_config_defaults -v
pytest tests/test_core_config.py::TestProxySettings -v
```

### Build & Package
```bash
python -m build                     # Build sdist and wheel
python publish.py release           # Build and prepare for upload
twine upload dist/*                 # Upload to PyPI
```

### CLI Entry Point
```bash
gangdan                             # Start web server (default :5000)
gangdan --port 8080                 # Custom port
gangdan cli                         # Start CLI REPL
gangdan chat "hello"                # Single chat command
python -m gangdan                   # Alternative launch
```

## Code Style Guidelines

### Imports
- Standard library imports first (alphabetically sorted)
- Third-party imports second (alphabetically sorted)
- Local imports last (alphabetically sorted)
- Use `from __future__ import annotations` for forward references
- Avoid wildcard imports; be explicit

```python
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from flask import Flask, jsonify
from unittest.mock import patch, MagicMock

from gangdan.core.config import CONFIG, load_config
```

### Type Hints
- Use type hints for all function signatures
- Prefer `str | None` over `Optional[str]` (Python 3.10+)
- Use `List[str]`, `Dict[str, Any]` from `typing` for compatibility
- Annotate dataclass fields

```python
def chat(
    message: str,
    *,
    model: str = "",
    conversation_id: str | None = None,
) -> ToolResult:
    ...
```

### Naming Conventions
- **Classes**: PascalCase (`OllamaClient`, `VectorDBBase`)
- **Functions**: snake_case (`load_config`, `index_directory`)
- **Constants**: UPPER_CASE (`CONFIG`, `DATA_DIR`, `TRANSLATIONS`)
- **Private methods**: leading underscore (`_get_data_dir`)
- **Test classes**: `Test<Feature>` pattern
- **Test functions**: `test_<behavior>` pattern

### Docstrings
- Use Google-style or reStructuredText docstrings
- Include Parameters, Returns, Raises sections
- Module docstrings at top of each file
- Keep docstrings concise but informative

```python
def index_documents(
    directory: str | Path,
    *,
    collection: str = "default",
) -> ToolResult:
    """Index documents from a directory into the knowledge base.

    Parameters
    ----------
    directory : str or Path
        Directory containing documents to index.
    collection : str
        Collection name in ChromaDB.

    Returns
    -------
    ToolResult
        With data containing indexing stats.
    """
```

### Error Handling
- Use try/except for external API calls (Ollama, file I/O)
- Return `ToolResult(success=False, error=str(e))` for API functions
- Raise exceptions for invalid arguments in internal functions
- Log errors to `sys.stderr` with context prefix
- Never silently swallow exceptions

### Data Classes
- Use `@dataclass` for configuration and result types
- Use `field(default_factory=...)` for mutable defaults
- Include `to_dict()` method for serialization when needed

```python
@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)
```

### Formatting
- Line length: 120 characters max (per existing code)
- Use f-strings for string formatting
- Trailing whitespace: trimmed (see `.editorconfig`)
- Line endings: LF (Unix), except `.bat` files use CRLF
- Final newline: required

### Testing
- Use pytest fixtures from `tests/conftest.py`
- Mock external services (Ollama, ChromaDB) with `unittest.mock`
- Use `temp_data_dir` fixture for isolated config/database tests
- Test classes group related functionality
- Assertions should be specific and test one behavior
- Set environment variables before importing modules that use them

```python
class TestConfigDataclass:
    """Test Config dataclass and defaults."""
    
    def test_config_defaults(self, temp_data_dir):
        """Test that Config has correct default values."""
        from gangdan.core.config import Config
        config = Config()
        assert config.ollama_url == "http://localhost:11434"
```

### Project Structure
```
gangdan/
  __init__.py          # Version, public API exports
  api.py               # Unified Python API (ToolResult-based)
  app.py               # Flask web application
  cli.py               # CLI entry point
  cli_app.py           # CLI command implementations
  tools.py             # Tool definitions
  learning_routes.py   # Learning module Flask routes
  core/
    config.py          # Configuration management
    ollama_client.py   # Ollama API client
    vector_db.py       # Vector database abstraction
    chroma_manager.py  # ChromaDB operations
    doc_manager.py     # Document processing
    conversation.py    # Chat history management
    web_searcher.py    # Web search integration
    image_handler.py   # Image processing
  learning/
    __init__.py        # Module init
    research.py        # Deep research feature
    rag_helper.py      # RAG utilities
    prompts.py         # Prompt templates
    guided.py          # Guided learning
    lecture.py         # Lecture mode
    exam.py            # Exam generation
    question_gen.py    # Question generator
    models.py          # Data models
    utils.py           # Utility functions
tests/
  conftest.py          # Shared pytest fixtures
  test_*.py            # Test modules
```

### Key Conventions
1. **Lazy imports** inside functions for optional dependencies
2. **Environment variables** set before importing modules that use them
3. **Global CONFIG** object loaded once, shared across modules
4. **Streaming responses** use generators with `yield`
5. **Thread safety**: use locks for shared mutable state
6. **Language support**: all user-facing strings use TRANSLATIONS dict
7. **No linting tools** configured; follow existing code style

### Git Workflow
- Commit messages: imperative mood ("Add feature", "Fix bug")
- Keep commits atomic and focused
- Run tests before committing: `pytest -x`
- No commits to main without review if collaborating