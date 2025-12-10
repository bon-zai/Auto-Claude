#!/usr/bin/env python3
"""
Multi-Agent Parallelism Coordinator with Staging Worktree
==========================================================

Implements a swarm coordination pattern for parallel execution of independent chunks.
All work is collected in a single STAGING worktree that the user can test before merging.

Architecture:
1. Create ONE staging worktree: .worktrees/auto-build/
2. Each worker gets a temporary worktree for isolation during work
3. Workers merge INTO staging (not base branch)
4. User can cd into staging, run the app, test the feature
5. Only merges to user's project when they explicitly approve

Benefits:
- User can TEST the complete feature before accepting it
- All work is collected in one place for review
- No partial merges - it's all or nothing
- Easy to discard if the feature doesn't work

Prerequisites:
- Git 2.5+ (for worktree support)
- implementation_plan.json must exist (planner runs first if needed)
"""

import asyncio
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from implementation_plan import ImplementationPlan, Phase, Chunk, ChunkStatus
from worktree import WorktreeManager, STAGING_WORKTREE_NAME


class WorkerStatus(Enum):
    """Status of a worker."""
    IDLE = "idle"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkerAssignment:
    """Tracks what a worker is doing."""
    worker_id: str
    phase_id: int
    chunk_id: str
    branch_name: str
    worktree_path: Path
    status: WorkerStatus
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "phase_id": self.phase_id,
            "chunk_id": self.chunk_id,
            "branch_name": self.branch_name,
            "worktree_path": str(self.worktree_path),
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class ParallelGroup:
    """Phases that can run in parallel."""
    phases: list[Phase]
    all_dependencies_met: bool

    def __post_init__(self):
        """Validate that phases can actually run in parallel."""
        # Check for file conflicts between phases
        file_sets = []
        for phase in self.phases:
            phase_files = set()
            for chunk in phase.chunks:
                phase_files.update(chunk.files_to_modify)
                phase_files.update(chunk.files_to_create)
            file_sets.append(phase_files)

        # Ensure no file overlap
        for i, files_a in enumerate(file_sets):
            for j, files_b in enumerate(file_sets[i+1:], i+1):
                overlap = files_a & files_b
                if overlap:
                    raise ValueError(
                        f"Phases {self.phases[i].name} and {self.phases[j].name} "
                        f"cannot run in parallel - they modify the same files: {overlap}"
                    )


class SwarmCoordinator:
    """
    Coordinates parallel execution of chunks using a staging worktree.

    The coordinator:
    1. Runs planner session first if no implementation_plan.json exists
    2. Creates a STAGING worktree where all work is collected
    3. Each worker gets a temporary worktree for isolation
    4. Workers merge their completed work INTO staging
    5. At the end, user has a complete feature to test in staging
    6. User can then merge staging to their project when ready
    """

    def __init__(
        self,
        spec_dir: Path,
        project_dir: Path,
        max_workers: int = 3,
        model: str = "claude-opus-4-5-20251101",
        verbose: bool = False,
    ):
        self.spec_dir = spec_dir
        self.project_dir = project_dir
        self.max_workers = max_workers
        self.model = model
        self.verbose = verbose

        # State tracking
        self.workers: dict[str, WorkerAssignment] = {}
        self.claimed_files: dict[str, str] = {}  # file_path -> worker_id
        self.plan: Optional[ImplementationPlan] = None
        self.worktree_manager: Optional[WorktreeManager] = None

        # Progress tracking file
        self.progress_file = spec_dir / "parallel_progress.json"

        # Merge lock for serializing merges to staging
        self._merge_lock = asyncio.Lock()

    def _get_base_branch(self) -> str:
        """Get the current branch to use as base for workers."""
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _get_spec_name(self) -> str:
        """Get the spec name for branch naming."""
        return self.spec_dir.name

    def load_implementation_plan(self) -> ImplementationPlan:
        """Load the implementation plan from spec directory."""
        plan_file = self.spec_dir / "implementation_plan.json"

        if not plan_file.exists():
            raise FileNotFoundError(
                f"Implementation plan not found: {plan_file}\n"
                "The planner session should have created this."
            )

        self.plan = ImplementationPlan.load(plan_file)
        return self.plan

    def save_implementation_plan(self):
        """Save the updated implementation plan."""
        if self.plan:
            plan_file = self.spec_dir / "implementation_plan.json"
            self.plan.save(plan_file)

    def get_available_chunks(self) -> list[tuple[Phase, Chunk]]:
        """
        Get chunks that are ready to be worked on.

        A chunk is available if:
        - Its phase dependencies are met
        - It's not claimed by another worker
        - Its files aren't claimed by another worker
        - Its status is PENDING
        """
        if not self.plan:
            return []

        available = []
        available_phases = self.plan.get_available_phases()

        for phase in available_phases:
            for chunk in phase.chunks:
                if chunk.status != ChunkStatus.PENDING:
                    continue

                # Check if chunk is already claimed
                if any(w.chunk_id == chunk.id for w in self.workers.values()):
                    continue

                # Check if any of chunk's files are claimed
                chunk_files = set(chunk.files_to_modify + chunk.files_to_create)
                if any(f in self.claimed_files for f in chunk_files):
                    continue

                available.append((phase, chunk))

        return available

    def claim_chunk(
        self,
        worker_id: str,
        phase: Phase,
        chunk: Chunk,
        worktree_path: Path,
        branch_name: str,
    ) -> bool:
        """Claim a chunk for a worker."""
        # Check if chunk already claimed
        if any(w.chunk_id == chunk.id for w in self.workers.values()):
            return False

        # Check if any files already claimed
        chunk_files = set(chunk.files_to_modify + chunk.files_to_create)
        if any(f in self.claimed_files for f in chunk_files):
            return False

        # Claim the files
        for file_path in chunk_files:
            self.claimed_files[file_path] = worker_id

        # Create worker assignment
        assignment = WorkerAssignment(
            worker_id=worker_id,
            phase_id=phase.phase,
            chunk_id=chunk.id,
            branch_name=branch_name,
            worktree_path=worktree_path,
            status=WorkerStatus.WORKING,
            started_at=datetime.now().isoformat(),
        )

        self.workers[worker_id] = assignment

        # Update chunk status
        chunk.status = ChunkStatus.IN_PROGRESS
        chunk.started_at = datetime.now().isoformat()

        return True

    def release_chunk(
        self,
        worker_id: str,
        chunk_id: str,
        success: bool,
        output: Optional[str] = None,
    ) -> None:
        """Release a chunk after completion or failure."""
        if worker_id not in self.workers:
            return

        assignment = self.workers[worker_id]

        # Update assignment
        assignment.completed_at = datetime.now().isoformat()
        assignment.status = WorkerStatus.COMPLETED if success else WorkerStatus.FAILED

        # Find and update the chunk
        for phase in self.plan.phases:
            for chunk in phase.chunks:
                if chunk.id == chunk_id:
                    if success:
                        chunk.complete(output)
                    else:
                        chunk.fail(output)
                    break

        # Release claimed files
        chunk_files = [f for f, wid in self.claimed_files.items() if wid == worker_id]
        for file_path in chunk_files:
            del self.claimed_files[file_path]

        # Remove worker assignment
        del self.workers[worker_id]

    async def run_planner_session(self) -> bool:
        """
        Run the planner session to create implementation_plan.json.

        This runs in the main project directory (not a worktree).
        """
        print("\n" + "=" * 70)
        print("  PLANNER SESSION")
        print("  Creating implementation plan from spec...")
        print("=" * 70 + "\n")

        # Import here to avoid circular dependency
        from agent import run_agent_session
        from client import create_client
        from prompt_generator import generate_planner_prompt
        from linear_integration import LinearManager, is_linear_enabled

        # Create client for planner (uses main project directory)
        client = create_client(self.project_dir, self.spec_dir, self.model)

        # Generate planner prompt
        prompt = generate_planner_prompt(self.spec_dir)

        # Run the planner session
        async with client:
            status, response = await run_agent_session(
                client, prompt, self.spec_dir, self.verbose
            )

        # Check if plan was created
        plan_file = self.spec_dir / "implementation_plan.json"
        if not plan_file.exists():
            print("\nError: Planner did not create implementation_plan.json")
            return False

        print("\n✓ Implementation plan created successfully")

        # Initialize Linear integration if enabled
        if is_linear_enabled():
            linear_manager = LinearManager(self.spec_dir, self.project_dir)
            if linear_manager.is_enabled and not linear_manager.is_initialized:
                print("\nInitializing Linear integration...")
                if linear_manager.initialize_from_plan():
                    print("✓ Linear project and issues created")
                else:
                    print("⚠ Linear initialization failed (continuing without it)")

        return True

    async def merge_worker_to_staging(self, worker_id: str, branch_name: str, worktree_path: Path) -> bool:
        """
        Merge a worker's completed work into the staging worktree.

        Uses a lock to serialize merges.
        """
        async with self._merge_lock:
            staging_path = self.worktree_manager.get_staging_path()
            if not staging_path:
                print(f"Worker {worker_id}: No staging worktree found!")
                return False

            print(f"Worker {worker_id}: Merging into staging...")

            # Merge the worker branch into staging
            result = subprocess.run(
                ["git", "merge", "--no-ff", branch_name,
                 "-m", f"auto-build: Merge {branch_name}"],
                cwd=staging_path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(f"  Merge conflict! Aborting merge...")
                subprocess.run(
                    ["git", "merge", "--abort"],
                    cwd=staging_path,
                    capture_output=True,
                )
                return False

            print(f"  Successfully merged {branch_name} into staging")
            return True

    async def run_worker(
        self,
        worker_id: str,
        phase: Phase,
        chunk: Chunk,
    ) -> bool:
        """
        Run a single worker on a chunk using a dedicated worktree.

        Worker creates work in its own worktree, then merges to staging.
        """
        print(f"\n{'='*70}")
        print(f"  WORKER {worker_id}: Starting {chunk.id}")
        print(f"  Phase: {phase.name}")
        print(f"  Description: {chunk.description}")
        print(f"{'='*70}\n")

        # Get staging info to branch from
        staging_info = self.worktree_manager.get_staging_info()
        if not staging_info:
            print(f"Worker {worker_id}: No staging worktree!")
            return False

        # Create temporary worktree for this worker (branching from staging)
        worker_name = f"worker-{worker_id}"
        branch_name = f"worker-{worker_id}/{chunk.id}"
        worktree_path = self.worktree_manager.worktrees_dir / worker_name

        try:
            # Create worktree branching from staging branch
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                cwd=self.project_dir,
                capture_output=True,
            )
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=self.project_dir,
                capture_output=True,
            )

            result = subprocess.run(
                ["git", "worktree", "add", "-b", branch_name,
                 str(worktree_path), staging_info.branch],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(f"Worker {worker_id}: Failed to create worktree: {result.stderr}")
                return False

            print(f"Created worker worktree: {worktree_path.name} (from staging)")

        except Exception as e:
            print(f"Worker {worker_id}: Failed to create worktree: {e}")
            return False

        # Claim the chunk
        if not self.claim_chunk(worker_id, phase, chunk, worktree_path, branch_name):
            print(f"Worker {worker_id}: Failed to claim chunk {chunk.id}")
            self._cleanup_worker_worktree(worktree_path, branch_name)
            return False

        try:
            # Import here to avoid circular dependency
            from agent import run_agent_session
            from client import create_client
            from prompts import get_coding_prompt

            # Create client for this worker - uses worker's worktree
            client = create_client(worktree_path, self.spec_dir, self.model)

            # Generate prompt for this specific chunk
            prompt = get_coding_prompt(self.spec_dir)

            # Add chunk-specific instructions
            prompt += f"\n\n## ASSIGNED CHUNK\n\n"
            prompt += f"You are working on a SPECIFIC chunk. Focus ONLY on this:\n\n"
            prompt += f"**Chunk ID:** {chunk.id}\n"
            prompt += f"**Description:** {chunk.description}\n"

            if chunk.files_to_modify:
                prompt += f"**Files to modify:** {', '.join(chunk.files_to_modify)}\n"
            if chunk.files_to_create:
                prompt += f"**Files to create:** {', '.join(chunk.files_to_create)}\n"

            prompt += f"\n**IMPORTANT:** Commit your changes when done.\n"

            # Run the agent session
            print(f"Worker {worker_id}: Running in worktree {worktree_path.name}...")
            async with client:
                status, response = await run_agent_session(
                    client, prompt, self.spec_dir, self.verbose
                )

            success = status == "continue" or status == "complete"

            # Commit any uncommitted work
            if success:
                subprocess.run(
                    ["git", "add", "."],
                    cwd=worktree_path,
                    check=False,
                )
                result = subprocess.run(
                    ["git", "commit", "-m", f"auto-build: Complete {chunk.id}\n\n{chunk.description}"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    print(f"Worker {worker_id}: Committed changes")
                elif "nothing to commit" not in result.stdout + result.stderr:
                    print(f"Worker {worker_id}: Commit issue: {result.stderr}")

            # Release the chunk
            self.release_chunk(worker_id, chunk.id, success, response)

            # Merge to staging if successful
            if success:
                merge_success = await self.merge_worker_to_staging(
                    worker_id, branch_name, worktree_path
                )
                if not merge_success:
                    print(f"Worker {worker_id}: Merge to staging failed for {chunk.id}")
                    # Mark chunk as failed due to merge conflict
                    for p in self.plan.phases:
                        for c in p.chunks:
                            if c.id == chunk.id:
                                c.fail("Merge conflict")
                    success = False

            # Clean up worker worktree
            self._cleanup_worker_worktree(worktree_path, branch_name)

            return success

        except Exception as e:
            print(f"Worker {worker_id}: Error executing chunk {chunk.id}: {e}")

            # Clean up on error
            self.release_chunk(worker_id, chunk.id, False, str(e))
            self._cleanup_worker_worktree(worktree_path, branch_name)

            return False

    def _cleanup_worker_worktree(self, worktree_path: Path, branch_name: str) -> None:
        """Clean up a worker's temporary worktree."""
        # Remove worktree
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=self.project_dir,
            capture_output=True,
        )

        # Delete branch
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=self.project_dir,
            capture_output=True,
        )

        # Prune
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=self.project_dir,
            capture_output=True,
        )

    def save_progress(self):
        """Save parallel execution progress."""
        progress_data = {
            "active_workers": len(self.workers),
            "workers": {wid: w.to_dict() for wid, w in self.workers.items()},
            "claimed_files": self.claimed_files,
            "last_update": datetime.now().isoformat(),
        }

        with open(self.progress_file, "w") as f:
            json.dump(progress_data, f, indent=2)

    def load_progress(self):
        """Load parallel execution progress if it exists."""
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                data = json.load(f)
                # Restore state if needed
                # For now, we start fresh each time

    async def run_parallel(self) -> Path:
        """
        Main coordination loop.

        Returns the path to the staging worktree where all work is collected.
        """
        # Check if implementation plan exists, run planner if not
        plan_file = self.spec_dir / "implementation_plan.json"
        if not plan_file.exists():
            success = await self.run_planner_session()
            if not success:
                print("\nFailed to create implementation plan. Exiting.")
                return None

        print(f"\n{'='*70}")
        print(f"  PARALLEL EXECUTION MODE")
        print(f"  Max Workers: {self.max_workers}")
        print(f"  All work collected in staging worktree for testing")
        print(f"{'='*70}\n")

        # Load the implementation plan
        self.load_implementation_plan()

        # Get the base branch
        base_branch = self._get_base_branch()
        print(f"Base branch: {base_branch}")

        # Initialize worktree manager
        self.worktree_manager = WorktreeManager(self.project_dir, base_branch)
        self.worktree_manager.setup()

        # Create or get the staging worktree
        spec_name = self._get_spec_name()
        staging_info = self.worktree_manager.get_or_create_staging(spec_name)
        print(f"Staging worktree: {staging_info.path}")
        print(f"Staging branch: {staging_info.branch}")
        print()

        # Load any existing progress
        self.load_progress()

        # Track worker tasks
        worker_tasks: dict[str, asyncio.Task] = {}
        next_worker_id = 1

        try:
            while True:
                # Get available chunks
                available_chunks = self.get_available_chunks()

                # Check if we're done
                if not available_chunks and not worker_tasks:
                    print("\n✓ All chunks completed!")
                    break

                # Assign chunks to available workers
                while len(worker_tasks) < self.max_workers and available_chunks:
                    phase, chunk = available_chunks.pop(0)
                    worker_id = str(next_worker_id)
                    next_worker_id += 1

                    print(f"Assigned chunk {chunk.id} to worker {worker_id}")

                    # Start worker task
                    task = asyncio.create_task(
                        self.run_worker(worker_id, phase, chunk)
                    )
                    worker_tasks[worker_id] = task

                # Wait for at least one worker to complete
                if worker_tasks:
                    done, pending = await asyncio.wait(
                        worker_tasks.values(),
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    # Remove completed tasks
                    for task in done:
                        # Find which worker completed
                        for wid, t in list(worker_tasks.items()):
                            if t == task:
                                try:
                                    result = await task
                                    print(f"\nWorker {wid} completed: {'SUCCESS' if result else 'FAILED'}")
                                except Exception as e:
                                    print(f"\nWorker {wid} crashed: {e}")
                                del worker_tasks[wid]
                                break

                    # Save progress
                    self.save_implementation_plan()
                    self.save_progress()
                else:
                    # No workers and no available chunks - might be waiting on dependencies
                    await asyncio.sleep(1)

        finally:
            # Clean up only worker worktrees, preserve staging
            print("\nCleaning up worker worktrees...")
            self.worktree_manager.cleanup_workers_only()

        # Print final summary
        print(f"\n{'='*70}")
        print(f"  BUILD COMPLETE!")
        print(f"{'='*70}\n")

        progress = self.plan.get_progress()
        print(f"Completed: {progress['completed_chunks']}/{progress['total_chunks']} chunks")

        if progress['failed_chunks'] > 0:
            print(f"⚠ Failed chunks: {progress['failed_chunks']}")

        # Show staging info
        staging_path = self.worktree_manager.get_staging_path()
        if staging_path:
            summary = self.worktree_manager.get_change_summary()
            test_commands = self.worktree_manager.get_test_commands(staging_path)

            print(f"\n{'='*70}")
            print(f"  YOUR FEATURE IS READY TO TEST")
            print(f"{'='*70}\n")

            print(f"All work has been collected in:")
            print(f"  {staging_path}\n")

            if summary["new_files"] + summary["modified_files"] + summary["deleted_files"] > 0:
                print("Changes:")
                if summary["new_files"] > 0:
                    print(f"  + {summary['new_files']} new files")
                if summary["modified_files"] > 0:
                    print(f"  ~ {summary['modified_files']} modified files")
                if summary["deleted_files"] > 0:
                    print(f"  - {summary['deleted_files']} deleted files")
                print()

            print("To test it:")
            print(f"  cd {staging_path}")
            for cmd in test_commands[:2]:  # Show first 2 commands
                print(f"  {cmd}")
            print()

            print("When you're happy with it:")
            print(f"  python auto-build/run.py --spec {spec_name} --merge")
            print()

            print("To see what changed:")
            print(f"  python auto-build/run.py --spec {spec_name} --review")
            print()

        return staging_path
