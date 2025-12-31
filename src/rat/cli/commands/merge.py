"""Merge worktree branch to main with AI session context."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from rat.claude.reader import ClaudeReader
from rat.session.tracker import SessionTracker
from rat.worktree.manager import WorktreeManager

console = Console()


def merge(
    squash: Annotated[
        bool,
        typer.Option("--squash", "-s", help="Squash commits into one"),
    ] = True,
    delete: Annotated[
        bool,
        typer.Option("--delete", "-d", help="Delete worktree after merge"),
    ] = False,
    target: Annotated[
        str,
        typer.Option("--target", "-t", help="Target branch to merge into"),
    ] = "main",
) -> None:
    """Merge current branch to main with AI session context.

    Switches to main worktree, merges the current branch with
    session summary in the commit message.

    Examples:
        rat merge
        rat merge --squash
        rat merge --delete
    """
    cwd = Path.cwd()

    if not (cwd / ".git").exists() and not (cwd / ".git").is_file():
        console.print("[red]Error:[/red] Not in a git repository")
        raise typer.Exit(1)

    branch = _get_current_branch(cwd)
    if branch in ("main", "master"):
        console.print("[red]Error:[/red] Already on main/master branch")
        raise typer.Exit(1)

    tracker = SessionTracker(cwd)
    session = tracker.load()

    reader = ClaudeReader(cwd)
    since = session.created_at if session else None
    interactions = reader.read_all_interactions(since=since)

    commit_msg = _build_commit_message(session, interactions, branch)

    try:
        main_path = asyncio.run(_get_main_worktree(cwd))
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        console.print("[red]Error:[/red] Uncommitted changes in worktree")
        console.print("[dim]Commit or stash changes first[/dim]")
        raise typer.Exit(1)

    console.print(f"[yellow]Merging {branch} into {target}...[/yellow]")

    subprocess.run(["git", "fetch", "origin", branch], cwd=main_path, capture_output=True)

    result = subprocess.run(
        ["git", "checkout", target],
        cwd=main_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "checkout", "-b", target],
            cwd=main_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print(f"[red]Error:[/red] Cannot checkout {target}")
            raise typer.Exit(1)

    subprocess.run(["git", "pull", "--ff-only"], cwd=main_path, capture_output=True)

    if squash:
        result = subprocess.run(
            ["git", "merge", "--squash", branch],
            cwd=main_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print(f"[red]Merge conflict:[/red] {result.stderr}")
            console.print(f"[dim]Resolve conflicts in {main_path}[/dim]")
            raise typer.Exit(1)

        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=main_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print(f"[red]Error committing:[/red] {result.stderr}")
            raise typer.Exit(1)
    else:
        result = subprocess.run(
            ["git", "merge", branch, "-m", commit_msg],
            cwd=main_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print(f"[red]Merge conflict:[/red] {result.stderr}")
            console.print(f"[dim]Resolve conflicts in {main_path}[/dim]")
            raise typer.Exit(1)

    console.print(f"[green]Merged {branch} into {target}[/green]")

    if delete:
        console.print(f"[yellow]Removing worktree {branch}...[/yellow]")
        result = subprocess.run(
            ["git", "worktree", "remove", str(cwd)],
            cwd=main_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print(f"[yellow]Warning:[/yellow] Could not remove worktree: {result.stderr}")
        else:
            console.print(f"[green]Worktree removed[/green]")

        subprocess.run(
            ["git", "branch", "-d", branch],
            cwd=main_path,
            capture_output=True,
        )

    console.print(f"\n[dim]Main worktree: {main_path}[/dim]")


def _get_current_branch(cwd: Path) -> str:
    """Get current git branch."""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or "HEAD"


async def _get_main_worktree(cwd: Path) -> Path:
    """Get path to main worktree."""
    manager = WorktreeManager(cwd)
    return await manager.get_main_worktree()


def _build_commit_message(session, interactions, branch: str) -> str:
    """Build commit message with session context."""
    lines = []

    title = branch.replace("-", " ").replace("/", ": ").title()
    lines.append(title)
    lines.append("")

    if session and session.metrics:
        lines.append("AI Session:")
        lines.append(f"  Duration: {session.duration_display}")
        lines.append(f"  Interactions: {session.metrics.interactions}")
        lines.append(f"  Tokens: {session.metrics.total_tokens:,}")
        lines.append(f"  Cost: {session.cost_display}")
        lines.append("")

    if interactions:
        lines.append("Conversation:")
        lines.append("")

        for interaction in reversed(interactions[-20:]):
            role_prefix = "User:" if interaction.role == "user" else "Assistant:"

            content = interaction.content.strip()
            if not content:
                continue

            if len(content) > 500:
                content = content[:500] + "..."

            indented = "\n  ".join(content.split("\n"))
            lines.append(f"  {role_prefix}")
            lines.append(f"    {indented}")
            lines.append("")

    lines.append("---")
    lines.append("Generated by rat")

    return "\n".join(lines)
