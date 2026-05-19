"""Knowledge base command handler for CLI."""

from __future__ import annotations


def cmd_kb(args: str, console, ollama) -> None:
    """Handle /kb command.

    Parameters
    ----------
    args : str
        KB subcommand and arguments.
    console : rich.console.Console
        Rich console for output.
    ollama : OllamaClient
        Ollama client instance.
    """
    from ...core.config import CONFIG, CHROMA_DIR
    from ...storage.kb_manager import CustomKBManager

    parts = args.split(maxsplit=1)
    subcmd = parts[0].lower() if parts else ""
    subargs = parts[1] if len(parts) > 1 else ""

    mgr = CustomKBManager()

    if subcmd in ("list", "ls"):
        kbs = mgr.list_kbs()
        if not kbs:
            console.print("[dim]No knowledge bases found.[/dim]")
            return
        for kb in kbs:
            console.print(f"  [cyan]{kb.internal_name}[/cyan]: {kb.display_name} ({kb.doc_count} docs)")
    elif subcmd == "search":
        if not subargs:
            console.print("[yellow]Usage: /kb search <query>[/yellow]")
            return
        results = mgr.search_all_kbs(subargs)
        for r in results:
            console.print(f"  [{r.get('kb', '')}] {r.get('title', r.get('source', 'N/A'))}")
    elif subcmd == "create":
        if not subargs:
            console.print("[yellow]Usage: /kb create <name>[/yellow]")
            return
        kb = mgr.create_kb(display_name=subargs)
        console.print(f"[green]Created: {kb.internal_name}[/green]")
    elif subcmd == "delete":
        if not subargs:
            console.print("[yellow]Usage: /kb delete <internal_name>[/yellow]")
            return
        success = mgr.delete_kb(subargs.strip())
        if success:
            console.print(f"[green]Deleted: {subargs}[/green]")
        else:
            console.print(f"[red]Failed to delete: {subargs}[/red]")
    else:
        console.print("[yellow]KB commands: list, search, create, delete[/yellow]")