"""Chat command handler for CLI."""

from __future__ import annotations

from typing import Optional


def cmd_chat(args: str, console, ollama, conversation) -> None:
    """Handle /chat command.

    Parameters
    ----------
    args : str
        Chat message or subcommand.
    console : rich.console.Console
        Rich console for output.
    ollama : OllamaClient
        Ollama client instance.
    conversation : ConversationManager
        Conversation history.
    """
    if not args:
        console.print("[yellow]Usage: /chat <message>[/yellow]")
        return

    from ...core.config import CONFIG

    conversation.add("user", args)
    messages = conversation.get_messages(limit=CONFIG.storage.top_k)
    model = CONFIG.llm.chat_model

    try:
        reply = ollama.chat(messages=messages, model=model)
        console.print(f"[green]{reply}[/green]")
        conversation.add("assistant", reply)
    except Exception as e:
        console.print(f"[red]Chat error: {e}[/red]")