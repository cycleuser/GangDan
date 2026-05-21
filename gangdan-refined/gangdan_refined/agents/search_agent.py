"""Search agent — search the web and academic sources."""

from __future__ import annotations

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class SearchAgent(BaseAgent):
    name = "gd-search"
    description = "Search the web and academic sources"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        query = input.query or input.text or ""
        source = input.options.get("source", "web")
        max_results = input.options.get("max_results", 10)
        engine = input.options.get("engine", "")

        if not query:
            return AgentOutput(success=False, error="Query required", metadata=AgentMetadata(agent=self.name, version=self.version))

        try:
            if source in ("academic", "arxiv", "semantic_scholar", "crossref", "pubmed", "github", "openalex", "dblp"):
                return self._academic_search(query, source, max_results)
            return self._web_search(query, max_results, engine)
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def _web_search(self, query: str, max_results: int, engine: str = "") -> AgentOutput:
        from ..search.web_searcher import WebSearcher
        searcher = WebSearcher(engine=engine or self.config.search.web_search_engine)
        results = searcher.search(query, max_results=max_results)
        formatted = []
        for r in results:
            if hasattr(r, "to_dict"):
                formatted.append(r.to_dict())
            elif isinstance(r, dict):
                formatted.append(r)
            else:
                formatted.append({"title": str(r)})
        return AgentOutput(
            success=True,
            data={"query": query, "results": formatted, "count": len(formatted), "source": "web"},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def _academic_search(self, query: str, source: str, max_results: int) -> AgentOutput:
        from ..search.research_searcher import ResearchSearcher
        config = self.config
        searcher = ResearchSearcher(
            sources=[source],
            max_results=max_results,
            timeout=config.search.research_search_timeout,
            semantic_scholar_api_key=config.search.semantic_scholar_api_key,
            crossref_email=config.search.crossref_email,
            pubmed_api_key=config.search.pubmed_api_key,
            github_token=config.search.github_token,
            openalex_email=config.search.openalex_email,
        )
        results = searcher.search(query, max_results=max_results)
        formatted = [r.to_dict() if hasattr(r, "to_dict") else str(r) for r in results]
        return AgentOutput(
            success=True,
            data={"query": query, "results": formatted, "count": len(formatted), "source": source},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        parser.add_argument("query", nargs="?", default="", help="Search query")
        parser.add_argument("--stdin", action="store_true", help="Read query from stdin")
        parser.add_argument("--source", "-s", default="web", choices=["web", "academic", "arxiv", "semantic_scholar", "crossref", "pubmed", "github", "openalex", "dblp"], help="Search source")
        parser.add_argument("--max-results", type=int, default=10, help="Max results")

    def build_input(self, args) -> AgentInput:
        return AgentInput(
            query=args.query,
            options={"source": args.source, "max_results": args.max_results},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )