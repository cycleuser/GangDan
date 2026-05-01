"""GangDan CLI Application - Full-featured command-line interface."""

import argparse
import json
import subprocess
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory

# Import core modules
from gangdan.core.config import (
    CONFIG,
    DATA_DIR,
    DOCS_DIR,
    CHROMA_DIR,
    load_config,
    save_config,
    get_proxies,
    load_user_kbs,
    detect_language,
    TRANSLATIONS,
    t,
)
from gangdan.core.ollama_client import OllamaClient
from gangdan.core.chroma_manager import ChromaManager
from gangdan.core.doc_manager import DocManager, DOC_SOURCES
from gangdan.core.web_searcher import WebSearcher
from gangdan.core.conversation import ConversationManager
from gangdan.core.openai_client import OpenAIClient

console = Console()

# Global instances (lazily initialized)
_ollama: Optional[OllamaClient] = None
_chroma: Optional[ChromaManager] = None
_doc_manager: Optional[DocManager] = None
_web_searcher: Optional[WebSearcher] = None
_conversation: Optional[ConversationManager] = None
_chat_client: Optional[object] = None


def get_ollama() -> OllamaClient:
    """Get or create OllamaClient instance."""
    global _ollama
    if _ollama is None:
        _ollama = OllamaClient(CONFIG.ollama_url)
    return _ollama


def get_chat_client():
    """Get or create chat client instance based on config."""
    global _chat_client
    if _chat_client is None:
        provider = CONFIG.chat_provider
        if provider == "ollama":
            _chat_client = get_ollama()
        else:
            _chat_client = OpenAIClient(
                api_key=CONFIG.chat_api_key,
                base_url=CONFIG.chat_api_base_url,
                provider=provider,
            )
    return _chat_client


def get_chroma() -> ChromaManager:
    """Get or create ChromaManager instance."""
    global _chroma
    if _chroma is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _chroma = ChromaManager(str(CHROMA_DIR))
    return _chroma


def get_doc_manager() -> DocManager:
    """Get or create DocManager instance."""
    global _doc_manager
    if _doc_manager is None:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        _doc_manager = DocManager(DOCS_DIR, get_chroma(), get_ollama())
    return _doc_manager


def get_web_searcher() -> WebSearcher:
    """Get or create WebSearcher instance."""
    global _web_searcher
    if _web_searcher is None:
        _web_searcher = WebSearcher()
    return _web_searcher


def get_conversation() -> ConversationManager:
    """Get or create ConversationManager with auto-save."""
    global _conversation
    if _conversation is None:
        _conversation = ConversationManager(max_history=20, auto_save=True)
    return _conversation


# =============================================================================
# Chat Command
# =============================================================================


def cmd_chat(args):
    """Handle chat command with streaming output."""
    message = " ".join(args.message) if args.message else None

    if not message:
        console.print("[red]Error: Please provide a message.[/red]")
        console.print('Usage: gangdan chat "your question here"')
        return 1

    load_config()
    chat_client = get_chat_client()

    model_name = CONFIG.chat_model_name if CONFIG.chat_provider != "ollama" else CONFIG.chat_model
    
    if not model_name:
        console.print("[red]Error: No chat model configured.[/red]")
        console.print("Run: gangdan config set chat_model <model_name>")
        return 1

    if CONFIG.chat_provider == "ollama" and not chat_client.is_available():
        console.print(
            f"[red]Error: Ollama is not available at {CONFIG.ollama_url}[/red]"
        )
        return 1

    # Build context from KB if requested
    context = ""
    references = []

    if args.kb:
        chroma = get_chroma()
        ollama = get_ollama()
        if chroma.client and CONFIG.embedding_model:
            try:
                query_embedding = ollama.embed(message, CONFIG.embedding_model)
                for kb_name in args.kb:
                    results = chroma.search(
                        kb_name, query_embedding, top_k=CONFIG.top_k
                    )
                    for r in results:
                        if r.get("distance", 1.0) < 0.5:
                            context += f"\n[Source: {r['metadata'].get('file', 'unknown')}]\n{r['document']}\n"
                            ref = r["metadata"].get("file", "unknown")
                            if ref not in references:
                                references.append(ref)
            except Exception as e:
                console.print(f"[yellow]Warning: KB search failed: {e}[/yellow]")

    if args.web:
        web = get_web_searcher()
        results = web.search(message, num_results=3)
        for r in results:
            context += f"\n[Web: {r['title']}]\n{r['snippet']}\n"

    # Build messages
    conversation = get_conversation()
    messages = conversation.get_messages(limit=10)

    if context:
        system_msg = f"You are a helpful programming assistant. Use the following context to help answer:\n\n{context}"
        messages = [{"role": "system", "content": system_msg}] + messages

    messages.append({"role": "user", "content": message})

    # Stream response
    console.print()
    full_response = ""

    if args.no_stream:
        with console.status("[bold green]Thinking...", spinner="dots"):
            full_response = chat_client.chat_complete(messages, model_name)
        console.print(Markdown(full_response))
    else:
        for chunk in chat_client.chat_stream(messages, model_name):
            console.print(chunk, end="", highlight=False)
            full_response += chunk
        console.print()

    # Show references
    if references:
        console.print()
        console.print(
            Panel(
                "\n".join(f"- {ref}" for ref in references),
                title="References",
                border_style="dim",
            )
        )

    # Save to conversation history
    conversation.add("user", message)
    conversation.add("assistant", full_response)

    return 0


# =============================================================================
# KB Commands
# =============================================================================


def cmd_kb_list(args):
    """List all knowledge bases."""
    load_config()
    chroma = get_chroma()

    if not chroma.client:
        console.print("[red]ChromaDB is not available.[/red]")
        return 1

    stats = chroma.get_stats()
    user_kbs = load_user_kbs()

    table = Table(title="Knowledge Bases")
    table.add_column("Name", style="cyan")
    table.add_column("Docs", justify="right")
    table.add_column("Type", style="green")

    for name, count in sorted(stats.items()):
        kb_type = "User" if name.startswith("user_") else "Built-in"
        display_name = name
        if name in user_kbs:
            display_name = user_kbs[name].get("display_name", name)
        table.add_row(display_name, str(count), kb_type)

    if not stats:
        console.print("[yellow]No knowledge bases indexed yet.[/yellow]")
        console.print(
            "Run: gangdan docs download <source> && gangdan docs index <source>"
        )
    else:
        console.print(table)

    return 0


def cmd_kb_search(args):
    """Search knowledge bases."""
    query = " ".join(args.query) if args.query else None

    if not query:
        console.print("[red]Error: Please provide a search query.[/red]")
        return 1

    load_config()
    chroma = get_chroma()
    ollama = get_ollama()

    if not chroma.client:
        console.print("[red]ChromaDB is not available.[/red]")
        return 1

    if not CONFIG.embedding_model:
        console.print("[red]No embedding model configured.[/red]")
        console.print("Run: gangdan config set embedding_model <model_name>")
        return 1

    try:
        query_embedding = ollama.embed(query, CONFIG.embedding_model)
    except Exception as e:
        console.print(f"[red]Error embedding query: {e}[/red]")
        return 1

    # Search specified KBs or all
    kb_names = args.kb if args.kb else chroma.list_collections()

    all_results = []
    for kb_name in kb_names:
        results = chroma.search(kb_name, query_embedding, top_k=5)
        for r in results:
            r["kb"] = kb_name
            all_results.append(r)

    # Sort by distance
    all_results.sort(key=lambda x: x.get("distance", 1.0))

    if not all_results:
        console.print("[yellow]No results found.[/yellow]")
        return 0

    console.print(f"\n[bold]Search Results for:[/bold] {query}\n")

    for i, r in enumerate(all_results[:10], 1):
        distance = r.get("distance", 0)
        relevance = max(0, 100 - int(distance * 100))
        source = r.get("metadata", {}).get("file", "unknown")
        kb = r.get("kb", "unknown")

        console.print(
            f"[bold cyan]{i}.[/bold cyan] [{relevance}%] [dim]{kb}[/dim] / {source}"
        )

        # Show snippet
        doc = r.get("document", "")[:200]
        if len(r.get("document", "")) > 200:
            doc += "..."
        console.print(f"   {doc}\n")

    return 0


# =============================================================================
# Docs Commands
# =============================================================================


def cmd_docs_list(args):
    """List downloaded documentation sources."""
    load_config()
    doc_manager = get_doc_manager()
    downloaded = doc_manager.list_downloaded()

    table = Table(title="Downloaded Documentation")
    table.add_column("Source", style="cyan")
    table.add_column("Files", justify="right")
    table.add_column("Display Name")

    for d in sorted(downloaded, key=lambda x: x["name"]):
        name = d["name"]
        display = DOC_SOURCES.get(name, {}).get("name", name)
        table.add_row(name, str(d["files"]), display)

    if not downloaded:
        console.print("[yellow]No documentation downloaded yet.[/yellow]")
        console.print("\nAvailable sources:")
        for key, val in sorted(DOC_SOURCES.items()):
            console.print(f"  - {key}: {val['name']}")
    else:
        console.print(table)

    return 0


def cmd_docs_download(args):
    """Download documentation sources."""
    if not args.sources:
        console.print("[red]Error: Please specify sources to download.[/red]")
        console.print("\nAvailable sources:")
        for key, val in sorted(DOC_SOURCES.items()):
            console.print(f"  - {key}: {val['name']}")
        return 1

    load_config()
    doc_manager = get_doc_manager()

    sources = args.sources
    if "all" in sources:
        sources = list(DOC_SOURCES.keys())

    for source in sources:
        if source not in DOC_SOURCES:
            console.print(f"[yellow]Unknown source: {source}, skipping.[/yellow]")
            continue

        console.print(f"\n[bold]Downloading {source}...[/bold]")
        downloaded, errors = doc_manager.download_source(source)
        console.print(f"  Downloaded: {downloaded}, Errors: {len(errors)}")

    return 0


def cmd_docs_index(args):
    """Index documentation sources."""
    if not args.sources:
        console.print("[red]Error: Please specify sources to index.[/red]")
        return 1

    load_config()

    if not CONFIG.embedding_model:
        console.print("[red]No embedding model configured.[/red]")
        console.print("Run: gangdan config set embedding_model <model_name>")
        return 1

    doc_manager = get_doc_manager()

    sources = args.sources
    if "all" in sources:
        downloaded = doc_manager.list_downloaded()
        sources = [d["name"] for d in downloaded]

    for source in sources:
        console.print(f"\n[bold]Indexing {source}...[/bold]")
        files, chunks = doc_manager.index_source(source)
        console.print(f"  Files: {files}, Chunks: {chunks}")

    return 0


# =============================================================================
# Config Commands
# =============================================================================


def cmd_config_get(args):
    """Show configuration."""
    load_config()

    if args.key:
        value = getattr(CONFIG, args.key, None)
        if value is not None:
            console.print(f"{args.key}: {value}")
        else:
            console.print(f"[red]Unknown config key: {args.key}[/red]")
            return 1
    else:
        table = Table(title="Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value")

        table.add_row("ollama_url", CONFIG.ollama_url)
        table.add_row("chat_model", CONFIG.chat_model or "[dim]not set[/dim]")
        table.add_row("embedding_model", CONFIG.embedding_model or "[dim]not set[/dim]")
        table.add_row("reranker_model", CONFIG.reranker_model or "[dim]not set[/dim]")
        table.add_row("language", CONFIG.language)
        table.add_row("top_k", str(CONFIG.top_k))
        table.add_row("proxy_mode", CONFIG.proxy_mode)
        table.add_row("strict_kb_mode", str(CONFIG.strict_kb_mode))

        console.print(table)
        console.print(f"\n[dim]Data directory: {DATA_DIR}[/dim]")

    return 0


def cmd_config_set(args):
    """Set configuration value."""
    if not args.key or args.value is None:
        console.print("[red]Error: Please provide key and value.[/red]")
        console.print("Usage: gangdan config set <key> <value>")
        return 1

    load_config()

    key = args.key
    value = args.value

    # Type conversion for specific keys
    if key in ("top_k", "chunk_size", "chunk_overlap", "max_context_tokens"):
        try:
            value = int(value)
        except ValueError:
            console.print(f"[red]Error: {key} must be an integer.[/red]")
            return 1
    elif key == "strict_kb_mode":
        value = value.lower() in ("true", "1", "yes")

    if hasattr(CONFIG, key):
        setattr(CONFIG, key, value)
        save_config()
        console.print(f"[green]Set {key} = {value}[/green]")
    else:
        console.print(f"[red]Unknown config key: {key}[/red]")
        return 1

    return 0


# =============================================================================
# Conversation Commands
# =============================================================================


def cmd_conversation_save(args):
    """Save conversation to file."""
    filepath = Path(args.file) if args.file else (DATA_DIR / "conversation_export.json")

    conversation = get_conversation()
    messages = conversation.get_all()

    content = {
        "version": "1.0",
        "app": "GangDan",
        "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "messages": messages,
    }

    filepath.write_text(
        json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    console.print(f"[green]Saved {len(messages)} messages to {filepath}[/green]")
    return 0


def cmd_conversation_load(args):
    """Load conversation from file."""
    if not args.file:
        console.print("[red]Error: Please specify a file to load.[/red]")
        return 1

    filepath = Path(args.file)
    if not filepath.exists():
        console.print(f"[red]File not found: {filepath}[/red]")
        return 1

    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        messages = data.get("messages", [])

        conversation = get_conversation()
        conversation.set_messages(messages)

        console.print(f"[green]Loaded {len(messages)} messages from {filepath}[/green]")
        return 0
    except Exception as e:
        console.print(f"[red]Error loading conversation: {e}[/red]")
        return 1


def cmd_conversation_clear(args):
    """Clear conversation history."""
    conversation = get_conversation()
    conversation.clear()
    console.print("[green]Conversation cleared.[/green]")
    return 0


# =============================================================================
# Run Command
# =============================================================================


def cmd_run(args):
    """Execute a shell command."""
    command = " ".join(args.command) if args.command else None

    if not command:
        console.print("[red]Error: Please provide a command to run.[/red]")
        return 1

    # Security check
    dangerous = ["rm -rf /", "mkfs", "dd if=", ":(){ :|:", "shutdown", "reboot"]
    if any(d in command.lower() for d in dangerous):
        console.print("[red]Error: Potentially dangerous command blocked.[/red]")
        return 1

    console.print(f"[bold]Running:[/bold] {command}\n")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(DATA_DIR),
        )

        if result.stdout:
            console.print(result.stdout)
        if result.stderr:
            console.print(f"[red]{result.stderr}[/red]")

        console.print(f"\n[dim]Exit code: {result.returncode}[/dim]")
        return result.returncode
    except subprocess.TimeoutExpired:
        console.print("[red]Command timed out (60s limit).[/red]")
        return 1
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return 1


# =============================================================================
# AI Command
# =============================================================================


def cmd_ai(args):
    """Generate shell command from natural language."""
    description = " ".join(args.description) if args.description else None

    if not description:
        console.print("[red]Error: Please describe what you want to do.[/red]")
        return 1

    load_config()
    ollama = get_ollama()

    if not CONFIG.chat_model:
        console.print("[red]No chat model configured.[/red]")
        return 1

    prompt = f"""Generate a shell command for the following task. Return ONLY the command, nothing else.

Task: {description}

Command:"""

    messages = [{"role": "user", "content": prompt}]

    with console.status("[bold green]Generating command...", spinner="dots"):
        response = ollama.chat_complete(messages, CONFIG.chat_model, temperature=0.3)

    command = response.strip().strip("`").strip()

    console.print(f"\n[bold]Generated command:[/bold]")
    console.print(Syntax(command, "bash", theme="monokai"))

    if args.run:
        console.print(f"\n[bold]Running...[/bold]\n")
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(DATA_DIR),
            )
            if result.stdout:
                console.print(result.stdout)
            if result.stderr:
                console.print(f"[red]{result.stderr}[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    return 0


# =============================================================================
# Interactive REPL
# =============================================================================


def cmd_repl(args):
    """Start interactive REPL mode."""
    load_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize components
    conversation = get_conversation()

    # Load previous conversation
    restored = conversation.load_auto_saved()
    if restored > 0:
        console.print(f"[green]Restored {restored} previous messages.[/green]")

    console.print(
        Panel(
            "[bold]GangDan Interactive Mode[/bold]\n\n"
            "Type a message to chat, or use commands:\n"
            "  /kb list        - List knowledge bases\n"
            "  /kb search <q>  - Search knowledge bases\n"
            "  /docs list      - List downloaded docs\n"
            "  /run <cmd>      - Execute shell command\n"
            "  /ai <desc>      - Generate shell command\n"
            "  /save [file]    - Save conversation\n"
            "  /load <file>    - Load conversation\n"
            "  /clear          - Clear conversation\n"
            "  /config         - Show configuration\n"
            "  /help           - Show this help\n"
            "  /exit           - Exit REPL",
            title="Welcome",
            border_style="blue",
        )
    )

    # Setup prompt session with history
    history_file = DATA_DIR / "cli_history"
    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
    )

    while True:
        try:
            user_input = session.prompt("\n[gangdan]> ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                parts = user_input[1:].split(maxsplit=1)
                cmd = parts[0].lower()
                cmd_args = parts[1] if len(parts) > 1 else ""

                if cmd in ("exit", "quit", "q"):
                    console.print("[dim]Goodbye![/dim]")
                    break
                elif cmd == "help":
                    console.print(
                        "/kb list, /kb search <query>\n"
                        "/docs list, /docs download <src>, /docs index <src>\n"
                        "/run <command>, /ai <description>\n"
                        "/save [file], /load <file>, /clear\n"
                        "/config, /exit"
                    )
                elif cmd == "kb":
                    kb_parts = cmd_args.split(maxsplit=1)
                    subcmd = kb_parts[0] if kb_parts else "list"
                    if subcmd == "list":
                        cmd_kb_list(argparse.Namespace())
                    elif subcmd == "search" and len(kb_parts) > 1:
                        cmd_kb_search(
                            argparse.Namespace(query=kb_parts[1].split(), kb=None)
                        )
                    else:
                        console.print(
                            "[yellow]Usage: /kb list | /kb search <query>[/yellow]"
                        )
                elif cmd == "docs":
                    doc_parts = cmd_args.split()
                    subcmd = doc_parts[0] if doc_parts else "list"
                    if subcmd == "list":
                        cmd_docs_list(argparse.Namespace())
                    elif subcmd == "download" and len(doc_parts) > 1:
                        cmd_docs_download(argparse.Namespace(sources=doc_parts[1:]))
                    elif subcmd == "index" and len(doc_parts) > 1:
                        cmd_docs_index(argparse.Namespace(sources=doc_parts[1:]))
                    else:
                        console.print(
                            "[yellow]Usage: /docs list | download <src> | index <src>[/yellow]"
                        )
                elif cmd == "run":
                    if cmd_args:
                        cmd_run(argparse.Namespace(command=cmd_args.split()))
                    else:
                        console.print("[yellow]Usage: /run <command>[/yellow]")
                elif cmd == "ai":
                    if cmd_args:
                        cmd_ai(
                            argparse.Namespace(description=cmd_args.split(), run=False)
                        )
                    else:
                        console.print("[yellow]Usage: /ai <description>[/yellow]")
                elif cmd == "save":
                    filepath = cmd_args if cmd_args else None
                    cmd_conversation_save(argparse.Namespace(file=filepath))
                elif cmd == "load":
                    if cmd_args:
                        cmd_conversation_load(argparse.Namespace(file=cmd_args))
                    else:
                        console.print("[yellow]Usage: /load <file>[/yellow]")
                elif cmd == "clear":
                    cmd_conversation_clear(argparse.Namespace())
                elif cmd == "config":
                    cmd_config_get(argparse.Namespace(key=None))
                else:
                    console.print(
                        f"[yellow]Unknown command: /{cmd}. Type /help for commands.[/yellow]"
                    )
            else:
                # Regular chat message
                chat_args = argparse.Namespace(
                    message=user_input.split(), kb=None, web=False, no_stream=False
                )
                cmd_chat(chat_args)

        except KeyboardInterrupt:
            console.print("\n[dim]Use /exit to quit.[/dim]")
            continue
        except EOFError:
            console.print("\n[dim]Goodbye![/dim]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    # Cleanup
    if _conversation:
        _conversation.shutdown()

    return 0


# =============================================================================
# Main CLI Entry Point
# =============================================================================


def cli_main(argv=None):
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="gangdan", description="GangDan CLI - Offline Development Assistant"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # CLI / REPL
    repl_parser = subparsers.add_parser("cli", help="Interactive REPL mode")
    repl_parser.set_defaults(func=cmd_repl)

    # Chat
    chat_parser = subparsers.add_parser("chat", help="Chat with AI")
    chat_parser.add_argument("message", nargs="*", help="Message to send")
    chat_parser.add_argument("--kb", nargs="*", help="Knowledge bases to use")
    chat_parser.add_argument("--web", action="store_true", help="Enable web search")
    chat_parser.add_argument(
        "--no-stream", action="store_true", help="Disable streaming"
    )
    chat_parser.set_defaults(func=cmd_chat)

    # KB
    kb_parser = subparsers.add_parser("kb", help="Knowledge base operations")
    kb_subparsers = kb_parser.add_subparsers(dest="kb_command")

    kb_list_parser = kb_subparsers.add_parser("list", help="List knowledge bases")
    kb_list_parser.set_defaults(func=cmd_kb_list)

    kb_search_parser = kb_subparsers.add_parser("search", help="Search knowledge bases")
    kb_search_parser.add_argument("query", nargs="*", help="Search query")
    kb_search_parser.add_argument("--kb", nargs="*", help="Specific KBs to search")
    kb_search_parser.set_defaults(func=cmd_kb_search)

    # Docs
    docs_parser = subparsers.add_parser("docs", help="Documentation management")
    docs_subparsers = docs_parser.add_subparsers(dest="docs_command")

    docs_list_parser = docs_subparsers.add_parser("list", help="List downloaded docs")
    docs_list_parser.set_defaults(func=cmd_docs_list)

    docs_download_parser = docs_subparsers.add_parser("download", help="Download docs")
    docs_download_parser.add_argument("sources", nargs="*", help="Sources to download")
    docs_download_parser.set_defaults(func=cmd_docs_download)

    docs_index_parser = docs_subparsers.add_parser("index", help="Index docs")
    docs_index_parser.add_argument("sources", nargs="*", help="Sources to index")
    docs_index_parser.set_defaults(func=cmd_docs_index)

    # Config
    config_parser = subparsers.add_parser("config", help="Configuration")
    config_subparsers = config_parser.add_subparsers(dest="config_command")

    config_get_parser = config_subparsers.add_parser("get", help="Get config value")
    config_get_parser.add_argument("key", nargs="?", help="Config key")
    config_get_parser.set_defaults(func=cmd_config_get)

    config_set_parser = config_subparsers.add_parser("set", help="Set config value")
    config_set_parser.add_argument("key", help="Config key")
    config_set_parser.add_argument("value", help="Config value")
    config_set_parser.set_defaults(func=cmd_config_set)

    # Conversation
    conv_parser = subparsers.add_parser("conversation", help="Conversation management")
    conv_subparsers = conv_parser.add_subparsers(dest="conv_command")

    conv_save_parser = conv_subparsers.add_parser("save", help="Save conversation")
    conv_save_parser.add_argument("file", nargs="?", help="Output file")
    conv_save_parser.set_defaults(func=cmd_conversation_save)

    conv_load_parser = conv_subparsers.add_parser("load", help="Load conversation")
    conv_load_parser.add_argument("file", help="Input file")
    conv_load_parser.set_defaults(func=cmd_conversation_load)

    conv_clear_parser = conv_subparsers.add_parser("clear", help="Clear conversation")
    conv_clear_parser.set_defaults(func=cmd_conversation_clear)

    # Run
    run_parser = subparsers.add_parser("run", help="Execute shell command")
    run_parser.add_argument("command", nargs="*", help="Command to run")
    run_parser.set_defaults(func=cmd_run)

    # AI
    ai_parser = subparsers.add_parser("ai", help="Generate command from description")
    ai_parser.add_argument("description", nargs="*", help="Task description")
    ai_parser.add_argument(
        "--run", action="store_true", help="Run the generated command"
    )
    ai_parser.set_defaults(func=cmd_ai)

    # Parse args
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(cli_main())
