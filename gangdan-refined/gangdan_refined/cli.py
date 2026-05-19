"""GangDan Refined - CLI entry point.

Routes CLI subcommands to the appropriate handler:
- Default/repl: Start interactive REPL
- cli: Start CLI REPL
- web: Start web server
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

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("cli", help="Start CLI REPL")
    subparsers.add_parser("web", help="Start web server")

    args = parser.parse_args()

    if args.command == "web" or (args.command is None and args.port is not None):
        _start_web(args.host, args.port)
    elif args.command == "cli" or args.command is None:
        _start_cli()
    else:
        parser.print_help()


def _start_cli() -> None:
    """Start CLI REPL."""
    from .cli_app.repl import start_repl
    start_repl()


def _start_web(host: str | None = None, port: int | None = None) -> None:
    """Start the Flask web server."""
    from .core.config import CONFIG, load_config
    from .core.constants import DEFAULT_WEB_HOST, DEFAULT_WEB_PORT
    from .core.port_utils import get_available_port

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
        print("[GangDan] Install with: pip install gangdan-refined[web]", file=sys.stderr)
        sys.exit(1)