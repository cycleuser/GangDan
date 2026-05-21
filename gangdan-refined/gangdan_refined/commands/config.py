"""gd-config - View and modify configuration.

Usage:
    gd-config show                       # Show current config
    gd-config get ollama_url             # Get a specific config value
    gd-config set llm.chat_model=qwen3  # Set a config value
    gd-config set llm.ollama_url=http://host:11434
    gd-config providers                  # List available LLM providers
    gd-config reset                      # Reload config from disk
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys


def main(args=None) -> None:
    parser = argparse.ArgumentParser(
        prog="gd-config",
        description="View and modify GangDan configuration",
    )
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    show_p = subparsers.add_parser("show", help="Show current configuration")
    show_p.add_argument("--group", "-g", default="", help="Show only a specific group (llm, storage, search, etc.)")

    get_p = subparsers.add_parser("get", help="Get a specific config value")
    get_p.add_argument("key", help="Config key (e.g. llm.chat_model, storage.chunk_size)")

    set_p = subparsers.add_parser("set", help="Set a config value")
    set_p.add_argument("key_value", help="key=value (e.g. llm.chat_model=qwen3:7b)")

    subparsers.add_parser("providers", help="List available LLM providers")

    get_models_p = subparsers.add_parser("models", help="List available models for a provider")
    get_models_p.add_argument("--provider", "-p", default="ollama", help="Provider name")
    get_models_p.add_argument("--api-key", default="", help="API key for cloud providers")

    subparsers.add_parser("reset", help="Reload configuration from disk")

    from .common import add_common_args, init_env, output, output_error
    add_common_args(parser)
    parsed = parser.parse_args(args)
    init_env(parsed)

    if not parsed.action:
        parser.print_help()
        sys.exit(1)

    from ..core.config import CONFIG, save_config, load_config

    if parsed.action == "show":
        group = parsed.group
        if group:
            obj = getattr(CONFIG, group, None)
            if obj is None or not dataclasses.is_dataclass(obj):
                output_error(f"Unknown config group: {group}", parsed)
            data = dataclasses.asdict(obj)
            output({"success": True, "group": group, "config": data}, parsed)
        else:
            data = {}
            for f in dataclasses.fields(CONFIG):
                v = getattr(CONFIG, f.name)
                if dataclasses.is_dataclass(v):
                    data[f.name] = dataclasses.asdict(v)
                else:
                    data[f.name] = v
            output({"success": True, "config": data}, parsed)

    elif parsed.action == "get":
        key = parsed.key
        parts = key.split(".", 1)
        if len(parts) == 2:
            group_name, attr = parts
            obj = getattr(CONFIG, group_name, None)
            if obj and hasattr(obj, attr):
                value = getattr(obj, attr)
                output({"success": True, "key": key, "value": value}, parsed, text=str(value))
            else:
                output_error(f"Unknown config key: {key}", parsed)
        else:
            if hasattr(CONFIG, key):
                value = getattr(CONFIG, key)
                output({"success": True, "key": key, "value": value}, parsed, text=str(value))
            else:
                output_error(f"Unknown config key: {key}", parsed)

    elif parsed.action == "set":
        key_value = parsed.key_value
        if "=" not in key_value:
            output_error("Format: key=value (e.g. llm.chat_model=qwen3)", parsed)
        key, _, value = key_value.partition("=")
        parts = key.split(".", 1)
        if len(parts) == 2:
            group_name, attr = parts
            obj = getattr(CONFIG, group_name, None)
            if obj and hasattr(obj, attr):
                setattr(obj, attr, _convert_value(value))
                save_config()
                output({"success": True, "key": key, "value": getattr(obj, attr)}, parsed)
            else:
                output_error(f"Unknown config key: {key}", parsed)
        else:
            if hasattr(CONFIG, key):
                setattr(CONFIG, key, _convert_value(value))
                save_config()
                output({"success": True, "key": key, "value": getattr(CONFIG, key)}, parsed)
            else:
                output_error(f"Unknown config key: {key}", parsed)

    elif parsed.action == "providers":
        from ..llm.factory import list_providers
        providers = list_providers()
        output({"success": True, "providers": providers}, parsed)

    elif parsed.action == "models":
        from ..llm.factory import create_client
        provider = parsed.provider
        api_key = parsed.api_key
        base_url = ""
        config = None
        from ..llm.models import PROVIDER_CONFIGS
        cfg = PROVIDER_CONFIGS.get(provider)
        if cfg:
            api_key = api_key or CONFIG.llm.provider_keys.get(provider, "")
            base_url = CONFIG.llm.provider_base_urls.get(provider, "") or cfg.base_url
        client = create_client(provider, api_key=api_key, base_url=base_url)
        models = client.get_models()
        output({"success": True, "provider": provider, "models": models, "count": len(models)}, parsed)

    elif parsed.action == "reset":
        load_config()
        output({"success": True, "message": "Configuration reloaded from disk"}, parsed)


def _convert_value(value: str):
    """Convert a string value to the appropriate Python type."""
    if value.lower() in ("true", "1", "yes", "on"):
        return True
    if value.lower() in ("false", "0", "no", "off"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value