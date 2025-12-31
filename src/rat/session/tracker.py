"""Session tracking for worktree-based AI development.

Manages session state per worktree, reading metrics from Claude's
JSONL files on-demand.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from rat.claude.reader import ClaudeReader, SessionMetrics


class SessionStatus(str, Enum):
    """Status of a worktree session."""

    READY = "ready"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


def generate_session_id() -> str:
    """Generate a unique session ID."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique = uuid4().hex[:6]
    return f"sess_{timestamp}_{unique}"


@dataclass
class WorktreeSession:
    """Session state for a worktree."""

    id: Optional[str]
    status: SessionStatus
    branch: str
    worktree_path: Path
    created_at: datetime
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    plan_file: Optional[Path] = None
    metrics: SessionMetrics = field(default_factory=SessionMetrics)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "status": self.status.value,
            "branch": self.branch,
            "worktree_path": str(self.worktree_path),
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "plan_file": str(self.plan_file) if self.plan_file else None,
            "metrics": self.metrics.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorktreeSession":
        """Create from dictionary."""
        metrics_data = data.get("metrics", {})
        metrics = SessionMetrics(
            interactions=metrics_data.get("interactions", 0),
            tokens_in=metrics_data.get("tokens_in", 0),
            tokens_out=metrics_data.get("tokens_out", 0),
            cost_usd=metrics_data.get("cost_usd", 0.0),
            first_timestamp=(
                datetime.fromisoformat(metrics_data["first_timestamp"])
                if metrics_data.get("first_timestamp")
                else None
            ),
            last_timestamp=(
                datetime.fromisoformat(metrics_data["last_timestamp"])
                if metrics_data.get("last_timestamp")
                else None
            ),
            models_used=set(metrics_data.get("models_used", [])),
        )

        return cls(
            id=data.get("id"),
            status=SessionStatus(data.get("status", "ready")),
            branch=data.get("branch", ""),
            worktree_path=Path(data.get("worktree_path", ".")),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.utcnow()
            ),
            started_at=(
                datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
            ),
            stopped_at=(
                datetime.fromisoformat(data["stopped_at"]) if data.get("stopped_at") else None
            ),
            plan_file=Path(data["plan_file"]) if data.get("plan_file") else None,
            metrics=metrics,
        )

    @property
    def duration_display(self) -> str:
        """Human-readable duration."""
        seconds = self.metrics.duration_seconds

        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"

    @property
    def cost_display(self) -> str:
        """Human-readable cost."""
        return f"${self.metrics.cost_usd:.2f}"


class SessionTracker:
    """Track and manage sessions per worktree."""

    SESSION_FILE = ".rat/session.json"
    SESSION_ID_FILE = ".claude-session-id"

    def __init__(self, worktree_path: Path):
        """Initialize session tracker.

        Args:
            worktree_path: Path to the worktree directory.
        """
        self.worktree_path = worktree_path.resolve()
        self._claude_reader: Optional[ClaudeReader] = None

    @property
    def session_file(self) -> Path:
        """Path to session state file."""
        return self.worktree_path / self.SESSION_FILE

    @property
    def session_id_file(self) -> Path:
        """Path to .claude-session-id file."""
        return self.worktree_path / self.SESSION_ID_FILE

    @property
    def claude_reader(self) -> ClaudeReader:
        """Get or create Claude reader."""
        if self._claude_reader is None:
            self._claude_reader = ClaudeReader(self.worktree_path)
        return self._claude_reader

    def has_session(self) -> bool:
        """Check if a session exists for this worktree."""
        return self.session_file.exists() or self.session_id_file.exists()

    def load(self) -> Optional[WorktreeSession]:
        """Load session state from disk.

        Returns:
            WorktreeSession or None if no session exists.
        """
        if not self.session_file.exists():
            return None

        try:
            data = json.loads(self.session_file.read_text())
            session = WorktreeSession.from_dict(data)

            self._update_metrics(session)

            self._update_status(session)

            return session
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return None

    def save(self, session: WorktreeSession) -> None:
        """Save session state to disk.

        Args:
            session: Session to save.
        """

        self.session_file.parent.mkdir(parents=True, exist_ok=True)

        self.session_file.write_text(json.dumps(session.to_dict(), indent=2))

        if session.id:
            self.session_id_file.write_text(session.id)

    def create(self, branch: str, plan_file: Optional[Path] = None) -> WorktreeSession:
        """Create a new session for this worktree.

        Args:
            branch: Git branch name.
            plan_file: Optional path to plan file.

        Returns:
            New WorktreeSession.
        """
        session = WorktreeSession(
            id=None,
            status=SessionStatus.READY,
            branch=branch,
            worktree_path=self.worktree_path,
            created_at=datetime.utcnow(),
            plan_file=plan_file,
        )
        self.save(session)
        return session

    def start(self, session: Optional[WorktreeSession] = None) -> WorktreeSession:
        """Start or resume a session.

        Args:
            session: Existing session to resume, or None to create new.

        Returns:
            Started session.
        """
        if session is None:
            session = self.load()

        if session is None:
            raise ValueError("No session exists. Create one first with 'rat new'.")

        if session.id is None:
            session.id = generate_session_id()

        session.status = SessionStatus.ACTIVE
        session.started_at = session.started_at or datetime.utcnow()

        self.save(session)
        return session

    def pause(self, session: Optional[WorktreeSession] = None) -> WorktreeSession:
        """Pause the current session.

        Args:
            session: Session to pause, or None to load current.

        Returns:
            Paused session.
        """
        if session is None:
            session = self.load()

        if session is None:
            raise ValueError("No session exists.")

        self._update_metrics(session)

        session.status = SessionStatus.PAUSED
        self.save(session)
        return session

    def stop(self, session: Optional[WorktreeSession] = None) -> WorktreeSession:
        """Stop the current session.

        Args:
            session: Session to stop, or None to load current.

        Returns:
            Stopped session.
        """
        if session is None:
            session = self.load()

        if session is None:
            raise ValueError("No session exists.")

        self._update_metrics(session)

        session.status = SessionStatus.STOPPED
        session.stopped_at = datetime.utcnow()
        self.save(session)
        return session

    def _update_metrics(self, session: WorktreeSession) -> None:
        """Update session metrics from Claude data.

        Args:
            session: Session to update.
        """
        if not self.claude_reader.has_claude_data:
            return

        since = session.created_at if session.created_at else None
        metrics = self.claude_reader.calculate_metrics(since=since)

        session.metrics = metrics

    def _update_status(self, session: WorktreeSession) -> None:
        """Update session status based on Claude activity.

        Args:
            session: Session to update.
        """
        if session.status == SessionStatus.STOPPED:
            return

        if self.claude_reader.is_claude_running():
            if self.claude_reader.get_recent_activity(minutes=5):
                session.status = SessionStatus.ACTIVE
            else:
                if session.status == SessionStatus.ACTIVE:
                    session.status = SessionStatus.PAUSED
        else:
            if session.status == SessionStatus.ACTIVE:
                session.status = SessionStatus.PAUSED

    def get_or_create(self, branch: str) -> WorktreeSession:
        """Get existing session or create new one.

        Args:
            branch: Git branch name.

        Returns:
            Session (existing or new).
        """
        session = self.load()
        if session is None:
            session = self.create(branch)
        return session

    def link_plan(self, plan_path: Path) -> None:
        """Link a plan file to this worktree.

        Creates a .claude-plan symlink.

        Args:
            plan_path: Path to the plan file.
        """
        plan_link = self.worktree_path / ".claude-plan"

        if plan_link.exists() or plan_link.is_symlink():
            plan_link.unlink()

        plan_link.symlink_to(plan_path.resolve())

        session = self.load()
        if session:
            session.plan_file = plan_path
            self.save(session)

    def get_plan_file(self) -> Optional[Path]:
        """Get the linked plan file.

        Returns:
            Path to plan file or None.
        """
        plan_link = self.worktree_path / ".claude-plan"

        if plan_link.is_symlink() and plan_link.exists():
            return plan_link.resolve()

        session = self.load()
        if session and session.plan_file:
            return session.plan_file

        return None
