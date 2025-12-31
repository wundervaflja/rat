"""Remove a worktree."""

import asyncio
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from rat.worktree.manager import WorktreeError, WorktreeManager

console = Console()


def remove(
    branch: Annotated[
        Optional[str],
        typer.Argument(help="Branch name or path of worktree to remove"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force removal even if worktree is dirty"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Remove a worktree.

    Removes the git worktree and its directory. Use --force to
    remove worktrees with uncommitted changes.

    Examples:
        rat remove feature/auth
        rat remove --force feature/old
    """
    cwd = Path.cwd()

    if not (cwd / ".git").exists() and not (cwd / ".git").is_file():
        console.print("[red]Error:[/red] Not in a git repository")
        raise typer.Exit(1)

    if branch is None:
        console.print("[red]Error:[/red] Please specify a branch or path to remove")
        raise typer.Exit(1)

    try:
        worktrees = asyncio.run(_get_worktrees(cwd))
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    target = None
    for wt in worktrees:
        if wt.branch == branch or str(wt.path) == branch:
            target = wt
            break

    if target is None:
        console.print(f"[red]Error:[/red] Worktree not found: {branch}")
        raise typer.Exit(1)

    if target.is_main:
        console.print("[red]Error:[/red] Cannot remove main worktree")
        raise typer.Exit(1)

    if not yes:
        console.print(f"[yellow]Warning:[/yellow] This will remove:")
        console.print(f"  Branch: {target.branch}")
        console.print(f"  Path: {target.path}")
        console.print()

        confirm = typer.confirm("Are you sure you want to remove this worktree?")
        if not confirm:
            console.print("[dim]Cancelled[/dim]")
            raise typer.Exit(0)

    try:
        asyncio.run(_remove_worktree(cwd, branch, force))
        console.print(f"[green]Removed worktree:[/green] {branch}")
    except WorktreeError as e:
        console.print(f"[red]Error:[/red] {e}")
        if "uncommitted changes" in str(e).lower() or "dirty" in str(e).lower():
            console.print("[dim]Use --force to remove anyway[/dim]")
        raise typer.Exit(1)


async def _get_worktrees(cwd: Path):
    """Get all worktrees."""
    manager = WorktreeManager(cwd)
    return await manager.list()


async def _remove_worktree(cwd: Path, branch: str, force: bool):
    """Remove a worktree."""
    manager = WorktreeManager(cwd)
    await manager.remove(branch, force=force)
