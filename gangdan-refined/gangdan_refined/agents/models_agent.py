"""Models agent — list and inspect available LLM models."""

from __future__ import annotations

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class ModelsAgent(BaseAgent):
    name = "gd-models"
    description = "List and inspect available LLM models"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        provider = input.options.get("provider", "")
        api_key = input.options.get("api_key", "")
        base_url = input.options.get("base_url", "")
        model_name = input.query or input.options.get("model", "")

        try:
            if model_name:
                return self._get_model_info(model_name, provider, api_key, base_url)
            return self._list_models(provider, api_key, base_url)
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def _list_models(self, provider: str, api_key: str, base_url: str) -> AgentOutput:
        try:
            client, _ = self._get_llm_client(provider=provider, api_key=api_key, base_url=base_url)
            models = client.get_models()
            return AgentOutput(
                success=True,
                data={"models": models, "count": len(models), "provider": provider or "default"},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def _get_model_info(self, model_name: str, provider: str, api_key: str, base_url: str) -> AgentOutput:
        try:
            client, _ = self._get_llm_client(provider=provider, api_key=api_key, base_url=base_url)
            info = client.get_model_info(model_name)
            return AgentOutput(
                success=True,
                data={"model": model_name, "info": info},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        parser.add_argument("model", nargs="?", default="", help="Model name to get info for (omit to list all)")
        parser.add_argument("--provider", "-p", default="", help="LLM provider")
        parser.add_argument("--api-key", default="", help="API key for cloud providers")
        parser.add_argument("--base-url", default="", help="Base URL for API providers")

    def build_input(self, args) -> AgentInput:
        return AgentInput(
            query=args.model or "",
            options={"provider": args.provider, "api_key": args.api_key, "base_url": args.base_url},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )