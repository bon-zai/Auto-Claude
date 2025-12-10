#!/usr/bin/env python3
"""
Git Worktree Manager
====================

Manages Git worktrees for isolated auto-build execution.

Architecture:
- ONE staging worktree per spec: .worktrees/auto-build/
- All work (sequential or parallel) happens in this staging worktree
- User can cd into it, run the app, test the feature
- Only merges to their project when they're ready

Worktrees allow auto-build to work in a completely separate directory
while sharing the same git repository. This provides:

1. Safety: User's current work is never touched
2. Isolation: Auto-build has a clean environment
3. Testability: User can run/test the feature before accepting
4. Easy rollback: Just remove the worktree if unwanted
"""

import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Standard name for the staging worktree
STAGING_WORKTREE_NAME = "auto-build"


class WorktreeError(Exception):
    """Error during worktree operations."""
    pass


@dataclass
class WorktreeInfo:
    """Information about a worktree."""
    path: Path
    branch: str
    base_branch: str
    is_active: bool = True


class WorktreeManager:
    """
    Manages Git worktrees for isolated execution.

    Each worktree is a complete copy of the project in a separate directory,
    on its own branch. This provides complete isolation - git operations
    in one worktree don't affect others.
    """

    def __init__(self, project_dir: Path, base_branch: Optional[str] = None):
        """
        Initialize the worktree manager.

        Args:
            project_dir: The main project directory (must be a git repo)
            base_branch: Branch to base worktrees on (default: current branch)
        """
        self.project_dir = project_dir
        self.base_branch = base_branch or self._get_current_branch()
        self.worktrees_dir = project_dir / ".worktrees"
        self._merge_lock = asyncio.Lock()
        self._active_worktrees: dict[str, WorktreeInfo] = {}

    def _get_current_branch(self) -> str:
        """Get the current git branch."""
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise WorktreeError(f"Failed to get current branch: {result.stderr}")
        return result.stdout.strip()

    def _run_git(self, args: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Run a git command and return the result."""
        return subprocess.run(
            ["git"] + args,
            cwd=cwd or self.project_dir,
            capture_output=True,
            text=True,
        )

    def setup(self) -> None:
        """Create worktrees directory and cleanup any stale worktrees."""
        self.worktrees_dir.mkdir(exist_ok=True)
        self._cleanup_stale_worktrees()

    def _cleanup_stale_worktrees(self) -> None:
        """Remove any worktrees left over from previous runs (except staging)."""
        if not self.worktrees_dir.exists():
            return

        # Get list of registered worktrees
        result = self._run_git(["worktree", "list", "--porcelain"])

        registered_paths = set()
        for line in result.stdout.split("\n"):
            if line.startswith("worktree "):
                registered_paths.add(Path(line.split(" ", 1)[1]))

        # Remove directories in .worktrees that aren't registered
        # BUT preserve the staging worktree (auto-build)
        for item in self.worktrees_dir.iterdir():
            if item.is_dir():
                # Don't auto-cleanup the staging worktree
                if item.name == STAGING_WORKTREE_NAME:
                    continue

                if item not in registered_paths:
                    print(f"  Removing stale worktree directory: {item.name}")
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    # Registered but stale - prune it
                    print(f"  Pruning stale worktree: {item.name}")
                    self._run_git(["worktree", "remove", "--force", str(item)])

        # Prune worktree list
        self._run_git(["worktree", "prune"])

    def create(self, name: str, branch_name: Optional[str] = None) -> WorktreeInfo:
        """
        Create a new worktree.

        Args:
            name: Name for the worktree directory (e.g., "auto-build" or "worker-1")
            branch_name: Branch name to create (default: auto-build/{name})

        Returns:
            WorktreeInfo with path and branch details
        """
        if branch_name is None:
            branch_name = f"auto-build/{name}"

        worktree_path = self.worktrees_dir / name

        # Remove existing worktree if present (from crashed previous run)
        if worktree_path.exists():
            self._run_git(["worktree", "remove", "--force", str(worktree_path)])

        # Delete branch if it exists (from previous attempt)
        self._run_git(["branch", "-D", branch_name])

        # Create worktree with new branch from base
        result = self._run_git([
            "worktree", "add", "-b", branch_name,
            str(worktree_path), self.base_branch
        ])

        if result.returncode != 0:
            raise WorktreeError(f"Failed to create worktree: {result.stderr}")

        info = WorktreeInfo(
            path=worktree_path,
            branch=branch_name,
            base_branch=self.base_branch,
            is_active=True,
        )
        self._active_worktrees[name] = info

        print(f"Created worktree: {worktree_path.name} on branch {branch_name}")
        return info

    def get_or_create_staging(self, spec_name: str) -> WorktreeInfo:
        """
        Get or create the staging worktree for a spec.

        The staging worktree is where all work happens. It persists
        until the user explicitly merges or discards it.

        Args:
            spec_name: Name of the spec (for branch naming)

        Returns:
            WorktreeInfo for the staging worktree
        """
        staging_path = self.worktrees_dir / STAGING_WORKTREE_NAME
        branch_name = f"auto-build/{spec_name}"

        # Check if it already exists
        if staging_path.exists():
            # Load existing worktree info
            result = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=staging_path)
            if result.returncode == 0:
                existing_branch = result.stdout.strip()
                info = WorktreeInfo(
                    path=staging_path,
                    branch=existing_branch,
                    base_branch=self.base_branch,
                    is_active=True,
                )
                self._active_worktrees[STAGING_WORKTREE_NAME] = info
                print(f"Using existing staging worktree: {staging_path}")
                return info

        # Create new staging worktree
        return self.create(STAGING_WORKTREE_NAME, branch_name)

    def staging_exists(self) -> bool:
        """Check if a staging worktree exists."""
        staging_path = self.worktrees_dir / STAGING_WORKTREE_NAME
        return staging_path.exists()

    def get_staging_path(self) -> Optional[Path]:
        """Get the path to the staging worktree if it exists."""
        staging_path = self.worktrees_dir / STAGING_WORKTREE_NAME
        if staging_path.exists():
            return staging_path
        return None

    def get_staging_info(self) -> Optional[WorktreeInfo]:
        """Get info about the staging worktree."""
        staging_path = self.worktrees_dir / STAGING_WORKTREE_NAME
        if not staging_path.exists():
            return None

        # Get branch info
        result = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=staging_path)
        if result.returncode != 0:
            return None

        branch = result.stdout.strip()

        info = WorktreeInfo(
            path=staging_path,
            branch=branch,
            base_branch=self.base_branch,
            is_active=True,
        )
        self._active_worktrees[STAGING_WORKTREE_NAME] = info
        return info

    def remove(self, name: str, delete_branch: bool = False) -> None:
        """
        Remove a worktree.

        Args:
            name: Name of the worktree to remove
            delete_branch: Whether to also delete the branch
        """
        info = self._active_worktrees.get(name)
        worktree_path = info.path if info else self.worktrees_dir / name

        if worktree_path.exists():
            result = self._run_git(["worktree", "remove", "--force", str(worktree_path)])

            if result.returncode == 0:
                print(f"Removed worktree: {worktree_path.name}")
            else:
                print(f"Warning: Could not remove worktree: {result.stderr}")
                # Try manual removal
                shutil.rmtree(worktree_path, ignore_errors=True)

        # Delete branch if requested
        if delete_branch and info:
            self._run_git(["branch", "-D", info.branch])

        # Remove from tracking
        self._active_worktrees.pop(name, None)

        # Prune worktree list
        self._run_git(["worktree", "prune"])

    def remove_staging(self, delete_branch: bool = True) -> None:
        """Remove the staging worktree."""
        self.remove(STAGING_WORKTREE_NAME, delete_branch=delete_branch)

    async def merge(self, name: str, delete_after: bool = True) -> bool:
        """
        Merge a worktree's branch back to base branch.

        Uses a lock to ensure only one merge happens at a time.

        Args:
            name: Name of the worktree to merge
            delete_after: Whether to remove the worktree after merging

        Returns:
            True if merge succeeded, False otherwise
        """
        info = self._active_worktrees.get(name)
        if not info:
            # Try to load it
            info = self.get_staging_info() if name == STAGING_WORKTREE_NAME else None
        if not info:
            print(f"Worktree '{name}' not found")
            return False

        async with self._merge_lock:
            return self._do_merge(info, name, delete_after)

    def _do_merge(self, info: WorktreeInfo, name: str, delete_after: bool) -> bool:
        """Actually perform the merge."""
        print(f"Merging {info.branch} into {self.base_branch}...")

        # Switch to base branch in main worktree
        result = self._run_git(["checkout", self.base_branch])
        if result.returncode != 0:
            print(f"  Error: Could not checkout base branch: {result.stderr}")
            return False

        # Merge the worktree branch
        result = self._run_git([
            "merge", "--no-ff", info.branch,
            "-m", f"auto-build: Merge {info.branch}"
        ])

        if result.returncode != 0:
            print(f"  Merge conflict! Aborting merge...")
            self._run_git(["merge", "--abort"])
            return False

        print(f"  Successfully merged {info.branch}")

        # Clean up
        if delete_after:
            self.remove(name, delete_branch=True)

        return True

    def merge_sync(self, name: str, delete_after: bool = True) -> bool:
        """
        Synchronous version of merge for non-async contexts.

        Args:
            name: Name of the worktree to merge
            delete_after: Whether to remove the worktree after merging

        Returns:
            True if merge succeeded, False otherwise
        """
        info = self._active_worktrees.get(name)
        if not info:
            # Try to load it
            info = self.get_staging_info() if name == STAGING_WORKTREE_NAME else None
        if not info:
            print(f"Worktree '{name}' not found")
            return False

        return self._do_merge(info, name, delete_after)

    def merge_staging(self, delete_after: bool = True) -> bool:
        """Merge the staging worktree to base branch."""
        return self.merge_sync(STAGING_WORKTREE_NAME, delete_after=delete_after)

    def commit_in_staging(self, message: str) -> bool:
        """
        Commit all changes in the staging worktree.

        Args:
            message: Commit message

        Returns:
            True if commit succeeded or nothing to commit
        """
        staging_path = self.get_staging_path()
        if not staging_path:
            return False

        # Stage all changes
        self._run_git(["add", "."], cwd=staging_path)

        # Commit
        result = self._run_git(["commit", "-m", message], cwd=staging_path)

        if result.returncode == 0:
            return True
        elif "nothing to commit" in result.stdout + result.stderr:
            return True
        else:
            print(f"Commit failed: {result.stderr}")
            return False

    def merge_branch_to_staging(self, branch_name: str) -> bool:
        """
        Merge a branch into the staging worktree.

        Used by parallel workers to merge their work into staging.

        Args:
            branch_name: Branch to merge into staging

        Returns:
            True if merge succeeded
        """
        staging_path = self.get_staging_path()
        if not staging_path:
            print("No staging worktree exists")
            return False

        print(f"Merging {branch_name} into staging...")

        result = self._run_git(
            ["merge", "--no-ff", branch_name, "-m", f"auto-build: Merge {branch_name}"],
            cwd=staging_path
        )

        if result.returncode != 0:
            print(f"  Merge conflict! Aborting merge...")
            self._run_git(["merge", "--abort"], cwd=staging_path)
            return False

        print(f"  Successfully merged {branch_name} into staging")
        return True

    def get_info(self, name: str) -> Optional[WorktreeInfo]:
        """Get information about a worktree."""
        return self._active_worktrees.get(name)

    def get_worktree_path(self, name: str) -> Optional[Path]:
        """Get the path to a worktree."""
        info = self._active_worktrees.get(name)
        if info:
            return info.path

        # Check if it exists but isn't tracked
        path = self.worktrees_dir / name
        if path.exists():
            return path

        return None

    def list_worktrees(self) -> list[WorktreeInfo]:
        """List all active worktrees."""
        return list(self._active_worktrees.values())

    def cleanup_all(self) -> None:
        """Remove all worktrees and the .worktrees directory."""
        # Remove all active worktrees
        for name in list(self._active_worktrees.keys()):
            self.remove(name, delete_branch=True)

        # Prune
        self._run_git(["worktree", "prune"])

        # Remove the directory if empty
        if self.worktrees_dir.exists():
            try:
                self.worktrees_dir.rmdir()
            except OSError:
                # Directory not empty, that's fine
                pass

    def cleanup_workers_only(self) -> None:
        """Remove only worker worktrees, preserve staging."""
        for name in list(self._active_worktrees.keys()):
            if name != STAGING_WORKTREE_NAME:
                self.remove(name, delete_branch=True)

        # Prune
        self._run_git(["worktree", "prune"])

    def has_uncommitted_changes(self, in_staging: bool = False) -> bool:
        """Check if there are uncommitted changes."""
        cwd = self.get_staging_path() if in_staging else None
        result = self._run_git(["status", "--porcelain"], cwd=cwd)
        return bool(result.stdout.strip())

    def get_change_summary(self, name: str = STAGING_WORKTREE_NAME) -> dict:
        """
        Get a summary of changes in a worktree compared to base.

        Args:
            name: Name of the worktree (default: staging)

        Returns:
            Dict with 'new_files', 'modified_files', 'deleted_files' counts
        """
        info = self._active_worktrees.get(name)
        if not info:
            info = self.get_staging_info() if name == STAGING_WORKTREE_NAME else None
        if not info:
            return {"new_files": 0, "modified_files": 0, "deleted_files": 0}

        # Get diff stats
        result = self._run_git([
            "diff", "--name-status",
            f"{info.base_branch}...{info.branch}"
        ])

        new_files = 0
        modified_files = 0
        deleted_files = 0

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            if line.startswith("A"):
                new_files += 1
            elif line.startswith("M"):
                modified_files += 1
            elif line.startswith("D"):
                deleted_files += 1

        return {
            "new_files": new_files,
            "modified_files": modified_files,
            "deleted_files": deleted_files,
        }

    def get_changed_files(self, name: str = STAGING_WORKTREE_NAME) -> list[tuple[str, str]]:
        """
        Get list of changed files in a worktree.

        Args:
            name: Name of the worktree (default: staging)

        Returns:
            List of (status, filepath) tuples where status is A/M/D
        """
        info = self._active_worktrees.get(name)
        if not info:
            info = self.get_staging_info() if name == STAGING_WORKTREE_NAME else None
        if not info:
            return []

        result = self._run_git([
            "diff", "--name-status",
            f"{info.base_branch}...{info.branch}"
        ])

        files = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                files.append((parts[0], parts[1]))

        return files

    def get_test_commands(self, staging_path: Path) -> list[str]:
        """
        Detect likely test/run commands for the project.

        Returns common commands based on what files exist.
        """
        commands = []

        # Check for package.json (Node.js)
        if (staging_path / "package.json").exists():
            commands.append("npm install && npm run dev")
            commands.append("npm test")

        # Check for requirements.txt (Python)
        if (staging_path / "requirements.txt").exists():
            commands.append("pip install -r requirements.txt")

        # Check for Cargo.toml (Rust)
        if (staging_path / "Cargo.toml").exists():
            commands.append("cargo run")
            commands.append("cargo test")

        # Check for go.mod (Go)
        if (staging_path / "go.mod").exists():
            commands.append("go run .")
            commands.append("go test ./...")

        # Default
        if not commands:
            commands.append("# Check the project's README for run instructions")

        return commands
