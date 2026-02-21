"""Command-line interface for GangDan."""

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="gangdan",
        description="GangDan - Offline Development Assistant powered by Ollama and ChromaDB",
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
        "--data-dir",
        default=None,
        help="Custom data directory (default: ~/.gangdan for installed, ./data for dev)",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit",
    )

    args = parser.parse_args()

    if args.version:
        from gangdan import __version__
        print(f"gangdan {__version__}")
        sys.exit(0)

    # Set data dir env var BEFORE importing app (app initializes at module level)
    if args.data_dir:
        os.environ["GANGDAN_DATA_DIR"] = args.data_dir

    # Import app after env var is set
    from gangdan.app import app

    url = f"http://{args.host}:{args.port}"
    print(f"\n"
          f"\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557\n"
          f"\u2551  GangDan - Offline Dev Assistant                          \u2551\n"
          f"\u2551                                                           \u2551\n"
          f"\u2551  Open in browser: {url:<40} \u2551\n"
          f"\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d\n")

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
