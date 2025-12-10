"""
Progress Tracking Utilities
===========================

Functions for tracking and displaying progress of the autonomous coding agent.
Uses chunk-based implementation plans (implementation_plan.json).
"""

import json
from pathlib import Path


def count_chunks(spec_dir: Path) -> tuple[int, int]:
    """
    Count completed and total chunks in implementation_plan.json.

    Args:
        spec_dir: Directory containing implementation_plan.json

    Returns:
        (completed_count, total_count)
    """
    plan_file = spec_dir / "implementation_plan.json"

    if not plan_file.exists():
        return 0, 0

    try:
        with open(plan_file, "r") as f:
            plan = json.load(f)

        total = 0
        completed = 0

        for phase in plan.get("phases", []):
            for chunk in phase.get("chunks", []):
                total += 1
                if chunk.get("status") == "completed":
                    completed += 1

        return completed, total
    except (json.JSONDecodeError, IOError):
        return 0, 0


def is_build_complete(spec_dir: Path) -> bool:
    """
    Check if all chunks are completed.

    Args:
        spec_dir: Directory containing implementation_plan.json

    Returns:
        True if all chunks complete, False otherwise
    """
    completed, total = count_chunks(spec_dir)
    return total > 0 and completed == total


def get_progress_percentage(spec_dir: Path) -> float:
    """
    Get the progress as a percentage.

    Args:
        spec_dir: Directory containing implementation_plan.json

    Returns:
        Percentage of chunks completed (0-100)
    """
    completed, total = count_chunks(spec_dir)
    if total == 0:
        return 0.0
    return (completed / total) * 100


def print_session_header(session_num: int, is_planner: bool) -> None:
    """Print a formatted header for the session."""
    session_type = "PLANNER AGENT" if is_planner else "CODING AGENT"

    print("\n" + "=" * 70)
    print(f"  SESSION {session_num}: {session_type}")
    print("=" * 70)
    print()


def print_progress_summary(spec_dir: Path) -> None:
    """Print a summary of current progress."""
    completed, total = count_chunks(spec_dir)

    if total > 0:
        percentage = (completed / total) * 100
        bar_width = 40
        filled = int(bar_width * completed / total)
        bar = "=" * filled + "-" * (bar_width - filled)

        print(f"\nProgress: [{bar}] {completed}/{total} ({percentage:.1f}%)")

        if completed == total:
            print("Status: BUILD COMPLETE - All chunks completed!")
        else:
            remaining = total - completed
            print(f"Status: {remaining} chunks remaining")

        # Show phase summary
        try:
            with open(spec_dir / "implementation_plan.json", "r") as f:
                plan = json.load(f)

            print("\nPhases:")
            for phase in plan.get("phases", []):
                phase_chunks = phase.get("chunks", [])
                phase_completed = sum(1 for c in phase_chunks if c.get("status") == "completed")
                phase_total = len(phase_chunks)

                if phase_completed == phase_total:
                    status = "✓"
                elif phase_completed > 0:
                    status = "→"
                else:
                    # Check if blocked by dependencies
                    deps = phase.get("depends_on", [])
                    all_deps_complete = True
                    for dep_id in deps:
                        for p in plan.get("phases", []):
                            if p.get("id") == dep_id:
                                p_chunks = p.get("chunks", [])
                                if not all(c.get("status") == "completed" for c in p_chunks):
                                    all_deps_complete = False
                                break
                    status = "○" if all_deps_complete else "⊘"

                print(f"  {status} {phase.get('name', phase.get('id'))}: {phase_completed}/{phase_total}")

        except (json.JSONDecodeError, IOError):
            pass
    else:
        print("\nProgress: implementation_plan.json not yet created")


def get_plan_summary(spec_dir: Path) -> dict:
    """
    Get a detailed summary of implementation plan status.

    Args:
        spec_dir: Directory containing implementation_plan.json

    Returns:
        Dictionary with plan statistics
    """
    plan_file = spec_dir / "implementation_plan.json"

    if not plan_file.exists():
        return {
            "workflow_type": None,
            "total_phases": 0,
            "total_chunks": 0,
            "completed_chunks": 0,
            "pending_chunks": 0,
            "in_progress_chunks": 0,
            "phases": [],
        }

    try:
        with open(plan_file, "r") as f:
            plan = json.load(f)

        summary = {
            "workflow_type": plan.get("workflow_type"),
            "total_phases": len(plan.get("phases", [])),
            "total_chunks": 0,
            "completed_chunks": 0,
            "pending_chunks": 0,
            "in_progress_chunks": 0,
            "phases": [],
        }

        for phase in plan.get("phases", []):
            phase_info = {
                "id": phase.get("id"),
                "name": phase.get("name"),
                "depends_on": phase.get("depends_on", []),
                "chunks": [],
            }

            for chunk in phase.get("chunks", []):
                status = chunk.get("status", "pending")
                summary["total_chunks"] += 1

                if status == "completed":
                    summary["completed_chunks"] += 1
                elif status == "in_progress":
                    summary["in_progress_chunks"] += 1
                else:
                    summary["pending_chunks"] += 1

                phase_info["chunks"].append({
                    "id": chunk.get("id"),
                    "description": chunk.get("description"),
                    "status": status,
                    "service": chunk.get("service"),
                })

            summary["phases"].append(phase_info)

        return summary

    except (json.JSONDecodeError, IOError):
        return {
            "workflow_type": None,
            "total_phases": 0,
            "total_chunks": 0,
            "completed_chunks": 0,
            "pending_chunks": 0,
            "in_progress_chunks": 0,
            "phases": [],
        }


def get_next_chunk(spec_dir: Path) -> dict | None:
    """
    Find the next chunk to work on, respecting phase dependencies.

    Args:
        spec_dir: Directory containing implementation_plan.json

    Returns:
        The next chunk dict to work on, or None if all complete
    """
    plan_file = spec_dir / "implementation_plan.json"

    if not plan_file.exists():
        return None

    try:
        with open(plan_file, "r") as f:
            plan = json.load(f)

        phases = plan.get("phases", [])

        # Build a map of phase completion
        phase_complete = {}
        for phase in phases:
            phase_id = phase.get("id")
            chunks = phase.get("chunks", [])
            phase_complete[phase_id] = all(
                c.get("status") == "completed" for c in chunks
            )

        # Find next available chunk
        for phase in phases:
            phase_id = phase.get("id")
            depends_on = phase.get("depends_on", [])

            # Check if dependencies are satisfied
            deps_satisfied = all(phase_complete.get(dep, False) for dep in depends_on)
            if not deps_satisfied:
                continue

            # Find first pending chunk in this phase
            for chunk in phase.get("chunks", []):
                if chunk.get("status") == "pending":
                    return {
                        "phase_id": phase_id,
                        "phase_name": phase.get("name"),
                        **chunk,
                    }

        return None

    except (json.JSONDecodeError, IOError):
        return None
