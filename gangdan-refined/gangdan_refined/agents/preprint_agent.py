"""Preprint agent — search, convert, and schedule preprint papers."""

from __future__ import annotations

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class PreprintAgent(BaseAgent):
    name = "gd-preprint"
    description = "Search, convert, and manage preprint papers"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        action = input.options.get("action", "search")

        try:
            if action == "search":
                return self._search(input)
            elif action == "convert":
                return self._convert(input)
            elif action == "categories":
                return self._categories()
            elif action == "schedule":
                return self._schedule(input)
            else:
                return self._search(input)
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def _search(self, input: AgentInput) -> AgentOutput:
        query = input.query or input.text or ""
        platform = input.options.get("platform", "arxiv")
        max_results = input.options.get("max_results", 20)
        if not query:
            return AgentOutput(success=False, error="Query required", metadata=AgentMetadata(agent=self.name, version=self.version))
        from ..document.preprint.fetcher import PreprintFetcher
        fetcher = PreprintFetcher()
        results = fetcher.search(query=query, platform=platform, max_results=max_results)
        formatted = [r.to_dict() if hasattr(r, "to_dict") else str(r) for r in results]
        return AgentOutput(
            success=True,
            data={"query": query, "results": formatted, "count": len(formatted), "platform": platform},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def _convert(self, input: AgentInput) -> AgentOutput:
        paper_id = input.options.get("paper_id", "")
        source_url = input.options.get("source_url", "")
        if not paper_id and not source_url:
            return AgentOutput(success=False, error="paper_id or source_url required", metadata=AgentMetadata(agent=self.name, version=self.version))
        from ..document.preprint.converter import PreprintConverter
        converter = PreprintConverter()
        result = converter.convert(paper_id=paper_id, source_url=source_url)
        return AgentOutput(
            success=True,
            data={"result": result if isinstance(result, dict) else str(result)},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def _categories(self) -> AgentOutput:
        try:
            from ..document.preprint.categories import PREPRINT_CATEGORIES
            return AgentOutput(success=True, data={"categories": PREPRINT_CATEGORIES}, metadata=AgentMetadata(agent=self.name, version=self.version))
        except ImportError:
            return AgentOutput(success=True, data={"categories": []}, metadata=AgentMetadata(agent=self.name, version=self.version))

    def _schedule(self, input: AgentInput) -> AgentOutput:
        schedule_action = input.options.get("schedule_action", "status")
        try:
            from ..document.preprint.scheduler import PreprintScheduler
            scheduler = PreprintScheduler()
            if schedule_action == "start":
                interval = input.options.get("interval", 3600)
                scheduler.start(interval=interval)
                return AgentOutput(success=True, data={"status": "started", "interval": interval}, metadata=AgentMetadata(agent=self.name, version=self.version))
            elif schedule_action == "stop":
                scheduler.stop()
                return AgentOutput(success=True, data={"status": "stopped"}, metadata=AgentMetadata(agent=self.name, version=self.version))
            elif schedule_action == "status":
                status = scheduler.get_status() if hasattr(scheduler, "get_status") else {"status": "ready"}
                return AgentOutput(success=True, data=status, metadata=AgentMetadata(agent=self.name, version=self.version))
            else:
                return AgentOutput(success=False, error=f"Unknown schedule action: {schedule_action}", metadata=AgentMetadata(agent=self.name, version=self.version))
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        subparsers = parser.add_subparsers(dest="action", help="Preprint action")
        search_cmd = subparsers.add_parser("search", help="Search preprints")
        search_cmd.add_argument("query", nargs="?", default="", help="Search query")
        search_cmd.add_argument("--platform", "-p", default="arxiv", choices=["arxiv", "biorxiv", "medrxiv"], help="Platform")
        search_cmd.add_argument("--max-results", type=int, default=20, help="Max results")
        search_cmd.add_argument("--json", action="store_true")
        convert_cmd = subparsers.add_parser("convert", help="Convert a preprint")
        convert_cmd.add_argument("--paper-id", default="", help="arXiv paper ID")
        convert_cmd.add_argument("--source-url", default="", help="Source URL")
        convert_cmd.add_argument("--json", action="store_true")
        cat_cmd = subparsers.add_parser("categories", help="List preprint categories")
        cat_cmd.add_argument("--json", action="store_true")
        sched_cmd = subparsers.add_parser("schedule", help="Manage scheduler")
        sched_cmd.add_argument("schedule_action", nargs="?", default="status", choices=["start", "stop", "status"])
        sched_cmd.add_argument("--interval", type=int, default=3600, help="Fetch interval in seconds")
        sched_cmd.add_argument("--json", action="store_true")

    def build_input(self, args) -> AgentInput:
        action = getattr(args, "action", "search") or "search"
        opts = {"action": action}
        if action == "search":
            opts.update({"platform": args.platform, "max_results": args.max_results})
        elif action == "convert":
            opts.update({"paper_id": getattr(args, "paper_id", ""), "source_url": getattr(args, "source_url", "")})
        elif action == "schedule":
            opts.update({"schedule_action": args.schedule_action, "interval": args.interval})
        return AgentInput(query=getattr(args, "query", ""), options=opts, metadata=AgentMetadata(agent=self.name, version=self.version))