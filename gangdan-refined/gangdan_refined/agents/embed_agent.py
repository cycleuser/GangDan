"""Embed agent — generate text embeddings."""

from __future__ import annotations

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class EmbedAgent(BaseAgent):
    name = "gd-embed"
    description = "Generate text embeddings using LLM models"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        text = input.text or input.query or ""
        model = input.options.get("model", "")

        if not text:
            return AgentOutput(success=False, error="Text required", metadata=AgentMetadata(agent=self.name, version=self.version))

        try:
            from ..llm.ollama import OllamaClient
            client = OllamaClient(self.config.llm.ollama_url)
            model_name = model or self.config.llm.embedding_model
            embedding = client.embed(text, model=model_name)
            dim = len(embedding) if embedding else 0
            return AgentOutput(
                success=True,
                data={"embedding": embedding[:10] if len(embedding) > 10 else embedding, "dimension": dim, "model": model_name, "text_preview": text[:200]},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        parser.add_argument("text", nargs="?", default="", help="Text to embed")
        parser.add_argument("--stdin", action="store_true", help="Read text from stdin")
        parser.add_argument("--full", action="store_true", help="Output full embedding (default: truncated)")

    def build_input(self, args) -> AgentInput:
        return AgentInput(
            text=args.text,
            options={"model": args.model, "full": args.full},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def output(self, result: AgentOutput, args) -> None:
        import json
        if getattr(args, "json", False) or getattr(args, "full", False):
            if result.success and "embedding" in result.data and not getattr(args, "full", False):
                result.data["embedding_preview"] = result.data["embedding"]
                result.data.pop("embedding", None)
                result.data["full_embedding_available"] = True
            print(result.to_json(indent=2))
        else:
            if result.success:
                dim = result.data.get("dimension", 0)
                model = result.data.get("model", "")
                print(f"Embedding: {dim} dimensions, model={model}")
            else:
                print(f"Error: {result.error}", file=__import__("sys").stderr)