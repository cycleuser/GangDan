"""Search engines for GangDan Refined.

Provides:
- Web search (DuckDuckGo, Serper, Brave)
- Academic paper search (arXiv, Semantic Scholar, CrossRef, etc.)
- Query expansion via LLM
- Adaptive embedding search
- Semantic Scholar cache
"""

from .web_searcher import WebSearcher, DuckDuckGoSearcher, SerperSearcher, BraveSearcher
from .research_searcher import ResearchSearcher, ArxivFetcher, SemanticScholarFetcher
from .query_expander import QueryExpander, ExpandedQuery
from .adaptive_search import AdaptiveResult, adaptive_embed, adaptive_search_collections

__all__ = [
    "WebSearcher",
    "DuckDuckGoSearcher",
    "SerperSearcher",
    "BraveSearcher",
    "ResearchSearcher",
    "ArxivFetcher",
    "SemanticScholarFetcher",
    "QueryExpander",
    "ExpandedQuery",
    "AdaptiveResult",
    "adaptive_embed",
    "adaptive_search_collections",
]