# GangDan-Refined

Modular, agent-pipeline architecture for LLM-powered knowledge management. Each function is an independent, composable agent communicating via JSON.

> **GangDan (纲担)** — Principled and Accountable.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLI Tools (gd-*)                           │
│  gd-config  gd-models  gd-chat  gd-search  gd-summarize      │
│  gd-translate  gd-embed  gd-ask  gd-kb  gd-docs             │
│  gd-convert  gd-research  gd-learn  gd-preprint               │
└──────────────────────────┬──────────────────────────────────────┘
                           │ --json / --stdin piping
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Agent Pipeline System                          │
│  AgentInput ──► Agent ──► AgentOutput ──► Agent ──► ...         │
│  Pipeline(A) | B | C  ──►  PipelineResult                       │
│  Protocol v2.0: metadata, pipeline_id, timestamps               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┼────────────────┐
              ▼            ▼                ▼
┌──────────────────┐ ┌──────────┐ ┌─────────────────┐
│   Core Modules   │ │   LLM    │ │    Storage       │
│  config  i18n    │ │ ollama   │ │  chroma_manager  │
│  errors constants│ │ factory  │ │  kb_manager      │
│  port_utils      │ │ openai_  │ │  vector_db       │
│                  │ │ compat   │ │  conversation    │
│                  │ │ models   │ │  doc_manager     │
└──────────────────┘ └──────────┘ └─────────────────┘
              │            │                │
              ▼            ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Web UI (Flask)                               │
│  156+ routes across 8 blueprints:                                │
│  kb(28) learning(25) docs(10) preprint(14) research(16)         │
│  export(7) chat(2) settings(6) api(48)                         │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### Agent Pipeline Architecture

Each function is a standalone **agent** with a standardized JSON protocol:

```python
# Agent Protocol v2.0
AgentInput  →  {query, text, file_path, data, options, metadata}
AgentOutput →  {success, data, error, metadata, protocol_version}
```

Agents are composable via Unix pipes or Python API:

```bash
# CLI pipeline — search → summarize → translate
gd-search "quantum computing" --json | gd-summarize --stdin --json | gd-translate --stdin --to zh --json
```

```python
# Python API pipeline
from gangdan_refined.agents import SearchAgent, SummarizeAgent, TranslateAgent
from gangdan_refined.agents.pipeline import Pipeline

pipeline = Pipeline(SearchAgent(), SummarizeAgent(), TranslateAgent())
result = pipeline.run(AgentInput(query="quantum computing"))
print(result.data["translation"])
```

### Grouped Configuration

Configuration is organized into 9 dataclass groups instead of a flat 50+ field monolith:

| Group | Fields | Example |
|-------|--------|---------|
| `proxy` | mode, http, https | `proxy.mode = "none"` |
| `llm` | chat_model, embedding_model, ollama_url, ... | `llm.chat_model = "qwen2.5:7b"` |
| `storage` | top_k, chunk_size, chunk_overlap, ... | `storage.top_k = 5` |
| `search` | web_search_engine, research_sources, ... | `search.web_search_engine = "duckduckgo"` |
| `learning` | default_question_type, num_questions, ... | `learning.default_question_type = "mcq"` |
| `adaptive` | auto_chunk_size, auto_context_length, ... | `adaptive.auto_chunk_size = True` |
| `document` | pdf_converter, download_retries, ... | `document.pdf_converter = "marker"` |
| `ui` | language, theme, ... | `ui.language = "en"` |
| `logging` | level, file, ... | `logging.level = "INFO"` |

### Internationalization (i18n)

437 translation keys across 10 languages, stored externally in `core/locales/translations.json`:

```python
from gangdan_refined.core.i18n import t
text = t("chat.send")  # → "Send" / "发送" / "送信" etc.
```

## 14 Agents

| Agent | CLI Command | Description |
|-------|-------------|-------------|
| ConfigAgent | `gd-config` | View and modify configuration |
| ModelsAgent | `gd-models` | List and manage LLM models |
| ChatAgent | `gd-chat` | Interactive LLM chat |
| SearchAgent | `gd-search` | Web and academic search |
| SummarizeAgent | `gd-summarize` | Summarize text (paragraph/bullet/outline) |
| TranslateAgent | `gd-translate` | Translate text between languages |
| EmbedAgent | `gd-embed` | Generate text embeddings |
| AskAgent | `gd-ask` | RAG-based question answering over knowledge bases |
| KBAgent | `gd-kb` | Knowledge base CRUD and search |
| DocsAgent | `gd-docs` | Download and index documentation |
| ConvertAgent | `gd-convert` | Convert PDF/HTML/TeX to Markdown |
| ResearchAgent | `gd-research` | Multi-phase deep research |
| LearnAgent | `gd-learn` | Question generation, guided learning, exams |
| PreprintAgent | `gd-preprint` | Search and convert academic preprints |

## Installation

```bash
# From PyPI (when published)
pip install gangdan-refined

# From source
git clone https://github.com/cycleuser/GangDan.git
cd GangDan/gangdan-refined
pip install -e .

# With optional dependencies
pip install -e ".[search]"   # Web search (duckduckgo, searxng)
pip install -e ".[pdf]"      # PDF conversion (marker, docling)
pip install -e ".[analytics]" # Analytics
pip install -e ".[all]"      # Everything
```

## Quick Start

### CLI

```bash
# View configuration
gd-config --json show

# List available models
gd-models --json

# Search the web
gd-search "transformer architecture" --json

# Summarize text
gd-summarize "Long text here..." --style bullet --json

# Translate
gd-translate "Hello world" --to zh --json

# Pipeline composition
gd-search "quantum computing" --json | gd-summarize --stdin --json

# Knowledge base operations
gd-kb --action list --json
gd-kb --action create --name my-kb --json

# Ask a question over knowledge bases
gd-ask "What is RAG?" --kb-names my-kb --json

# Web interface
gd-web --port 8080
```

### Python API

```python
from gangdan_refined.agents import SearchAgent, SummarizeAgent, TranslateAgent
from gangdan_refined.agents.protocol import AgentInput
from gangdan_refined.agents.pipeline import Pipeline

# Single agent
agent = SearchAgent()
result = agent.run(AgentInput(query="transformer architecture"))
print(result.data["results"])

# Pipeline composition
pipeline = Pipeline(SearchAgent(), SummarizeAgent())
result = pipeline.run(AgentInput(query="quantum computing"))
print(result.data["summary"])

# Pipeline with | operator
pipeline = Pipeline(SearchAgent()) | SummarizeAgent() | TranslateAgent()
result = pipeline.run(AgentInput(query="neural networks", options={"target_language": "zh"}))
```

## Project Structure

```
gangdan-refined/
├── pyproject.toml                     # Package config, 13 CLI entry points
├── gangdan_refined/
│   ├── __init__.py / __main__.py      # Package entry
│   ├── cli.py                          # CLI router
│   ├── cli_app/                        # Interactive REPL
│   ├── api.py                          # Top-level API exports
│   ├── agents/                         # 14 agents + protocol + pipeline
│   │   ├── base.py                     # BaseAgent ABC
│   │   ├── protocol.py                 # AgentInput/Output/Metadata, v2.0
│   │   ├── pipeline.py                 # Pipeline composition engine
│   │   ├── __init__.py                 # Registry: get_agent(), list_agents()
│   │   ├── config_agent.py             # gd-config
│   │   ├── models_agent.py             # gd-models
│   │   ├── chat_agent.py              # gd-chat
│   │   ├── search_agent.py            # gd-search
│   │   ├── summarize_agent.py         # gd-summarize
│   │   ├── translate_agent.py         # gd-translate
│   │   ├── embed_agent.py             # gd-embed
│   │   ├── ask_agent.py               # gd-ask
│   │   ├── kb_agent.py                # gd-kb
│   │   ├── docs_agent.py              # gd-docs
│   │   ├── convert_agent.py           # gd-convert
│   │   ├── research_agent.py          # gd-research
│   │   ├── learn_agent.py             # gd-learn
│   │   └── preprint_agent.py          # gd-preprint
│   ├── commands/                       # CLI command implementations
│   │   ├── common.py                  # Shared arg parsing, output formatting
│   │   ├── config.py / models.py / chat.py / search.py
│   │   ├── summarize.py / translate.py / embed.py / ask.py
│   │   ├── kb.py / docs.py / convert.py / research.py / web.py
│   ├── core/                           # Shared modules
│   │   ├── config.py                  # 9 grouped dataclass configs
│   │   ├── i18n.py                    # External translation loader
│   │   ├── constants.py               # Path constants
│   │   ├── errors.py                  # Error hierarchy
│   │   ├── port_utils.py             # Port detection
│   │   └── locales/translations.json # 437 keys × 10 languages
│   ├── llm/                            # LLM abstraction
│   │   ├── ollama.py                 # Ollama client
│   │   ├── openai_compat.py          # OpenAI-compatible providers
│   │   ├── factory.py                # Provider factory
│   │   └── models.py                 # Provider configs
│   ├── storage/                        # Persistence layer
│   │   ├── chroma_manager.py         # ChromaDB with auto-recovery
│   │   ├── kb_manager.py             # Knowledge base CRUD
│   │   ├── vector_db.py              # Multi-backend vector DB
│   │   ├── conversation.py           # Chat history with auto-save
│   │   ├── doc_manager.py           # Document download/index
│   │   └── image_handler.py         # Image extraction/storage
│   ├── search/                         # Search backends
│   │   ├── web_searcher.py           # DuckDuckGo/SearXNG/Brave
│   │   ├── research_searcher.py       # Academic search (arXiv, S2, etc.)
│   │   ├── adaptive_search.py        # Query refinement
│   │   └── query_expander.py        # Translation + synonym expansion
│   ├── learning/                       # Teaching module
│   │   ├── question_gen.py           # MCQ/short answer/TF generation
│   │   ├── guided.py                 # Guided learning sessions
│   │   ├── exam.py                   # Exam generation
│   │   ├── lecture.py                # Lecture content
│   │   ├── research.py              # Multi-phase research reports
│   │   └── prompts.py               # Prompt templates
│   ├── document/                       # Document processing
│   │   ├── pdf_converter.py         # PDF → Markdown
│   │   ├── pdf_downloader.py        # Paper download
│   │   ├── pdf_renamer.py          # Citation-format naming
│   │   └── preprint/                # Preprint search/convert/batch
│   ├── research/                       # Deep research pipeline
│   │   ├── pipeline.py              # Multi-phase research
│   │   ├── models.py                # Data models
│   │   └── export.py                # Report export
│   └── web/                            # Flask web UI
│       ├── app.py                    # Flask factory (8 blueprints)
│       └── routes/                   # 156+ route handlers
│           ├── kb.py / learning.py / docs.py / preprint.py
│           ├── research.py / export.py / chat.py / settings.py
│           └── api.py                # REST API routes
└── tests/                              # 352 tests
    ├── test_agent_protocol.py         # Protocol layer tests
    ├── test_agent_base_pipeline.py    # BaseAgent + Pipeline tests
    ├── test_agent_whitebox.py        # 14 agents with mocked deps
    ├── test_pipeline_e2e.py          # Pipeline composition E2E
    ├── test_cli_commands.py           # CLI command tests
    ├── test_edge_cases.py             # Error handling + edge cases
    ├── test_config.py                 # Config tests
    ├── test_llm.py                    # LLM client tests
    ├── test_errors.py                 # Error hierarchy tests
    ├── test_web_routes.py             # Web route tests
    └── test_architecture.py           # Architecture validation
```

## Testing

```bash
pip install pytest pytest-cov

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=gangdan_refined

# Run specific test file
pytest tests/test_agent_whitebox.py -v

# Stop on first failure
pytest tests/ -x
```

### Test Coverage

| Module | Tests | Focus |
|--------|-------|-------|
| Protocol | 60 | AgentInput/Output/Metadata, encode/decode, validation |
| BaseAgent | 19 | Agent ABC, CLI args, JSON/text output |
| Pipeline | 17 | Composition, __or__, error propagation, data flow |
| White-box | 35+ | All 14 agents with mocked dependencies |
| E2E | 21 | Pipeline composition with real and test agents |
| CLI | 16 | All 12 CLI commands, JSON/text output |
| Errors | 15 | Edge cases, whitespace, None handling |
| Config | 13 | Config groups, validation, save/load |
| LLM | 12 | Ollama client, factory, errors |
| Web Routes | 44 | All page routes and API endpoints |
| Architecture | 15 | Module structure, imports, conventions |

## Agent Protocol v2.0

### Input Format

```json
{
  "query": "quantum computing",
  "text": "Optional text content for processing",
  "file_path": "/path/to/document.pdf",
  "data": {"key": "value"},
  "options": {"model": "qwen2.5:7b", "language": "zh"},
  "metadata": {
    "agent": "gd-search",
    "version": "2.0.0",
    "timestamp": "2026-05-22T10:30:00+00:00",
    "pipeline_id": "pipe_12345678"
  }
}
```

### Output Format

```json
{
  "success": true,
  "data": {
    "results": [...],
    "count": 10,
    "source": "web"
  },
  "error": null,
  "metadata": {
    "agent": "gd-search",
    "version": "2.0.0",
    "timestamp": "2026-05-22T10:30:01+00:00",
    "pipeline_id": "pipe_12345678"
  },
  "protocol_version": "2.0"
}
```

### Pipeline Composition

```python
# Python: Pipeline with | operator
pipeline = Pipeline(SearchAgent()) | SummarizeAgent() | TranslateAgent()
result = pipeline.run(AgentInput(query="neural networks"))

# CLI: Unix pipe chain
gd-search "topic" --json | gd-summarize --stdin --json | gd-translate --stdin --to zh --json
```

Pipeline results track each step:

```json
{
  "success": true,
  "data": {...},
  "steps": [
    {"name": "gd-search", "duration_ms": 450.2, "success": true},
    {"name": "gd-summarize", "duration_ms": 1200.5, "success": true}
  ],
  "pipeline_id": "pipe_1779336607901",
  "total_duration_ms": 1650.7,
  "protocol_version": "2.0"
}
```

## Ollama Setup

```bash
ollama serve
ollama pull qwen2.5
ollama pull nomic-embed-text
```

## Configuration

All settings via `gd-config` CLI or the Web UI Settings tab:

```bash
# Show all config
gd-config --json show

# Get a specific value
gd-config --json get llm.chat_model

# Set a value
gd-config --json set llm.chat_model=qwen2.5:7b

# List LLM providers
gd-config --json providers
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai/) running locally (default `http://localhost:11434`)
- Chat model (e.g. `ollama pull qwen2.5`)
- Embedding model (e.g. `ollama pull nomic-embed-text`)

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) for details.