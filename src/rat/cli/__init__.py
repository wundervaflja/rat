"""CLI module for rat."""

import typer
from rich.console import Console

from rat import __version__

RAT_LOGO = """
┏━┓┏━┓╺┳╸
┣┳┛┣━┫ ┃
╹┗╸╹ ╹ ╹
"""

console = Console()

app = typer.Typer(
    name="rat",
    help="AI worktree manager for parallel development.",
    add_completion=False,
    no_args_is_help=False,
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold cyan]{RAT_LOGO}[/bold cyan]")
        console.print(f"\n[dim]rat[/dim] v{__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """AI worktree manager for parallel development."""
    if ctx.invoked_subcommand is None:
        console.print(f"[bold cyan]{RAT_LOGO}[/bold cyan]\n")
        console.print(ctx.get_help())
        raise typer.Exit()


from rat.cli.commands import (
    export,
    init,
    merge,
    new,
    pr,
    remove,
    shell,
    status,
    switch,
)
from rat.cli.commands import (
    list as list_cmd,
)

app.command()(init.init)
app.command()(new.new)
app.command(name="list")(list_cmd.list_cmd)
app.command()(switch.switch)
app.command()(remove.remove)
app.command()(status.status)

app.command()(pr.pr)
app.command()(merge.merge)
app.command(name="export")(export.export)

# Shell integration subcommands
shell_app = typer.Typer(
    name="shell",
    help="Shell integration for directory switching.",
    no_args_is_help=True,
)
shell_app.command(name="init")(shell.shell_init)
shell_app.command(name="setup")(shell.shell_setup)
shell_app.command(name="status")(shell.shell_status)
shell_app.command(name="uninstall")(shell.shell_uninstall)
app.add_typer(shell_app)


if __name__ == "__main__":
    app()
