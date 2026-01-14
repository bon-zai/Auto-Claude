"""Native Auto Claude methodology runner.

This module implements the MethodologyRunner Protocol for the Native Auto Claude
methodology. It wraps the existing spec_runner.py and agent implementations
to provide a plugin-compatible interface.

Architecture Source: architecture.md#Native-Plugin-Structure
Story Reference: Story 2.1 - Create Native Methodology Plugin Structure
"""

from apps.backend.methodologies.protocols import (
    Artifact,
    Checkpoint,
    CheckpointStatus,
    Phase,
    PhaseResult,
    PhaseStatus,
    RunContext,
)


class NativeRunner:
    """MethodologyRunner implementation for Native Auto Claude methodology.

    This class implements the MethodologyRunner Protocol, providing the interface
    for the plugin framework to execute the Native methodology.

    The Native methodology follows a 6-phase pipeline:
    1. Discovery - Gather project context and user requirements
    2. Requirements - Structure and validate requirements
    3. Context - Build codebase context for implementation
    4. Spec - Generate specification document
    5. Plan - Create implementation plan with subtasks
    6. Validate - Validate spec completeness

    Implementation Note:
        The actual phase execution logic will be implemented in Story 2.2.
        This stub provides the Protocol interface for framework integration.

    Example:
        runner = NativeRunner()
        runner.initialize(context)
        phases = runner.get_phases()
        for phase in phases:
            result = runner.execute_phase(phase.id)
    """

    def __init__(self) -> None:
        """Initialize NativeRunner instance."""
        self._context: RunContext | None = None
        self._phases: list[Phase] = []
        self._checkpoints: list[Checkpoint] = []
        self._artifacts: list[Artifact] = []
        self._initialized: bool = False

    def initialize(self, context: RunContext) -> None:
        """Initialize the runner with framework context.

        Sets up the runner with access to framework services and
        initializes phase, checkpoint, and artifact definitions.

        Args:
            context: RunContext with access to all framework services

        Raises:
            RuntimeError: If runner is already initialized
        """
        if self._initialized:
            raise RuntimeError("NativeRunner already initialized")

        self._context = context
        self._init_phases()
        self._init_checkpoints()
        self._init_artifacts()
        self._initialized = True

    def get_phases(self) -> list[Phase]:
        """Return all phase definitions for the Native methodology.

        Returns:
            List of Phase objects defining the 6-phase pipeline:
            discovery, requirements, context, spec, plan, validate

        Raises:
            RuntimeError: If runner has not been initialized
        """
        self._ensure_initialized()
        return self._phases.copy()

    def execute_phase(self, phase_id: str) -> PhaseResult:
        """Execute a specific phase of the Native methodology.

        Args:
            phase_id: ID of the phase to execute (discovery, requirements,
                     context, spec, plan, or validate)

        Returns:
            PhaseResult indicating success/failure and any artifacts produced

        Raises:
            RuntimeError: If runner has not been initialized
            ValueError: If phase_id is not recognized

        Note:
            Full implementation will be added in Story 2.2.
            This stub returns a placeholder result.
        """
        self._ensure_initialized()

        # Find the phase
        phase = self._find_phase(phase_id)
        if phase is None:
            return PhaseResult(
                success=False,
                phase_id=phase_id,
                error=f"Unknown phase: {phase_id}",
            )

        # Update phase status
        phase.status = PhaseStatus.IN_PROGRESS

        # TODO: Story 2.2 - Implement actual phase execution
        # This stub returns a placeholder success result
        phase.status = PhaseStatus.COMPLETED
        return PhaseResult(
            success=True,
            phase_id=phase_id,
            message=f"Phase '{phase.name}' completed (stub implementation)",
            artifacts=[],
        )

    def get_checkpoints(self) -> list[Checkpoint]:
        """Return checkpoint definitions for Semi-Auto mode.

        Returns:
            List of Checkpoint objects defining the 3 pause points:
            after_planning, after_spec, after_validation

        Raises:
            RuntimeError: If runner has not been initialized
        """
        self._ensure_initialized()
        return self._checkpoints.copy()

    def get_artifacts(self) -> list[Artifact]:
        """Return artifact definitions produced by the Native methodology.

        Returns:
            List of Artifact objects defining methodology outputs:
            requirements.json, context.json, spec.md, implementation_plan.json

        Raises:
            RuntimeError: If runner has not been initialized
        """
        self._ensure_initialized()
        return self._artifacts.copy()

    def _ensure_initialized(self) -> None:
        """Ensure the runner has been initialized.

        Raises:
            RuntimeError: If runner has not been initialized
        """
        if not self._initialized:
            raise RuntimeError("NativeRunner not initialized. Call initialize() first.")

    def _find_phase(self, phase_id: str) -> Phase | None:
        """Find a phase by its ID.

        Args:
            phase_id: ID of the phase to find

        Returns:
            Phase object if found, None otherwise
        """
        for phase in self._phases:
            if phase.id == phase_id:
                return phase
        return None

    def _init_phases(self) -> None:
        """Initialize phase definitions for the Native methodology."""
        self._phases = [
            Phase(
                id="discovery",
                name="Discovery",
                description="Gather project context and user requirements",
                order=1,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
            Phase(
                id="requirements",
                name="Requirements",
                description="Structure and validate requirements",
                order=2,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
            Phase(
                id="context",
                name="Context",
                description="Build codebase context for implementation",
                order=3,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
            Phase(
                id="spec",
                name="Specification",
                description="Generate specification document",
                order=4,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
            Phase(
                id="plan",
                name="Planning",
                description="Create implementation plan with subtasks",
                order=5,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
            Phase(
                id="validate",
                name="Validation",
                description="Validate spec completeness",
                order=6,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
        ]

    def _init_checkpoints(self) -> None:
        """Initialize checkpoint definitions for Semi-Auto mode."""
        self._checkpoints = [
            Checkpoint(
                id="after_planning",
                name="Planning Review",
                description="Review implementation plan before coding",
                phase_id="plan",
                status=CheckpointStatus.PENDING,
                requires_approval=True,
            ),
            Checkpoint(
                id="after_spec",
                name="Specification Review",
                description="Review specification before planning",
                phase_id="spec",
                status=CheckpointStatus.PENDING,
                requires_approval=True,
            ),
            Checkpoint(
                id="after_validation",
                name="Validation Review",
                description="Review validation results before completion",
                phase_id="validate",
                status=CheckpointStatus.PENDING,
                requires_approval=True,
            ),
        ]

    def _init_artifacts(self) -> None:
        """Initialize artifact definitions for the Native methodology."""
        self._artifacts = [
            Artifact(
                id="requirements-json",
                artifact_type="json",
                name="Requirements",
                file_path="requirements.json",
                phase_id="discovery",
                content_type="application/json",
            ),
            Artifact(
                id="context-json",
                artifact_type="json",
                name="Context",
                file_path="context.json",
                phase_id="context",
                content_type="application/json",
            ),
            Artifact(
                id="spec-md",
                artifact_type="markdown",
                name="Specification",
                file_path="spec.md",
                phase_id="spec",
                content_type="text/markdown",
            ),
            Artifact(
                id="implementation-plan-json",
                artifact_type="json",
                name="Implementation Plan",
                file_path="implementation_plan.json",
                phase_id="plan",
                content_type="application/json",
            ),
        ]
