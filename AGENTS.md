# GangDan - Agent Guidelines

## Quick Start

```bash
pip install -e .
pip install pytest pytest-cov
```

## Critical Architecture Notes

### Entry Points
- **Web server**: `gangdan` or `gangdan --port 8080` (default :5000)
- **CLI REPL**: `gangdan cli`
- **Programmatic**: `python -m gangdan`
- **Entry routing**: `gangdan/cli.py:main()` routes CLI subcommands to `cli_app.py`, web server to `app.py`

### Shared Core (`gangdan/core/`)
Both GUI and CLI share these modules:
- `config.py` - Global `CONFIG` object loaded once at import time
- `ollama_client.py` - Ollama API wrapper (chat, embed, stream)
- `chroma_manager.py` - ChromaDB with auto-recovery on corruption
- `conversation.py` - Chat history with auto-save thread
- `doc_manager.py` - Documentation downloader/indexer
- `web_searcher.py` - DuckDuckGo/SearXNG/Brave search

### Learning Module (`gangdan/learning/`)
Self-contained Flask Blueprint with three features:
- `/question` - Question generator (MCQ, short answer, etc.)
- `/guide` - Guided learning sessions
- `/research` - Multi-phase research reports

### Key Conventions
1. **Lazy imports** for optional dependencies (inside functions)
2. **Environment variables** must be set BEFORE importing modules that use them (especially `GANGDAN_DATA_DIR`)
3. **Global CONFIG** is shared across modules; do not reinitialize
4. **Streaming responses** use generators with `yield`
5. **Thread safety**: locks for shared mutable state
6. **Language support**: all UI strings use `TRANSLATIONS` dict
7. **No linting tools**; follow existing code style

## Testing

### Run Tests
```bash
pytest                              # All tests
pytest -v                           # Verbose
pytest -k "test_config"             # By name pattern
pytest --cov=gangdan                # With coverage
pytest -x                           # Stop on first failure
```

### Single Test
```bash
pytest tests/test_core_config.py::TestConfigDataclass::test_config_defaults -v
```

### Test Fixtures (from `tests/conftest.py`)
- `temp_data_dir` - Isolated temp directory, sets `GANGDAN_DATA_DIR`
- `mock_ollama_available` / `mock_ollama_unavailable` - Mock Ollama API
- `mock_chroma_client` - Mock ChromaDB client
- `cli_runner` - Helper to run CLI commands and capture output

### Important
- Set environment variables BEFORE importing gangdan modules
- All tests run offline with mocked external services
- 142 tests covering core modules and CLI

## Build & Publish

```bash
python -m build                     # Build sdist and wheel
python publish.py release           # Prepare for upload
twine upload dist/*                 # Upload to PyPI
```

## Code Style

### Imports (3 sections, alphabetically sorted)
```python
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from flask import Flask

from gangdan.core.config import CONFIG
```

### Type Hints
- Required on all function signatures
- Use `str | None` (Python 3.10+) but `Optional[str]` for compatibility
- Use `List[str]`, `Dict[str, Any]` from `typing`

### Naming
- Classes: `PascalCase`
- Functions: `snake_case`
- Constants: `UPPER_CASE`
- Private methods: `_leading_underscore`
- Test classes: `Test<Feature>`
- Test functions: `test_<behavior>`

### Docstrings
- Google-style or reStructuredText
- Include Parameters, Returns, Raises sections
- Module docstrings at top of each file

### Formatting
- Line length: 120 characters
- f-strings for formatting
- LF line endings (`.bat` files use CRLF)
- Final newline required

## Error Handling
- `try/except` for external API calls (Ollama, file I/O)
- Return `ToolResult(success=False, error=str(e))` for API functions
- Raise exceptions for invalid arguments in internal functions
- Log errors to `sys.stderr` with context prefix
- Never silently swallow exceptions

## Data Classes
```python
@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)
```

## Git Workflow
- Commit messages: imperative mood ("Add feature", "Fix bug")
- Atomic commits
- Run `pytest -x` before committing
- No direct commits to main without review
