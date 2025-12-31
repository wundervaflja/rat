"""Git worktree management for parallel AI development."""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


class WorktreeError(Exception):
    """Exception raised for worktree operation failures."""

    pass


@dataclass
class Worktree:
    """Represents a git worktree."""

    path: Path
    branch: str
    head: str
    is_main: bool = False
    is_bare: bool = False
    is_detached: bool = False
    prunable: Optional[str] = None

    @property
    def name(self) -> str:
        """Get worktree name (directory name)."""
        return self.path.name


class WorktreeManager:
    """Manages git worktrees for parallel AI development.

    Provides methods for creating, listing, switching, and removing
    worktrees with AI context preservation.
    """

    def __init__(self, repo_path: Path):
        """Initialize worktree manager.

        Args:
            repo_path: Path to any worktree in the repository.
        """
        self.repo_path = repo_path
        self._main_worktree: Optional[Path] = None

    async def _run_git(self, *args: str, cwd: Optional[Path] = None, check: bool = True) -> str:
        """Execute a git command and return output.

        Args:
            *args: Git command arguments.
            cwd: Working directory (defaults to repo_path).
            check: Whether to raise on non-zero exit.

        Returns:
            Command stdout.

        Raises:
            WorktreeError: If command fails and check is True.
        """
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=cwd or self.repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if check and proc.returncode != 0:
            raise WorktreeError(f"Git command failed: {stderr.decode().strip()}")

        return stdout.decode().strip()

    async def get_main_worktree(self) -> Path:
        """Get the path to the main worktree.

        Returns:
            Path to the main repository worktree.
        """
        if self._main_worktree:
            return self._main_worktree

        worktrees = await self.list()
        for wt in worktrees:
            if wt.is_main:
                self._main_worktree = wt.path
                return wt.path

        self._main_worktree = self.repo_path
        return self.repo_path

    async def list(self) -> list[Worktree]:
        """List all worktrees in the repository.

        Returns:
            List of Worktree objects.
        """
        output = await self._run_git("worktree", "list", "--porcelain")

        worktrees = []
        current: dict = {}

        for line in output.split("\n"):
            if not line:
                if current:
                    worktrees.append(self._parse_worktree(current))
                    current = {}
                continue

            if line.startswith("worktree "):
                current["path"] = line[9:]
            elif line.startswith("HEAD "):
                current["head"] = line[5:]
            elif line.startswith("branch "):
                current["branch"] = line[7:]
            elif line == "bare":
                current["bare"] = True
            elif line == "detached":
                current["detached"] = True
            elif line.startswith("prunable "):
                current["prunable"] = line[9:]

        if current:
            worktrees.append(self._parse_worktree(current))

        if worktrees:
            worktrees[0].is_main = True

        return worktrees

    def _parse_worktree(self, data: dict) -> Worktree:
        """Parse worktree data from git output."""
        path = Path(data.get("path", ""))
        branch = data.get("branch", "")

        if branch.startswith("refs/heads/"):
            branch = branch[11:]

        return Worktree(
            path=path,
            branch=branch or "HEAD",
            head=data.get("head", ""),
            is_bare=data.get("bare", False),
            is_detached=data.get("detached", False),
            prunable=data.get("prunable"),
        )

    async def create(
        self,
        branch: str,
        path: Optional[Path] = None,
        base: str = "HEAD",
        create_branch: bool = True,
        copy_context: bool = True,
    ) -> Worktree:
        """Create a new worktree with AI context.

        Args:
            branch: Branch name for the worktree.
            path: Path for the worktree (defaults to sibling directory).
            base: Base commit/branch to create from.
            create_branch: Create a new branch (vs checkout existing).
            copy_context: Copy CLAUDE.local.md and other context files.

        Returns:
            The created Worktree.

        Raises:
            WorktreeError: If worktree creation fails.
        """
        main_worktree = await self.get_main_worktree()

        if path is None:
            safe_name = branch.replace("/", "-")
            base_name = main_worktree.name
            path = main_worktree.parent / f"{base_name}.{safe_name}"

        path = path.resolve()

        args = ["worktree", "add"]
        if create_branch:
            args.extend(["-b", branch])
        args.append(str(path))
        if not create_branch:
            args.append(branch)
        else:
            args.append(base)

        try:
            await self._run_git(*args)
        except WorktreeError as e:
            # If branch already exists, retry without -b flag
            if "already exists" in str(e) and create_branch:
                args = ["worktree", "add", str(path), branch]
                await self._run_git(*args)
            else:
                raise

        if copy_context:
            await self._copy_context_files(main_worktree, path)

        await self._init_rat_dir(path, branch)

        worktrees = await self.list()
        for wt in worktrees:
            if wt.path == path:
                return wt

        head = await self._run_git("rev-parse", "HEAD", cwd=path)
        return Worktree(path=path, branch=branch, head=head)

    async def _copy_context_files(self, src: Path, dest: Path) -> None:
        """Copy AI context files to new worktree.

        Args:
            src: Source worktree path.
            dest: Destination worktree path.
        """
        context_files = [
            "CLAUDE.local.md",
            ".claude-plan",
        ]

        for filename in context_files:
            src_file = src / filename
            dest_file = dest / filename

            if src_file.exists():
                if src_file.is_symlink():
                    link_target = src_file.resolve()
                    if dest_file.exists():
                        dest_file.unlink()
                    dest_file.symlink_to(link_target)
                else:
                    shutil.copy2(src_file, dest_file)

    async def _init_rat_dir(self, worktree_path: Path, branch: str) -> None:
        """Initialize .rat directory in worktree.

        Args:
            worktree_path: Path to the worktree.
            branch: Branch name.
        """
        rat_dir = worktree_path / ".rat"
        rat_dir.mkdir(exist_ok=True)

        session_file = rat_dir / "session.json"
        if not session_file.exists():
            session_data = {
                "id": None,
                "status": "ready",
                "branch": branch,
                "worktree_path": str(worktree_path),
                "created_at": datetime.utcnow().isoformat(),
                "metrics": {
                    "duration_seconds": 0,
                    "interactions": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost_usd": 0.0,
                },
            }
            session_file.write_text(json.dumps(session_data, indent=2))

    async def remove(
        self,
        branch_or_path: str,
        force: bool = False,
    ) -> None:
        """Remove a worktree.

        Args:
            branch_or_path: Branch name or path to remove.
            force: Force removal even if dirty.

        Raises:
            WorktreeError: If removal fails.
        """

        worktrees = await self.list()
        target = None

        for wt in worktrees:
            if wt.branch == branch_or_path or str(wt.path) == branch_or_path:
                target = wt
                break

        if not target:
            raise WorktreeError(f"Worktree not found: {branch_or_path}")

        if target.is_main:
            raise WorktreeError("Cannot remove main worktree")

        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(target.path))

        await self._run_git(*args)

    async def get_current(self) -> Optional[Worktree]:
        """Get the current worktree.

        Returns:
            The current Worktree, or None if not in a worktree.
        """
        worktrees = await self.list()
        cwd = self.repo_path.resolve()

        for wt in worktrees:
            if wt.path.resolve() == cwd:
                return wt

        return None

    async def find_by_branch(self, branch: str) -> Optional[Worktree]:
        """Find a worktree by branch name.

        Args:
            branch: Branch name to find.

        Returns:
            The Worktree if found, None otherwise.
        """
        worktrees = await self.list()

        for wt in worktrees:
            if wt.branch == branch:
                return wt

        return None

    async def prune(self) -> list[str]:
        """Remove stale worktree entries.

        Returns:
            List of pruned worktree paths.
        """

        worktrees = await self.list()
        pruned = [str(wt.path) for wt in worktrees if wt.prunable]

        await self._run_git("worktree", "prune")

        return pruned

    async def get_remote_default_branch(self) -> str:
        """Get the default branch from origin.

        Returns:
            Default branch name (e.g., 'main' or 'master').
        """
        try:
            output = await self._run_git("symbolic-ref", "refs/remotes/origin/HEAD", check=False)
            if output:
                return output.split("/")[-1]
        except WorktreeError:
            pass

        for branch in ["main", "master"]:
            try:
                await self._run_git("rev-parse", f"refs/heads/{branch}")
                return branch
            except WorktreeError:
                continue

        return "main"
