"""Create PR with AI session context."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from rat.claude.reader import ClaudeReader
from rat.session.tracker import SessionTracker

console = Console()


def pr(
    title: Annotated[
        Optional[str],
        typer.Option("--title", "-t", help="PR title (defaults to branch name)"),
    ] = None,
    draft: Annotated[
        bool,
        typer.Option("--draft", "-d", help="Create as draft PR"),
    ] = False,
    push: Annotated[
        bool,
        typer.Option("--push/--no-push", help="Push branch before creating PR"),
    ] = True,
) -> None:
    """Create a PR with AI session context.

    Pushes the current branch and creates a PR with session
    summary and interaction history in the description.

    Examples:
        rat pr
        rat pr --title "Add authentication"
        rat pr --draft
    """
    cwd = Path.cwd()

    if not (cwd / ".git").exists() and not (cwd / ".git").is_file():
        console.print("[red]Error:[/red] Not in a git repository")
        raise typer.Exit(1)

    if not _check_gh_cli():
        console.print("[red]Error:[/red] GitHub CLI (gh) not found")
        console.print("[dim]Install: https://cli.github.com/[/dim]")
        raise typer.Exit(1)

    branch = _get_current_branch(cwd)
    if branch in ("main", "master"):
        console.print("[red]Error:[/red] Cannot create PR from main/master branch")
        raise typer.Exit(1)

    tracker = SessionTracker(cwd)
    session = tracker.load()

    reader = ClaudeReader(cwd)
    since = session.created_at if session else None
    interactions = reader.read_all_interactions(since=since)

    pr_body = _build_pr_body(session, interactions, branch)

    if push:
        console.print(f"[yellow]Pushing {branch}...[/yellow]")
        result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print(f"[red]Error pushing:[/red] {result.stderr}")
            raise typer.Exit(1)

    pr_title = title or branch.replace("-", " ").replace("/", ": ").title()

    console.print(f"[yellow]Creating PR...[/yellow]")

    cmd = ["gh", "pr", "create", "--title", pr_title, "--body", pr_body]
    if draft:
        cmd.append("--draft")

    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

    if result.returncode != 0:
        console.print(f"[red]Error creating PR:[/red] {result.stderr}")
        raise typer.Exit(1)

    pr_url = result.stdout.strip()
    console.print(f"[green]PR created:[/green] {pr_url}")


def _check_gh_cli() -> bool:
    """Check if gh CLI is installed."""
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _get_current_branch(cwd: Path) -> str:
    """Get current git branch."""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or "HEAD"


def _build_pr_body(session, interactions, branch: str) -> str:
    """Build PR description with session context."""
    lines = []

    lines.append("## Summary")
    lines.append("")
    lines.append(f"Branch: `{branch}`")
    lines.append("")

    if session and session.metrics:
        lines.append("## AI Session Metrics")
        lines.append("")
        lines.append(f"- **Duration**: {session.duration_display}")
        lines.append(f"- **Interactions**: {session.metrics.interactions}")
        lines.append(
            f"- **Tokens**: {session.metrics.total_tokens:,} ({session.metrics.tokens_in:,} in / {session.metrics.tokens_out:,} out)"
        )
        lines.append(f"- **Cost**: {session.cost_display}")
        if session.metrics.models_used:
            models = ", ".join(sorted(session.metrics.models_used))
            lines.append(f"- **Models**: {models}")
        lines.append("")

    if interactions:
        lines.append("## AI Conversation")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>Click to expand conversation history</summary>")
        lines.append("")

        for interaction in reversed(interactions[-50:]):
            role_emoji = "👤" if interaction.role == "user" else "🤖"
            role_label = "User" if interaction.role == "user" else "Assistant"

            lines.append(f"### {role_emoji} {role_label}")
            lines.append("")

            content = interaction.content.strip()
            if len(content) > 2000:
                content = content[:2000] + "\n\n*[truncated]*"

            if content:
                lines.append(content)
            else:
                lines.append("*[tool calls only]*")

            lines.append("")

            if interaction.tool_calls:
                lines.append("<details>")
                lines.append("<summary>Tool calls</summary>")
                lines.append("")
                for tc in interaction.tool_calls[:10]:
                    lines.append(f"- `{tc.get('name', 'unknown')}`")
                lines.append("")
                lines.append("</details>")
                lines.append("")

        lines.append("</details>")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by [rat](https://github.com/your/rat)*")

    return "\n".join(lines)
