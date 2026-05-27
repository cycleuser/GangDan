"""GangDan Refined - CLI entry point.

Supports two modes:
1. Subcommand mode: gangdan-refined chat "hello", gangdan-refined search "query", etc.
2. Legacy mode: gangdan-refined (interactive REPL), gangdan-refined web (server)

Can also be called via individual gd-* commands:
    gd-chat, gd-search, gd-kb, gd-docs, gd-config, gd-translate,
    gd-summarize, gd-ask, gd-embed, gd-models, gd-convert, gd-web
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="gangdan-refined",
        description="GangDan Refined - LLM-powered knowledge management assistant",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Web server port (default: 5000)",
    )
    parser.add_argument(
        "--host", type=str, default=None,
        help="Web server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="output_json",
        help="Output results as JSON (for AI/pipe consumption)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Core commands
    subparsers.add_parser("web", help="Start web server")
    subparsers.add_parser("cli", help="Start interactive REPL")

    # Individual tool subcommands (same as gd-* commands)
    chat_p = subparsers.add_parser("chat", help="Send a message to an LLM")
    chat_p.add_argument("message", nargs="?", help="Message to send")
    chat_p.add_argument("--stdin", action="store_true", help="Read from stdin")
    chat_p.add_argument("--model", "-m", default="", help="Model name")
    chat_p.add_argument("--provider", "-p", default="", help="LLM provider")
    chat_p.add_argument("--system", "-s", default="", help="System prompt")
    chat_p.add_argument("--stream", action="store_true", help="Stream output")
    chat_p.add_argument("--temperature", "-t", type=float, default=0.7)

    search_p = subparsers.add_parser("search", help="Search web or academic papers")
    search_p.add_argument("query", help="Search query")
    search_p.add_argument("--source", "-s", default="web",
                           choices=["web", "arxiv", "semantic_scholar", "crossref", "pubmed", "github", "openalex", "dblp"])
    search_p.add_argument("--max", "-n", type=int, default=10)

    kb_p = subparsers.add_parser("kb", help="Knowledge base operations")
    kb_sub = kb_p.add_subparsers(dest="kb_action")
    kb_sub.add_parser("list", help="List knowledge bases")
    kb_create = kb_sub.add_parser("create", help="Create a KB")
    kb_create.add_argument("name", help="KB display name")
    kb_search = kb_sub.add_parser("search", help="Search a KB")
    kb_search.add_argument("kb_name", help="KB internal name")
    kb_search.add_argument("query", help="Search query")

    ask_p = subparsers.add_parser("ask", help="Ask a question (RAG)")
    ask_p.add_argument("question", nargs="?", help="Question")
    ask_p.add_argument("--stdin", action="store_true")
    ask_p.add_argument("--kb", "-k", default="default")
    ask_p.add_argument("--top-k", "-n", type=int, default=None)
    ask_p.add_argument("--no-generate", action="store_true", help="Only retrieve, don't generate")

    models_p = subparsers.add_parser("models", help="List available models")
    models_p.add_argument("--chat", action="store_true", help="Chat models only")
    models_p.add_argument("--embed", action="store_true", help="Embedding models only")
    models_p.add_argument("--info", "-i", default="", help="Model info")

    config_p = subparsers.add_parser("config", help="View/modify configuration")
    config_sub = config_p.add_subparsers(dest="cfg_action")
    config_sub.add_parser("show", help="Show configuration")
    config_set = config_sub.add_parser("set", help="Set a config value")
    config_set.add_argument("key_value", help="key=value")
    config_get = config_sub.add_parser("get", help="Get a config value")
    config_get.add_argument("key", help="Config key")
    config_sub.add_parser("providers", help="List LLM providers")

    translate_p = subparsers.add_parser("translate", help="Translate text")
    translate_p.add_argument("text", nargs="?")
    translate_p.add_argument("--stdin", action="store_true")
    translate_p.add_argument("--to", "-t", default="en")
    translate_p.add_argument("--from", "-f", dest="source_lang", default="auto")

    summarize_p = subparsers.add_parser("summarize", help="Summarize text")
    summarize_p.add_argument("text", nargs="?")
    summarize_p.add_argument("--stdin", action="store_true")
    summarize_p.add_argument("--style", "-s", default="paragraph",
                              choices=["paragraph", "bullet", "abstract", "key_points", "eli5"])

    embed_p = subparsers.add_parser("embed", help="Generate embeddings")
    embed_p.add_argument("texts", nargs="*")
    embed_p.add_argument("--stdin", action="store_true")
    embed_p.add_argument("--model", "-m", default="")

    convert_p = subparsers.add_parser("convert", help="Convert PDF/CAJ to Markdown")
    convert_p.add_argument("file", nargs="?")
    convert_p.add_argument("--stdin", action="store_true")
    convert_p.add_argument("--output", "-o", default="")

    args = parser.parse_args()

    # Check for first-run setup wizard
    cmd = args.command
    if cmd is None or cmd in ("cli", "web"):
        from .core.setup_wizard import is_first_run, run_cli_wizard

        if is_first_run():
            print("[GangDan] First-time setup detected. Starting configuration wizard...", file=sys.stderr)
            success = run_cli_wizard()
            if not success:
                print("[GangDan] Setup cancelled. Exiting.", file=sys.stderr)
                sys.exit(0)
            print("[GangDan] Configuration saved. Continuing...", file=sys.stderr)

    # Route to appropriate handler
    cmd = args.command

    if cmd == "web" or (cmd is None and args.port is not None):
        _start_web(args.host, args.port)
    elif cmd == "cli" or cmd is None:
        _start_cli()
    elif cmd in ("chat", "search", "kb", "ask", "models", "config",
                "translate", "summarize", "embed", "convert"):
        _dispatch_command(cmd, args)
    else:
        parser.print_help()


def _start_cli() -> None:
    from .cli_app.repl import start_repl
    start_repl()


def _start_web(host=None, port=None) -> None:
    import sys
    from .core.config import load_config
    from .core.constants import DEFAULT_WEB_HOST, DEFAULT_WEB_PORT

    load_config()
    web_host = host or DEFAULT_WEB_HOST
    web_port = port or DEFAULT_WEB_PORT

    try:
        from .web.app import create_app
        app = create_app()
        print(f"[GangDan] Starting web server on {web_host}:{web_port}", file=sys.stderr)
        app.run(host=web_host, port=web_port, debug=False, threaded=True)
    except ImportError as e:
        print(f"[GangDan] Web dependencies not installed: {e}", file=sys.stderr)
        sys.exit(1)


def _dispatch_command(cmd: str, args) -> None:
    """Dispatch to the appropriate gd-* command module."""
    cmd_map = {
        "chat": ".commands.chat",
        "search": ".commands.search",
        "kb": ".commands.kb",
        "ask": ".commands.ask",
        "models": ".commands.models",
        "config": ".commands.config",
        "translate": ".commands.translate",
        "summarize": ".commands.summarize",
        "embed": ".commands.embed",
        "convert": ".commands.convert",
    }
    module_path = cmd_map.get(cmd)
    if module_path:
        import importlib
        from . import commands as cmd_pkg
        module = importlib.import_module(module_path, package="gangdan_refined")
        # Build args from parsed namespace
        if cmd == "chat":
            argv = []
            if args.message:
                argv.append(args.message)
            if args.stdin:
                argv.append("--stdin")
            if args.model:
                argv.extend(["--model", args.model])
            if args.provider:
                argv.extend(["--provider", args.provider])
            if args.system:
                argv.extend(["--system", args.system])
            if args.stream:
                argv.append("--stream")
            if args.output_json:
                argv.append("--json")
            module.main(argv)
        elif cmd == "search":
            argv = [args.query]
            argv.extend(["--source", args.source])
            argv.extend(["--max", str(args.max)])
            if args.output_json:
                argv.append("--json")
            module.main(argv)
        elif cmd == "kb":
            argv = []
            if args.kb_action == "list":
                argv = ["list"]
            elif args.kb_action == "create":
                argv = ["create", args.name]
            elif args.kb_action == "search":
                argv = ["search", args.kb_name, args.query]
            else:
                argv = ["list"]
            if args.output_json:
                argv.append("--json")
            module.main(argv)
        elif cmd == "ask":
            argv = []
            if args.question:
                argv.append(args.question)
            if args.stdin:
                argv.append("--stdin")
            argv.extend(["--kb", args.kb])
            if args.top_k:
                argv.extend(["--top-k", str(args.top_k)])
            if args.no_generate:
                argv.append("--no-generate")
            if args.output_json:
                argv.append("--json")
            module.main(argv)
        elif cmd == "models":
            argv = []
            if args.chat:
                argv.append("--chat")
            if args.embed:
                argv.append("--embed")
            if args.info:
                argv.extend(["--info", args.info])
            if args.output_json:
                argv.append("--json")
            module.main(argv)
        elif cmd == "config":
            argv = []
            if args.cfg_action == "show":
                argv = ["show"]
            elif args.cfg_action == "set":
                argv = ["set", args.key_value]
            elif args.cfg_action == "get":
                argv = ["get", args.key]
            elif args.cfg_action == "providers":
                argv = ["providers"]
            else:
                argv = ["show"]
            if args.output_json:
                argv.append("--json")
            module.main(argv)
        elif cmd == "translate":
            argv = []
            if args.text:
                argv.append(args.text)
            if args.stdin:
                argv.append("--stdin")
            argv.extend(["--to", args.to])
            argv.extend(["--from", args.source_lang])
            if args.output_json:
                argv.append("--json")
            module.main(argv)
        elif cmd == "summarize":
            argv = []
            if args.text:
                argv.append(args.text)
            if args.stdin:
                argv.append("--stdin")
            argv.extend(["--style", args.style])
            if args.output_json:
                argv.append("--json")
            module.main(argv)
        elif cmd == "embed":
            argv = list(args.texts) if args.texts else []
            if args.stdin:
                argv.append("--stdin")
            if args.model:
                argv.extend(["--model", args.model])
            if args.output_json:
                argv.append("--json")
            module.main(argv)
        elif cmd == "convert":
            argv = []
            if args.file:
                argv.append(args.file)
            if args.stdin:
                argv.append("--stdin")
            if args.output:
                argv.extend(["--output", args.output])
            if args.output_json:
                argv.append("--json")
            module.main(argv)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)