"""CLI interface for GangDan Refined.

Provides a Rich TUI REPL with command routing.
Business logic is delegated to domain modules.
"""

from .repl import start_repl

__all__ = ["start_repl"]