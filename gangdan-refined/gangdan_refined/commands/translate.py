"""gd-translate - Translate text between languages.

Usage:
    gd-translate "Hello world" --to zh
    gd-translate "你好世界" --to en --from zh
    echo "Complex text here" | gd-translate --to ja --stdin
"""

from __future__ import annotations

import argparse
import sys


def main(args=None) -> None:
    parser = argparse.ArgumentParser(
        prog="gd-translate",
        description="Translate text between languages using LLM",
    )
    parser.add_argument("text", nargs="?", help="Text to translate (use --stdin for piped input)")
    parser.add_argument("--stdin", action="store_true", help="Read text from stdin")
    parser.add_argument("--to", "-t", default="en", help="Target language code (zh, en, ja, ko, fr, de, etc.)")
    parser.add_argument("--from", "-f", dest="source_lang", default="auto", help="Source language code (default: auto-detect)")
    parser.add_argument("--model", "-m", default="", help="Model to use")
    parser.add_argument("--provider", "-p", default="", help="LLM provider")
    parser.add_argument("--api-key", default="", help="API key for cloud providers")
    from .common import add_common_args, init_env, output, output_error, get_llm_client
    add_common_args(parser)
    parsed = parser.parse_args(args)
    init_env(parsed)

    if parsed.stdin:
        text = sys.stdin.read().strip()
    elif parsed.text:
        text = parsed.text
    else:
        output_error("Text required. Use positional arg or --stdin", parsed)

    from ..core.config import CONFIG

    if parsed.provider == "ollama" or (not parsed.provider and not parsed.api_key):
        from ..llm.ollama import OllamaClient
        client = OllamaClient(CONFIG.llm.ollama_url)
    else:
        client = get_llm_client(provider=parsed.provider)

    result = client.translate(
        text=text,
        target_language=parsed.to,
        source_language=parsed.source_lang,
    )

    output({
        "success": bool(result),
        "original": text,
        "translation": result,
        "from": parsed.source_lang,
        "to": parsed.to,
    }, parsed, text=result)