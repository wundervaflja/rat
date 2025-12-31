"""On-demand reader for Claude Code conversation files.

Reads Claude's JSONL files and calculates session metrics without
requiring a background daemon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rat.claude.watcher import (
    ClaudeInteraction,
    get_claude_project_path,
    get_latest_interaction,
    parse_conversation_file,
)


@dataclass
class SessionMetrics:
    """Aggregated metrics for a Claude session."""

    interactions: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    first_timestamp: Optional[datetime] = None
    last_timestamp: Optional[datetime] = None
    models_used: set = field(default_factory=set)

    @property
    def duration_seconds(self) -> int:
        """Calculate session duration in seconds."""
        if self.first_timestamp and self.last_timestamp:
            return int((self.last_timestamp - self.first_timestamp).total_seconds())
        return 0

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.tokens_in + self.tokens_out

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "interactions": self.interactions,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 4),
            "duration_seconds": self.duration_seconds,
            "first_timestamp": self.first_timestamp.isoformat() if self.first_timestamp else None,
            "last_timestamp": self.last_timestamp.isoformat() if self.last_timestamp else None,
            "models_used": list(self.models_used),
        }


class ClaudeReader:
    """Read Claude Code conversation files on-demand."""

    def __init__(self, project_root: Path):
        """Initialize reader.

        Args:
            project_root: Path to project root.
        """
        self.project_root = project_root
        self.claude_path = get_claude_project_path(project_root)

    @property
    def has_claude_data(self) -> bool:
        """Check if Claude data exists for this project."""
        return self.claude_path is not None and self.claude_path.exists()

    def get_conversation_files(self) -> list[Path]:
        """Get all conversation JSONL files.

        Returns:
            List of conversation file paths, sorted by modification time.
        """
        if not self.claude_path:
            return []

        files = []
        for f in self.claude_path.glob("*.jsonl"):
            if f.name.startswith("agent-"):
                continue
            files.append(f)

        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    def get_active_conversation(self) -> Optional[Path]:
        """Get the currently active conversation file.

        Returns the most recently modified JSONL file.
        """
        files = self.get_conversation_files()
        return files[0] if files else None

    def read_all_interactions(
        self,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[ClaudeInteraction]:
        """Read all interactions from all conversation files.

        Args:
            since: Only return interactions after this time.
            limit: Maximum number of interactions to return.

        Returns:
            List of interactions, newest first.
        """
        all_interactions = []

        for file_path in self.get_conversation_files():
            interactions = parse_conversation_file(file_path)

            if since:
                since_utc = since.replace(tzinfo=timezone.utc) if since.tzinfo is None else since
                filtered = []
                for i in interactions:
                    i_ts = i.timestamp
                    i_ts_utc = i_ts.replace(tzinfo=timezone.utc) if i_ts.tzinfo is None else i_ts
                    if i_ts_utc > since_utc:
                        filtered.append(i)
                interactions = filtered

            all_interactions.extend(interactions)

        all_interactions.sort(key=lambda i: i.timestamp, reverse=True)

        if limit:
            all_interactions = all_interactions[:limit]

        return all_interactions

    def calculate_metrics(
        self,
        since: Optional[datetime] = None,
        conversation_id: Optional[str] = None,
    ) -> SessionMetrics:
        """Calculate aggregated metrics from Claude conversations.

        Args:
            since: Only include interactions after this time.
            conversation_id: Limit to specific conversation file.

        Returns:
            Aggregated session metrics.
        """
        metrics = SessionMetrics()

        if conversation_id and self.claude_path:
            file_path = self.claude_path / f"{conversation_id}.jsonl"
            if file_path.exists():
                files = [file_path]
            else:
                files = []
        else:
            files = self.get_conversation_files()

        for file_path in files:
            interactions = parse_conversation_file(file_path)

            for interaction in interactions:
                if since:
                    since_utc = (
                        since.replace(tzinfo=timezone.utc) if since.tzinfo is None else since
                    )
                    int_ts = interaction.timestamp
                    int_ts_utc = (
                        int_ts.replace(tzinfo=timezone.utc) if int_ts.tzinfo is None else int_ts
                    )
                    if int_ts_utc <= since_utc:
                        continue

                if interaction.role == "assistant":
                    metrics.interactions += 1
                    metrics.tokens_in += interaction.tokens_in
                    metrics.tokens_out += interaction.tokens_out
                    if interaction.model:
                        metrics.models_used.add(interaction.model)

                if (
                    metrics.first_timestamp is None
                    or interaction.timestamp < metrics.first_timestamp
                ):
                    metrics.first_timestamp = interaction.timestamp
                if metrics.last_timestamp is None or interaction.timestamp > metrics.last_timestamp:
                    metrics.last_timestamp = interaction.timestamp

        return metrics

    def get_session_id_from_conversation(self) -> Optional[str]:
        """Get the current session ID from Claude's conversations.

        Returns:
            Session ID or None.
        """
        active = self.get_active_conversation()
        if not active:
            return None

        return active.stem

    def is_claude_running(self) -> bool:
        """Check if Claude Code is currently running for this project.

        Uses process checking to determine if Claude is active.
        """
        import subprocess

        try:
            result = subprocess.run(
                ["pgrep", "-f", "claude"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_recent_activity(self, minutes: int = 5) -> bool:
        """Check if there was recent Claude activity.

        Args:
            minutes: Number of minutes to check.

        Returns:
            True if there was activity within the time window.
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        for file_path in self.get_conversation_files():
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                continue

            latest = get_latest_interaction(file_path)
            if latest:
                latest_ts = latest.timestamp
                if latest_ts.tzinfo is None:
                    latest_ts = latest_ts.replace(tzinfo=timezone.utc)
                if latest_ts > cutoff:
                    return True

        return False
