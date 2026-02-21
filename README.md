# GangDan - Offline Dev Assistant

A local-first, offline programming assistant powered by [Ollama](https://ollama.ai/) and [ChromaDB](https://www.trychroma.com/). Chat with LLMs, build a vector knowledge base from documentation, run terminal commands, and get AI-generated shell suggestions -- all from a single browser tab.

> **GangDan (纲担)** -- Principled and Accountable.

![Chat Panel](images/chat.png)

## Features

- **RAG Chat** -- Ask questions with optional retrieval from a local ChromaDB knowledge base and/or web search (DuckDuckGo, SearXNG, Brave). Responses stream in real-time via SSE.
- **AI Command Assistant** -- Describe what you want to do in natural language; the assistant generates a shell command you can drag-and-drop into the terminal, execute, and auto-summarize.
- **Built-in Terminal** -- Run commands directly in the browser with stdout/stderr display.
- **Documentation Manager** -- One-click download and indexing of 30+ popular library docs (Python, Rust, Go, JS, C/C++, CUDA, Docker, SciPy, Scikit-learn, SymPy, Jupyter, etc.). Batch operations and GitHub repo search included.
- **10-Language UI** -- Switch between Chinese, English, Japanese, French, Russian, German, Italian, Spanish, Portuguese, and Korean without page reload.
- **Proxy Support** -- None / system / manual proxy modes for both the chat backend and documentation downloads.
- **Offline by Design** -- Runs entirely on your machine. No cloud APIs required.

## Screenshots

| Chat | Terminal |
|:----:|:--------:|
| ![Chat](images/chat.png) | ![Terminal](images/terminal.png) |

| Documentation | Settings |
|:-------------:|:--------:|
| ![Docs](images/documents.png) | ![Settings](images/setting.png) |

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai/) running locally (default `http://localhost:11434`)
- A chat model pulled in Ollama (e.g. `ollama pull qwen2.5`)
- An embedding model for RAG (e.g. `ollama pull nomic-embed-text`)

## Installation

### Method 1: Install from PyPI (Recommended)

```bash
pip install gangdan
```

After installation, launch directly:

```bash
# Start GangDan
gangdan

# Or use python -m
python -m gangdan

# Custom host and port
gangdan --host 127.0.0.1 --port 8080

# Specify a custom data directory
gangdan --data-dir /path/to/my/data
```

### Method 2: Install from Source (Development)

```bash
# 1. Clone the repository
git clone https://github.com/cycleuser/GangDan.git
cd GangDan

# 2. (Optional) Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows

# 3. Install in editable mode with all dependencies
pip install -e .

# 4. Launch GangDan
gangdan
```

### Ollama Setup

Make sure Ollama is installed and running before starting GangDan:

```bash
# Start Ollama service
ollama serve

# Pull a chat model
ollama pull qwen2.5

# Pull an embedding model for RAG
ollama pull nomic-embed-text
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

## CLI Options

```
gangdan [OPTIONS]

Options:
  --host TEXT       Host to bind to (default: 0.0.0.0)
  --port INT        Port to listen on (default: 5000)
  --debug           Enable Flask debug mode
  --data-dir PATH   Custom data directory
  --version         Show version and exit
```

## Project Structure

```
GangDan/
├── pyproject.toml              # Package metadata & build config
├── MANIFEST.in                 # Source distribution manifest
├── LICENSE                     # GPL-3.0-or-later
├── README.md                   # English documentation
├── README_CN.md                # Chinese documentation
├── gangdan/
│   ├── __init__.py             # Package version
│   ├── __main__.py             # python -m gangdan entry
│   ├── cli.py                  # CLI argument parsing & startup
│   ├── app.py                  # Flask backend (routes, Ollama, ChromaDB, i18n)
│   ├── templates/
│   │   └── index.html          # Jinja2 HTML template
│   └── static/
│       ├── css/
│       │   └── style.css       # Application styles (dark theme)
│       └── js/
│           ├── i18n.js         # Internationalization & state management
│           ├── utils.js        # Panel switching & toast notifications
│           ├── markdown.js     # Markdown / LaTeX (KaTeX) rendering
│           ├── chat.js         # Chat panel & SSE streaming
│           ├── terminal.js     # Terminal & AI command assistant
│           ├── docs.js         # Documentation download & indexing
│           └── settings.js     # Settings panel & initialization
├── images/                     # Screenshots
├── publish.py                  # PyPI publish helper script
└── test_package.py             # Comprehensive package test suite
```

Runtime data (created automatically):

```
~/.gangdan/                     # Default when installed via pip
  ├── gangdan_config.json       # Persisted settings
  ├── docs/                     # Downloaded documentation
  └── chroma/                   # ChromaDB vector store
```

## Architecture

The frontend and backend are fully decoupled:

- **Backend** (`app.py`) -- A single Python file containing Flask routes, the Ollama client, ChromaDB manager, documentation downloader, web searcher, and conversation manager. All server-side configuration is injected into the template via a `window.SERVER_CONFIG` block.
- **Frontend** (`templates/` + `static/`) -- Pure HTML/CSS/JS with no build step. JavaScript files are loaded in dependency order and share state through global functions. KaTeX is loaded from CDN for LaTeX rendering.

ChromaDB is initialized with automatic corruption recovery: if the database is damaged, it is backed up and recreated transparently.

## Configuration

All settings are managed through the **Settings** tab in the UI:

| Setting | Description |
|---------|-------------|
| Ollama URL | Ollama server address (default `http://localhost:11434`) |
| Chat Model | Model for conversation (e.g. `qwen2.5:7b-instruct`) |
| Embedding Model | Model for RAG embeddings (e.g. `nomic-embed-text`) |
| Reranker Model | Optional reranker for better search results |
| Proxy Mode | `none` / `system` / `manual` for network requests |

Settings are persisted to `gangdan_config.json` in the data directory.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) for details.
