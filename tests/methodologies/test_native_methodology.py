"""Tests for the Native methodology plugin structure.

Tests manifest validation, NativeRunner Protocol compliance, and plugin structure.
Story Reference: Story 2.1 - Create Native Methodology Plugin Structure
"""

import pytest
from pathlib import Path
from typing import Any

# Project root directory for file path resolution
PROJECT_ROOT = Path(__file__).parent.parent.parent
NATIVE_METHODOLOGY_DIR = PROJECT_ROOT / "apps" / "backend" / "methodologies" / "native"


# =============================================================================
# Shared Fixtures
# =============================================================================


@pytest.fixture
def mock_context() -> Any:
    """Create a mock RunContext for testing.

    Returns:
        A fully configured mock RunContext with all required services.
    """
    from apps.backend.methodologies.protocols import (
        RunContext,
        TaskConfig,
        ComplexityLevel,
        ExecutionMode,
    )

    class MockWorkspace:
        def get_project_root(self) -> str:
            return "/mock/project"

    class MockMemory:
        def get_context(self, query: str) -> str:
            return "mock context"

    class MockProgress:
        def update(self, phase_id: str, progress: float, message: str) -> None:
            pass

    class MockCheckpoint:
        def create_checkpoint(self, checkpoint_id: str, data: dict[str, Any]) -> None:
            pass

    class MockLLM:
        def generate(self, prompt: str) -> str:
            return "mock response"

    return RunContext(
        workspace=MockWorkspace(),
        memory=MockMemory(),
        progress=MockProgress(),
        checkpoint=MockCheckpoint(),
        llm=MockLLM(),
        task_config=TaskConfig(
            complexity=ComplexityLevel.STANDARD,
            execution_mode=ExecutionMode.FULL_AUTO,
            task_id="test-task",
            task_name="Test Task",
        ),
    )


@pytest.fixture
def initialized_runner(mock_context: Any) -> Any:
    """Create and initialize a NativeRunner for testing.

    Args:
        mock_context: The mock RunContext fixture.

    Returns:
        An initialized NativeRunner instance.
    """
    from apps.backend.methodologies.native import NativeRunner

    runner = NativeRunner()
    runner.initialize(mock_context)
    return runner


# =============================================================================
# Plugin Structure Tests
# =============================================================================


class TestNativePluginStructure:
    """Test that the Native methodology plugin structure is complete."""

    def test_native_directory_exists(self):
        """Test that the native methodology directory exists."""
        assert NATIVE_METHODOLOGY_DIR.exists(), f"Native methodology directory not found: {NATIVE_METHODOLOGY_DIR}"
        assert NATIVE_METHODOLOGY_DIR.is_dir()

    def test_manifest_yaml_exists(self):
        """Test that manifest.yaml exists in native methodology."""
        manifest_path = NATIVE_METHODOLOGY_DIR / "manifest.yaml"
        assert manifest_path.exists(), f"manifest.yaml not found: {manifest_path}"

    def test_methodology_py_exists(self):
        """Test that methodology.py exists in native methodology."""
        methodology_path = NATIVE_METHODOLOGY_DIR / "methodology.py"
        assert methodology_path.exists(), f"methodology.py not found: {methodology_path}"

    def test_init_py_exists(self):
        """Test that __init__.py exists in native methodology."""
        init_path = NATIVE_METHODOLOGY_DIR / "__init__.py"
        assert init_path.exists(), f"__init__.py not found: {init_path}"


# =============================================================================
# Manifest Validation Tests
# =============================================================================


class TestNativeManifestValidation:
    """Test that the Native methodology manifest validates correctly."""

    def test_manifest_loads_without_error(self):
        """Test that manifest.yaml can be loaded and validated."""
        from apps.backend.methodologies.manifest import load_manifest

        manifest_path = NATIVE_METHODOLOGY_DIR / "manifest.yaml"
        manifest = load_manifest(manifest_path)
        assert manifest is not None

    def test_manifest_name_is_native(self):
        """Test that manifest name is 'native'."""
        from apps.backend.methodologies.manifest import load_manifest

        manifest_path = NATIVE_METHODOLOGY_DIR / "manifest.yaml"
        manifest = load_manifest(manifest_path)
        assert manifest.name == "native"

    def test_manifest_version_is_valid(self):
        """Test that manifest has a valid version string."""
        from apps.backend.methodologies.manifest import load_manifest

        manifest_path = NATIVE_METHODOLOGY_DIR / "manifest.yaml"
        manifest = load_manifest(manifest_path)
        assert manifest.version == "1.0.0"

    def test_manifest_entry_point_is_valid(self):
        """Test that manifest entry_point points to NativeRunner."""
        from apps.backend.methodologies.manifest import load_manifest

        manifest_path = NATIVE_METHODOLOGY_DIR / "manifest.yaml"
        manifest = load_manifest(manifest_path)
        assert manifest.entry_point == "methodology.NativeRunner"

    def test_manifest_has_six_phases(self):
        """Test that manifest defines exactly 6 phases."""
        from apps.backend.methodologies.manifest import load_manifest

        manifest_path = NATIVE_METHODOLOGY_DIR / "manifest.yaml"
        manifest = load_manifest(manifest_path)
        assert len(manifest.phases) == 6

    def test_manifest_phase_ids_are_correct(self):
        """Test that phases have the correct IDs per AC #2."""
        from apps.backend.methodologies.manifest import load_manifest

        manifest_path = NATIVE_METHODOLOGY_DIR / "manifest.yaml"
        manifest = load_manifest(manifest_path)

        expected_phase_ids = [
            "discovery",
            "requirements",
            "context",
            "spec",
            "plan",
            "validate",
        ]
        actual_phase_ids = [phase.id for phase in manifest.phases]
        assert actual_phase_ids == expected_phase_ids

    def test_manifest_has_checkpoints(self):
        """Test that manifest defines checkpoints for Semi-Auto mode."""
        from apps.backend.methodologies.manifest import load_manifest

        manifest_path = NATIVE_METHODOLOGY_DIR / "manifest.yaml"
        manifest = load_manifest(manifest_path)
        assert len(manifest.checkpoints) == 3

    def test_manifest_checkpoint_references_valid_phases(self):
        """Test that all checkpoints reference valid phases."""
        from apps.backend.methodologies.manifest import load_manifest

        manifest_path = NATIVE_METHODOLOGY_DIR / "manifest.yaml"
        manifest = load_manifest(manifest_path)

        phase_ids = {phase.id for phase in manifest.phases}
        for checkpoint in manifest.checkpoints:
            assert checkpoint.phase in phase_ids, (
                f"Checkpoint '{checkpoint.id}' references non-existent phase: '{checkpoint.phase}'"
            )


# =============================================================================
# Import Tests
# =============================================================================


class TestNativeRunnerImport:
    """Test that NativeRunner can be imported correctly."""

    def test_native_runner_importable_from_module(self):
        """Test that NativeRunner can be imported from methodology module."""
        from apps.backend.methodologies.native.methodology import NativeRunner

        assert NativeRunner is not None

    def test_native_runner_importable_from_package(self):
        """Test that NativeRunner can be imported from package __init__."""
        from apps.backend.methodologies.native import NativeRunner

        assert NativeRunner is not None

    def test_native_runner_is_class(self):
        """Test that NativeRunner is a class."""
        from apps.backend.methodologies.native import NativeRunner

        assert isinstance(NativeRunner, type)


# =============================================================================
# Protocol Compliance Tests
# =============================================================================


class TestNativeRunnerProtocolCompliance:
    """Test that NativeRunner implements the MethodologyRunner Protocol."""

    def test_native_runner_is_methodology_runner(self):
        """Test NativeRunner implements MethodologyRunner Protocol."""
        from apps.backend.methodologies.protocols import MethodologyRunner
        from apps.backend.methodologies.native import NativeRunner

        runner = NativeRunner()
        assert isinstance(runner, MethodologyRunner)

    def test_native_runner_has_initialize_method(self):
        """Test NativeRunner has initialize method."""
        from apps.backend.methodologies.native import NativeRunner

        assert hasattr(NativeRunner, "initialize")
        assert callable(getattr(NativeRunner, "initialize"))

    def test_native_runner_has_get_phases_method(self):
        """Test NativeRunner has get_phases method."""
        from apps.backend.methodologies.native import NativeRunner

        assert hasattr(NativeRunner, "get_phases")
        assert callable(getattr(NativeRunner, "get_phases"))

    def test_native_runner_has_execute_phase_method(self):
        """Test NativeRunner has execute_phase method."""
        from apps.backend.methodologies.native import NativeRunner

        assert hasattr(NativeRunner, "execute_phase")
        assert callable(getattr(NativeRunner, "execute_phase"))

    def test_native_runner_has_get_checkpoints_method(self):
        """Test NativeRunner has get_checkpoints method."""
        from apps.backend.methodologies.native import NativeRunner

        assert hasattr(NativeRunner, "get_checkpoints")
        assert callable(getattr(NativeRunner, "get_checkpoints"))

    def test_native_runner_has_get_artifacts_method(self):
        """Test NativeRunner has get_artifacts method."""
        from apps.backend.methodologies.native import NativeRunner

        assert hasattr(NativeRunner, "get_artifacts")
        assert callable(getattr(NativeRunner, "get_artifacts"))


# =============================================================================
# Initialization Tests
# =============================================================================


class TestNativeRunnerInitialization:
    """Test NativeRunner initialization behavior."""

    def test_runner_not_initialized_before_initialize(self):
        """Test runner raises error if used before initialization."""
        from apps.backend.methodologies.native import NativeRunner

        runner = NativeRunner()
        with pytest.raises(RuntimeError, match="not initialized"):
            runner.get_phases()

    def test_runner_initializes_with_context(self, mock_context):
        """Test runner initializes successfully with RunContext."""
        from apps.backend.methodologies.native import NativeRunner

        runner = NativeRunner()
        runner.initialize(mock_context)
        # Should not raise after initialization
        phases = runner.get_phases()
        assert len(phases) == 6

    def test_runner_cannot_initialize_twice(self, mock_context):
        """Test runner raises error if initialized twice."""
        from apps.backend.methodologies.native import NativeRunner

        runner = NativeRunner()
        runner.initialize(mock_context)

        with pytest.raises(RuntimeError, match="already initialized"):
            runner.initialize(mock_context)


# =============================================================================
# Phase Tests
# =============================================================================


class TestNativeRunnerPhases:
    """Test NativeRunner phase definitions."""

    def test_get_phases_returns_list(self, initialized_runner):
        """Test get_phases returns a list."""
        phases = initialized_runner.get_phases()
        assert isinstance(phases, list)

    def test_get_phases_returns_six_phases(self, initialized_runner):
        """Test get_phases returns exactly 6 phases."""
        phases = initialized_runner.get_phases()
        assert len(phases) == 6

    def test_phases_have_correct_order(self, initialized_runner):
        """Test phases are in correct execution order."""
        phases = initialized_runner.get_phases()
        orders = [phase.order for phase in phases]
        assert orders == [1, 2, 3, 4, 5, 6]

    def test_phases_have_pending_status_initially(self, initialized_runner):
        """Test all phases start with PENDING status."""
        from apps.backend.methodologies.protocols import PhaseStatus

        phases = initialized_runner.get_phases()
        for phase in phases:
            assert phase.status == PhaseStatus.PENDING

    def test_phases_are_not_optional(self, initialized_runner):
        """Test all phases are required (not optional)."""
        phases = initialized_runner.get_phases()
        for phase in phases:
            assert phase.is_optional is False


# =============================================================================
# Checkpoint Tests
# =============================================================================


class TestNativeRunnerCheckpoints:
    """Test NativeRunner checkpoint definitions."""

    def test_get_checkpoints_returns_list(self, initialized_runner):
        """Test get_checkpoints returns a list."""
        checkpoints = initialized_runner.get_checkpoints()
        assert isinstance(checkpoints, list)

    def test_get_checkpoints_returns_three_checkpoints(self, initialized_runner):
        """Test get_checkpoints returns exactly 3 checkpoints."""
        checkpoints = initialized_runner.get_checkpoints()
        assert len(checkpoints) == 3

    def test_checkpoints_have_pending_status_initially(self, initialized_runner):
        """Test all checkpoints start with PENDING status."""
        from apps.backend.methodologies.protocols import CheckpointStatus

        checkpoints = initialized_runner.get_checkpoints()
        for checkpoint in checkpoints:
            assert checkpoint.status == CheckpointStatus.PENDING

    def test_checkpoints_require_approval(self, initialized_runner):
        """Test all checkpoints require approval."""
        checkpoints = initialized_runner.get_checkpoints()
        for checkpoint in checkpoints:
            assert checkpoint.requires_approval is True

    def test_checkpoints_reference_valid_phase_ids(self, initialized_runner):
        """Test checkpoints reference phase IDs that exist in phases."""
        phases = initialized_runner.get_phases()
        checkpoints = initialized_runner.get_checkpoints()

        phase_ids = {phase.id for phase in phases}
        for checkpoint in checkpoints:
            assert checkpoint.phase_id in phase_ids, (
                f"Checkpoint '{checkpoint.id}' references invalid phase: '{checkpoint.phase_id}'"
            )


# =============================================================================
# Artifact Tests
# =============================================================================


class TestNativeRunnerArtifacts:
    """Test NativeRunner artifact definitions."""

    def test_get_artifacts_returns_list(self, initialized_runner):
        """Test get_artifacts returns a list."""
        artifacts = initialized_runner.get_artifacts()
        assert isinstance(artifacts, list)

    def test_get_artifacts_returns_four_artifacts(self, initialized_runner):
        """Test get_artifacts returns exactly 4 artifacts."""
        artifacts = initialized_runner.get_artifacts()
        assert len(artifacts) == 4

    def test_artifacts_have_expected_ids(self, initialized_runner):
        """Test artifacts have the expected IDs."""
        artifacts = initialized_runner.get_artifacts()

        expected_ids = {
            "requirements-json",
            "context-json",
            "spec-md",
            "implementation-plan-json",
        }
        actual_ids = {artifact.id for artifact in artifacts}
        assert actual_ids == expected_ids

    def test_artifacts_have_file_paths(self, initialized_runner):
        """Test all artifacts have file paths defined."""
        artifacts = initialized_runner.get_artifacts()

        for artifact in artifacts:
            assert artifact.file_path, f"Artifact '{artifact.id}' missing file_path"


# =============================================================================
# Phase Execution Tests
# =============================================================================


class TestNativeRunnerPhaseExecution:
    """Test NativeRunner phase execution (stub implementation).

    Note: execute_phase() returns stub results in Story 2.1.
    Full implementation will be added in Story 2.2.
    """

    def test_execute_phase_returns_phase_result(self, initialized_runner):
        """Test execute_phase returns a PhaseResult."""
        from apps.backend.methodologies.protocols import PhaseResult

        result = initialized_runner.execute_phase("discovery")
        assert isinstance(result, PhaseResult)

    def test_execute_phase_returns_success_for_valid_phase(self, initialized_runner):
        """Test execute_phase returns success for valid phase ID."""
        result = initialized_runner.execute_phase("discovery")
        assert result.success is True
        assert result.phase_id == "discovery"

    def test_execute_phase_returns_failure_for_unknown_phase(self, initialized_runner):
        """Test execute_phase returns failure for unknown phase ID."""
        result = initialized_runner.execute_phase("nonexistent")
        assert result.success is False
        assert "Unknown phase" in result.error

    def test_execute_phase_requires_initialization(self):
        """Test execute_phase raises error if not initialized."""
        from apps.backend.methodologies.native import NativeRunner

        runner = NativeRunner()
        with pytest.raises(RuntimeError, match="not initialized"):
            runner.execute_phase("discovery")
