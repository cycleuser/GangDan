"""CLI REPL for GangDan Refined.

Provides a Rich-based interactive command loop that delegates
all business logic to domain modules.
"""

from __future__ import annotations

import sys
from typing import Optional

from ..core.config import CONFIG, load_config
from ..core.constants import APP_NAME, APP_VERSION
from ..core.errors import GangDanError


def start_repl() -> None:
    """Start the interactive REPL."""
    load_config()

    try:
        from rich.console import Console
        from rich.panel import Panel
        console = Console()
    except ImportError:
        _basic_repl()
        return

    console.print(Panel(
        f"[bold]{APP_NAME}[/bold] v{APP_VERSION}\n"
        f"Type [bold]/help[/bold] for commands, [bold]/quit[/bold] to exit.",
        title=f"{APP_NAME} Refined",
        border_style="blue",
    ))

    from ..llm.ollama import OllamaClient
    from ..storage.conversation import ConversationManager

    ollama = OllamaClient(CONFIG.llm.ollama_url)
    conversation = ConversationManager(auto_save=True)

    while True:
        try:
            user_input = console.input("[bold cyan]gangdan> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            _handle_command(user_input, console, ollama, conversation)
        else:
            _handle_chat(user_input, console, ollama, conversation)


def _handle_command(cmd: str, console, ollama, conversation) -> None:
    """Route slash commands to their handlers."""
    from .commands.chat import cmd_chat
    from .commands.kb import cmd_kb
    from .commands.config import cmd_config

    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command in ("/quit", "/exit", "/q"):
        console.print("[dim]Goodbye![/dim]")
        raise SystemExit(0)
    elif command in ("/help", "/h", "/?"):
        _show_help(console)
    elif command in ("/chat", "/c"):
        cmd_chat(args, console, ollama, conversation)
    elif command in ("/kb", "/k"):
        cmd_kb(args, console, ollama)
    elif command in ("/config", "/cfg"):
        cmd_config(args, console)
    else:
        console.print(f"[yellow]Unknown command: {command}[/yellow]")


def _handle_chat(message: str, console, ollama, conversation) -> None:
    """Handle a direct chat message (no slash)."""
    conversation.add("user", message)
    messages = conversation.get_messages(limit=CONFIG.storage.top_k)

    model = CONFIG.llm.chat_model
    console.print(f"[dim]Using model: {model}[/dim]")

    try:
        for chunk in ollama.chat_stream(messages=messages, model=model):
            console.print(chunk, end="")
        console.print()
        reply = ollama.chat(messages=messages, model=model)
        conversation.add("assistant", reply)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _show_help(console) -> None:
    """Show available commands."""
    console.print("""
[bold]Available Commands:[/bold]

  /chat <message>   Send a chat message
  /kb <command>     Knowledge base operations
  /config <cmd>     Configuration management
  /help             Show this help
  /quit             Exit the REPL
""")


def _basic_repl() -> None:
    """Basic REPL fallback without Rich."""
    print(f"{APP_NAME} v{APP_VERSION}")
    print("Type /help for commands, /quit to exit.")

    from ..llm.ollama import OllamaClient
    ollama = OllamaClient(CONFIG.llm.ollama_url)
    model = CONFIG.llm.chat_model

    while True:
        try:
            user_input = input("gangdan> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            if cmd in ("/quit", "/exit", "/q"):
                print("Goodbye!")
                break
            elif cmd in ("/help", "/h", "/?"):
                print("Commands: /chat, /kb, /config, /help, /quit")
            else:
                print(f"Unknown command: {cmd}")
        else:
            try:
                reply = ollama.chat(messages=[{"role": "user", "content": user_input}], model=model)
                print(reply)
            except Exception as e:
                print(f"Error: {e}")