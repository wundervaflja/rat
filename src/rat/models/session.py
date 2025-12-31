"""Session model for tracking work sessions."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field, field_validator


class SessionStatus(str, Enum):
    """Status of a tracking session."""

    ACTIVE = "active"
    STOPPED = "stopped"
    ERROR = "error"


def generate_session_id() -> str:
    """Generate a unique session ID."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique = uuid4().hex[:6]
    return f"sess_{timestamp}_{unique}"


class Session(BaseModel):
    """Represents a rat tracking session.

    A session tracks work from `start` to `stop`, grouping all
    AI interactions and commits during that period.
    """

    id: str = Field(default_factory=generate_session_id)
    status: SessionStatus = SessionStatus.ACTIVE
    started_at: datetime = Field(default_factory=datetime.utcnow)
    stopped_at: Optional[datetime] = None
    project_root: Path
    branch: str = Field(..., min_length=1, max_length=255)
    proxy_port: int = Field(default=8787, ge=1024, le=65535)

    total_interactions: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost: float = 0.0
    total_commits: int = 0

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("project_root", mode="before")
    @classmethod
    def validate_project_root(cls, v: Path | str) -> Path:
        """Validate that project root exists and is a git repository."""
        path = Path(v) if isinstance(v, str) else v
        if not path.exists():
            raise ValueError(f"Project root does not exist: {path}")
        if not (path / ".git").exists():
            raise ValueError(f"Not a git repository: {path}")
        return path

    @field_validator("id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        """Validate session ID format."""
        if not v.startswith("sess_"):
            raise ValueError("Session ID must start with 'sess_'")
        return v

    @computed_field
    @property
    def duration_seconds(self) -> Optional[int]:
        """Calculate session duration in seconds."""
        if self.stopped_at:
            return int((self.stopped_at - self.started_at).total_seconds())
        return int((datetime.utcnow() - self.started_at).total_seconds())

    def stop(self) -> None:
        """Mark the session as stopped."""
        self.status = SessionStatus.STOPPED
        self.stopped_at = datetime.utcnow()

    def to_db_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "project_root": str(self.project_root),
            "branch": self.branch,
            "proxy_port": self.proxy_port,
            "total_interactions": self.total_interactions,
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_cost": self.total_cost,
            "total_commits": self.total_commits,
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "Session":
        """Create a Session from a database row."""
        return cls(
            id=row["id"],
            status=SessionStatus(row["status"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            stopped_at=(datetime.fromisoformat(row["stopped_at"]) if row["stopped_at"] else None),
            project_root=Path(row["project_root"]),
            branch=row["branch"],
            proxy_port=row["proxy_port"],
            total_interactions=row["total_interactions"],
            total_tokens_in=row["total_tokens_in"],
            total_tokens_out=row["total_tokens_out"],
            total_cost=row["total_cost"],
            total_commits=row["total_commits"],
        )
