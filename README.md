# GangDan (纲担)

LLM-powered knowledge management and teaching assistant with offline support.

> **GangDan (纲担)** — Principled and Accountable.

## Features

### Knowledge Management
- **Unified Literature Search** — Search arXiv, bioRxiv, medRxiv, Semantic Scholar, CrossRef, OpenAlex, DBLP, PubMed, and GitHub in one interface. AI-powered query refinement with automatic translation and synonym expansion.
- **Batch Operations** — Multi-select, select-all, batch convert (PDF/HTML/TeX to Markdown with image and formula preservation), batch add to knowledge base. Sort by relevance, date, or title.
- **Smart Renaming** — Downloaded papers automatically renamed to citation format: `Author et al. (Year) - Title.pdf`
- **LLM-Generated Wiki** — Build structured wiki pages from knowledge base content with cross-KB concept linking.
- **Image Gallery** — Browse and search images stored in knowledge bases with context and source attribution.
- **Document Manager** — One-click download and indexing of 30+ library docs (Python, Rust, Go, JS, CUDA, Docker, etc.). Upload custom docs, batch operations, GitHub repo search, web search to KB.

### Teaching Assistant
- **Question Generator** — MCQ, short answer, fill-in-the-blank, true/false from KB content.
- **Guided Learning** — Auto-extract knowledge points, generate interactive lessons with Q&A.
- **Deep Research** — Multi-phase research pipeline: topic decomposition → RAG research → comprehensive reports.
- **Lecture Maker** — Generate structured lecture content from KB materials.
- **Exam Generator** — Create complete exam papers with answer keys from KB content.

### Core
- **RAG Chat** — Streaming chat with knowledge base retrieval and web search. Strict KB mode ensures grounded answers.
- **AI Command Assistant** — Natural language → shell commands, draggable to terminal.
- **Built-in Terminal** — Run commands with stdout/stderr display.
- **Literature Review & Paper Writer** — Generate academic reviews and papers from KB content.
- **Conversation Save/Load** — JSON export/import for session continuity.
- **10-Language UI** — Chinese, English, Japanese, French, Russian, German, Italian, Spanish, Portuguese, Korean.
- **Dark/Light Theme** — Full theme support with CSS variables.
- **Offline by Design** — Runs entirely on your machine. No cloud APIs required.

### CLI
- Streaming chat (`gangdan chat "question"`), interactive REPL (`gangdan cli`)
- KB operations, doc management, config, conversation persistence
- AI command generation, shell execution with safety checks

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai/) running locally (default `http://localhost:11434`)
- Chat model (e.g. `ollama pull qwen2.5`)
- Embedding model (e.g. `ollama pull nomic-embed-text`)

## Installation

```bash
pip install gangdan
gangdan                    # Web GUI
gangdan cli                # Interactive CLI
gangdan --port 8080        # Custom port
```

From source:

```bash
git clone https://github.com/cycleuser/GangDan.git
cd GangDan
pip install -e .
gangdan
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

## Ollama Setup

```bash
ollama serve
ollama pull qwen2.5
ollama pull nomic-embed-text
```

## Project Structure

```
GangDan/
├── pyproject.toml
├── README.md / README_CN.md
├── gangdan/
│   ├── __init__.py / __main__.py
│   ├── cli.py / cli_app.py          # CLI entry + REPL
│   ├── app.py                       # Flask backend
│   ├── learning_routes.py           # Learning module blueprint
│   ├── preprint_routes.py           # Preprint search + convert
│   ├── research_routes.py           # Paper search
│   ├── kb_routes.py                 # Custom KB management
│   ├── export_routes.py             # Export API
│   ├── core/                        # Shared modules
│   │   ├── config.py                # Config, i18n, translations
│   │   ├── ollama_client.py         # Ollama API
│   │   ├── chroma_manager.py        # ChromaDB
│   │   ├── vector_db.py             # Multi-backend vector DB
│   │   ├── kb_manager.py            # Custom KB CRUD
│   │   ├── conversation.py          # Chat history
│   │   ├── doc_manager.py           # Doc download/index
│   │   ├── wiki_builder.py          # LLM wiki generation
│   │   ├── preprint_fetcher.py      # Preprint search
│   │   ├── preprint_converter.py    # HTML/TeX/PDF → MD
│   │   ├── pdf_converter.py         # PDF → MD (marker/mineru/docling)
│   │   ├── export_manager.py        # Batch convert/export
│   │   ├── web_searcher.py          # Web search
│   │   └── ...
│   ├── templates/index.html         # Main SPA template
│   └── static/{css,js}/             # Frontend assets
├── tests/                           # Test suite
├── images/                          # Screenshots
└── removed/                         # Deprecated files
```

## Architecture

```
┌──────────────┐    ┌──────────────┐
│   Flask GUI  │    │  CLI / REPL  │
│   (app.py)   │    │ (cli_app.py) │
└──────┬───────┘    └──────┬───────┘
       │                   │
┌──────┴───────────────────┴──────┐
│          gangdan/core/          │
└─────────────────────────────────┘
       │                   │
┌──────┴───────┐    ┌──────┴───────┐
│    Ollama    │    │   ChromaDB   │
└──────────────┘    └──────────────┘
```

## Configuration

All settings through the **Settings** tab: Ollama URL, chat/embedding/reranker models, proxy, context length, output language, vector DB type.

## Testing

```bash
pip install pytest pytest-cov
pytest tests/ -v
pytest tests/ --cov=gangdan
```

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) for details.
