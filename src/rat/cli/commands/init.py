"""Initialize rat in current directory."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from rat.session.tracker import SessionTracker
from rat.worktree.manager import WorktreeManager

console = Console()


def init() -> None:
    """Initialize rat in current directory.

    Creates a .rat/ directory with session tracking
    for the current worktree.

    Examples:
        rat init
        rat init
    """
    cwd = Path.cwd()

    if not (cwd / ".git").exists() and not (cwd / ".git").is_file():
        console.print("[red]Error:[/red] Not a git repository")
        console.print("Run 'git init' first or navigate to a git repository.")
        raise typer.Exit(1)

    rat_dir = cwd / ".rat"
    if rat_dir.exists():
        console.print("[yellow]Already initialized[/yellow]")
        console.print(f"Session file at {rat_dir / 'session.json'}")
        return

    try:
        branch = asyncio.run(_get_current_branch(cwd))
    except Exception:
        branch = "main"

    tracker = SessionTracker(cwd)
    session = tracker.create(branch)

    gitignore = cwd / ".gitignore"
    _update_gitignore(gitignore)

    console.print(
        Panel(
            f"[green]Initialized in {cwd.name}[/green]\n\n"
            f"[bold]Branch:[/bold] {branch}\n"
            f"[bold]Session:[/bold] {session.status.value}\n\n"
            f"[dim]Session tracking is now enabled.[/dim]\n"
            f"[dim]Use 'rat status' to view session metrics.[/dim]\n\n"
            f"[bold]Worktree commands:[/bold]\n"
            f"  [cyan]rat new <branch>[/cyan]   Create parallel worktree\n"
            f"  [cyan]rat list[/cyan]          List all worktrees\n"
            f"  [cyan]rat switch[/cyan]        Switch between worktrees",
            title="rat",
            border_style="green",
        )
    )


async def _get_current_branch(cwd: Path) -> str:
    """Get current git branch."""
    manager = WorktreeManager(cwd)
    worktree = await manager.get_current()
    return worktree.branch if worktree else "main"


def _update_gitignore(gitignore_path: Path) -> None:
    """Add rat entries to .gitignore."""
    entries = [
        "",
        "",
        ".rat/",
        ".claude-session-id",
    ]

    if gitignore_path.exists():
        content = gitignore_path.read_text()

        if ".rat/" in content:
            return
        content += "\n".join(entries) + "\n"
    else:
        content = "\n".join(entries[1:]) + "\n"

    gitignore_path.write_text(content)
