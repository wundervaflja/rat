"""Shell integration for rat."""

import os
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()

MARKER_START = "# >>> rat shell integration >>>"
MARKER_END = "# <<< rat shell integration <<<"

SHELL_FUNCTIONS = {
    "bash": """
rat() {
    if [[ "$1" == "switch" ]]; then
        local dir=$(command rat switch --print-path "${@:2}")
        if [[ -n "$dir" && -d "$dir" ]]; then
            cd "$dir"
        else
            return 1
        fi
    else
        command rat "$@"
    fi
}
""",
    "zsh": """
rat() {
    if [[ "$1" == "switch" ]]; then
        local dir=$(command rat switch --print-path "${@:2}")
        if [[ -n "$dir" && -d "$dir" ]]; then
            cd "$dir"
        else
            return 1
        fi
    else
        command rat "$@"
    fi
}
""",
    "fish": """
function rat
    if test "$argv[1]" = "switch"
        set -l dir (command rat switch --print-path $argv[2..])
        if test -n "$dir" -a -d "$dir"
            cd "$dir"
        else
            return 1
        end
    else
        command rat $argv
    end
end
""",
}

RC_FILES = {
    "bash": [".bashrc", ".bash_profile"],
    "zsh": [".zshrc"],
    "fish": [".config/fish/config.fish"],
}


def _detect_shell() -> Optional[str]:
    """Detect current shell type."""
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return "zsh"
    elif "bash" in shell:
        return "bash"
    elif "fish" in shell:
        return "fish"
    return None


def _get_rc_file(shell_type: str) -> Optional[Path]:
    """Get the appropriate rc file for the shell."""
    home = Path.home()
    for rc in RC_FILES.get(shell_type, []):
        rc_path = home / rc
        if rc_path.exists():
            return rc_path
    candidates = RC_FILES.get(shell_type)
    if candidates:
        return home / candidates[0]
    return None


def _is_installed(rc_file: Path) -> bool:
    """Check if shell integration is already installed."""
    if not rc_file.exists():
        return False
    content = rc_file.read_text()
    return MARKER_START in content


def shell_init(
    shell: Annotated[
        Optional[str],
        typer.Argument(help="Shell type: bash, zsh, fish (auto-detected if omitted)"),
    ] = None,
) -> None:
    """Output shell integration code.

    Add this to your shell config:

        eval "$(rat shell init)"

    Or specify shell explicitly:

        eval "$(rat shell init bash)"
    """
    if shell is None:
        shell = _detect_shell()
        if shell is None:
            console.print("[red]Error:[/red] Could not detect shell", err=True)
            console.print("Specify shell explicitly: rat shell init bash", err=True)
            raise typer.Exit(1)

    if shell not in SHELL_FUNCTIONS:
        console.print(f"[red]Error:[/red] Unsupported shell: {shell}", err=True)
        console.print(f"Supported: {', '.join(SHELL_FUNCTIONS.keys())}", err=True)
        raise typer.Exit(1)

    # Output to stdout (no formatting - this gets eval'd)
    print(SHELL_FUNCTIONS[shell].strip())


def shell_setup(
    shell: Annotated[
        Optional[str],
        typer.Option("--shell", "-s", help="Shell type (auto-detected if omitted)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing installation"),
    ] = False,
) -> None:
    """Install shell integration to your rc file.

    Automatically detects your shell and modifies the appropriate
    config file (.bashrc, .zshrc, or config.fish).

    Examples:
        rat shell setup
        rat shell setup --shell zsh
        rat shell setup --force
    """
    if shell is None:
        shell = _detect_shell()
        if shell is None:
            console.print("[red]Error:[/red] Could not detect shell")
            console.print("Specify shell: rat shell setup --shell bash")
            raise typer.Exit(1)

    if shell not in SHELL_FUNCTIONS:
        console.print(f"[red]Error:[/red] Unsupported shell: {shell}")
        console.print(f"Supported: {', '.join(SHELL_FUNCTIONS.keys())}")
        raise typer.Exit(1)

    rc_file = _get_rc_file(shell)
    if rc_file is None:
        console.print(f"[red]Error:[/red] Could not find rc file for {shell}")
        raise typer.Exit(1)

    if _is_installed(rc_file) and not force:
        console.print(f"[yellow]Already installed in {rc_file}[/yellow]")
        console.print("Use --force to reinstall")
        return

    if _is_installed(rc_file) and force:
        content = rc_file.read_text()
        start_idx = content.find(MARKER_START)
        end_idx = content.find(MARKER_END)
        if start_idx != -1 and end_idx != -1:
            content = content[:start_idx] + content[end_idx + len(MARKER_END) :]
            content = content.strip() + "\n"
            rc_file.write_text(content)

    integration = f"""
{MARKER_START}
eval "$(rat shell init {shell})"
{MARKER_END}
"""

    content = rc_file.read_text() if rc_file.exists() else ""
    if not content.endswith("\n"):
        content += "\n"
    content += integration

    rc_file.write_text(content)

    console.print(
        Panel(
            f"[green]Shell integration installed![/green]\n\n"
            f"[bold]File:[/bold] {rc_file}\n"
            f"[bold]Shell:[/bold] {shell}\n\n"
            f"[dim]Restart your shell or run:[/dim]\n"
            f"  [cyan]source {rc_file}[/cyan]",
            title="rat shell",
            border_style="green",
        )
    )


def shell_status() -> None:
    """Check shell integration status."""
    shell = _detect_shell()

    if shell is None:
        console.print("[yellow]Could not detect shell[/yellow]")
        return

    rc_file = _get_rc_file(shell)

    console.print(f"[bold]Shell:[/bold] {shell}")
    console.print(f"[bold]Config:[/bold] {rc_file}")

    if rc_file and _is_installed(rc_file):
        console.print("[bold]Status:[/bold] [green]Installed[/green]")
    else:
        console.print("[bold]Status:[/bold] [yellow]Not installed[/yellow]")
        console.print("\n[dim]Run 'rat shell setup' to install[/dim]")


def shell_uninstall() -> None:
    """Remove shell integration from rc file."""
    shell = _detect_shell()

    if shell is None:
        console.print("[red]Error:[/red] Could not detect shell")
        raise typer.Exit(1)

    rc_file = _get_rc_file(shell)

    if rc_file is None or not _is_installed(rc_file):
        console.print("[yellow]Shell integration not installed[/yellow]")
        return

    content = rc_file.read_text()
    start_idx = content.find(MARKER_START)
    end_idx = content.find(MARKER_END)

    if start_idx != -1 and end_idx != -1:
        content = content[:start_idx] + content[end_idx + len(MARKER_END) :]
        content = content.strip() + "\n"
        rc_file.write_text(content)

    console.print(f"[green]Removed shell integration from {rc_file}[/green]")
    console.print(f"[dim]Restart your shell or run: source {rc_file}[/dim]")
