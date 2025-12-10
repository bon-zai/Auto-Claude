#!/usr/bin/env python3
"""
Tests for Git Worktree Management
=================================

Tests the worktree.py module functionality including:
- Worktree creation and removal
- Staging worktree management
- Branch operations
- Merge operations
- Change tracking
"""

import subprocess
from pathlib import Path

import pytest

from worktree import WorktreeManager, WorktreeInfo, WorktreeError, STAGING_WORKTREE_NAME


class TestWorktreeManagerInitialization:
    """Tests for WorktreeManager initialization."""

    def test_init_with_valid_git_repo(self, temp_git_repo: Path):
        """Manager initializes correctly with valid git repo."""
        manager = WorktreeManager(temp_git_repo)

        assert manager.project_dir == temp_git_repo
        assert manager.worktrees_dir == temp_git_repo / ".worktrees"
        assert manager.base_branch is not None

    def test_init_detects_current_branch(self, temp_git_repo: Path):
        """Manager correctly detects the current branch."""
        # Create and switch to a new branch
        subprocess.run(
            ["git", "checkout", "-b", "feature-branch"],
            cwd=temp_git_repo, capture_output=True
        )

        manager = WorktreeManager(temp_git_repo)
        assert manager.base_branch == "feature-branch"

    def test_init_with_explicit_base_branch(self, temp_git_repo: Path):
        """Manager uses explicitly provided base branch."""
        manager = WorktreeManager(temp_git_repo, base_branch="main")
        assert manager.base_branch == "main"

    def test_setup_creates_worktrees_directory(self, temp_git_repo: Path):
        """Setup creates the .worktrees directory."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()

        assert manager.worktrees_dir.exists()
        assert manager.worktrees_dir.is_dir()


class TestWorktreeCreation:
    """Tests for creating worktrees."""

    def test_create_worktree(self, temp_git_repo: Path):
        """Can create a new worktree."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()

        info = manager.create("test-worker")

        assert info.path.exists()
        assert info.branch == "auto-build/test-worker"
        assert info.is_active is True
        assert (info.path / "README.md").exists()

    def test_create_worktree_with_custom_branch(self, temp_git_repo: Path):
        """Can create worktree with custom branch name."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()

        info = manager.create("test-worker", branch_name="my-feature-branch")

        assert info.branch == "my-feature-branch"

    def test_create_replaces_existing_worktree(self, temp_git_repo: Path):
        """Creating worktree with same name replaces existing one."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()

        info1 = manager.create("test-worker")
        # Create a file in the worktree
        (info1.path / "test-file.txt").write_text("test")

        # Create again should work (replacing the old one)
        info2 = manager.create("test-worker")

        assert info2.path.exists()
        # The test file should be gone (fresh worktree)
        assert not (info2.path / "test-file.txt").exists()


class TestStagingWorktree:
    """Tests for staging worktree operations."""

    def test_get_or_create_staging_creates_new(self, temp_git_repo: Path):
        """Creates staging worktree if it doesn't exist."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()

        info = manager.get_or_create_staging("test-spec")

        assert info.path.exists()
        assert info.path.name == STAGING_WORKTREE_NAME
        assert "test-spec" in info.branch

    def test_get_or_create_staging_returns_existing(self, temp_git_repo: Path):
        """Returns existing staging worktree without recreating."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()

        info1 = manager.get_or_create_staging("test-spec")
        # Add a file
        (info1.path / "marker.txt").write_text("marker")

        info2 = manager.get_or_create_staging("test-spec")

        # Should be the same worktree (marker file exists)
        assert (info2.path / "marker.txt").exists()

    def test_staging_exists_false_when_none(self, temp_git_repo: Path):
        """staging_exists returns False when no staging worktree."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()

        assert manager.staging_exists() is False

    def test_staging_exists_true_when_created(self, temp_git_repo: Path):
        """staging_exists returns True after creating staging."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        manager.get_or_create_staging("test-spec")

        assert manager.staging_exists() is True

    def test_get_staging_path(self, temp_git_repo: Path):
        """get_staging_path returns correct path."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        manager.get_or_create_staging("test-spec")

        path = manager.get_staging_path()

        assert path is not None
        assert path.name == STAGING_WORKTREE_NAME

    def test_get_staging_info(self, temp_git_repo: Path):
        """get_staging_info returns WorktreeInfo."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        manager.get_or_create_staging("test-spec")

        info = manager.get_staging_info()

        assert info is not None
        assert isinstance(info, WorktreeInfo)
        assert info.branch is not None


class TestWorktreeRemoval:
    """Tests for removing worktrees."""

    def test_remove_worktree(self, temp_git_repo: Path):
        """Can remove a worktree."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        info = manager.create("test-worker")

        manager.remove("test-worker")

        assert not info.path.exists()

    def test_remove_staging(self, temp_git_repo: Path):
        """Can remove staging worktree."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        info = manager.get_or_create_staging("test-spec")

        manager.remove_staging()

        assert not info.path.exists()
        assert manager.staging_exists() is False

    def test_remove_with_delete_branch(self, temp_git_repo: Path):
        """Removing worktree can also delete the branch."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        info = manager.create("test-worker")
        branch_name = info.branch

        manager.remove("test-worker", delete_branch=True)

        # Verify branch is deleted
        result = subprocess.run(
            ["git", "branch", "--list", branch_name],
            cwd=temp_git_repo, capture_output=True, text=True
        )
        assert branch_name not in result.stdout


class TestWorktreeCommitAndMerge:
    """Tests for commit and merge operations."""

    def test_commit_in_staging(self, temp_git_repo: Path):
        """Can commit changes in staging worktree."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        info = manager.get_or_create_staging("test-spec")

        # Make changes in staging
        (info.path / "new-file.txt").write_text("new content")

        result = manager.commit_in_staging("Test commit")

        assert result is True

        # Verify commit was made
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=info.path, capture_output=True, text=True
        )
        assert "Test commit" in log_result.stdout

    def test_commit_in_staging_nothing_to_commit(self, temp_git_repo: Path):
        """commit_in_staging succeeds when nothing to commit."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        manager.get_or_create_staging("test-spec")

        # No changes made
        result = manager.commit_in_staging("Empty commit")

        assert result is True  # Should succeed (nothing to commit is OK)

    def test_merge_staging_sync(self, temp_git_repo: Path):
        """Can merge staging worktree to main branch."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        info = manager.get_or_create_staging("test-spec")

        # Make changes in staging
        (info.path / "feature.txt").write_text("feature content")
        manager.commit_in_staging("Add feature")

        # Merge back
        result = manager.merge_staging(delete_after=False)

        assert result is True

        # Verify file is in main branch
        subprocess.run(["git", "checkout", manager.base_branch], cwd=temp_git_repo, capture_output=True)
        assert (temp_git_repo / "feature.txt").exists()

    def test_merge_branch_to_staging(self, temp_git_repo: Path):
        """Can merge a branch into staging worktree."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        manager.get_or_create_staging("test-spec")

        # Create another worktree with changes
        worker_info = manager.create("worker-1")
        (worker_info.path / "worker-file.txt").write_text("worker content")
        subprocess.run(["git", "add", "."], cwd=worker_info.path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Worker commit"],
            cwd=worker_info.path, capture_output=True
        )

        # Merge worker branch into staging
        result = manager.merge_branch_to_staging(worker_info.branch)

        assert result is True

        # Verify file is in staging
        staging_path = manager.get_staging_path()
        assert (staging_path / "worker-file.txt").exists()


class TestChangeTracking:
    """Tests for tracking changes in worktrees."""

    def test_has_uncommitted_changes_false(self, temp_git_repo: Path):
        """has_uncommitted_changes returns False when clean."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()

        assert manager.has_uncommitted_changes() is False

    def test_has_uncommitted_changes_true(self, temp_git_repo: Path):
        """has_uncommitted_changes returns True when dirty."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()

        # Make uncommitted changes
        (temp_git_repo / "dirty.txt").write_text("uncommitted")

        assert manager.has_uncommitted_changes() is True

    def test_get_change_summary(self, temp_git_repo: Path):
        """get_change_summary returns correct counts."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        info = manager.get_or_create_staging("test-spec")

        # Make various changes
        (info.path / "new-file.txt").write_text("new")
        (info.path / "README.md").write_text("modified")
        manager.commit_in_staging("Changes")

        summary = manager.get_change_summary()

        assert summary["new_files"] == 1  # new-file.txt
        assert summary["modified_files"] == 1  # README.md

    def test_get_changed_files(self, temp_git_repo: Path):
        """get_changed_files returns list of changed files."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        info = manager.get_or_create_staging("test-spec")

        # Make changes
        (info.path / "added.txt").write_text("new file")
        manager.commit_in_staging("Add file")

        files = manager.get_changed_files()

        assert len(files) > 0
        file_names = [f[1] for f in files]
        assert "added.txt" in file_names


class TestWorktreeUtilities:
    """Tests for utility methods."""

    def test_list_worktrees(self, temp_git_repo: Path):
        """list_worktrees returns active worktrees."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        manager.create("worker-1")
        manager.create("worker-2")

        worktrees = manager.list_worktrees()

        assert len(worktrees) == 2

    def test_get_info(self, temp_git_repo: Path):
        """get_info returns correct WorktreeInfo."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        manager.create("test-worker")

        info = manager.get_info("test-worker")

        assert info is not None
        assert info.branch == "auto-build/test-worker"

    def test_get_worktree_path(self, temp_git_repo: Path):
        """get_worktree_path returns correct path."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        info = manager.create("test-worker")

        path = manager.get_worktree_path("test-worker")

        assert path == info.path

    def test_cleanup_all(self, temp_git_repo: Path):
        """cleanup_all removes all worktrees."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        manager.create("worker-1")
        manager.create("worker-2")
        manager.get_or_create_staging("test-spec")

        manager.cleanup_all()

        assert len(manager.list_worktrees()) == 0

    def test_cleanup_workers_only_preserves_staging(self, temp_git_repo: Path):
        """cleanup_workers_only removes workers but keeps staging."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        manager.create("worker-1")
        manager.get_or_create_staging("test-spec")

        manager.cleanup_workers_only()

        assert manager.staging_exists() is True
        assert manager.get_info("worker-1") is None

    def test_get_test_commands_python(self, temp_git_repo: Path):
        """get_test_commands detects Python project commands."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        info = manager.get_or_create_staging("test-spec")

        # Create requirements.txt
        (info.path / "requirements.txt").write_text("flask\n")

        commands = manager.get_test_commands(info.path)

        assert any("pip" in cmd for cmd in commands)

    def test_get_test_commands_node(self, temp_git_repo: Path):
        """get_test_commands detects Node.js project commands."""
        manager = WorktreeManager(temp_git_repo)
        manager.setup()
        info = manager.get_or_create_staging("test-spec")

        # Create package.json
        (info.path / "package.json").write_text('{"name": "test"}')

        commands = manager.get_test_commands(info.path)

        assert any("npm" in cmd for cmd in commands)
