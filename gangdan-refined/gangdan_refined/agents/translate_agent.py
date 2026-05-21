"""Translate agent — translate text between languages."""

from __future__ import annotations

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class TranslateAgent(BaseAgent):
    name = "gd-translate"
    description = "Translate text between languages"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        text = input.text or input.query or ""
        target = input.options.get("target_language", "en") or input.options.get("to", "en")
        source = input.options.get("source_language", "auto") or input.options.get("from", "auto")
        model = input.options.get("model", "")
        provider = input.options.get("provider", "")

        if not text:
            return AgentOutput(success=False, error="Text required", metadata=AgentMetadata(agent=self.name, version=self.version))

        try:
            client, model_name = self._get_llm_client(provider=provider, model=model)
            result = client.translate(text, target_language=target, source_language=source)
            return AgentOutput(
                success=True,
                data={"translation": result, "source_language": source, "target_language": target, "model": model_name, "original": text},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        parser.add_argument("text", nargs="?", default="", help="Text to translate")
        parser.add_argument("--stdin", action="store_true", help="Read text from stdin")
        parser.add_argument("--to", "-t", default="en", help="Target language code (zh, en, ja, etc.)")
        parser.add_argument("--from", "-f", default="auto", dest="from_lang", help="Source language code (auto for detection)")

    def build_input(self, args) -> AgentInput:
        return AgentInput(
            text=args.text,
            options={"target_language": args.to, "source_language": args.from_lang, "model": args.model, "provider": args.provider},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )