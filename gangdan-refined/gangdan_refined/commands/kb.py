"""gd-kb - Manage knowledge bases (CRUD, search, index).

Usage:
    gd-kb list                       # List all knowledge bases
    gd-kb create "My KB"            # Create a new KB
    gd-kb search "my_kb" "query"    # Search within a KB
    gd-kb delete "my_kb"            # Delete a KB
    gd-kb index /path/to/docs        # Index documents into a KB
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(args=None) -> None:
    parser = argparse.ArgumentParser(
        prog="gd-kb",
        description="Manage knowledge bases (CRUD, search, index)",
    )
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # list
    list_p = subparsers.add_parser("list", help="List all knowledge bases")

    # create
    create_p = subparsers.add_parser("create", help="Create a new knowledge base")
    create_p.add_argument("name", help="Display name for the KB")
    create_p.add_argument("--description", "-d", default="", help="Description")
    create_p.add_argument("--tags", nargs="+", default=[], help="Tags")

    # search
    search_p = subparsers.add_parser("search", help="Search within a KB")
    search_p.add_argument("kb_name", help="Internal KB name")
    search_p.add_argument("query", help="Search query")
    search_p.add_argument("--limit", "-n", type=int, default=20, help="Max results")

    # delete
    delete_p = subparsers.add_parser("delete", help="Delete a KB")
    delete_p.add_argument("kb_name", help="Internal KB name")
    delete_p.add_argument("--files", action="store_true", help="Also delete files")

    # index
    index_p = subparsers.add_parser("index", help="Index documents into a KB")
    index_p.add_argument("path", help="Path to documents directory")
    index_p.add_argument("--collection", "-c", default="default", help="Collection name")

    # reindex
    reindex_p = subparsers.add_parser("reindex", help="Re-index a KB with new model")
    reindex_p.add_argument("kb_name", help="Internal KB name")
    reindex_p.add_argument("--model", "-m", default="", help="New embedding model")

    from .common import add_common_args, init_env, output, output_error
    add_common_args(parser)
    parsed = parser.parse_args(args)
    init_env(parsed)

    if not parsed.action:
        parser.print_help()
        sys.exit(1)

    from ..storage.kb_manager import CustomKBManager
    from ..core.config import CONFIG

    if parsed.action == "list":
        mgr = CustomKBManager()
        kbs = mgr.list_kbs()
        result = [kb.to_dict() for kb in kbs]
        output({"success": True, "kbs": result, "count": len(result)}, parsed)

    elif parsed.action == "create":
        mgr = CustomKBManager()
        kb = mgr.create_kb(display_name=parsed.name, description=parsed.description, tags=parsed.tags)
        output({"success": True, "kb": kb.to_dict()}, parsed)

    elif parsed.action == "search":
        mgr = CustomKBManager()
        results = mgr.search_kb(parsed.kb_name, parsed.query, limit=parsed.limit)
        output({"success": True, "kb": parsed.kb_name, "query": parsed.query, "results": results, "count": len(results)}, parsed)

    elif parsed.action == "delete":
        mgr = CustomKBManager()
        success = mgr.delete_kb(parsed.kb_name, delete_files=parsed.files)
        output({"success": success, "kb": parsed.kb_name}, parsed)

    elif parsed.action == "index":
        directory = Path(parsed.path)
        if not directory.is_dir():
            output_error(f"Not a directory: {directory}", parsed)
        from ..api import index_documents
        result = index_documents(str(directory), collection=parsed.collection)
        output(result.to_dict(), parsed, text=f"Indexed {result.data.get('indexed', 0)} documents")

    elif parsed.action == "reindex":
        mgr = CustomKBManager()
        result = mgr.reindex_kb(parsed.kb_name, new_model=parsed.model or None)
        output({"success": True, "result": result}, parsed)