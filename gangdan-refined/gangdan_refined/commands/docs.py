"""gd-docs - Download and index documentation sources.

Usage:
    gd-docs list                          # List available doc sources
    gd-docs download numpy                # Download numpy docs
    gd-docs index numpy                   # Index numpy docs
"""

from __future__ import annotations

import argparse
import sys


def main(args=None) -> None:
    parser = argparse.ArgumentParser(
        prog="gd-docs",
        description="Download and index documentation sources",
    )
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    list_p = subparsers.add_parser("list", help="List available documentation sources")

    dl_p = subparsers.add_parser("download", help="Download a documentation source")
    dl_p.add_argument("source", help="Source name (e.g. numpy, pytorch)")

    idx_p = subparsers.add_parser("index", help="Index a downloaded source")
    idx_p.add_argument("source", help="Source name")
    idx_p.add_argument("--no-images", action="store_true", help="Skip image processing")

    from .common import add_common_args, init_env, output, output_error
    add_common_args(parser)
    parsed = parser.parse_args(args)
    init_env(parsed)

    if not parsed.action:
        parser.print_help()
        sys.exit(1)

    from ..core.config import CONFIG, DOCS_DIR
    from ..storage.doc_manager import DOC_SOURCES, DocManager
    from ..storage.chroma_manager import ChromaManager
    from ..llm.ollama import OllamaClient

    if parsed.action == "list":
        output({"success": True, "sources": DOC_SOURCES, "count": len(DOC_SOURCES)}, parsed)

    elif parsed.action == "download":
        if parsed.source not in DOC_SOURCES:
            output_error(f"Unknown source: {parsed.source}. Available: {list(DOC_SOURCES.keys())}", parsed)
        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager()
        doc_mgr = DocManager(DOCS_DIR, chroma, ollama)
        count, errors = doc_mgr.download_source(parsed.source)
        output({"success": True, "source": parsed.source, "count": count, "errors": errors}, parsed)

    elif parsed.action == "index":
        if parsed.source not in DOC_SOURCES:
            output_error(f"Unknown source: {parsed.source}. Available: {list(DOC_SOURCES.keys())}", parsed)
        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager()
        doc_mgr = DocManager(DOCS_DIR, chroma, ollama)
        process_images = not parsed.no_images
        files, chunks, images = doc_mgr.index_source(parsed.source, process_images=process_images)
        output({
            "success": True, "source": parsed.source,
            "files": files, "chunks": chunks, "images": images,
        }, parsed)