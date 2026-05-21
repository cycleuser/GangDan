"""gd-embed - Generate text embeddings.

Usage:
    gd-embed "Hello world"
    gd-embed "text1" "text2" "text3" --json
    echo "text to embed" | gd-embed --stdin
"""

from __future__ import annotations

import argparse
import sys


def main(args=None) -> None:
    parser = argparse.ArgumentParser(
        prog="gd-embed",
        description="Generate text embeddings using an embedding model",
    )
    parser.add_argument("texts", nargs="*", help="Text(s) to embed")
    parser.add_argument("--stdin", action="store_true", help="Read text from stdin")
    parser.add_argument("--model", "-m", default="", help="Embedding model name")
    parser.add_argument("--truncate", type=int, default=500, help="Max text length (truncated)")
    from .common import add_common_args, init_env, output, output_error
    add_common_args(parser)
    parsed = parser.parse_args(args)
    init_env(parsed)

    from ..core.config import CONFIG
    from ..llm.ollama import OllamaClient

    texts = []
    if parsed.stdin:
        texts = [line.strip() for line in sys.stdin if line.strip()]
    elif parsed.texts:
        texts = list(parsed.texts)
    else:
        output_error("Provide text to embed. Use positional args or --stdin", parsed)

    client = OllamaClient(CONFIG.llm.ollama_url)
    model = parsed.model or CONFIG.llm.embedding_model

    results = []
    for i, text in enumerate(texts):
        truncated = text[:parsed.truncate]
        embedding = client.embed(truncated, model=model)
        dim = len(embedding)
        results.append({
            "index": i,
            "text_preview": text[:80] + ("..." if len(text) > 80 else ""),
            "dimension": dim,
            "embedding_preview": embedding[:5] if dim >= 5 else embedding,
        })

    output({
        "success": True,
        "model": model,
        "count": len(results),
        "results": results,
    }, parsed)