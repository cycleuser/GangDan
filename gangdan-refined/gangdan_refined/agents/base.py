"""Base agent abstract class and common utilities.

Every GangDan agent inherits from BaseAgent and implements run().
The base class handles:
- CLI argument parsing (--json, --stdin, --model, --provider, etc.)
- stdin/stdout JSON pipeline communication
- Error handling and output formatting
"""

from __future__ import annotations

import argparse
import json
import sys
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .protocol import (
    AgentInput,
    AgentOutput,
    AgentMetadata,
    AGENT_PROTOCOL_VERSION,
    validate_input,
    validate_output,
    encode_output,
    decode_input,
)


class BaseAgent(ABC):
    name: str = "unknown"
    description: str = ""
    version: str = "2.0.0"

    def __init__(self):
        self._config = None
        self._config_loaded = False

    @abstractmethod
    def run(self, input: AgentInput) -> AgentOutput:
        """Execute the agent's core logic.

        Args:
            input: Standardized agent input.

        Returns:
            AgentOutput with success status, data, and metadata.
        """

    def _ensure_config(self):
        if not self._config_loaded:
            from ..core.config import CONFIG, load_config
            load_config()
            self._config = CONFIG
            self._config_loaded = True
        return self._config

    @property
    def config(self):
        return self._ensure_config()

    def _get_llm_client(self, provider: str = "", model: str = "", api_key: str = "", base_url: str = ""):
        from ..llm.factory import create_client
        p = provider or self.config.llm.chat_provider
        m = model or self.config.llm.chat_model
        k = api_key or ""
        b = base_url or ""
        return create_client(p, api_key=k, base_url=b), m

    def _get_ollama_client(self):
        from ..llm.ollama import OllamaClient
        return OllamaClient(self.config.llm.ollama_url)

    def _get_chroma(self):
        from ..storage.chroma_manager import ChromaManager
        from ..core.config import CHROMA_DIR
        return ChromaManager(persist_dir=str(CHROMA_DIR))

    def add_common_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        parser.add_argument("--model", "-m", default="", help="Model to use")
        parser.add_argument("--provider", "-p", default="", help="LLM provider")
        parser.add_argument("--api-key", default="", help="API key for cloud providers")
        parser.add_argument("--base-url", default="", help="Base URL for API providers")
        parser.add_argument("--language", default="", help="Output language code (zh, en, ja, etc.)")
        parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    def init_env(self, args: argparse.Namespace) -> None:
        import os
        if hasattr(args, "data_dir") and args.data_dir:
            os.environ["GANGLAN_REFINED_DATA_DIR"] = args.data_dir
        self._ensure_config()

    def output(self, result: AgentOutput, args: argparse.Namespace) -> None:
        json_mode = getattr(args, "json", False)
        print(encode_output(result, json_mode=json_mode))

    def output_error(self, error: str, args: argparse.Namespace) -> None:
        json_mode = getattr(args, "json", False)
        result = AgentOutput(
            success=False,
            error=error,
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )
        print(encode_output(result, json_mode=json_mode), file=sys.stderr)
        sys.exit(1)

    def run_from_stdin(self, args: argparse.Namespace) -> None:
        agent_input = decode_input(use_stdin=True)
        if agent_input is None:
            self.output_error("No input provided on stdin", args)
            return
        if hasattr(args, "model") and args.model:
            agent_input.options["model"] = args.model
        if hasattr(args, "provider") and args.provider:
            agent_input.options["provider"] = args.provider
        result = self.run(agent_input)
        self.output(result, args)

    def main(self, args=None) -> None:
        parser = argparse.ArgumentParser(
            prog=f"gangdan-refined-{self.name}",
            description=self.description,
        )
        self.add_common_args(parser)
        self.add_arguments(parser)
        parsed = parser.parse_args(args)
        self.init_env(parsed)

        if getattr(parsed, "stdin", False):
            self.run_from_stdin(parsed)
            return

        agent_input = self.build_input(parsed)
        result = self.run(agent_input)
        self.output(result, parsed)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def build_input(self, args: argparse.Namespace) -> AgentInput:
        return AgentInput(
            query=getattr(args, "query", None) or getattr(args, "text", None),
            options={
                "model": getattr(args, "model", ""),
                "provider": getattr(args, "provider", ""),
                "api_key": getattr(args, "api_key", ""),
                "base_url": getattr(args, "base_url", ""),
                "language": getattr(args, "language", ""),
                "verbose": getattr(args, "verbose", False),
            },
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )