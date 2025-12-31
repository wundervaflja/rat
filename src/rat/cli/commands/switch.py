"""Switch to a different worktree."""

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from rat.session.tracker import SessionTracker
from rat.worktree.manager import WorktreeManager

console = Console()

# Marker file to track if we've shown the shell integration hint
_HINT_SHOWN_MARKER = Path.home() / ".rat_shell_hint_shown"


def _should_show_shell_hint() -> bool:
    """Check if we should show the shell integration hint."""
    if _HINT_SHOWN_MARKER.exists():
        return False

    # Check if shell integration is installed
    shell = os.environ.get("SHELL", "")
    home = Path.home()

    if "zsh" in shell:
        rc_file = home / ".zshrc"
    elif "bash" in shell:
        rc_file = home / ".bashrc"
        if not rc_file.exists():
            rc_file = home / ".bash_profile"
    else:
        return False

    if rc_file.exists():
        content = rc_file.read_text()
        if "rat shell init" in content or ">>> rat shell integration >>>" in content:
            return False

    return True


def _mark_hint_shown() -> None:
    """Mark that we've shown the hint."""
    _HINT_SHOWN_MARKER.touch()


def switch(
    branch: Annotated[
        Optional[str],
        typer.Argument(help="Branch name to switch to (uses fzf if not provided)"),
    ] = None,
    print_path: Annotated[
        bool,
        typer.Option("--print-path", "-p", help="Print path only (for shell integration)"),
    ] = False,
) -> None:
    """Switch to a different worktree.

    If no branch is specified and fzf is available, shows an
    interactive picker.

    For automatic directory changing, install shell integration:

        rat shell setup

    Or manually add to your shell config:

        eval "$(rat shell init)"

    Examples:
        rat switch feature/auth
        rat switch              # Interactive picker with fzf
    """
    cwd = Path.cwd()

    if not (cwd / ".git").exists() and not (cwd / ".git").is_file():
        if not print_path:
            console.print("[red]Error:[/red] Not in a git repository")
        raise typer.Exit(1)

    try:
        worktrees = asyncio.run(_get_worktrees(cwd))
    except Exception as e:
        if not print_path:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not worktrees:
        if not print_path:
            console.print("[yellow]No worktrees found[/yellow]")
        raise typer.Exit(1)

    if branch is None:
        branch = _select_with_fzf(worktrees)
        if branch is None:
            if not print_path:
                console.print("[yellow]No worktree selected[/yellow]")
            raise typer.Exit(0)

    target = None
    for wt in worktrees:
        if wt.branch == branch or str(wt.path) == branch:
            target = wt
            break

    if target is None:
        if not print_path:
            console.print(f"[red]Error:[/red] Worktree not found: {branch}")
        raise typer.Exit(1)

    if print_path:
        print(target.path)
    else:
        tracker = SessionTracker(target.path)
        session = tracker.load()

        console.print(f"\n[bold]Switching to:[/bold] {target.branch}")
        console.print(f"[bold]Path:[/bold] {target.path}")

        if session:
            console.print(f"[bold]Status:[/bold] {session.status.value}")
            if session.metrics.interactions > 0:
                console.print(
                    f"[bold]Session:[/bold] {session.metrics.interactions} interactions, "
                    f"{session.cost_display}"
                )

        console.print(f"\n[dim]Run: cd {target.path}[/dim]")

        # Show shell integration hint on first use
        if _should_show_shell_hint():
            console.print()
            console.print("[yellow]Tip:[/yellow] Enable automatic directory switching:")
            console.print("  [cyan]rat shell setup[/cyan]")
            console.print('[dim]Or add to your shell config: eval "$(rat shell init)"[/dim]')
            _mark_hint_shown()


async def _get_worktrees(cwd: Path):
    """Get all worktrees."""
    manager = WorktreeManager(cwd)
    return await manager.list()


def _select_with_fzf(worktrees) -> Optional[str]:
    """Use fzf to select a worktree interactively."""

    try:
        subprocess.run(
            ["which", "fzf"],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("[yellow]fzf not found. Please specify a branch.[/yellow]")
        console.print("[dim]Install fzf for interactive selection.[/dim]")
        return None

    lines = []
    for wt in worktrees:
        marker = "* " if wt.is_main else "  "
        lines.append(f"{marker}{wt.branch}\t{wt.path}")

    try:
        result = subprocess.run(
            ["fzf", "--ansi", "--reverse", "--height=40%"],
            input="\n".join(lines),
            capture_output=True,
            text=True,
        )

        if result.returncode == 0 and result.stdout.strip():
            selection = result.stdout.strip()

            parts = selection.lstrip("* ").split("\t")
            return parts[0].strip()

    except subprocess.CalledProcessError:
        pass
    except FileNotFoundError:
        pass

    return None
