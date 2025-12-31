"""Show rat session status."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rat.cli import RAT_LOGO
from rat.session.tracker import SessionStatus, SessionTracker
from rat.worktree.manager import WorktreeManager

console = Console()


def status() -> None:
    """Show current worktree's AI session status.

    Displays information about the session in the current worktree,
    including interactions, tokens, cost, and duration.
    """
    cwd = Path.cwd()

    if not (cwd / ".git").exists() and not (cwd / ".git").is_file():
        console.print("[red]Error:[/red] Not in a git repository")
        raise typer.Exit(1)

    try:
        worktree = asyncio.run(_get_current_worktree(cwd))
    except Exception:
        worktree = None

    tracker = SessionTracker(cwd)
    session = tracker.load()

    if session is None:
        console.print(
            Panel(
                f"[bold cyan]{RAT_LOGO.strip()}[/bold cyan]\n\n"
                "[yellow]No session found[/yellow]\n\n"
                "To start tracking:\n"
                "  [cyan]rat new <branch>[/cyan]  Create a new worktree\n"
                "  [cyan]rat init[/cyan]          Initialize in current directory",
                title="rat",
                border_style="yellow",
            )
        )
        return

    if session.status == SessionStatus.ACTIVE:
        status_str = "[green]active[/green] (Claude running)"
        border_style = "green"
    elif session.status == SessionStatus.PAUSED:
        status_str = "[yellow]paused[/yellow]"
        border_style = "yellow"
    elif session.status == SessionStatus.STOPPED:
        status_str = "[red]stopped[/red]"
        border_style = "red"
    else:
        status_str = "[dim]ready[/dim]"
        border_style = "blue"

    worktree_name = worktree.branch if worktree else cwd.name
    session_id = session.id or "[dim]not started[/dim]"

    status_text = (
        f"[bold cyan]{RAT_LOGO.strip()}[/bold cyan]\n\n"
        f"[bold]Worktree:[/bold]  {worktree_name}\n"
        f"[bold]Session:[/bold]   {session_id}\n"
        f"[bold]Status:[/bold]    {status_str}\n"
        f"[bold]Duration:[/bold]  {session.duration_display}\n"
    )

    tokens = session.metrics.total_tokens
    tokens_in = session.metrics.tokens_in
    tokens_out = session.metrics.tokens_out
    status_text += f"[bold]Tokens:[/bold]    {tokens:,} ({tokens_in:,} in / {tokens_out:,} out)\n"

    plan_file = session.plan_file or tracker.get_plan_file()
    if plan_file:
        status_text += f"[bold]Plan:[/bold]      {plan_file}"

    console.print(
        Panel(
            status_text,
            title="rat",
            border_style=border_style,
        )
    )

    if session.metrics.interactions > 0:
        console.print()
        table = Table(title="Session Statistics")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Interactions", str(session.metrics.interactions))
        table.add_row("Tokens (in)", f"{session.metrics.tokens_in:,}")
        table.add_row("Tokens (out)", f"{session.metrics.tokens_out:,}")
        table.add_row("Duration", session.duration_display)

        if session.metrics.models_used:
            models = ", ".join(sorted(session.metrics.models_used))
            table.add_row("Models", models)

        console.print(table)


async def _get_current_worktree(cwd: Path):
    """Get the current worktree."""
    manager = WorktreeManager(cwd)
    return await manager.get_current()
