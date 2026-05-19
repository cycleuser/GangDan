"""gd-chat - Send a message to an LLM.

Usage:
    gd-chat "Hello, world!"
    gd-chat "Explain quantum computing" --model qwen3:7b --provider ollama
    gd-chat "Write a function" --system "You are a Python expert" --json
    echo "What is AI?" | gd-chat --stdin
"""

from __future__ import annotations

import argparse
import sys


def main(args=None) -> None:
    parser = argparse.ArgumentParser(
        prog="gd-chat",
        description="Send a message to an LLM and get a response",
    )
    parser.add_argument("message", nargs="?", help="Message to send (use --stdin for piped input)")
    parser.add_argument("--stdin", action="store_true", help="Read message from stdin")
    parser.add_argument("--model", "-m", default="", help="Model name (default: from config)")
    parser.add_argument("--provider", "-p", default="", help="LLM provider (ollama, openai, deepseek, etc.)")
    parser.add_argument("--api-key", default="", help="API key for cloud providers")
    parser.add_argument("--base-url", default="", help="Custom base URL")
    parser.add_argument("--system", "-s", default="", help="System prompt")
    parser.add_argument("--temperature", "-t", type=float, default=0.7, help="Sampling temperature")
    parser.add_argument("--stream", action="store_true", help="Stream response token by token")
    parser.add_argument("--conversation", "-c", default="", help="Conversation ID to continue")
    from .common import add_common_args, init_env, output, output_error, get_llm_client, get_ollama_client
    add_common_args(parser)
    parsed = parser.parse_args(args)
    init_env(parsed)

    if parsed.stdin:
        message = sys.stdin.read().strip()
    elif parsed.message:
        message = parsed.message
    else:
        output_error("Message required. Use positional arg or --stdin", parsed)

    if parsed.provider == "ollama" or (not parsed.provider and not parsed.api_key):
        from ..llm.ollama import OllamaClient
        from ..core.config import CONFIG
        client = OllamaClient(parsed.base_url or CONFIG.llm.ollama_url)
        model = parsed.model or CONFIG.llm.chat_model
    else:
        client = get_llm_client(
            provider=parsed.provider,
            api_key=parsed.api_key,
            base_url=parsed.base_url,
        )
        model = parsed.model or CONFIG.llm.chat_model

    messages = []
    if parsed.system:
        messages.append({"role": "system", "content": parsed.system})

    if parsed.conversation:
        from ..storage.conversation import ConversationManager
        mgr = ConversationManager()
        mgr.load_auto_saved()
        messages.extend(mgr.get_messages(limit=CONFIG.storage.top_k))

    messages.append({"role": "user", "content": message})

    if parsed.stream:
        for chunk in client.chat_stream(messages=messages, model=model, temperature=parsed.temperature):
            print(chunk, end="", flush=True)
        print()
        return

    reply = client.chat(messages=messages, model=model, temperature=parsed.temperature)
    output(
        {"response": reply, "model": model, "provider": parsed.provider or "ollama"},
        parsed,
        text=reply,
    )