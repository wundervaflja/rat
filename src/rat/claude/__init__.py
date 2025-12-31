"""Claude Code integration module."""

from rat.claude.watcher import (
    ClaudeInteraction,
    ClaudeWatcher,
    get_claude_project_path,
    get_latest_interaction,
    parse_conversation_file,
)

__all__ = [
    "ClaudeInteraction",
    "ClaudeWatcher",
    "get_claude_project_path",
    "parse_conversation_file",
    "get_latest_interaction",
]
