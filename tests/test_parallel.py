#!/usr/bin/env python3
"""
Test script for parallel execution coordinator

Tests the SwarmCoordinator class that manages parallel chunk execution.
"""

import json
import sys
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "auto-build"))

from coordinator import SwarmCoordinator, ParallelGroup, WorkerAssignment, WorkerStatus
from implementation_plan import (
    ImplementationPlan,
    Phase,
    Chunk,
    ChunkStatus,
    PhaseType,
    WorkflowType,
)


class TestCoordinatorInitialization:
    """Tests for SwarmCoordinator initialization."""

    def test_creates_with_required_params(self):
        """Coordinator can be initialized with required params."""
        spec_dir = Path("/tmp/test-spec")
        project_dir = Path("/tmp/test-project")

        coordinator = SwarmCoordinator(
            spec_dir=spec_dir,
            project_dir=project_dir,
        )

        assert coordinator.spec_dir == spec_dir
        assert coordinator.project_dir == project_dir

    def test_default_max_workers(self):
        """Default max_workers is 3."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        assert coordinator.max_workers == 3

    def test_custom_max_workers(self):
        """Can set custom max_workers."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
            max_workers=5,
        )

        assert coordinator.max_workers == 5

    def test_empty_workers_and_files(self):
        """Starts with empty workers and claimed_files."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        assert len(coordinator.workers) == 0
        assert len(coordinator.claimed_files) == 0

    def test_progress_file_path(self):
        """Progress file is in spec_dir."""
        spec_dir = Path("/tmp/test-spec")
        coordinator = SwarmCoordinator(
            spec_dir=spec_dir,
            project_dir=Path("/tmp/test-project"),
        )

        assert coordinator.progress_file == spec_dir / "parallel_progress.json"


class TestGetAvailableChunks:
    """Tests for get_available_chunks method."""

    def test_returns_empty_without_plan(self):
        """Returns empty list when no plan loaded."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        assert coordinator.get_available_chunks() == []

    def test_returns_pending_chunks_from_available_phases(self):
        """Returns pending chunks from phases with met dependencies."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        # Create plan with one phase (no dependencies)
        plan = ImplementationPlan(
            feature="Test",
            workflow_type=WorkflowType.FEATURE,
            services_involved=["backend"],
        )

        chunk = Chunk(
            id="chunk-1",
            description="Test chunk",
            status=ChunkStatus.PENDING,
        )

        phase = Phase(
            phase=1,
            name="Test Phase",
            chunks=[chunk],
            depends_on=[],
        )

        plan.phases = [phase]
        coordinator.plan = plan

        available = coordinator.get_available_chunks()

        assert len(available) == 1
        assert available[0] == (phase, chunk)

    def test_excludes_completed_chunks(self):
        """Excludes chunks that are already completed."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        plan = ImplementationPlan(
            feature="Test",
            workflow_type=WorkflowType.FEATURE,
            services_involved=["backend"],
        )

        chunk = Chunk(
            id="chunk-1",
            description="Test chunk",
            status=ChunkStatus.COMPLETED,
        )

        phase = Phase(
            phase=1,
            name="Test Phase",
            chunks=[chunk],
            depends_on=[],
        )

        plan.phases = [phase]
        coordinator.plan = plan

        available = coordinator.get_available_chunks()

        assert len(available) == 0

    def test_excludes_chunks_with_claimed_files(self):
        """Excludes chunks whose files are already claimed."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        plan = ImplementationPlan(
            feature="Test",
            workflow_type=WorkflowType.FEATURE,
            services_involved=["backend"],
        )

        chunk = Chunk(
            id="chunk-1",
            description="Test chunk",
            files_to_modify=["app.py"],
            status=ChunkStatus.PENDING,
        )

        phase = Phase(
            phase=1,
            name="Test Phase",
            chunks=[chunk],
            depends_on=[],
        )

        plan.phases = [phase]
        coordinator.plan = plan

        # Claim the file
        coordinator.claimed_files["app.py"] = "other-worker"

        available = coordinator.get_available_chunks()

        assert len(available) == 0


class TestClaimChunk:
    """Tests for claim_chunk method."""

    def test_claims_chunk_successfully(self):
        """Successfully claims an unclaimed chunk."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        plan = ImplementationPlan(
            feature="Test",
            workflow_type=WorkflowType.FEATURE,
            services_involved=["backend"],
        )

        chunk = Chunk(
            id="chunk-1",
            description="Test chunk",
            files_to_modify=["file1.py"],
            files_to_create=["file2.py"],
            status=ChunkStatus.PENDING,
        )

        phase = Phase(
            phase=1,
            name="Test Phase",
            chunks=[chunk],
        )

        plan.phases = [phase]
        coordinator.plan = plan

        worktree_path = Path("/tmp/worktree")
        branch_name = "worker-1/chunk-1"

        success = coordinator.claim_chunk(
            "worker-1", phase, chunk, worktree_path, branch_name
        )

        assert success is True
        assert "file1.py" in coordinator.claimed_files
        assert "file2.py" in coordinator.claimed_files
        assert coordinator.claimed_files["file1.py"] == "worker-1"
        assert chunk.status == ChunkStatus.IN_PROGRESS

    def test_fails_to_claim_already_claimed_chunk(self):
        """Fails to claim a chunk that's already claimed."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        plan = ImplementationPlan(
            feature="Test",
            workflow_type=WorkflowType.FEATURE,
            services_involved=["backend"],
        )

        chunk = Chunk(
            id="chunk-1",
            description="Test chunk",
            files_to_modify=["file1.py"],
            status=ChunkStatus.PENDING,
        )

        phase = Phase(
            phase=1,
            name="Test Phase",
            chunks=[chunk],
        )

        plan.phases = [phase]
        coordinator.plan = plan

        # First worker claims
        coordinator.claim_chunk(
            "worker-1", phase, chunk, Path("/tmp/wt1"), "branch-1"
        )

        # Second worker tries to claim same chunk
        success = coordinator.claim_chunk(
            "worker-2", phase, chunk, Path("/tmp/wt2"), "branch-2"
        )

        assert success is False

    def test_fails_when_files_already_claimed(self):
        """Fails when chunk's files are already claimed by another worker."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        plan = ImplementationPlan(
            feature="Test",
            workflow_type=WorkflowType.FEATURE,
            services_involved=["backend"],
        )

        chunk = Chunk(
            id="chunk-1",
            description="Test chunk",
            files_to_modify=["shared.py"],
            status=ChunkStatus.PENDING,
        )

        phase = Phase(
            phase=1,
            name="Test Phase",
            chunks=[chunk],
        )

        plan.phases = [phase]
        coordinator.plan = plan

        # Pre-claim the file
        coordinator.claimed_files["shared.py"] = "other-worker"

        success = coordinator.claim_chunk(
            "worker-1", phase, chunk, Path("/tmp/wt"), "branch-1"
        )

        assert success is False

    def test_creates_worker_assignment(self):
        """Creates WorkerAssignment when claiming chunk."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        plan = ImplementationPlan(
            feature="Test",
            workflow_type=WorkflowType.FEATURE,
            services_involved=["backend"],
        )

        chunk = Chunk(
            id="chunk-1",
            description="Test chunk",
            status=ChunkStatus.PENDING,
        )

        phase = Phase(
            phase=1,
            name="Test Phase",
            chunks=[chunk],
        )

        plan.phases = [phase]
        coordinator.plan = plan

        worktree_path = Path("/tmp/worktree")
        branch_name = "worker-1/chunk-1"

        coordinator.claim_chunk("worker-1", phase, chunk, worktree_path, branch_name)

        assert "worker-1" in coordinator.workers
        assignment = coordinator.workers["worker-1"]
        assert assignment.worker_id == "worker-1"
        assert assignment.chunk_id == "chunk-1"
        assert assignment.branch_name == branch_name
        assert assignment.worktree_path == worktree_path
        assert assignment.status == WorkerStatus.WORKING


class TestReleaseChunk:
    """Tests for release_chunk method."""

    def test_releases_files_on_success(self):
        """Releases claimed files when chunk completes successfully."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        plan = ImplementationPlan(
            feature="Test",
            workflow_type=WorkflowType.FEATURE,
            services_involved=["backend"],
        )

        chunk = Chunk(
            id="chunk-1",
            description="Test chunk",
            files_to_modify=["file1.py"],
            status=ChunkStatus.PENDING,
        )

        phase = Phase(
            phase=1,
            name="Test Phase",
            chunks=[chunk],
        )

        plan.phases = [phase]
        coordinator.plan = plan

        # Claim chunk
        coordinator.claim_chunk(
            "worker-1", phase, chunk, Path("/tmp/wt"), "branch-1"
        )

        # Release chunk
        coordinator.release_chunk("worker-1", "chunk-1", success=True)

        assert "file1.py" not in coordinator.claimed_files
        assert "worker-1" not in coordinator.workers
        assert chunk.status == ChunkStatus.COMPLETED

    def test_marks_chunk_failed_on_failure(self):
        """Marks chunk as failed when released with success=False."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        plan = ImplementationPlan(
            feature="Test",
            workflow_type=WorkflowType.FEATURE,
            services_involved=["backend"],
        )

        chunk = Chunk(
            id="chunk-1",
            description="Test chunk",
            status=ChunkStatus.PENDING,
        )

        phase = Phase(
            phase=1,
            name="Test Phase",
            chunks=[chunk],
        )

        plan.phases = [phase]
        coordinator.plan = plan

        coordinator.claim_chunk(
            "worker-1", phase, chunk, Path("/tmp/wt"), "branch-1"
        )

        coordinator.release_chunk("worker-1", "chunk-1", success=False, output="Error!")

        assert chunk.status == ChunkStatus.FAILED

    def test_ignores_unknown_worker(self):
        """Does nothing when releasing unknown worker."""
        coordinator = SwarmCoordinator(
            spec_dir=Path("/tmp/test-spec"),
            project_dir=Path("/tmp/test-project"),
        )

        # Should not raise
        coordinator.release_chunk("unknown-worker", "chunk-1", success=True)


class TestParallelGroup:
    """Tests for ParallelGroup dataclass."""

    def test_validates_no_file_overlap(self):
        """Raises error when phases have overlapping files."""
        phase1 = Phase(
            phase=1,
            name="Phase 1",
            chunks=[
                Chunk(
                    id="c1",
                    description="Chunk 1",
                    files_to_modify=["shared.py"],
                )
            ],
        )

        phase2 = Phase(
            phase=2,
            name="Phase 2",
            chunks=[
                Chunk(
                    id="c2",
                    description="Chunk 2",
                    files_to_modify=["shared.py"],  # Same file!
                )
            ],
        )

        import pytest
        with pytest.raises(ValueError, match="cannot run in parallel"):
            ParallelGroup(phases=[phase1, phase2], all_dependencies_met=True)

    def test_allows_non_overlapping_files(self):
        """Allows phases with different files."""
        phase1 = Phase(
            phase=1,
            name="Phase 1",
            chunks=[
                Chunk(
                    id="c1",
                    description="Chunk 1",
                    files_to_modify=["file1.py"],
                )
            ],
        )

        phase2 = Phase(
            phase=2,
            name="Phase 2",
            chunks=[
                Chunk(
                    id="c2",
                    description="Chunk 2",
                    files_to_modify=["file2.py"],
                )
            ],
        )

        # Should not raise
        group = ParallelGroup(phases=[phase1, phase2], all_dependencies_met=True)
        assert len(group.phases) == 2


class TestWorkerAssignment:
    """Tests for WorkerAssignment dataclass."""

    def test_to_dict(self):
        """Converts to dictionary correctly."""
        assignment = WorkerAssignment(
            worker_id="worker-1",
            phase_id=1,
            chunk_id="chunk-1",
            branch_name="worker-1/chunk-1",
            worktree_path=Path("/tmp/worktree"),
            status=WorkerStatus.WORKING,
            started_at="2024-01-01T10:00:00",
        )

        result = assignment.to_dict()

        assert result["worker_id"] == "worker-1"
        assert result["phase_id"] == 1
        assert result["chunk_id"] == "chunk-1"
        assert result["branch_name"] == "worker-1/chunk-1"
        assert result["worktree_path"] == "/tmp/worktree"
        assert result["status"] == "working"
        assert result["started_at"] == "2024-01-01T10:00:00"
        assert result["completed_at"] is None


class TestWorkerStatus:
    """Tests for WorkerStatus enum."""

    def test_status_values(self):
        """Has expected status values."""
        assert WorkerStatus.IDLE.value == "idle"
        assert WorkerStatus.WORKING.value == "working"
        assert WorkerStatus.COMPLETED.value == "completed"
        assert WorkerStatus.FAILED.value == "failed"


# Legacy test functions for backwards compatibility
def test_coordinator_initialization():
    """Test coordinator can be initialized."""
    spec_dir = Path("/tmp/test-spec")
    project_dir = Path("/tmp/test-project")

    coordinator = SwarmCoordinator(
        spec_dir=spec_dir,
        project_dir=project_dir,
        max_workers=2,
    )

    assert coordinator.max_workers == 2
    assert coordinator.spec_dir == spec_dir
    assert coordinator.project_dir == project_dir
    assert len(coordinator.workers) == 0
    assert len(coordinator.claimed_files) == 0


def run_tests():
    """Run all tests."""
    print("\nTesting Multi-Agent Parallelism Coordinator")
    print("=" * 60)

    try:
        test_coordinator_initialization()

        print("=" * 60)
        print("✓ All tests passed!")
        return 0

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
