"""Research agent — run multi-phase research reports."""

from __future__ import annotations

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class ResearchAgent(BaseAgent):
    name = "gd-research"
    description = "Run multi-phase research on a topic"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        topic = input.query or input.text or ""
        depth = input.options.get("depth", "medium")
        kb_names = input.options.get("kb_names", [])
        model = input.options.get("model", "")

        if not topic:
            return AgentOutput(success=False, error="Topic required", metadata=AgentMetadata(agent=self.name, version=self.version))

        if isinstance(kb_names, str):
            kb_names = [kb_names]

        try:
            from ..learning.research import run_research
            from ..llm.ollama import OllamaClient
            from ..storage.chroma_manager import ChromaManager
            from ..core.config import CHROMA_DIR

            ollama = OllamaClient(self.config.llm.ollama_url)
            chroma = ChromaManager(persist_dir=str(CHROMA_DIR))

            results = []
            for event in run_research(topic=topic, kb_names=kb_names, depth=depth, ollama=ollama, chroma=chroma, config=self.config):
                if isinstance(event, dict):
                    results.append(event)

            report_text = ""
            for r in results:
                if isinstance(r, dict) and r.get("type") == "section":
                    report_text += r.get("content", "") + "\n\n"
                elif isinstance(r, dict) and r.get("type") == "summary":
                    report_text += r.get("content", "") + "\n\n"

            if not report_text:
                report_text = str(results[-1]) if results else "Research completed"

            return AgentOutput(
                success=True,
                data={"topic": topic, "depth": depth, "report": report_text, "events_count": len(results)},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        parser.add_argument("topic", nargs="?", default="", help="Research topic")
        parser.add_argument("--depth", "-d", default="medium", choices=["shallow", "medium", "deep"], help="Research depth")
        parser.add_argument("--kb", "-k", nargs="+", default=[], help="Knowledge base name(s)")
        parser.add_argument("--model", "-m", default="", help="Model to use")

    def build_input(self, args) -> AgentInput:
        return AgentInput(
            query=args.topic,
            options={"depth": args.depth, "kb_names": args.kb, "model": args.model, "provider": args.provider},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )