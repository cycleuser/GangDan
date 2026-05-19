"""gd-search - Search the web or academic papers.

Usage:
    gd-search "quantum computing" --json
    gd-search "transformer architecture" --source arxiv --max 5
    gd-search "latest AI news" --source web
    gd-search "machine learning" --source semantic_scholar --api-key KEY
"""

from __future__ import annotations

import argparse
import sys


def main(args=None) -> None:
    parser = argparse.ArgumentParser(
        prog="gd-search",
        description="Search the web or academic papers",
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument("--source", "-s", default="web",
                        choices=["web", "arxiv", "semantic_scholar", "crossref", "pubmed", "github", "openalex", "dblp"],
                        help="Search source (default: web)")
    parser.add_argument("--max", "-n", type=int, default=10, help="Maximum results")
    parser.add_argument("--api-key", default="", help="API key (for Semantic Scholar, Serper, Brave)")
    parser.add_argument("--web-engine", default="duckduckgo", choices=["duckduckgo", "serper", "brave"],
                        help="Web search engine")
    from .common import add_common_args, init_env, output, output_error
    add_common_args(parser)
    parsed = parser.parse_args(args)
    init_env(parsed)

    from ..core.config import CONFIG
    query = parsed.query
    max_results = parsed.max

    if parsed.source == "web":
        from ..search.web_searcher import WebSearcher
        engine = WebSearcher(
            engine=parsed.web_engine,
            serper_api_key=CONFIG.search.serper_api_key or parsed.api_key,
            brave_api_key=CONFIG.search.brave_api_key,
        )
        results = engine.search(query, num_results=max_results)
        output({"success": True, "query": query, "source": "web", "results": results}, parsed)

    else:
        from ..search.research_searcher import ResearchSearcher
        from ..core.config import CONFIG as cfg

        searcher = ResearchSearcher(
            sources=[parsed.source],
            max_results=max_results,
            timeout=cfg.search.research_search_timeout,
            semantic_scholar_api_key=cfg.search.semantic_scholar_api_key or parsed.api_key,
            crossref_email=cfg.search.crossref_email,
            pubmed_api_key=cfg.search.pubmed_api_key,
            github_token=cfg.search.github_token,
            openalex_email=cfg.search.openalex_email,
        )
        results = searcher.search(query, max_results=max_results)

        papers = []
        for r in results:
            papers.append({
                "title": r.paper.title if hasattr(r, "paper") else str(r),
                "authors": r.paper.authors if hasattr(r, "paper") and hasattr(r.paper, "authors") else [],
                "year": r.paper.year if hasattr(r, "paper") and hasattr(r.paper, "year") else None,
                "url": r.paper.url if hasattr(r, "paper") and hasattr(r.paper, "url") else None,
                "doi": r.paper.doi if hasattr(r, "paper") and hasattr(r.paper, "doi") else None,
                "abstract": r.paper.abstract_text if hasattr(r, "paper") and hasattr(r.paper, "abstract_text") else None,
                "source": r.source if hasattr(r, "source") else parsed.source,
            })

        output({"success": True, "query": query, "source": parsed.source, "results": papers}, parsed)