#!/usr/bin/env python3
"""
Workspace Selection and Management
===================================

Provides a user-friendly interface for choosing where auto-build should work.
Designed for "vibe coders" - people who may not understand git internals.

Key principles:
1. Simple language - no git jargon
2. Safe defaults - protect user's work
3. Clear outcomes - explain what will happen
4. No dangerous options - discard requires separate deliberate action

Terminology mapping (technical -> user-friendly):
- worktree -> "separate workspace"
- branch -> "version of your project"
- uncommitted changes -> "unsaved work"
- merge -> "add to your project"
- working directory -> "your project"
"""

import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

from worktree import WorktreeManager, WorktreeInfo, STAGING_WORKTREE_NAME


class WorkspaceMode(Enum):
    """How auto-build should work."""
    ISOLATED = "isolated"  # Work in a separate worktree (safe)
    DIRECT = "direct"      # Work directly in user's project


class WorkspaceChoice(Enum):
    """User's choice after build completes."""
    MERGE = "merge"        # Add changes to project
    REVIEW = "review"      # Show what changed
    TEST = "test"          # Test the feature in the staging worktree
    LATER = "later"        # Decide later


def has_uncommitted_changes(project_dir: Path) -> bool:
    """Check if user has unsaved work."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def get_current_branch(project_dir: Path) -> str:
    """Get the current branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def get_existing_build_worktree(project_dir: Path, spec_name: str) -> Optional[Path]:
    """Check if there's an existing staging worktree."""
    worktree_path = project_dir / ".worktrees" / STAGING_WORKTREE_NAME
    if worktree_path.exists():
        return worktree_path
    return None


def choose_workspace(
    project_dir: Path,
    spec_name: str,
    force_isolated: bool = False,
    force_direct: bool = False,
) -> WorkspaceMode:
    """
    Let user choose where auto-build should work.

    Uses simple, non-technical language. Safe defaults.

    Args:
        project_dir: The project directory
        spec_name: Name of the spec being built
        force_isolated: Skip prompts and use isolated mode
        force_direct: Skip prompts and use direct mode

    Returns:
        WorkspaceMode indicating where to work
    """
    # Handle forced modes
    if force_isolated:
        return WorkspaceMode.ISOLATED
    if force_direct:
        return WorkspaceMode.DIRECT

    # Check for unsaved work
    has_unsaved = has_uncommitted_changes(project_dir)

    if has_unsaved:
        # Unsaved work detected - use isolated mode for safety
        print()
        print("=" * 60)
        print("  YOUR WORK IS PROTECTED")
        print("=" * 60)
        print()
        print("You have unsaved work in your project.")
        print()
        print("To keep your work safe, the AI will build in a")
        print("separate workspace. Your current files won't be")
        print("touched until you're ready.")
        print()

        try:
            input("Press Enter to continue...")
        except KeyboardInterrupt:
            print("\n\nCancelled.")
            sys.exit(0)

        return WorkspaceMode.ISOLATED

    # Clean working directory - give choice
    print()
    print("=" * 60)
    print("  WHERE SHOULD THE AI BUILD YOUR FEATURE?")
    print("=" * 60)
    print()
    print("[1] In a separate workspace (Recommended)")
    print("    Your current files stay untouched")
    print("    You can review changes before keeping them")
    print("    Easy to undo if you don't like it")
    print()
    print("[2] Right here in your project")
    print("    Changes happen directly in your files")
    print("    Best if you're not working on anything else")
    print()

    try:
        choice = input("Your choice [1]: ").strip() or "1"
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(0)

    if choice == "2":
        print()
        print("Got it! Working directly in your project.")
        return WorkspaceMode.DIRECT
    else:
        print()
        print("Got it! Using a separate workspace for safety.")
        return WorkspaceMode.ISOLATED


def setup_workspace(
    project_dir: Path,
    spec_name: str,
    mode: WorkspaceMode,
) -> tuple[Path, Optional[WorktreeManager]]:
    """
    Set up the workspace based on user's choice.

    Uses the staging worktree pattern - all work happens in one worktree
    that the user can test before merging.

    Args:
        project_dir: The project directory
        spec_name: Name of the spec being built
        mode: The workspace mode to use

    Returns:
        Tuple of (working_directory, worktree_manager or None)
    """
    if mode == WorkspaceMode.DIRECT:
        # Work directly in project
        return project_dir, None

    # Create isolated workspace using staging worktree
    print()
    print("Setting up separate workspace...")

    manager = WorktreeManager(project_dir)
    manager.setup()

    # Get or create the staging worktree
    info = manager.get_or_create_staging(spec_name)

    print(f"Workspace ready: {info.path}")
    print()

    return info.path, manager


def show_build_summary(manager: WorktreeManager, name: str = STAGING_WORKTREE_NAME) -> None:
    """Show a summary of what was built."""
    summary = manager.get_change_summary(name)
    files = manager.get_changed_files(name)

    total = summary["new_files"] + summary["modified_files"] + summary["deleted_files"]

    if total == 0:
        print("  No changes were made.")
        return

    print()
    print("What was built:")
    if summary["new_files"] > 0:
        print(f"  + {summary['new_files']} new file{'s' if summary['new_files'] != 1 else ''}")
    if summary["modified_files"] > 0:
        print(f"  ~ {summary['modified_files']} modified file{'s' if summary['modified_files'] != 1 else ''}")
    if summary["deleted_files"] > 0:
        print(f"  - {summary['deleted_files']} deleted file{'s' if summary['deleted_files'] != 1 else ''}")


def show_changed_files(manager: WorktreeManager, name: str = STAGING_WORKTREE_NAME) -> None:
    """Show detailed list of changed files."""
    files = manager.get_changed_files(name)

    if not files:
        print("  No changes.")
        return

    status_labels = {
        "A": "+ (new)",
        "M": "~ (modified)",
        "D": "- (deleted)",
    }

    print()
    print("Changed files:")
    for status, filepath in files:
        label = status_labels.get(status, status)
        print(f"  {label} {filepath}")


def finalize_workspace(
    project_dir: Path,
    spec_name: str,
    manager: Optional[WorktreeManager],
) -> WorkspaceChoice:
    """
    Handle post-build workflow - let user decide what to do with changes.

    Safe design:
    - No "discard" option (requires separate --discard command)
    - Default is "test" - encourages testing before merging
    - Everything is preserved until user explicitly merges or discards

    Args:
        project_dir: The project directory
        spec_name: Name of the spec that was built
        manager: The worktree manager (None if direct mode was used)

    Returns:
        WorkspaceChoice indicating what user wants to do
    """
    if manager is None:
        # Direct mode - nothing to finalize
        print()
        print("=" * 60)
        print("  BUILD COMPLETE!")
        print("=" * 60)
        print()
        print("Changes were made directly to your project.")
        print("Use 'git status' to see what changed.")
        return WorkspaceChoice.MERGE  # Already merged

    # Isolated mode - show options with testing as the recommended path
    print()
    print("=" * 60)
    print("  BUILD COMPLETE!")
    print("=" * 60)
    print()
    print("The AI built your feature in a separate workspace.")

    show_build_summary(manager)

    # Get the staging path for test instructions
    staging_path = manager.get_staging_path()

    print()
    print("What would you like to do?")
    print()
    print("[1] Test the feature (Recommended)")
    print("    Run the app and try it out before adding to your project")
    print()
    print("[2] Add to my project now")
    print("    Merge the changes into your files immediately")
    print()
    print("[3] Review what changed")
    print("    See exactly what files were modified")
    print()
    print("[4] Decide later")
    print("    Your build is saved - you can come back anytime")
    print()

    try:
        choice = input("Your choice [1]: ").strip() or "1"
    except KeyboardInterrupt:
        print("\n\nNo problem! Your build is saved.")
        choice = "4"

    if choice == "1":
        return WorkspaceChoice.TEST
    elif choice == "2":
        return WorkspaceChoice.MERGE
    elif choice == "3":
        return WorkspaceChoice.REVIEW
    else:
        return WorkspaceChoice.LATER


def handle_workspace_choice(
    choice: WorkspaceChoice,
    project_dir: Path,
    spec_name: str,
    manager: WorktreeManager,
) -> None:
    """
    Execute the user's choice.

    Args:
        choice: What the user wants to do
        project_dir: The project directory
        spec_name: Name of the spec
        manager: The worktree manager
    """
    staging_path = manager.get_staging_path()

    if choice == WorkspaceChoice.TEST:
        # Show testing instructions
        print()
        print("=" * 60)
        print("  TEST YOUR FEATURE")
        print("=" * 60)
        print()
        print("Your feature is ready to test in a separate workspace.")
        print()
        print("To test it, open a NEW terminal and run:")
        print()
        if staging_path:
            print(f"  cd {staging_path}")
        else:
            print(f"  cd {project_dir}/.worktrees/{STAGING_WORKTREE_NAME}")

        # Show likely test/run commands
        if staging_path:
            commands = manager.get_test_commands(staging_path)
            print()
            print("Then run your project:")
            for cmd in commands[:2]:  # Show top 2 commands
                print(f"  {cmd}")

        print()
        print("-" * 60)
        print()
        print("When you're done testing:")
        print(f"  python auto-build/run.py --spec {spec_name} --merge")
        print()
        print("To discard (if you don't like it):")
        print(f"  python auto-build/run.py --spec {spec_name} --discard")
        print()

    elif choice == WorkspaceChoice.MERGE:
        print()
        print("Adding changes to your project...")
        success = manager.merge_staging(delete_after=True)

        if success:
            print()
            print("Done! Your feature has been added to your project.")
        else:
            print()
            print("There was a conflict merging the changes.")
            print("Your build is still saved in the separate workspace.")
            print()
            print("You may need to merge manually or ask for help.")

    elif choice == WorkspaceChoice.REVIEW:
        show_changed_files(manager)
        print()
        print("-" * 60)
        print()
        print("To see full details of changes:")
        info = manager.get_staging_info()
        if info:
            print(f"  git diff {info.base_branch}...{info.branch}")
        print()
        print("To test the feature:")
        if staging_path:
            print(f"  cd {staging_path}")
        print()
        print("To add these changes to your project:")
        print(f"  python auto-build/run.py --spec {spec_name} --merge")
        print()

    else:  # LATER
        print()
        print("No problem! Your build is saved.")
        print()
        print("To test the feature:")
        if staging_path:
            print(f"  cd {staging_path}")
        else:
            print(f"  cd {project_dir}/.worktrees/{STAGING_WORKTREE_NAME}")
        print()
        print("When you're ready to add it:")
        print(f"  python auto-build/run.py --spec {spec_name} --merge")
        print()
        print("To see what was built:")
        print(f"  python auto-build/run.py --spec {spec_name} --review")
        print()


def merge_existing_build(project_dir: Path, spec_name: str) -> bool:
    """
    Merge an existing build into the project.

    Called when user runs: python auto-build/run.py --spec X --merge

    Args:
        project_dir: The project directory
        spec_name: Name of the spec

    Returns:
        True if merge succeeded
    """
    worktree_path = get_existing_build_worktree(project_dir, spec_name)

    if not worktree_path:
        print()
        print(f"No existing build found for '{spec_name}'.")
        print()
        print("To start a new build:")
        print(f"  python auto-build/run.py --spec {spec_name}")
        return False

    print()
    print("=" * 60)
    print("  ADDING BUILD TO YOUR PROJECT")
    print("=" * 60)

    manager = WorktreeManager(project_dir)
    # Load the staging worktree info
    manager.get_staging_info()

    show_build_summary(manager)
    print()

    success = manager.merge_staging(delete_after=True)

    if success:
        print()
        print("Done! Your feature has been added to your project.")
        return True
    else:
        print()
        print("There was a conflict merging the changes.")
        print("You may need to merge manually.")
        return False


def review_existing_build(project_dir: Path, spec_name: str) -> bool:
    """
    Show what an existing build contains.

    Called when user runs: python auto-build/run.py --spec X --review

    Args:
        project_dir: The project directory
        spec_name: Name of the spec

    Returns:
        True if build exists
    """
    worktree_path = get_existing_build_worktree(project_dir, spec_name)

    if not worktree_path:
        print()
        print(f"No existing build found for '{spec_name}'.")
        print()
        print("To start a new build:")
        print(f"  python auto-build/run.py --spec {spec_name}")
        return False

    print()
    print("=" * 60)
    print("  BUILD CONTENTS")
    print("=" * 60)

    manager = WorktreeManager(project_dir)
    # Load the staging worktree info
    info = manager.get_staging_info()

    show_build_summary(manager)
    show_changed_files(manager)

    print()
    print("-" * 60)
    print()
    print("To test the feature:")
    print(f"  cd {worktree_path}")
    print()
    print("To add these changes to your project:")
    print(f"  python auto-build/run.py --spec {spec_name} --merge")
    print()
    print("To see full diff:")
    if info:
        print(f"  git diff {info.base_branch}...{info.branch}")
    print()

    return True


def discard_existing_build(project_dir: Path, spec_name: str) -> bool:
    """
    Discard an existing build (with confirmation).

    Called when user runs: python auto-build/run.py --spec X --discard

    Requires typing "delete" to confirm - prevents accidents.

    Args:
        project_dir: The project directory
        spec_name: Name of the spec

    Returns:
        True if discarded
    """
    worktree_path = get_existing_build_worktree(project_dir, spec_name)

    if not worktree_path:
        print()
        print(f"No existing build found for '{spec_name}'.")
        return False

    print()
    print("=" * 60)
    print("  DELETE BUILD RESULTS?")
    print("=" * 60)

    manager = WorktreeManager(project_dir)
    # Load the staging worktree info
    manager.get_staging_info()

    print()
    print("This will permanently delete all work for this build.")

    show_build_summary(manager)

    print()
    print("Are you sure? Type 'delete' to confirm: ", end="")

    try:
        confirmation = input().strip().lower()
    except KeyboardInterrupt:
        print("\n\nCancelled. Your build is still saved.")
        return False

    if confirmation != "delete":
        print()
        print("Cancelled. Your build is still saved.")
        return False

    # Actually delete
    manager.remove_staging(delete_branch=True)

    print()
    print("Build deleted.")
    return True


def check_existing_build(project_dir: Path, spec_name: str) -> bool:
    """
    Check if there's an existing build and offer options.

    Returns True if user wants to continue with existing build,
    False if they want to start fresh (after discarding).
    """
    worktree_path = get_existing_build_worktree(project_dir, spec_name)

    if not worktree_path:
        return False  # No existing build

    print()
    print("=" * 60)
    print("  EXISTING BUILD FOUND")
    print("=" * 60)
    print()
    print("There's already a build in progress for this spec.")
    print()
    print("[1] Continue where it left off")
    print("[2] Review what was built")
    print("[3] Add to my project now")
    print("[4] Start fresh (discard current build)")
    print()

    try:
        choice = input("Your choice [1]: ").strip() or "1"
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(0)

    if choice == "1":
        return True  # Continue with existing
    elif choice == "2":
        review_existing_build(project_dir, spec_name)
        print()
        input("Press Enter to continue building...")
        return True
    elif choice == "3":
        merge_existing_build(project_dir, spec_name)
        return False  # Start fresh after merge
    elif choice == "4":
        discarded = discard_existing_build(project_dir, spec_name)
        return not discarded  # If discarded, start fresh
    else:
        return True  # Default to continue
