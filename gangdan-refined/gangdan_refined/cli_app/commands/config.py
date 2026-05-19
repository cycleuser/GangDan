"""Configuration command handler for CLI."""

from __future__ import annotations

import dataclasses

from ...core.config import CONFIG, save_config, load_config


def cmd_config(args: str, console) -> None:
    """Handle /config command.

    Parameters
    ----------
    args : str
        Config subcommand and arguments.
    console : rich.console.Console
        Rich console for output.
    """
    parts = args.split(maxsplit=1)
    subcmd = parts[0].lower() if parts else ""
    subargs = parts[1] if len(parts) > 1 else ""

    if subcmd in ("show", "get"):
        _show_config(console)
    elif subcmd == "set":
        _set_config(subargs, console)
    elif subcmd == "reset":
        _reset_config(console)
    elif subcmd == "save":
        save_config()
        console.print("[green]Configuration saved.[/green]")
    else:
        console.print("[yellow]Config commands: show, set, reset, save[/yellow]")


def _show_config(console) -> None:
    """Display current configuration."""
    console.print("[bold]Current Configuration:[/bold]")
    for field_info in dataclasses.fields(CONFIG):
        name = field_info.name
        value = getattr(CONFIG, name)
        if dataclasses.is_dataclass(value):
            console.print(f"  [cyan]{name}:[/cyan]")
            for sub_field in dataclasses.fields(value):
                sub_name = sub_field.name
                sub_val = getattr(value, sub_name)
                if "api_key" in sub_name or "token" in sub_name:
                    sub_val = sub_val[:4] + "****" if sub_val else ""
                console.print(f"    {sub_name} = {sub_val}")
        else:
            if "api_key" in name or "token" in name:
                value = value[:4] + "****" if value else ""
            console.print(f"  {name} = {value}")


def _set_config(args: str, console) -> None:
    """Set a configuration value."""
    if not args or "=" not in args:
        console.print("[yellow]Usage: /config set <key>=<value>[/yellow]")
        return

    key, _, value = args.partition("=")
    key = key.strip()
    value = value.strip()

    # Check grouped configs
    for field_info in dataclasses.fields(CONFIG):
        group_name = field_info.name
        group_obj = getattr(CONFIG, group_name)
        if dataclasses.is_dataclass(group_obj):
            for sub_field in dataclasses.fields(group_obj):
                if sub_field.name == key:
                    try:
                        typed_val = _convert_value(value, sub_field.type)
                        setattr(group_obj, key, typed_val)
                        console.print(f"[green]Set {group_name}.{key} = {typed_val}[/green]")
                        return
                    except (ValueError, TypeError) as e:
                        console.print(f"[red]Invalid value: {e}[/red]")
                        return

    # Check top-level config
    if hasattr(CONFIG, key):
        for field_info in dataclasses.fields(CONFIG):
            if field_info.name == key:
                try:
                    typed_val = _convert_value(value, field_info.type)
                    setattr(CONFIG, key, typed_val)
                    console.print(f"[green]Set {key} = {typed_val}[/green]")
                    return
                except (ValueError, TypeError) as e:
                    console.print(f"[red]Invalid value: {e}[/red]")
                    return

    console.print(f"[red]Unknown config key: {key}[/red]")


def _reset_config(console) -> None:
    """Reset configuration to defaults."""
    load_config()
    console.print("[green]Configuration reloaded from disk.[/green]")


def _convert_value(value: str, type_hint) -> object:
    """Convert a string value to the appropriate Python type."""
    if type_hint in ("int", int):
        return int(value)
    elif type_hint in ("float", float):
        return float(value)
    elif type_hint in ("bool", bool):
        return value.lower() in ("true", "1", "yes", "on")
    else:
        return value