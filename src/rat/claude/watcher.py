"""Watch Claude Code conversation files for new interactions."""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


@dataclass
class ClaudeInteraction:
    """Parsed interaction from Claude conversation file."""

    id: str
    session_id: str
    timestamp: datetime
    role: str
    content: str
    model: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls: list = None
    thinking: Optional[str] = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


def get_claude_project_path(project_root: Path) -> Optional[Path]:
    """Get Claude's project directory for the given project root.

    Claude stores projects with path-based names like:
    -Users-gorysko-repo-rat/

    Args:
        project_root: The project root directory.

    Returns:
        Path to Claude's project directory or None if not found.
    """
    claude_projects = Path.home() / ".claude" / "projects"
    if not claude_projects.exists():
        return None

    project_name = str(project_root).replace("/", "-")
    if project_name.startswith("-"):
        pass
    else:
        project_name = "-" + project_name

    claude_project = claude_projects / project_name
    if claude_project.exists():
        return claude_project

    alt_name = str(project_root).lstrip("/").replace("/", "-")
    alt_name = "-" + alt_name
    alt_project = claude_projects / alt_name
    if alt_project.exists():
        return alt_project

    return None


def parse_jsonl_line(line: str) -> Optional[dict]:
    """Parse a single JSONL line.

    Args:
        line: JSON string.

    Returns:
        Parsed dict or None if invalid.
    """
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None


def extract_interaction(entry: dict) -> Optional[ClaudeInteraction]:
    """Extract interaction data from a Claude JSONL entry.

    Args:
        entry: Parsed JSONL entry.

    Returns:
        ClaudeInteraction or None if not a user/assistant message.
    """
    entry_type = entry.get("type")
    if entry_type not in ("user", "assistant"):
        return None

    message = entry.get("message", {})
    role = message.get("role", entry_type)

    content_raw = message.get("content", "")
    if isinstance(content_raw, str):
        content = content_raw
        tool_calls = []
        thinking = None
    elif isinstance(content_raw, list):
        text_parts = []
        tool_calls = []
        thinking = None

        for block in content_raw:
            if isinstance(block, dict):
                block_type = block.get("type")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.get("id"),
                            "name": block.get("name"),
                            "input": block.get("input"),
                        }
                    )
                elif block_type == "thinking":
                    thinking = block.get("thinking", "")
            elif isinstance(block, str):
                text_parts.append(block)

        content = "\n".join(text_parts)
    else:
        content = str(content_raw)
        tool_calls = []
        thinking = None

    usage = message.get("usage", {})
    tokens_in = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
    tokens_out = usage.get("output_tokens", 0)

    timestamp_str = entry.get("timestamp", "")
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        timestamp = datetime.utcnow()

    return ClaudeInteraction(
        id=entry.get("uuid", ""),
        session_id=entry.get("sessionId", ""),
        timestamp=timestamp,
        role=role,
        content=content,
        model=message.get("model"),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tool_calls=tool_calls,
        thinking=thinking,
    )


def parse_conversation_file(file_path: Path) -> list[ClaudeInteraction]:
    """Parse all interactions from a Claude conversation file.

    Args:
        file_path: Path to .jsonl file.

    Returns:
        List of interactions.
    """
    interactions = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = parse_jsonl_line(line)
                if entry:
                    interaction = extract_interaction(entry)
                    if interaction:
                        interactions.append(interaction)
    except Exception as e:
        logger.error(f"Error parsing {file_path}: {e}")

    return interactions


def get_latest_interaction(file_path: Path) -> Optional[ClaudeInteraction]:
    """Get the most recent interaction from a conversation file.

    Reads from the end of file for efficiency.

    Args:
        file_path: Path to .jsonl file.

    Returns:
        Latest interaction or None.
    """
    try:
        with open(file_path, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()

            if file_size == 0:
                return None

            read_size = min(50000, file_size)
            f.seek(file_size - read_size)
            content = f.read().decode("utf-8", errors="ignore")

        lines = content.strip().split("\n")
        for line in reversed(lines):
            if not line.strip():
                continue
            entry = parse_jsonl_line(line)
            if entry:
                interaction = extract_interaction(entry)
                if interaction:
                    return interaction

    except Exception as e:
        logger.error(f"Error reading latest from {file_path}: {e}")

    return None


class ClaudeConversationHandler(FileSystemEventHandler):
    """Handle Claude conversation file changes."""

    def __init__(
        self,
        callback: Callable[[ClaudeInteraction], None],
        loop: asyncio.AbstractEventLoop,
    ):
        """Initialize handler.

        Args:
            callback: Async function to call with new interactions.
            loop: Event loop for async callbacks.
        """
        self.callback = callback
        self.loop = loop
        self._file_positions: dict[str, int] = {}
        self._debounce_tasks: dict[str, asyncio.Task] = {}
        self._debounce_ms = 500

    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if not file_path.suffix == ".jsonl":
            return

        if file_path.name.startswith("agent-"):
            return

        self._schedule_process(file_path)

    def _schedule_process(self, file_path: Path):
        """Schedule processing with debounce."""
        key = str(file_path)

        if key in self._debounce_tasks:
            self._debounce_tasks[key].cancel()

        async def delayed_process():
            await asyncio.sleep(self._debounce_ms / 1000)
            await self._process_file(file_path)

        self._debounce_tasks[key] = self.loop.create_task(delayed_process())

    async def _process_file(self, file_path: Path):
        """Process new entries in a conversation file."""
        key = str(file_path)
        last_pos = self._file_positions.get(key, 0)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                f.seek(last_pos)
                new_content = f.read()
                new_pos = f.tell()

            if new_content:
                for line in new_content.strip().split("\n"):
                    if not line.strip():
                        continue
                    entry = parse_jsonl_line(line)
                    if entry:
                        interaction = extract_interaction(entry)
                        if interaction:
                            if asyncio.iscoroutinefunction(self.callback):
                                await self.callback(interaction)
                            else:
                                self.callback(interaction)

            self._file_positions[key] = new_pos

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")


class ClaudeWatcher:
    """Watch Claude conversation directory for new interactions."""

    def __init__(
        self,
        project_root: Path,
        callback: Callable[[ClaudeInteraction], None],
    ):
        """Initialize watcher.

        Args:
            project_root: Project root directory.
            callback: Function to call with new interactions.
        """
        self.project_root = project_root
        self.callback = callback
        self.claude_path = get_claude_project_path(project_root)
        self._observer: Optional[Observer] = None
        self._handler: Optional[ClaudeConversationHandler] = None

    def start(self, loop: asyncio.AbstractEventLoop) -> bool:
        """Start watching Claude conversations.

        Args:
            loop: Event loop for async callbacks.

        Returns:
            True if started successfully.
        """
        if not self.claude_path:
            logger.warning(f"No Claude project found for {self.project_root}")
            return False

        self._handler = ClaudeConversationHandler(self.callback, loop)
        self._observer = Observer()
        self._observer.schedule(
            self._handler,
            str(self.claude_path),
            recursive=False,
        )
        self._observer.start()

        logger.info(f"Watching Claude conversations at {self.claude_path}")
        return True

    def stop(self):
        """Stop watching."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

    @property
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._observer is not None and self._observer.is_alive()
