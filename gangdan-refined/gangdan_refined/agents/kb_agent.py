"""Knowledge base agent — manage, search, and index knowledge bases."""

from __future__ import annotations

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class KBAgent(BaseAgent):
    name = "gd-kb"
    description = "Manage, search, and index knowledge bases"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        action = input.options.get("action", "list")

        try:
            if action == "list":
                return self._list()
            elif action == "create":
                return self._create(input)
            elif action == "delete":
                return self._delete(input)
            elif action == "search":
                return self._search(input)
            elif action == "index":
                return self._index(input)
            elif action == "info":
                return self._info(input)
            else:
                return self._list()
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def _list(self) -> AgentOutput:
        from ..storage.kb_manager import CustomKBManager
        mgr = CustomKBManager()
        kbs = mgr.list_kbs()
        return AgentOutput(
            success=True,
            data={"kbs": [kb.to_dict() for kb in kbs], "count": len(kbs)},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def _create(self, input: AgentInput) -> AgentOutput:
        from ..storage.kb_manager import CustomKBManager
        from ..core.errors import GangDanError
        name = input.options.get("name", input.query or "")
        description = input.options.get("description", "")
        tags = input.options.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        if not name:
            return AgentOutput(success=False, error="KB name required", metadata=AgentMetadata(agent=self.name, version=self.version))
        mgr = CustomKBManager()
        try:
            kb = mgr.create_kb(display_name=name, description=description, tags=tags)
            return AgentOutput(success=True, data={"kb": kb.to_dict()}, metadata=AgentMetadata(agent=self.name, version=self.version))
        except GangDanError as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def _delete(self, input: AgentInput) -> AgentOutput:
        from ..storage.kb_manager import CustomKBManager
        name = input.options.get("name", input.query or "")
        delete_files = input.options.get("delete_files", False)
        if not name:
            return AgentOutput(success=False, error="KB name required", metadata=AgentMetadata(agent=self.name, version=self.version))
        mgr = CustomKBManager()
        success = mgr.delete_kb(name, delete_files=delete_files)
        return AgentOutput(success=success, data={"name": name, "deleted": success}, metadata=AgentMetadata(agent=self.name, version=self.version))

    def _search(self, input: AgentInput) -> AgentOutput:
        from ..storage.kb_manager import CustomKBManager
        query = input.query or input.text or ""
        kb_name = input.options.get("kb_name", "")
        limit = input.options.get("limit", 10)
        if not query:
            return AgentOutput(success=False, error="Search query required", metadata=AgentMetadata(agent=self.name, version=self.version))
        mgr = CustomKBManager()
        if kb_name:
            results = mgr.search_kb(kb_name, query, limit=limit)
            return AgentOutput(success=True, data={"results": results, "query": query, "kb": kb_name}, metadata=AgentMetadata(agent=self.name, version=self.version))
        results = mgr.search_all_kbs(query, limit=limit)
        return AgentOutput(success=True, data={"results": results, "query": query}, metadata=AgentMetadata(agent=self.name, version=self.version))

    def _index(self, input: AgentInput) -> AgentOutput:
        from ..storage.doc_manager import DocManager
        from ..storage.chroma_manager import ChromaManager
        source = input.options.get("source", input.query or "")
        kb_name = input.options.get("kb_name", "")
        process_images = input.options.get("process_images", True)
        from ..core.config import CHROMA_DIR
        ollama = self._get_ollama_client()
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        doc_mgr = DocManager(self.config.docs_dir, chroma, ollama)
        files, chunks, images = doc_mgr.index_source(source, process_images=process_images)
        return AgentOutput(success=True, data={"files": files, "chunks": chunks, "images": images, "source": source}, metadata=AgentMetadata(agent=self.name, version=self.version))

    def _info(self, input: AgentInput) -> AgentOutput:
        from ..storage.kb_manager import CustomKBManager
        name = input.options.get("name", input.query or "")
        if not name:
            return AgentOutput(success=False, error="KB name required", metadata=AgentMetadata(agent=self.name, version=self.version))
        mgr = CustomKBManager()
        kb = mgr.get_kb(name)
        if kb is None:
            return AgentOutput(success=False, error=f"KB '{name}' not found", metadata=AgentMetadata(agent=self.name, version=self.version))
        return AgentOutput(success=True, data={"kb": kb.to_dict()}, metadata=AgentMetadata(agent=self.name, version=self.version))

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        subparsers = parser.add_subparsers(dest="action", help="KB action")
        list_cmd = subparsers.add_parser("list", help="List knowledge bases")
        list_cmd.add_argument("--json", action="store_true")
        create_cmd = subparsers.add_parser("create", help="Create a KB")
        create_cmd.add_argument("name", help="KB name")
        create_cmd.add_argument("--description", "-d", default="", help="Description")
        create_cmd.add_argument("--tags", default="", help="Comma-separated tags")
        create_cmd.add_argument("--json", action="store_true")
        delete_cmd = subparsers.add_parser("delete", help="Delete a KB")
        delete_cmd.add_argument("name", help="KB name")
        delete_cmd.add_argument("--delete-files", action="store_true", help="Also delete source files")
        delete_cmd.add_argument("--json", action="store_true")
        search_cmd = subparsers.add_parser("search", help="Search a KB")
        search_cmd.add_argument("query", help="Search query")
        search_cmd.add_argument("--kb", "-k", default="", help="KB name (omit for all)")
        search_cmd.add_argument("--limit", type=int, default=10, help="Max results")
        search_cmd.add_argument("--json", action="store_true")
        index_cmd = subparsers.add_parser("index", help="Index a document source")
        index_cmd.add_argument("source", help="Source name")
        index_cmd.add_argument("--json", action="store_true")
        info_cmd = subparsers.add_parser("info", help="Get KB details")
        info_cmd.add_argument("name", help="KB name")
        info_cmd.add_argument("--json", action="store_true")

    def build_input(self, args) -> AgentInput:
        action = getattr(args, "action", "list") or "list"
        opts = {"action": action}
        if action == "create":
            opts["name"] = args.name
            opts["description"] = args.description
            opts["tags"] = args.tags.split(",") if args.tags else []
        elif action == "delete":
            opts["name"] = args.name
            opts["delete_files"] = args.delete_files
        elif action == "search":
            opts["kb_name"] = args.kb
            opts["limit"] = args.limit
        elif action == "index":
            opts["source"] = args.source
        elif action == "info":
            opts["name"] = args.name
        return AgentInput(query=getattr(args, "query", "") or getattr(args, "name", ""), options=opts, metadata=AgentMetadata(agent=self.name, version=self.version))