"""List all worktrees with session status."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from rat.session.tracker import SessionStatus, SessionTracker
from rat.worktree.manager import WorktreeManager

console = Console()


def list_cmd() -> None:
    """List all worktrees with AI session status.

    Shows all git worktrees in the repository along with their
    session status, duration, and cost.

    Examples:
        rat list
    """
    cwd = Path.cwd()

    if not (cwd / ".git").exists() and not (cwd / ".git").is_file():
        console.print("[red]Error:[/red] Not in a git repository")
        raise typer.Exit(1)

    try:
        worktrees = asyncio.run(_get_worktrees(cwd))
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not worktrees:
        console.print("[yellow]No worktrees found[/yellow]")
        return

    table = Table(title="Worktrees")
    table.add_column("Branch", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Interactions", justify="right")

    for wt, session in worktrees:
        if session is None:
            status_str = "[dim]-[/dim]"
            duration = "[dim]-[/dim]"
            cost = "[dim]-[/dim]"
            interactions = "[dim]-[/dim]"
        else:
            if session.status == SessionStatus.ACTIVE:
                status_str = "[green]active[/green]"
            elif session.status == SessionStatus.PAUSED:
                status_str = "[yellow]paused[/yellow]"
            elif session.status == SessionStatus.STOPPED:
                status_str = "[red]stopped[/red]"
            else:
                status_str = "[dim]ready[/dim]"

            duration = session.duration_display
            cost = session.cost_display
            interactions = str(session.metrics.interactions)

        branch = wt.branch
        if wt.is_main:
            branch = f"{branch} [dim](main)[/dim]"

        if wt.path == cwd.resolve():
            branch = f"[bold]{branch}[/bold] *"

        table.add_row(
            branch,
            str(wt.path),
            status_str,
            duration,
            cost,
            interactions,
        )

    console.print(table)


async def _get_worktrees(cwd: Path):
    """Get all worktrees with their session status."""
    manager = WorktreeManager(cwd)
    worktrees = await manager.list()

    result = []
    for wt in worktrees:
        tracker = SessionTracker(wt.path)
        session = tracker.load() if tracker.has_session() else None
        result.append((wt, session))

    return result
