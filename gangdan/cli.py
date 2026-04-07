"""Command-line interface for GangDan.

Entry point routing:
- CLI commands (cli, chat, kb, docs, etc.) -> cli_app.py
- No arguments or web flags -> app.py (Flask server)
"""

import argparse
import os
import sys

# CLI commands that route to cli_app
CLI_COMMANDS = {"cli", "chat", "kb", "docs", "config", "conversation", "run", "ai"}


def main() -> None:
    """Main entry point for gangdan CLI."""
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
        "-V",
        "--version",
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
        "-v",
        "--verbose",
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
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress non-essential output",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Custom data directory (default: ~/.gangdan for installed, ./data for dev)",
    )
    parser.add_argument(
        "--force-port",
        action="store_true",
        help="Force use of the specified port by killing any process using it",
    )
    parser.add_argument(
        "--auto-port",
        action="store_true",
        help="Automatically find an available port if the specified one is in use",
    )

    args = parser.parse_args()

    # Set data dir env var BEFORE importing app (app initializes at module level)
    if args.data_dir:
        os.environ["GANGDAN_DATA_DIR"] = args.data_dir

    port = args.port

    # Handle port conflict
    from gangdan.core.port_utils import (
        is_port_in_use,
        resolve_port_conflict,
        get_available_port,
    )

    if is_port_in_use(port, args.host):
        if args.force_port:
            # Force kill process using the port
            success, _ = resolve_port_conflict(port, args.host, force=True)
            if not success:
                print(f"[Port] Could not free port {port}. Exiting.", file=sys.stderr)
                sys.exit(1)
        elif args.auto_port:
            # Find next available port
            port = get_available_port(port + 1, args.host)
            print(f"[Port] Using available port: {port}")
        else:
            # Interactive mode - ask user
            success, new_port = resolve_port_conflict(port, args.host, force=False)
            if not success:
                sys.exit(1)
            if new_port:
                port = new_port

    # Import app after env var is set
    from gangdan.app import app

    if not args.quiet:
        url = f"http://{args.host}:{port}"
        banner = (
            f"\n"
            f"\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557\n"
            f"\u2551  GangDan - Offline Dev Assistant                          \u2551\n"
            f"\u2551                                                           \u2551\n"
            f"\u2551  Open in browser: {url:<40} \u2551\n"
            f"\u2551                                                           \u2551\n"
            f"\u2551  CLI mode: gangdan cli                                    \u2551\n"
            f"\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d\n"
        )
        print(banner)

    app.run(host=args.host, port=port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
