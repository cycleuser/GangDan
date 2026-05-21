"""Summarize agent — summarize text with an LLM."""

from __future__ import annotations

from ..core.config import detect_language, LANGUAGES
from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class SummarizeAgent(BaseAgent):
    name = "gd-summarize"
    description = "Summarize text with an LLM"
    version = "2.0.0"

    STYLE_PROMPTS = {
        "paragraph": "Summarize the following text in a concise paragraph.",
        "bullet": "Summarize the following text as bullet points.",
        "abstract": "Write an academic abstract summarizing the following text.",
        "key_points": "Extract the key points from the following text.",
        "eli5": "Explain the following text in simple terms a 5-year-old could understand.",
    }

    LENGTH_HINTS = {"brief": "in 1-2 sentences", "medium": "in 2-4 sentences", "detailed": "in detail"}

    def run(self, input: AgentInput) -> AgentOutput:
        text = input.text or input.query or ""
        style = input.options.get("style", "paragraph")
        length = input.options.get("length", "medium")
        language = input.options.get("language", "")
        model = input.options.get("model", "")
        provider = input.options.get("provider", "")
        api_key = input.options.get("api_key", "")
        base_url = input.options.get("base_url", "")

        if not text:
            return AgentOutput(success=False, error="Text required", metadata=AgentMetadata(agent=self.name, version=self.version))

        try:
            client, model_name = self._get_llm_client(provider=provider, model=model, api_key=api_key, base_url=base_url)

            prompt = self.STYLE_PROMPTS.get(style, self.STYLE_PROMPTS["paragraph"])
            length_hint = self.LENGTH_HINTS.get(length, "")
            if length_hint:
                prompt += f" {length_hint}."

            if language:
                lang_name = LANGUAGES.get(language, language)
                prompt += f" Write in {lang_name}."
            elif style != "eli5":
                detected = detect_language(text)
                if detected != "en":
                    prompt += " Write in the same language as the input."

            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ]
            summary = client.chat(messages=messages, model=model_name)

            return AgentOutput(
                success=True,
                data={"summary": summary, "style": style, "length": length, "model": model_name},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        parser.add_argument("text", nargs="?", default="", help="Text to summarize")
        parser.add_argument("--stdin", action="store_true", help="Read text from stdin")
        parser.add_argument("--style", "-s", default="paragraph", choices=["paragraph", "bullet", "abstract", "key_points", "eli5"], help="Summary style")
        parser.add_argument("--length", "-l", default="medium", choices=["brief", "medium", "detailed"], help="Summary length")

    def build_input(self, args) -> AgentInput:
        return AgentInput(
            text=args.text,
            options={"style": args.style, "length": args.length, "language": args.language, "model": args.model, "provider": args.provider, "api_key": args.api_key, "base_url": args.base_url},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )