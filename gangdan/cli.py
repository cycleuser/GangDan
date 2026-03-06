"""Command-line interface for GangDan."""

import argparse
import os
import sys


# CLI commands that should route to cli_app
CLI_COMMANDS = {"cli", "chat", "kb", "docs", "config", "conversation", "run", "ai"}


def main():
    from gangdan import __version__

    # Check if first arg is a CLI command (route to cli_app)
    if len(sys.argv) > 1 and sys.argv[1] in CLI_COMMANDS:
        from gangdan.cli_app import cli_main
        sys.exit(cli_main(sys.argv[1:]))
    
    # Otherwise, handle web server mode
    parser = argparse.ArgumentParser(
        prog="gangdan",
        description="GangDan - Offline Development Assistant powered by Ollama and ChromaDB",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"gangdan {__version__}",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to listen on (default: 5000)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable Flask debug mode",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-essential output",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Custom data directory (default: ~/.gangdan for installed, ./data for dev)",
    )

    args = parser.parse_args()

    # Set data dir env var BEFORE importing app (app initializes at module level)
    if args.data_dir:
        os.environ["GANGDAN_DATA_DIR"] = args.data_dir

    # Import app after env var is set
    from gangdan.app import app

    if not args.quiet:
        url = f"http://{args.host}:{args.port}"
        print(f"\n"
              f"\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557\n"
              f"\u2551  GangDan - Offline Dev Assistant                          \u2551\n"
              f"\u2551                                                           \u2551\n"
              f"\u2551  Open in browser: {url:<40} \u2551\n"
              f"\u2551                                                           \u2551\n"
              f"\u2551  CLI mode: gangdan cli                                    \u2551\n"
              f"\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d\n")

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
