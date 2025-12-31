"""Create new worktree with AI context."""

import asyncio
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from rat.session.tracker import SessionTracker
from rat.worktree.manager import WorktreeError, WorktreeManager

console = Console()


def new(
    branch: Annotated[str, typer.Argument(help="Branch name for the new worktree")],
    path: Annotated[
        Optional[Path],
        typer.Argument(help="Path for the worktree (defaults to sibling directory)"),
    ] = None,
    base: Annotated[
        str,
        typer.Option("--base", "-b", help="Base branch/commit to create from"),
    ] = "HEAD",
    no_branch: Annotated[
        bool,
        typer.Option("--no-branch", help="Checkout existing branch instead of creating new"),
    ] = False,
    no_context: Annotated[
        bool,
        typer.Option("--no-context", help="Don't copy CLAUDE.local.md and other context files"),
    ] = False,
) -> None:
    """Create a new worktree with AI context.

    Creates a git worktree for parallel AI-assisted development.
    Copies CLAUDE.local.md and initializes session tracking.

    Examples:
        rat new feature/auth
        rat new feature/api ../api-worktree
        rat new bugfix/issue-123 --base main
    """
    cwd = Path.cwd()

    if not (cwd / ".git").exists() and not (cwd / ".git").is_file():
        console.print("[red]Error:[/red] Not in a git repository")
        raise typer.Exit(1)

    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cwd,
        capture_output=True,
    )
    if result.returncode != 0:
        console.print("[red]Error:[/red] No commits yet")
        console.print("Git worktrees require at least one commit.")
        console.print("\n[dim]Run:[/dim] git add . && git commit -m 'Initial commit'")
        raise typer.Exit(1)

    try:
        worktree = asyncio.run(
            _create_worktree(
                cwd,
                branch,
                path,
                base,
                create_branch=not no_branch,
                copy_context=not no_context,
            )
        )

        console.print(
            Panel(
                f"[green]Worktree created[/green]\n\n"
                f"[bold]Branch:[/bold]  {worktree.branch}\n"
                f"[bold]Path:[/bold]    {worktree.path}\n\n"
                f"[dim]To switch to this worktree:[/dim]\n"
                f"  [cyan]cd {worktree.path}[/cyan]\n"
                f"  [dim]or[/dim]\n"
                f"  [cyan]rat switch {worktree.branch}[/cyan]",
                title="rat",
                border_style="green",
            )
        )

    except WorktreeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


async def _create_worktree(
    cwd: Path,
    branch: str,
    path: Optional[Path],
    base: str,
    create_branch: bool,
    copy_context: bool,
):
    """Async helper to create worktree."""
    manager = WorktreeManager(cwd)

    worktree = await manager.create(
        branch=branch,
        path=path,
        base=base,
        create_branch=create_branch,
        copy_context=copy_context,
    )

    tracker = SessionTracker(worktree.path)
    tracker.create(branch)

    return worktree
