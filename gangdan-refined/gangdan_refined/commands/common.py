"""Shared utilities for CLI commands.

Provides common argument parsing, output formatting, and error handling
for all gd-* commands.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional

from ..core.config import CONFIG, load_config, save_config, DATA_DIR


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments common to all commands."""
    parser.add_argument(
        "--json", action="store_true", dest="output_json",
        help="Output results as JSON (for AI/pipe consumption)",
    )
    parser.add_argument(
        "--data-dir", type=str, default=None,
        help="Custom data directory path",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress non-essential output",
    )


def init_env(args: argparse.Namespace) -> None:
    """Initialize environment from common args (load config, set data dir)."""
    import os
    if args.data_dir:
        os.environ["GANGLAN_REFINED_DATA_DIR"] = args.data_dir
    load_config()


def output(data: Any, args: argparse.Namespace, *, text: str = "") -> None:
    """Format output based on --json flag.

    If --json is set, print data as JSON to stdout.
    Otherwise, print the human-readable text (or a default representation).
    """
    if getattr(args, "output_json", False):
        if isinstance(data, dict) and "success" not in data:
            data["success"] = True
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        if text:
            print(text)
        elif isinstance(data, dict):
            for k, v in data.items():
                if k == "success":
                    continue
                if isinstance(v, (list, dict)):
                    print(f"{k}: {json.dumps(v, ensure_ascii=False, indent=2, default=str)}")
                else:
                    print(f"{k}: {v}")
        else:
            print(data)


def output_error(error: str, args: argparse.Namespace, *, code: int = 1) -> None:
    """Output an error message. If --json, output as JSON error. Otherwise print to stderr."""
    if getattr(args, "output_json", False):
        json.dump({"success": False, "error": error}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"Error: {error}", file=sys.stderr)
    sys.exit(code)


def get_llm_client(provider: str = "", model: str = "", api_key: str = "", base_url: str = ""):
    """Get an LLM client based on arguments."""
    if provider:
        from ..llm.factory import create_client
        return create_client(provider, api_key=api_key, base_url=base_url)
    from ..llm.factory import create_chat_client
    return create_chat_client()


def get_ollama_client():
    """Get an Ollama client for embedding/local operations."""
    from ..llm.ollama import OllamaClient
    return OllamaClient(CONFIG.llm.ollama_url)