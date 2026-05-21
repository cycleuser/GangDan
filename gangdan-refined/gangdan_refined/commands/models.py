"""gd-models - List and inspect available LLM models.

Usage:
    gd-models                    # List all models
    gd-models --chat             # List chat models only
    gd-models --embed            # List embedding models only
    gd-models --info qwen3:7b    # Get detailed model info
    gd-models --memory           # Show GPU memory usage
"""

from __future__ import annotations

import argparse
import sys


def main(args=None) -> None:
    parser = argparse.ArgumentParser(
        prog="gd-models",
        description="List and inspect available LLM models",
    )
    parser.add_argument("--chat", action="store_true", help="Show only chat models")
    parser.add_argument("--embed", action="store_true", help="Show only embedding models")
    parser.add_argument("--info", "-i", default="", help="Get detailed info for a model")
    parser.add_argument("--memory", action="store_true", help="Show GPU/memory usage")
    parser.add_argument("--provider", "-p", default="ollama", help="Provider to query")
    parser.add_argument("--api-key", default="", help="API key for cloud providers")
    from .common import add_common_args, init_env, output, output_error
    add_common_args(parser)
    parsed = parser.parse_args(args)
    init_env(parsed)

    from ..core.config import CONFIG
    from ..llm.ollama import OllamaClient
    from ..llm.factory import create_client, list_providers

    # Memory info (Ollama only)
    if parsed.memory:
        client = OllamaClient(CONFIG.llm.ollama_url)
        mem = client.get_memory_usage()
        output({"success": True, "memory": mem}, parsed)
        return

    # Detailed model info (Ollama only)
    if parsed.info:
        client = OllamaClient(CONFIG.llm.ollama_url)
        info = client.get_model_info(parsed.info)
        if not parsed.output_json:
            for k, v in info.items():
                print(f"{k}: {v}")
        else:
            output({"success": True, "model": parsed.info, "info": info}, parsed)
        return

    # List providers
    if parsed.provider != "ollama":
        from ..llm.models import PROVIDER_CONFIGS
        cfg = PROVIDER_CONFIGS.get(parsed.provider)
        api_key = parsed.api_key or CONFIG.llm.provider_keys.get(parsed.provider, "")
        base_url = CONFIG.llm.provider_base_urls.get(parsed.provider, "") or (cfg.base_url if cfg else "")
        client = create_client(parsed.provider, api_key=api_key, base_url=base_url)
        models = client.get_models()
        output({
            "success": True,
            "provider": parsed.provider,
            "models": models,
            "count": len(models),
        }, parsed)
        return

    # Ollama local models
    client = OllamaClient(CONFIG.llm.ollama_url)

    if not client.is_available():
        output_error("Ollama server is not running. Start it with: ollama serve", parsed)

    if parsed.chat:
        models = client.get_chat_models()
        output({"success": True, "type": "chat", "models": models, "count": len(models)}, parsed)
    elif parsed.embed:
        models = client.get_embedding_models()
        output({"success": True, "type": "embedding", "models": models, "count": len(models)}, parsed)
    else:
        all_models = client.get_models()
        output({"success": True, "models": all_models, "count": len(all_models)}, parsed)