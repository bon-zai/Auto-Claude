"""
Agent Session Logic
===================

Core agent interaction functions for running autonomous coding sessions.
Uses chunk-based implementation plans with minimal, focused prompts.

Architecture:
- Orchestrator (Python) handles all bookkeeping: memory, commits, progress
- Agent focuses ONLY on implementing code
- Post-session processing updates memory automatically (100% reliable)
"""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Optional

from claude_code_sdk import ClaudeSDKClient

from client import create_client
from progress import (
    print_session_header,
    print_progress_summary,
    count_chunks,
    is_build_complete,
    get_next_chunk,
)
from prompt_generator import (
    generate_chunk_prompt,
    generate_planner_prompt,
    load_chunk_context,
    format_context_for_prompt,
)
from prompts import is_first_run
from recovery import RecoveryManager
from linear_integration import (
    LinearManager,
    is_linear_enabled,
    prepare_coder_linear_instructions,
)


# Configuration
AUTO_CONTINUE_DELAY_SECONDS = 3
HUMAN_INTERVENTION_FILE = "PAUSE"


def get_latest_commit(project_dir: Path) -> Optional[str]:
    """Get the hash of the latest git commit."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_commit_count(project_dir: Path) -> int:
    """Get the total number of commits."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        return int(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0


def load_implementation_plan(spec_dir: Path) -> Optional[dict]:
    """Load the implementation plan JSON."""
    plan_file = spec_dir / "implementation_plan.json"
    if not plan_file.exists():
        return None
    try:
        with open(plan_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def find_chunk_in_plan(plan: dict, chunk_id: str) -> Optional[dict]:
    """Find a chunk by ID in the plan."""
    for phase in plan.get("phases", []):
        for chunk in phase.get("chunks", []):
            if chunk.get("id") == chunk_id:
                return chunk
    return None


def find_phase_for_chunk(plan: dict, chunk_id: str) -> Optional[dict]:
    """Find the phase containing a chunk."""
    for phase in plan.get("phases", []):
        for chunk in phase.get("chunks", []):
            if chunk.get("id") == chunk_id:
                return phase
    return None


def post_session_processing(
    spec_dir: Path,
    project_dir: Path,
    chunk_id: str,
    session_num: int,
    commit_before: Optional[str],
    commit_count_before: int,
    recovery_manager: RecoveryManager,
    linear_manager: Optional[LinearManager] = None,
) -> bool:
    """
    Process session results and update memory automatically.

    This runs in Python (100% reliable) instead of relying on agent compliance.

    Args:
        spec_dir: Spec directory containing memory/
        project_dir: Project root for git operations
        chunk_id: The chunk that was being worked on
        session_num: Current session number
        commit_before: Git commit hash before session
        commit_count_before: Number of commits before session
        recovery_manager: Recovery manager instance
        linear_manager: Optional Linear integration manager

    Returns:
        True if chunk was completed successfully
    """
    print("\n--- Post-Session Processing ---")

    # Check if implementation plan was updated
    plan = load_implementation_plan(spec_dir)
    if not plan:
        print("  Warning: Could not load implementation plan")
        return False

    chunk = find_chunk_in_plan(plan, chunk_id)
    if not chunk:
        print(f"  Warning: Chunk {chunk_id} not found in plan")
        return False

    chunk_status = chunk.get("status", "pending")

    # Check for new commits
    commit_after = get_latest_commit(project_dir)
    commit_count_after = get_commit_count(project_dir)
    new_commits = commit_count_after - commit_count_before

    print(f"  Chunk status: {chunk_status}")
    print(f"  New commits: {new_commits}")

    if chunk_status == "completed":
        # Success! Record the attempt and good commit
        print(f"  ✓ Chunk {chunk_id} completed successfully")

        # Record successful attempt
        recovery_manager.record_attempt(
            chunk_id=chunk_id,
            session=session_num,
            success=True,
            approach=f"Implemented: {chunk.get('description', 'chunk')[:100]}",
        )

        # Record good commit for rollback safety
        if commit_after and commit_after != commit_before:
            recovery_manager.record_good_commit(commit_after, chunk_id)
            print(f"  ✓ Recorded good commit: {commit_after[:8]}")

        # Record Linear session result (if enabled)
        if linear_manager and linear_manager.is_initialized:
            comment = linear_manager.record_session_result(
                chunk_id=chunk_id,
                session_num=session_num,
                success=True,
                approach=f"Implemented: {chunk.get('description', 'chunk')[:100]}",
                git_commit=commit_after or "",
            )
            print(f"  ✓ Linear session recorded")

        return True

    elif chunk_status == "in_progress":
        # Session ended without completion
        print(f"  ⚠ Chunk {chunk_id} still in progress")

        recovery_manager.record_attempt(
            chunk_id=chunk_id,
            session=session_num,
            success=False,
            approach="Session ended with chunk in_progress",
            error="Chunk not marked as completed",
        )

        # Still record commit if one was made (partial progress)
        if commit_after and commit_after != commit_before:
            recovery_manager.record_good_commit(commit_after, chunk_id)
            print(f"  ✓ Recorded partial progress commit: {commit_after[:8]}")

        # Record Linear session result (if enabled)
        if linear_manager and linear_manager.is_initialized:
            linear_manager.record_session_result(
                chunk_id=chunk_id,
                session_num=session_num,
                success=False,
                approach="Session ended with chunk in_progress",
                error="Chunk not marked as completed",
                git_commit=commit_after or "",
            )

        return False

    else:
        # Chunk still pending or failed
        print(f"  ✗ Chunk {chunk_id} not completed (status: {chunk_status})")

        recovery_manager.record_attempt(
            chunk_id=chunk_id,
            session=session_num,
            success=False,
            approach="Session ended without progress",
            error=f"Chunk status is {chunk_status}",
        )

        # Record Linear session result (if enabled)
        if linear_manager and linear_manager.is_initialized:
            linear_manager.record_session_result(
                chunk_id=chunk_id,
                session_num=session_num,
                success=False,
                approach="Session ended without progress",
                error=f"Chunk status is {chunk_status}",
            )

        return False


async def run_agent_session(
    client: ClaudeSDKClient,
    message: str,
    spec_dir: Path,
    verbose: bool = False,
) -> tuple[str, str]:
    """
    Run a single agent session using Claude Agent SDK.

    Args:
        client: Claude SDK client
        message: The prompt to send
        spec_dir: Spec directory path
        verbose: Whether to show detailed output

    Returns:
        (status, response_text) where status is:
        - "continue" if agent should continue working
        - "complete" if all chunks complete
        - "error" if an error occurred
    """
    print("Sending prompt to Claude Agent SDK...\n")

    try:
        # Send the query
        await client.query(message)

        # Collect response text and show tool use
        response_text = ""
        async for msg in client.receive_response():
            msg_type = type(msg).__name__

            # Handle AssistantMessage (text and tool use)
            if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "TextBlock" and hasattr(block, "text"):
                        response_text += block.text
                        print(block.text, end="", flush=True)
                    elif block_type == "ToolUseBlock" and hasattr(block, "name"):
                        print(f"\n[Tool: {block.name}]", flush=True)
                        if verbose and hasattr(block, "input"):
                            input_str = str(block.input)
                            if len(input_str) > 300:
                                print(f"   Input: {input_str[:300]}...", flush=True)
                            else:
                                print(f"   Input: {input_str}", flush=True)

            # Handle UserMessage (tool results)
            elif msg_type == "UserMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "ToolResultBlock":
                        result_content = getattr(block, "content", "")
                        is_error = getattr(block, "is_error", False)

                        # Check if command was blocked by security hook
                        if "blocked" in str(result_content).lower():
                            print(f"   [BLOCKED] {result_content}", flush=True)
                        elif is_error:
                            # Show errors (truncated)
                            error_str = str(result_content)[:500]
                            print(f"   [Error] {error_str}", flush=True)
                        else:
                            # Tool succeeded
                            if verbose:
                                result_str = str(result_content)[:200]
                                print(f"   [Done] {result_str}", flush=True)
                            else:
                                print("   [Done]", flush=True)

        print("\n" + "-" * 70 + "\n")

        # Check if build is complete
        if is_build_complete(spec_dir):
            return "complete", response_text

        return "continue", response_text

    except Exception as e:
        print(f"Error during agent session: {e}")
        return "error", str(e)


async def run_autonomous_agent(
    project_dir: Path,
    spec_dir: Path,
    model: str,
    max_iterations: Optional[int] = None,
    verbose: bool = False,
) -> None:
    """
    Run the autonomous agent loop with automatic memory management.

    Args:
        project_dir: Root directory for the project
        spec_dir: Directory containing the spec (auto-build/specs/001-name/)
        model: Claude model to use
        max_iterations: Maximum number of iterations (None for unlimited)
        verbose: Whether to show detailed output
    """
    # Initialize recovery manager (handles memory persistence)
    recovery_manager = RecoveryManager(spec_dir, project_dir)

    # Initialize Linear manager (optional integration)
    linear_manager = None
    if is_linear_enabled():
        linear_manager = LinearManager(spec_dir, project_dir)
        if linear_manager.is_enabled:
            print("Linear integration: ENABLED")
            if linear_manager.is_initialized:
                summary = linear_manager.get_progress_summary()
                print(f"  Project: {summary.get('project_name', 'Unknown')}")
                print(f"  Issues: {summary.get('mapped_chunks', 0)}/{summary.get('total_chunks', 0)} mapped")
            else:
                print("  Status: Not yet initialized (will setup during planner session)")
            print()

    # Check if this is a fresh start or continuation
    first_run = is_first_run(spec_dir)

    if first_run:
        print("Fresh start - will use Planner Agent to create implementation plan")
        print()
        print("=" * 70)
        print("  PLANNER SESSION")
        print(f"  Spec: {spec_dir.name}")
        print("  The agent will analyze your spec and create a chunk-based plan.")
        print("=" * 70)
        print()
    else:
        print(f"Continuing build: {spec_dir.name}")
        print_progress_summary(spec_dir)

        # Check if already complete
        if is_build_complete(spec_dir):
            print("\n" + "=" * 70)
            print("  BUILD ALREADY COMPLETE!")
            print("=" * 70)
            print("\nAll chunks are completed. The build is ready for human review.")
            print("\nNext steps:")
            print("  1. Review the code on the auto-build/* branch")
            print("  2. Run manual tests")
            print("  3. Merge to main when satisfied")
            return

    # Show human intervention hint
    print("-" * 70)
    print("  INTERACTIVE CONTROLS:")
    print("  Press Ctrl+C once  → Pause and optionally add instructions")
    print("  Press Ctrl+C twice → Exit immediately")
    print("-" * 70)
    print()

    # Main loop
    iteration = 0

    while True:
        iteration += 1

        # Check for human intervention (PAUSE file)
        pause_file = spec_dir / HUMAN_INTERVENTION_FILE
        if pause_file.exists():
            print("\n" + "=" * 70)
            print("  PAUSED BY HUMAN")
            print("=" * 70)

            pause_content = pause_file.read_text().strip()
            if pause_content:
                print(f"\nMessage: {pause_content}")

            print(f"\nTo resume, delete the PAUSE file:")
            print(f"  rm {pause_file}")
            print(f"\nThen run again:")
            print(f"  python auto-build/run.py --spec {spec_dir.name}")
            return

        # Check max iterations
        if max_iterations and iteration > max_iterations:
            print(f"\nReached max iterations ({max_iterations})")
            print("To continue, run the script again without --max-iterations")
            break

        # Get the next chunk to work on
        next_chunk = get_next_chunk(spec_dir)
        chunk_id = next_chunk.get("id") if next_chunk else None

        # Print session header
        print_session_header(iteration, first_run)

        # Capture state before session for post-processing
        commit_before = get_latest_commit(project_dir)
        commit_count_before = get_commit_count(project_dir)

        # Create client (fresh context)
        client = create_client(project_dir, spec_dir, model)

        # Generate appropriate prompt
        if first_run:
            prompt = generate_planner_prompt(spec_dir)
            first_run = False
        else:
            if not next_chunk:
                print("No pending chunks found - build may be complete!")
                break

            # Get attempt count for recovery context
            attempt_count = recovery_manager.get_attempt_count(chunk_id)
            recovery_hints = recovery_manager.get_recovery_hints(chunk_id) if attempt_count > 0 else None

            # Find the phase for this chunk
            plan = load_implementation_plan(spec_dir)
            phase = find_phase_for_chunk(plan, chunk_id) if plan else {}

            # Generate focused, minimal prompt for this chunk
            prompt = generate_chunk_prompt(
                spec_dir=spec_dir,
                project_dir=project_dir,
                chunk=next_chunk,
                phase=phase or {},
                attempt_count=attempt_count,
                recovery_hints=recovery_hints,
            )

            # Load and append relevant file context
            context = load_chunk_context(spec_dir, project_dir, next_chunk)
            if context.get("patterns") or context.get("files_to_modify"):
                prompt += "\n\n" + format_context_for_prompt(context)

            # Show what we're working on
            print(f"Working on: {chunk_id}")
            print(f"Description: {next_chunk.get('description', 'No description')}")
            if attempt_count > 0:
                print(f"⚠️  Previous attempts: {attempt_count}")
            print()

        # Run session with async context manager
        async with client:
            status, response = await run_agent_session(
                client, prompt, spec_dir, verbose
            )

        # === POST-SESSION PROCESSING (100% reliable) ===
        if chunk_id and not first_run:
            success = post_session_processing(
                spec_dir=spec_dir,
                project_dir=project_dir,
                chunk_id=chunk_id,
                session_num=iteration,
                commit_before=commit_before,
                commit_count_before=commit_count_before,
                recovery_manager=recovery_manager,
                linear_manager=linear_manager,
            )

            # Check for stuck chunks
            attempt_count = recovery_manager.get_attempt_count(chunk_id)
            if not success and attempt_count >= 3:
                recovery_manager.mark_chunk_stuck(
                    chunk_id,
                    f"Failed after {attempt_count} attempts"
                )
                print(f"\n⚠️  Chunk {chunk_id} marked as STUCK after {attempt_count} attempts")
                print("Consider: manual intervention or skipping this chunk")

                # Prepare Linear escalation data (if enabled)
                if linear_manager and linear_manager.is_initialized:
                    chunk_history = recovery_manager.get_chunk_history(chunk_id)
                    escalation = linear_manager.prepare_stuck_escalation(
                        chunk_id=chunk_id,
                        attempt_count=attempt_count,
                        attempts=chunk_history.get("attempts", []),
                        reason=f"Failed after {attempt_count} attempts",
                    )
                    print(f"  Linear escalation prepared for issue: {escalation.get('issue_id')}")

        # Handle session status
        if status == "complete":
            print("\n" + "=" * 70)
            print("  BUILD COMPLETE!")
            print("=" * 70)
            print_progress_summary(spec_dir)
            print("\nAll chunks are completed. The build is ready for human review.")
            print("\nNext steps:")
            print("  1. Review the code on the auto-build/* branch")
            print("  2. Run manual tests")
            print("  3. Create a PR and merge to main when satisfied")
            break

        elif status == "continue":
            print(f"\nAgent will auto-continue in {AUTO_CONTINUE_DELAY_SECONDS}s...")
            print_progress_summary(spec_dir)

            # Show next chunk info
            next_chunk = get_next_chunk(spec_dir)
            if next_chunk:
                chunk_id = next_chunk.get('id')
                print(f"\nNext: {chunk_id} - {next_chunk.get('description')}")

                attempt_count = recovery_manager.get_attempt_count(chunk_id)
                if attempt_count > 0:
                    print(f"  ⚠️  WARNING: {attempt_count} previous attempt(s)")

            await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

        elif status == "error":
            print("\nSession encountered an error")
            print("Will retry with a fresh session...")
            await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

        # Small delay between sessions
        if max_iterations is None or iteration < max_iterations:
            print("\nPreparing next session...\n")
            await asyncio.sleep(1)

    # Final summary
    print("\n" + "=" * 70)
    print("  SESSION SUMMARY")
    print("=" * 70)
    print(f"\nProject directory: {project_dir}")
    print(f"Spec: {spec_dir.name}")
    print(f"Sessions completed: {iteration}")
    print_progress_summary(spec_dir)

    # Show stuck chunks if any
    stuck_chunks = recovery_manager.get_stuck_chunks()
    if stuck_chunks:
        print("\n⚠️  STUCK CHUNKS (need manual intervention):")
        for stuck in stuck_chunks:
            print(f"  - {stuck['chunk_id']}: {stuck['reason']}")

    # Instructions
    print("\n" + "-" * 70)
    print("  NEXT STEPS")
    print("-" * 70)

    completed, total = count_chunks(spec_dir)
    if completed < total:
        print(f"\n  {total - completed} chunks remaining.")
        print(f"  Run again to continue: python auto-build/run.py --spec {spec_dir.name}")
    else:
        print("\n  All chunks completed!")
        print("  1. Review the auto-build/* branch")
        print("  2. Run manual tests")
        print("  3. Merge to main")

    print("-" * 70)
    print()
