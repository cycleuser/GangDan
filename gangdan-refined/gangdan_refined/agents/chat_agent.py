"""Chat agent — have a conversation with an LLM."""

from __future__ import annotations

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class ChatAgent(BaseAgent):
    name = "gd-chat"
    description = "Chat with an LLM model"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        message = input.query or input.text or ""
        system_prompt = input.options.get("system_prompt", "")
        model = input.options.get("model", "")
        provider = input.options.get("provider", "")
        api_key = input.options.get("api_key", "")
        base_url = input.options.get("base_url", "")
        language = input.options.get("language", "")

        if not message:
            return AgentOutput(success=False, error="No message provided", metadata=AgentMetadata(agent=self.name, version=self.version))

        try:
            client, model_name = self._get_llm_client(provider=provider, model=model, api_key=api_key, base_url=base_url)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            if language:
                messages.append({"role": "system", "content": f"Respond in {language}."})

            messages.append({"role": "user", "content": message})

            response = client.chat(messages=messages, model=model_name)
            return AgentOutput(
                success=True,
                data={"response": response, "model": model_name, "message": message},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        parser.add_argument("message", nargs="?", default="", help="Message to send")
        parser.add_argument("--stdin", action="store_true", help="Read message from stdin")
        parser.add_argument("--system-prompt", default="", help="System prompt")
        parser.add_argument("--model", "-m", default="", help="Model to use")
        parser.add_argument("--provider", "-p", default="", help="LLM provider")
        parser.add_argument("--api-key", default="", help="API key")
        parser.add_argument("--base-url", default="", help="Base URL")

    def main(self, args=None) -> None:
        parser = argparse.ArgumentParser(prog="gd-chat", description=self.description)
        self.add_arguments(parser)
        parsed = parser.parse_args(args)
        self.init_env(parsed)

        if parsed.stdin and not sys.stdin.isatty():
            import json as _json
            raw = sys.stdin.read().strip()
            parsed.message = raw

        agent_input = self.build_input(parsed)
        result = self.run(agent_input)
        self.output(result, parsed)

    def build_input(self, args) -> AgentInput:
        return AgentInput(
            query=args.message or "",
            options={
                "model": args.model,
                "provider": args.provider,
                "api_key": args.api_key,
                "base_url": args.base_url,
                "system_prompt": args.system_prompt,
                "language": args.language,
            },
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )


import argparse
import sys