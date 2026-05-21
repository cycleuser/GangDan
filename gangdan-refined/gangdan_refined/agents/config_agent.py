"""Configuration agent — view and modify GangDan settings."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class ConfigAgent(BaseAgent):
    name = "gd-config"
    description = "View and modify GangDan configuration"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        action = input.options.get("action", "show")
        key = input.options.get("key", "")
        value = input.options.get("value")

        try:
            if action == "set" and key:
                return self._set_config(key, value)
            elif action == "get" and key:
                return self._get_config(key)
            elif action == "show" or action == "list":
                return self._show_config()
            elif action == "providers":
                return self._list_providers()
            elif action == "reset":
                return self._reset_config()
            else:
                return self._show_config()
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def _show_config(self) -> AgentOutput:
        from ..core.config import CONFIG, DATA_DIR
        config_dict = self._config_to_dict(CONFIG)
        return AgentOutput(
            success=True,
            data={"config": config_dict, "data_dir": str(DATA_DIR)},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def _get_config(self, key: str) -> AgentOutput:
        from ..core.config import CONFIG
        value = self._get_nested_attr(CONFIG, key)
        if value is None:
            return AgentOutput(
                success=False,
                error=f"Config key '{key}' not found",
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        return AgentOutput(
            success=True,
            data={"key": key, "value": value},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def _set_config(self, key: str, value: Any) -> AgentOutput:
        from ..core.config import CONFIG, save_config
        if isinstance(value, str):
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            elif value.isdigit():
                value = int(value)
            elif value.replace(".", "", 1).isdigit():
                value = float(value)
        self._set_nested_attr(CONFIG, key, value)
        save_config()
        return AgentOutput(
            success=True,
            data={"key": key, "value": value, "message": f"Set {key} = {value}"},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def _list_providers(self) -> AgentOutput:
        from ..llm.factory import list_providers
        providers = list_providers()
        return AgentOutput(
            success=True,
            data={"providers": providers},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def _reset_config(self) -> AgentOutput:
        from ..core.config import CONFIG, save_config
        from ..core.config import Config, ProxyConfig, LLMConfig, StorageConfig, SearchConfig
        from ..core.config import DocumentConfig, PreprintConfig, ResearchConfig, AdaptiveConfig, UIConfig
        CONFIG.proxy = ProxyConfig()
        CONFIG.llm = LLMConfig()
        CONFIG.storage = StorageConfig()
        CONFIG.search = SearchConfig()
        CONFIG.document = DocumentConfig()
        CONFIG.preprint = PreprintConfig()
        CONFIG.research = ResearchConfig()
        CONFIG.adaptive = AdaptiveConfig()
        CONFIG.ui = UIConfig()
        save_config()
        return AgentOutput(
            success=True,
            data={"message": "Configuration reset to defaults"},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )

    def _config_to_dict(self, config) -> Dict[str, Any]:
        result = {}
        for group in ("proxy", "llm", "storage", "search", "document", "preprint", "research", "adaptive", "ui"):
            grp = getattr(config, group, None)
            if grp is not None:
                result[group] = {}
                for k, v in vars(grp).items():
                    if not k.startswith("_"):
                        result[group][k] = v
        return result

    def _get_nested_attr(self, obj, key: str) -> Any:
        parts = key.split(".")
        current = obj
        for part in parts:
            current = getattr(current, part, None)
            if current is None:
                return None
        return current

    def _set_nested_attr(self, obj, key: str, value: Any) -> None:
        parts = key.split(".")
        current = obj
        for part in parts[:-1]:
            current = getattr(current, part, None)
            if current is None:
                raise ValueError(f"Config path '{key}' not found")
        setattr(current, parts[-1], value)

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        subparsers = parser.add_subparsers(dest="action", help="Config action")
        show = subparsers.add_parser("show", help="Show all config")
        show.add_argument("--json", action="store_true", help="Output as JSON")
        get = subparsers.add_parser("get", help="Get config value")
        get.add_argument("key", help="Config key (e.g., llm.chat_model)")
        get.add_argument("--json", action="store_true", help="Output as JSON")
        set_cmd = subparsers.add_parser("set", help="Set config value")
        set_cmd.add_argument("key", help="Config key")
        set_cmd.add_argument("value", help="Config value")
        set_cmd.add_argument("--json", action="store_true", help="Output as JSON")
        providers = subparsers.add_parser("providers", help="List LLM providers")
        providers.add_argument("--json", action="store_true", help="Output as JSON")
        reset = subparsers.add_parser("reset", help="Reset to defaults")
        reset.add_argument("--json", action="store_true", help="Output as JSON")

    def build_input(self, args) -> AgentInput:
        action = getattr(args, "action", "show") or "show"
        options = {
            "action": action,
            "key": getattr(args, "key", ""),
            "value": getattr(args, "value", None),
        }
        return AgentInput(options=options, metadata=AgentMetadata(agent=self.name, version=self.version))