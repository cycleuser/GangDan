"""Docs agent — download and index documentation sources."""

from __future__ import annotations

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class DocsAgent(BaseAgent):
    name = "gd-docs"
    description = "Download and index documentation sources"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        action = input.options.get("action", "list")

        try:
            if action == "list":
                return self._list()
            elif action == "download":
                return self._download(input)
            elif action == "index":
                return self._index(input)
            else:
                return self._list()
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def _list(self) -> AgentOutput:
        from ..storage.doc_manager import DOC_SOURCES
        return AgentOutput(
            success=True,
            data={"sources": DOC_SOURCES, "count": len(DOC_SOURCES)},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def _download(self, input: AgentInput) -> AgentOutput:
        source = input.options.get("source", input.query or "")
        if not source:
            return AgentOutput(success=False, error="Source name required", metadata=AgentMetadata(agent=self.name, version=self.version))
        from ..storage.doc_manager import DocManager
        from ..storage.chroma_manager import ChromaManager
        from ..core.config import CHROMA_DIR
        ollama = self._get_ollama_client()
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        doc_mgr = DocManager(self.config.docs_dir, chroma, ollama)
        count, errors = doc_mgr.download_source(source)
        return AgentOutput(
            success=True,
            data={"source": source, "count": count, "errors": errors},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def _index(self, input: AgentInput) -> AgentOutput:
        source = input.options.get("source", input.query or "")
        if not source:
            return AgentOutput(success=False, error="Source name required", metadata=AgentMetadata(agent=self.name, version=self.version))
        from ..storage.doc_manager import DocManager
        from ..storage.chroma_manager import ChromaManager
        from ..core.config import CHROMA_DIR
        ollama = self._get_ollama_client()
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        doc_mgr = DocManager(self.config.docs_dir, chroma, ollama)
        files, chunks, images = doc_mgr.index_source(source)
        return AgentOutput(
            success=True,
            data={"source": source, "files": files, "chunks": chunks, "images": images},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        subparsers = parser.add_subparsers(dest="action", help="Docs action")
        list_cmd = subparsers.add_parser("list", help="List documentation sources")
        list_cmd.add_argument("--json", action="store_true")
        dl_cmd = subparsers.add_parser("download", help="Download a documentation source")
        dl_cmd.add_argument("source", help="Source name")
        dl_cmd.add_argument("--json", action="store_true")
        idx_cmd = subparsers.add_parser("index", help="Index a documentation source")
        idx_cmd.add_argument("source", help="Source name")
        idx_cmd.add_argument("--json", action="store_true")

    def build_input(self, args) -> AgentInput:
        action = getattr(args, "action", "list") or "list"
        opts = {"action": action}
        if action in ("download", "index"):
            opts["source"] = args.source
        return AgentInput(query=getattr(args, "source", ""), options=opts, metadata=AgentMetadata(agent=self.name, version=self.version))