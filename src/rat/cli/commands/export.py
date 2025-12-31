"""Export AI conversation to file."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from rat.claude.reader import ClaudeReader
from rat.session.tracker import SessionTracker

console = Console()


def export(
    format: Annotated[
        str,
        typer.Argument(help="Export format: md or html"),
    ] = "md",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path"),
    ] = None,
    include_tools: Annotated[
        bool,
        typer.Option("--tools", "-t", help="Include tool calls"),
    ] = False,
    include_thinking: Annotated[
        bool,
        typer.Option("--thinking", help="Include thinking blocks"),
    ] = False,
) -> None:
    """Export AI conversation to markdown or HTML.

    Exports the full conversation history including prompts
    and responses.

    Examples:
        rat export md
        rat export html -o conversation.html
        rat export md --tools --thinking
    """
    cwd = Path.cwd()

    if format not in ("md", "html"):
        console.print(f"[red]Error:[/red] Invalid format '{format}'. Use 'md' or 'html'")
        raise typer.Exit(1)


    tracker = SessionTracker(cwd)
    session = tracker.load()


    reader = ClaudeReader(cwd)
    since = session.created_at if session else None
    interactions = reader.read_all_interactions(since=since)

    if not interactions:
        console.print("[yellow]No interactions found[/yellow]")
        raise typer.Exit(0)


    if format == "md":
        content = _export_markdown(session, interactions, include_tools, include_thinking)
        ext = "md"
    else:
        content = _export_html(session, interactions, include_tools, include_thinking)
        ext = "html"


    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        branch = session.branch if session else "session"
        safe_branch = branch.replace("/", "-")
        output = cwd / f"conversation_{safe_branch}_{timestamp}.{ext}"


    output.write_text(content)
    console.print(f"[green]Exported to:[/green] {output}")


def _export_markdown(session, interactions, include_tools: bool, include_thinking: bool) -> str:
    """Export conversation to Markdown."""
    lines = []


    lines.append("# AI Conversation Export")
    lines.append("")
    lines.append(f"**Exported**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")


    if session:
        lines.append("## Session Info")
        lines.append("")
        lines.append(f"- **Branch**: {session.branch}")
        lines.append(f"- **Duration**: {session.duration_display}")
        lines.append(f"- **Interactions**: {session.metrics.interactions}")
        lines.append(f"- **Tokens**: {session.metrics.total_tokens:,} ({session.metrics.tokens_in:,} in / {session.metrics.tokens_out:,} out)")
        if session.metrics.models_used:
            lines.append(f"- **Models**: {', '.join(sorted(session.metrics.models_used))}")
        lines.append("")


    lines.append("## Conversation")
    lines.append("")

    for interaction in reversed(interactions):
        content = interaction.content.strip()
        has_tools = bool(interaction.tool_calls)
        has_thinking = bool(interaction.thinking)


        if not content and not (include_tools and has_tools) and not (include_thinking and has_thinking):
            continue

        timestamp = interaction.timestamp.strftime("%Y-%m-%d %H:%M:%S")

        if interaction.role == "user":
            lines.append("### 👤 User")
            lines.append(f"*{timestamp}*")
            lines.append("")
        else:
            model = interaction.model or "unknown"
            lines.append(f"### 🤖 Assistant ({model})")
            lines.append(f"*{timestamp}* - {interaction.tokens_in:,} in / {interaction.tokens_out:,} out")
            lines.append("")


        if include_thinking and interaction.thinking:
            lines.append("<details>")
            lines.append("<summary>Thinking</summary>")
            lines.append("")
            lines.append("```")
            lines.append(interaction.thinking)
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")


        if content:
            lines.append(content)
            lines.append("")


        if include_tools and interaction.tool_calls:
            lines.append("<details>")
            lines.append("<summary>Tool Calls</summary>")
            lines.append("")
            for tc in interaction.tool_calls:
                name = tc.get("name", "unknown")
                lines.append(f"**{name}**")
                lines.append("```json")
                import json
                lines.append(json.dumps(tc.get("input", {}), indent=2))
                lines.append("```")
                lines.append("")
            lines.append("</details>")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _export_html(session, interactions, include_tools: bool, include_thinking: bool) -> str:
    """Export conversation to HTML."""
    import html

    parts = []


    parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Conversation Export</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }
        h1 { color: #1a1a1a; border-bottom: 2px solid #ddd; padding-bottom: 10px; }
        .session-info {
            background: #fff;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .session-info h2 { margin-top: 0; }
        .session-info ul { list-style: none; padding: 0; margin: 0; }
        .session-info li { padding: 5px 0; }
        .message {
            background: #fff;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 15px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .message.user { border-left: 4px solid #007bff; }
        .message.assistant { border-left: 4px solid #28a745; }
        .message-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
        }
        .message-role { font-weight: bold; font-size: 1.1em; }
        .message-meta { color: #666; font-size: 0.85em; }
        .message-content { white-space: pre-wrap; line-height: 1.6; }
        .message-content code {
            background: #f0f0f0;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'SF Mono', Consolas, monospace;
        }
        .message-content pre {
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 15px;
            border-radius: 6px;
            overflow-x: auto;
        }
        .message-content pre code { background: none; padding: 0; }
        details {
            margin-top: 10px;
            padding: 10px;
            background: #f9f9f9;
            border-radius: 4px;
        }
        details summary {
            cursor: pointer;
            font-weight: 500;
            color: #555;
        }
        .thinking { background: #fff8e1; }
        .tools { background: #e3f2fd; }
    </style>
</head>
<body>
    <h1>AI Conversation Export</h1>
""")


    if session:
        parts.append(f"""
    <div class="session-info">
        <h2>Session Info</h2>
        <ul>
            <li><strong>Branch:</strong> {html.escape(session.branch)}</li>
            <li><strong>Duration:</strong> {session.duration_display}</li>
            <li><strong>Interactions:</strong> {session.metrics.interactions}</li>
            <li><strong>Tokens:</strong> {session.metrics.total_tokens:,} ({session.metrics.tokens_in:,} in / {session.metrics.tokens_out:,} out)</li>
        </ul>
    </div>
""")

    parts.append("    <h2>Conversation</h2>\n")


    for interaction in reversed(interactions):
        content = interaction.content.strip()
        has_tools = bool(interaction.tool_calls)
        has_thinking = bool(interaction.thinking)


        if not content and not (include_tools and has_tools) and not (include_thinking and has_thinking):
            continue

        timestamp = interaction.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        role_class = "user" if interaction.role == "user" else "assistant"

        if interaction.role == "user":
            role_label = "User"
            meta = timestamp
        else:
            model = interaction.model or "unknown"
            role_label = f"Assistant ({html.escape(model)})"
            meta = f"{timestamp} — {interaction.tokens_in:,} in / {interaction.tokens_out:,} out"

        parts.append(f"""    <div class="message {role_class}">
        <div class="message-header">
            <span class="message-role">{role_label}</span>
            <span class="message-meta">{meta}</span>
        </div>
""")


        if include_thinking and interaction.thinking:
            thinking_escaped = html.escape(interaction.thinking)
            parts.append(f"""        <details class="thinking">
            <summary>Thinking</summary>
            <pre><code>{thinking_escaped}</code></pre>
        </details>
""")


        content = interaction.content.strip()
        if content:

            content_escaped = html.escape(content)

            import re
            content_escaped = re.sub(
                r'```(\w*)\n(.*?)```',
                r'<pre><code>\2</code></pre>',
                content_escaped,
                flags=re.DOTALL
            )

            content_escaped = re.sub(r'`([^`]+)`', r'<code>\1</code>', content_escaped)

            parts.append(f"""        <div class="message-content">{content_escaped}</div>
""")


        if include_tools and interaction.tool_calls:
            parts.append("""        <details class="tools">
            <summary>Tool Calls</summary>
""")
            for tc in interaction.tool_calls:
                import json
                name = html.escape(tc.get("name", "unknown"))
                input_json = html.escape(json.dumps(tc.get("input", {}), indent=2))
                parts.append(f"""            <p><strong>{name}</strong></p>
            <pre><code>{input_json}</code></pre>
""")
            parts.append("        </details>\n")

        parts.append("    </div>\n")


    parts.append(f"""
    <footer style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; text-align: center;">
        Exported on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by rat
    </footer>
</body>
</html>
""")

    return "".join(parts)
