"""BMAD (Business Model Agile Development) methodology runner.

This module implements the MethodologyRunner Protocol for the BMAD methodology.
BMAD is a structured approach to software development that emphasizes
PRD creation, architecture design, epic/story planning, and iterative development.

Architecture Source: architecture.md#BMAD-Plugin-Structure
Story Reference: Story 6.1 - Create BMAD Methodology Plugin Structure
"""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Coroutine, TypeVar

from apps.backend.core.debug import (
    debug,
    debug_section,
    debug_success,
    debug_error,
    debug_warning,
    is_debug_enabled,
)
from apps.backend.methodologies.protocols import (
    Artifact,
    Checkpoint,
    CheckpointStatus,
    ComplexityLevel,
    Phase,
    PhaseResult,
    PhaseStatus,
    ProgressCallback,
    RunContext,
    TaskConfig,
)

# Type hints for optional dependencies
if TYPE_CHECKING:
    from apps.backend.task_logger import LogPhase

logger = logging.getLogger(__name__)

# Type variable for async return types
T = TypeVar("T")


class BMADRunner:
    """MethodologyRunner implementation for BMAD methodology.

    This class implements the MethodologyRunner Protocol, providing the interface
    for the plugin framework to execute the BMAD methodology.

    The BMAD methodology follows a 7-phase pipeline:
    1. Analyze - Project analysis and context gathering
    2. PRD - Product Requirements Document creation
    3. Architecture - Architecture design and documentation
    4. Epics - Epic and story creation
    5. Stories - Story preparation and refinement
    6. Dev - Development/implementation
    7. Review - Code review

    Complexity Levels (Story 6.8):
        - QUICK: Skips PRD/Architecture phases for faster iteration
          Phases: analyze → epics → stories → dev → review
        - STANDARD: Full 7-phase pipeline (default)
          Phases: analyze → prd → architecture → epics → stories → dev → review
        - COMPLEX: Full pipeline with additional validation depth
          Phases: analyze → prd → architecture → epics → stories → dev → review
          (with deeper analysis and self-critique in each phase)

    Artifact Storage (Story 6.9):
        All artifacts are stored in task-scoped directories:
        `.auto-claude/specs/{task-id}/bmad/`

        This enables parallel execution of multiple BMAD tasks without
        artifact collisions.

    Story Reference: Story 6.1 - Create BMAD Methodology Plugin Structure
    Story Reference: Story 6.8 - Implement BMAD Complexity Level Support
    Story Reference: Story 6.9 - Task-Scoped Output Directories
    """

    # BMAD output subdirectory name within spec_dir
    BMAD_OUTPUT_SUBDIR = "bmad"

    # Default model for BMAD agent sessions
    _DEFAULT_AGENT_MODEL = "claude-sonnet-4-20250514"

    # Phase configuration per complexity level (Story 6.8)
    # Maps ComplexityLevel to list of phase IDs that should be executed
    COMPLEXITY_PHASES: dict[ComplexityLevel, list[str]] = {
        ComplexityLevel.QUICK: [
            "analyze",
            "epics",
            "stories",
            "dev",
            "review",
        ],
        ComplexityLevel.STANDARD: [
            "analyze",
            "prd",
            "architecture",
            "epics",
            "stories",
            "dev",
            "review",
        ],
        ComplexityLevel.COMPLEX: [
            "analyze",
            "prd",
            "architecture",
            "epics",
            "stories",
            "dev",
            "review",
        ],
    }

    # Checkpoints per complexity level (Story 6.8)
    # Quick has fewer checkpoints for faster iteration
    COMPLEXITY_CHECKPOINTS: dict[ComplexityLevel, list[str]] = {
        ComplexityLevel.QUICK: [
            "after_epics",
            "after_review",
        ],
        ComplexityLevel.STANDARD: [
            "after_prd",
            "after_architecture",
            "after_epics",
            "after_story",
            "after_review",
        ],
        ComplexityLevel.COMPLEX: [
            "after_prd",
            "after_architecture",
            "after_epics",
            "after_story",
            "after_review",
        ],
    }

    def __init__(self) -> None:
        """Initialize BMADRunner instance."""
        self._context: RunContext | None = None
        self._phases: list[Phase] = []
        self._checkpoints: list[Checkpoint] = []
        self._artifacts: list[Artifact] = []
        self._initialized: bool = False
        # Context attributes for phase execution
        self._project_dir: str = ""
        self._spec_dir: Path | None = None
        self._task_config: TaskConfig | None = None
        self._complexity: ComplexityLevel | None = None
        # Progress callback for current execution
        self._current_progress_callback: ProgressCallback | None = None
        # Task-scoped output directory (Story 6.9)
        self._output_dir: Path | None = None

    def _reset_state(self) -> None:
        """Reset runner state for re-initialization.

        Called when initialize() is invoked on an already-initialized runner
        to support runner reuse across multiple tasks.
        """
        self._context = None
        self._phases = []
        self._checkpoints = []
        self._artifacts = []
        self._initialized = False
        self._project_dir = ""
        self._spec_dir = None
        self._task_config = None
        self._complexity = None
        self._current_progress_callback = None
        self._output_dir = None

    def _run_async(self, coro: Coroutine[Any, Any, T]) -> T:
        """Run an async coroutine from sync context.

        Handles the case where we might already be in an async context
        (e.g., when called from FullAutoExecutor).

        Args:
            coro: The coroutine to run

        Returns:
            The result of the coroutine

        Note:
            Uses asyncio.run() which creates a new event loop. This is
            preferred over get_event_loop() which is deprecated in Python 3.10+.
        """
        try:
            # Check if we're already in an async context
            asyncio.get_running_loop()
            # We're in an async context, run in thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                return executor.submit(asyncio.run, coro).result()
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(coro)

    def initialize(self, context: RunContext) -> None:
        """Initialize the runner with framework context.

        Sets up the runner with access to framework services and
        initializes phase, checkpoint, and artifact definitions.

        This method can be called multiple times to reinitialize the runner
        for a new task context. Previous state is reset.

        Args:
            context: RunContext with access to all framework services
        """
        debug_section("bmad.methodology", "INITIALIZING BMAD METHODOLOGY")

        # Reset state if already initialized (support runner reuse)
        if self._initialized:
            debug("bmad.methodology", "Resetting state for re-initialization")
            self._reset_state()

        self._context = context
        self._project_dir = context.workspace.get_project_root()
        self._task_config = context.task_config
        self._complexity = context.task_config.complexity

        # Get spec_dir from task_config metadata if available
        spec_dir_str = context.task_config.metadata.get("spec_dir")
        if spec_dir_str:
            self._spec_dir = Path(spec_dir_str)

        debug(
            "bmad.methodology",
            "Configuration loaded",
            project_dir=self._project_dir,
            spec_dir=str(self._spec_dir) if self._spec_dir else "(none)",
            complexity=self._complexity.value if self._complexity else "(default)",
            task_description=context.task_config.metadata.get("task_description", "(none)")[:100],
        )

        # Story 6.9: Initialize task-scoped output directory
        self._init_output_dir()

        # Initialize BMAD skills in target project
        self._init_skills()

        self._init_phases()
        self._init_checkpoints()
        self._init_artifacts()
        self._initialized = True

        debug_success(
            "bmad.methodology",
            "BMAD methodology initialized",
            enabled_phases=self.get_enabled_phases(),
        )

    def get_phases(self) -> list[Phase]:
        """Return phase definitions for the BMAD methodology.

        Returns phases based on the current complexity level:
        - QUICK: analyze, epics, stories, dev, review (5 phases)
        - STANDARD: analyze, prd, architecture, epics, stories, dev, review (7 phases)
        - COMPLEX: Same as STANDARD with deeper analysis in each phase

        Returns:
            List of Phase objects enabled for the current complexity level

        Raises:
            RuntimeError: If runner has not been initialized

        Story Reference: Story 6.8 - Implement BMAD Complexity Level Support
        """
        self._ensure_initialized()

        # Filter phases based on complexity level (Story 6.8)
        enabled_phase_ids = self.get_enabled_phases()
        filtered_phases = [p for p in self._phases if p.id in enabled_phase_ids]

        # Recompute order for filtered phases
        for i, phase in enumerate(filtered_phases, start=1):
            phase.order = i

        return filtered_phases

    def execute_phase(
        self,
        phase_id: str,
        progress_callback: ProgressCallback | None = None,
    ) -> PhaseResult:
        """Execute a specific phase of the BMAD methodology.

        Delegates to the BMAD workflow integration for each phase.
        Emits ProgressEvents at phase start and end for frontend updates.

        Phases not enabled for the current complexity level are automatically
        skipped with SKIPPED status.

        Args:
            phase_id: ID of the phase to execute (analyze, prd, architecture,
                     epics, stories, dev, review)
            progress_callback: Optional callback invoked during execution for
                     incremental progress reporting

        Returns:
            PhaseResult indicating success/failure and any artifacts produced

        Raises:
            RuntimeError: If runner has not been initialized

        Story Reference: Story 6.8 - Implement BMAD Complexity Level Support
        """
        self._ensure_initialized()

        # Store callback for use during phase execution
        self._current_progress_callback = progress_callback

        # Story 6.8: Check if phase is enabled for current complexity level
        if not self.is_phase_enabled(phase_id):
            complexity = self.get_complexity_level()
            logger.info(
                f"Skipping phase '{phase_id}' - not enabled for {complexity.value} complexity"
            )
            # Mark the phase as skipped in the internal list
            phase = self._find_phase(phase_id)
            if phase:
                phase.status = PhaseStatus.SKIPPED

            return PhaseResult(
                success=True,
                phase_id=phase_id,
                message=f"Phase skipped for {complexity.value} complexity level",
                metadata={
                    "skipped": True,
                    "complexity": complexity.value,
                },
            )

        # Find the phase
        phase = self._find_phase(phase_id)
        if phase is None:
            return PhaseResult(
                success=False,
                phase_id=phase_id,
                error=f"Unknown phase: {phase_id}",
            )

        # Update phase status to IN_PROGRESS
        phase.status = PhaseStatus.IN_PROGRESS

        # Emit start progress event
        if self._context:
            self._context.progress.update(phase_id, 0.0, f"Starting {phase.name}")

        # Execute the phase using the dispatch table
        try:
            result = self._execute_phase_impl(phase_id)

            # Update phase status based on result
            if result.success:
                phase.status = PhaseStatus.COMPLETED
                if self._context:
                    self._context.progress.update(
                        phase_id, 1.0, f"{phase.name} completed"
                    )
            else:
                phase.status = PhaseStatus.FAILED
                if self._context:
                    self._context.progress.update(
                        phase_id, 0.0, f"{phase.name} failed: {result.error}"
                    )

            return result

        except Exception as e:
            phase.status = PhaseStatus.FAILED
            return PhaseResult(
                success=False,
                phase_id=phase_id,
                error=str(e),
            )
        finally:
            # Clear the progress callback after execution
            self._current_progress_callback = None

    def _execute_phase_impl(self, phase_id: str) -> PhaseResult:
        """Dispatch to the appropriate phase implementation.

        Args:
            phase_id: ID of the phase to execute

        Returns:
            PhaseResult from the phase execution
        """
        dispatch = {
            "analyze": self._execute_analyze,
            "prd": self._execute_prd,
            "architecture": self._execute_architecture,
            "epics": self._execute_epics,
            "stories": self._execute_stories,
            "dev": self._execute_dev,
            "review": self._execute_review,
        }

        handler = dispatch.get(phase_id)
        if handler is None:
            return PhaseResult(
                success=False,
                phase_id=phase_id,
                error=f"No implementation for phase: {phase_id}",
            )

        return handler()

    # =========================================================================
    # Phase Implementations using Claude Agent SDK
    # =========================================================================

    def _execute_analyze(self) -> PhaseResult:
        """Execute the project analysis phase via BMAD document-project workflow.

        Uses Claude Agent SDK to run the BMAD document-project workflow which
        analyzes brownfield project structure and creates project documentation.

        Returns:
            PhaseResult with success status and artifacts

        Story Reference: Story 6.2 - Implement BMAD Project Analysis Phase
        """
        from apps.backend.agents.session import run_agent_session
        from apps.backend.core.client import create_client
        from apps.backend.task_logger import LogPhase

        debug_section("bmad.methodology", "ANALYZE PHASE - document-project")

        if self._spec_dir is None:
            debug_error("bmad.methodology", "No spec_dir configured")
            return PhaseResult(
                success=False,
                phase_id="analyze",
                error="No spec_dir configured. Set spec_dir in task_config.metadata.",
            )

        project_dir = Path(self._project_dir)

        debug(
            "bmad.methodology",
            "Phase configuration",
            project_dir=str(project_dir),
            spec_dir=str(self._spec_dir),
        )

        # Report progress
        self._invoke_progress_callback("Starting BMAD document-project workflow...", 10.0)

        try:
            # Get model from task config or use default
            model = (
                self._task_config.metadata.get("model", self._DEFAULT_AGENT_MODEL)
                if self._task_config
                else self._DEFAULT_AGENT_MODEL
            )

            # Create client for BMAD agent
            self._invoke_progress_callback("Creating BMAD agent client...", 20.0)
            debug(
                "bmad.methodology",
                "Creating Claude Agent SDK client",
                model=model,
                agent_type="coder",
            )
            client = create_client(
                project_dir,
                self._spec_dir,
                model=model,
                agent_type="coder",  # Use coder permissions for file operations
                max_thinking_tokens=None,
            )
            debug_success("bmad.methodology", "Client created successfully")

            # The prompt is the BMAD slash command
            prompt = "/bmad:bmm:workflows:document-project"

            debug(
                "bmad.methodology",
                "Invoking BMAD workflow via slash command",
                prompt=prompt,
            )

            # Run agent session
            self._invoke_progress_callback("Running document-project workflow...", 30.0)

            async def _run_analyze():
                debug("bmad.methodology", "Starting agent session...")
                async with client:
                    status, response = await run_agent_session(
                        client,
                        prompt,
                        self._spec_dir,
                        verbose=False,
                        phase=LogPhase.PLANNING,
                    )
                    debug(
                        "bmad.methodology",
                        "Agent session completed",
                        status=status,
                        response_length=len(response) if response else 0,
                    )
                    return status, response

            status, response = self._run_async(_run_analyze())

            self._invoke_progress_callback("Document-project workflow completed", 100.0)

            debug_success(
                "bmad.methodology",
                "ANALYZE phase completed",
                status=status,
            )

            # Check for output artifacts
            # BMAD writes to _bmad-output/project_knowledge/ by default
            # We'll consider it successful if the agent completed
            return PhaseResult(
                success=True,
                phase_id="analyze",
                message="Project documentation created via BMAD workflow",
                metadata={"agent_status": status},
            )

        except Exception as e:
            debug_error("bmad.methodology", f"Project analysis failed: {e}")
            logger.error(f"Project analysis failed: {e}")
            return PhaseResult(
                success=False,
                phase_id="analyze",
                error=f"Project analysis failed: {str(e)}",
            )

    def _execute_prd(self) -> PhaseResult:
        """Execute the PRD creation phase via BMAD create-prd workflow.

        Uses Claude Agent SDK to run the BMAD create-prd workflow which
        creates a Product Requirements Document. For brownfield projects,
        this automatically loads project documentation and adapts the flow.

        Returns:
            PhaseResult with success status and artifacts

        Story Reference: Story 6.3 - Implement BMAD PRD Workflow Integration
        """
        from apps.backend.agents.session import run_agent_session
        from apps.backend.core.client import create_client
        from apps.backend.task_logger import LogPhase

        debug_section("bmad.methodology", "PRD PHASE - create-prd")

        if self._spec_dir is None:
            debug_error("bmad.methodology", "No spec_dir configured")
            return PhaseResult(
                success=False,
                phase_id="prd",
                error="No spec_dir configured. Set spec_dir in task_config.metadata.",
            )

        project_dir = Path(self._project_dir)

        debug(
            "bmad.methodology",
            "Phase configuration",
            project_dir=str(project_dir),
            spec_dir=str(self._spec_dir),
        )

        # Report progress
        self._invoke_progress_callback("Starting BMAD create-prd workflow...", 10.0)

        try:
            # Get model from task config or use default
            model = (
                self._task_config.metadata.get("model", self._DEFAULT_AGENT_MODEL)
                if self._task_config
                else self._DEFAULT_AGENT_MODEL
            )

            # Create client for BMAD agent
            self._invoke_progress_callback("Creating BMAD agent client...", 20.0)
            debug(
                "bmad.methodology",
                "Creating Claude Agent SDK client",
                model=model,
                agent_type="coder",
            )
            client = create_client(
                project_dir,
                self._spec_dir,
                model=model,
                agent_type="coder",
                max_thinking_tokens=None,
            )
            debug_success("bmad.methodology", "Client created successfully")

            # Build the prompt with task description context
            task_description = ""
            if self._task_config:
                task_description = self._task_config.metadata.get("task_description", "")

            # The prompt is the BMAD slash command with optional context
            prompt = "/bmad:bmm:workflows:create-prd"
            if task_description:
                prompt += f"\n\nTask: {task_description}"

            debug(
                "bmad.methodology",
                "Invoking BMAD workflow via slash command",
                prompt=prompt,
                task_description=task_description or "(none)",
            )

            # Run agent session
            self._invoke_progress_callback("Running create-prd workflow...", 30.0)

            async def _run_prd():
                debug("bmad.methodology", "Starting agent session...")
                async with client:
                    status, response = await run_agent_session(
                        client,
                        prompt,
                        self._spec_dir,
                        verbose=False,
                        phase=LogPhase.PLANNING,
                    )
                    debug(
                        "bmad.methodology",
                        "Agent session completed",
                        status=status,
                        response_length=len(response) if response else 0,
                    )
                    return status, response

            status, response = self._run_async(_run_prd())

            self._invoke_progress_callback("PRD workflow completed", 100.0)

            debug_success(
                "bmad.methodology",
                "PRD phase completed",
                status=status,
            )

            return PhaseResult(
                success=True,
                phase_id="prd",
                message="PRD created via BMAD workflow",
                metadata={"agent_status": status},
            )

        except Exception as e:
            debug_error("bmad.methodology", f"PRD creation failed: {e}")
            logger.error(f"PRD creation failed: {e}")
            return PhaseResult(
                success=False,
                phase_id="prd",
                error=f"PRD creation failed: {str(e)}",
            )

    def _execute_architecture(self) -> PhaseResult:
        """Execute the architecture phase via BMAD create-architecture workflow.

        Uses Claude Agent SDK to run the BMAD create-architecture workflow which
        creates architecture decisions document.

        Returns:
            PhaseResult with success status and artifacts

        Story Reference: Story 6.4 - Implement BMAD Architecture Workflow Integration
        """
        from apps.backend.agents.session import run_agent_session
        from apps.backend.core.client import create_client
        from apps.backend.task_logger import LogPhase

        debug_section("bmad.methodology", "ARCHITECTURE PHASE - create-architecture")

        if self._spec_dir is None:
            debug_error("bmad.methodology", "No spec_dir configured")
            return PhaseResult(
                success=False,
                phase_id="architecture",
                error="No spec_dir configured. Set spec_dir in task_config.metadata.",
            )

        project_dir = Path(self._project_dir)

        debug(
            "bmad.methodology",
            "Phase configuration",
            project_dir=str(project_dir),
            spec_dir=str(self._spec_dir),
        )

        # Report progress
        self._invoke_progress_callback("Starting BMAD create-architecture workflow...", 10.0)

        try:
            model = (
                self._task_config.metadata.get("model", self._DEFAULT_AGENT_MODEL)
                if self._task_config
                else self._DEFAULT_AGENT_MODEL
            )

            self._invoke_progress_callback("Creating BMAD agent client...", 20.0)
            debug(
                "bmad.methodology",
                "Creating Claude Agent SDK client",
                model=model,
                agent_type="coder",
            )
            client = create_client(
                project_dir,
                self._spec_dir,
                model=model,
                agent_type="coder",
                max_thinking_tokens=None,
            )
            debug_success("bmad.methodology", "Client created successfully")

            prompt = "/bmad:bmm:workflows:create-architecture"

            debug(
                "bmad.methodology",
                "Invoking BMAD workflow via slash command",
                prompt=prompt,
            )

            self._invoke_progress_callback("Running create-architecture workflow...", 30.0)

            async def _run_architecture():
                debug("bmad.methodology", "Starting agent session...")
                async with client:
                    status, response = await run_agent_session(
                        client,
                        prompt,
                        self._spec_dir,
                        verbose=False,
                        phase=LogPhase.PLANNING,
                    )
                    debug(
                        "bmad.methodology",
                        "Agent session completed",
                        status=status,
                        response_length=len(response) if response else 0,
                    )
                    return status, response

            status, response = self._run_async(_run_architecture())

            self._invoke_progress_callback("Architecture workflow completed", 100.0)

            debug_success(
                "bmad.methodology",
                "ARCHITECTURE phase completed",
                status=status,
            )

            return PhaseResult(
                success=True,
                phase_id="architecture",
                message="Architecture created via BMAD workflow",
                metadata={"agent_status": status},
            )

        except Exception as e:
            debug_error("bmad.methodology", f"Architecture creation failed: {e}")
            logger.error(f"Architecture creation failed: {e}")
            return PhaseResult(
                success=False,
                phase_id="architecture",
                error=f"Architecture creation failed: {str(e)}",
            )

    def _execute_epics(self) -> PhaseResult:
        """Execute the epic and story creation phase via BMAD workflow.

        Uses Claude Agent SDK to run the BMAD create-epics-and-stories workflow
        which transforms PRD + Architecture into implementation-ready stories.

        Returns:
            PhaseResult with success status and artifacts

        Story Reference: Story 6.5 - Implement BMAD Epic and Story Creation
        """
        from apps.backend.agents.session import run_agent_session
        from apps.backend.core.client import create_client
        from apps.backend.task_logger import LogPhase

        debug_section("bmad.methodology", "EPICS PHASE - create-epics-and-stories")

        if self._spec_dir is None:
            debug_error("bmad.methodology", "No spec_dir configured")
            return PhaseResult(
                success=False,
                phase_id="epics",
                error="No spec_dir configured. Set spec_dir in task_config.metadata.",
            )

        project_dir = Path(self._project_dir)

        debug(
            "bmad.methodology",
            "Phase configuration",
            project_dir=str(project_dir),
            spec_dir=str(self._spec_dir),
        )

        self._invoke_progress_callback("Starting BMAD create-epics-and-stories workflow...", 10.0)

        try:
            model = (
                self._task_config.metadata.get("model", self._DEFAULT_AGENT_MODEL)
                if self._task_config
                else self._DEFAULT_AGENT_MODEL
            )

            self._invoke_progress_callback("Creating BMAD agent client...", 20.0)
            debug(
                "bmad.methodology",
                "Creating Claude Agent SDK client",
                model=model,
                agent_type="coder",
            )
            client = create_client(
                project_dir,
                self._spec_dir,
                model=model,
                agent_type="coder",
                max_thinking_tokens=None,
            )
            debug_success("bmad.methodology", "Client created successfully")

            prompt = "/bmad:bmm:workflows:create-epics-and-stories"

            debug(
                "bmad.methodology",
                "Invoking BMAD workflow via slash command",
                prompt=prompt,
            )

            self._invoke_progress_callback("Running create-epics-and-stories workflow...", 30.0)

            async def _run_epics():
                debug("bmad.methodology", "Starting agent session...")
                async with client:
                    status, response = await run_agent_session(
                        client,
                        prompt,
                        self._spec_dir,
                        verbose=False,
                        phase=LogPhase.PLANNING,
                    )
                    debug(
                        "bmad.methodology",
                        "Agent session completed",
                        status=status,
                        response_length=len(response) if response else 0,
                    )
                    return status, response

            status, response = self._run_async(_run_epics())

            self._invoke_progress_callback("Epics and stories workflow completed", 100.0)

            debug_success(
                "bmad.methodology",
                "EPICS phase completed",
                status=status,
            )

            return PhaseResult(
                success=True,
                phase_id="epics",
                message="Epics and stories created via BMAD workflow",
                metadata={"agent_status": status},
            )

        except Exception as e:
            debug_error("bmad.methodology", f"Epics creation failed: {e}")
            logger.error(f"Epics creation failed: {e}")
            return PhaseResult(
                success=False,
                phase_id="epics",
                error=f"Epics creation failed: {str(e)}",
            )

    def _execute_stories(self) -> PhaseResult:
        """Execute the story preparation phase via BMAD create-story workflow.

        Uses Claude Agent SDK to run the BMAD create-story workflow which
        prepares individual stories for development.

        Returns:
            PhaseResult with success status and artifacts

        Story Reference: Story 6.5 - Implement BMAD Epic and Story Creation
        """
        from apps.backend.agents.session import run_agent_session
        from apps.backend.core.client import create_client
        from apps.backend.task_logger import LogPhase

        debug_section("bmad.methodology", "STORIES PHASE - create-story")

        if self._spec_dir is None:
            debug_error("bmad.methodology", "No spec_dir configured")
            return PhaseResult(
                success=False,
                phase_id="stories",
                error="No spec_dir configured. Set spec_dir in task_config.metadata.",
            )

        project_dir = Path(self._project_dir)

        debug(
            "bmad.methodology",
            "Phase configuration",
            project_dir=str(project_dir),
            spec_dir=str(self._spec_dir),
        )

        self._invoke_progress_callback("Starting BMAD create-story workflow...", 10.0)

        try:
            model = (
                self._task_config.metadata.get("model", self._DEFAULT_AGENT_MODEL)
                if self._task_config
                else self._DEFAULT_AGENT_MODEL
            )

            self._invoke_progress_callback("Creating BMAD agent client...", 20.0)
            debug(
                "bmad.methodology",
                "Creating Claude Agent SDK client",
                model=model,
                agent_type="coder",
            )
            client = create_client(
                project_dir,
                self._spec_dir,
                model=model,
                agent_type="coder",
                max_thinking_tokens=None,
            )
            debug_success("bmad.methodology", "Client created successfully")

            prompt = "/bmad:bmm:workflows:create-story"

            debug(
                "bmad.methodology",
                "Invoking BMAD workflow via slash command",
                prompt=prompt,
            )

            self._invoke_progress_callback("Running create-story workflow...", 30.0)

            async def _run_stories():
                debug("bmad.methodology", "Starting agent session...")
                async with client:
                    status, response = await run_agent_session(
                        client,
                        prompt,
                        self._spec_dir,
                        verbose=False,
                        phase=LogPhase.PLANNING,
                    )
                    debug(
                        "bmad.methodology",
                        "Agent session completed",
                        status=status,
                        response_length=len(response) if response else 0,
                    )
                    return status, response

            status, response = self._run_async(_run_stories())

            self._invoke_progress_callback("Story preparation workflow completed", 100.0)

            debug_success(
                "bmad.methodology",
                "STORIES phase completed",
                status=status,
            )

            return PhaseResult(
                success=True,
                phase_id="stories",
                message="Stories prepared via BMAD workflow",
                metadata={"agent_status": status},
            )

        except Exception as e:
            debug_error("bmad.methodology", f"Story preparation failed: {e}")
            logger.error(f"Story preparation failed: {e}")
            return PhaseResult(
                success=False,
                phase_id="stories",
                error=f"Story preparation failed: {str(e)}",
            )

    def _execute_dev(self) -> PhaseResult:
        """Execute the development phase via BMAD dev-story workflow.

        Uses Claude Agent SDK to run the BMAD dev-story workflow which
        implements stories from the backlog.

        Returns:
            PhaseResult with success status and artifacts

        Story Reference: Story 6.6 - Implement BMAD Dev-Story Workflow Integration
        """
        from apps.backend.agents.session import run_agent_session
        from apps.backend.core.client import create_client
        from apps.backend.task_logger import LogPhase

        debug_section("bmad.methodology", "DEV PHASE - dev-story")

        if self._spec_dir is None:
            debug_error("bmad.methodology", "No spec_dir configured")
            return PhaseResult(
                success=False,
                phase_id="dev",
                error="No spec_dir configured. Set spec_dir in task_config.metadata.",
            )

        project_dir = Path(self._project_dir)

        debug(
            "bmad.methodology",
            "Phase configuration",
            project_dir=str(project_dir),
            spec_dir=str(self._spec_dir),
        )

        self._invoke_progress_callback("Starting BMAD dev-story workflow...", 10.0)

        try:
            model = (
                self._task_config.metadata.get("model", self._DEFAULT_AGENT_MODEL)
                if self._task_config
                else self._DEFAULT_AGENT_MODEL
            )

            self._invoke_progress_callback("Creating BMAD agent client...", 20.0)
            debug(
                "bmad.methodology",
                "Creating Claude Agent SDK client",
                model=model,
                agent_type="coder",
            )
            client = create_client(
                project_dir,
                self._spec_dir,
                model=model,
                agent_type="coder",
                max_thinking_tokens=None,
            )
            debug_success("bmad.methodology", "Client created successfully")

            prompt = "/bmad:bmm:workflows:dev-story"

            debug(
                "bmad.methodology",
                "Invoking BMAD workflow via slash command",
                prompt=prompt,
            )

            self._invoke_progress_callback("Running dev-story workflow...", 30.0)

            async def _run_dev():
                debug("bmad.methodology", "Starting agent session...")
                async with client:
                    status, response = await run_agent_session(
                        client,
                        prompt,
                        self._spec_dir,
                        verbose=False,
                        phase=LogPhase.CODING,
                    )
                    debug(
                        "bmad.methodology",
                        "Agent session completed",
                        status=status,
                        response_length=len(response) if response else 0,
                    )
                    return status, response

            status, response = self._run_async(_run_dev())

            self._invoke_progress_callback("Dev-story workflow completed", 100.0)

            debug_success(
                "bmad.methodology",
                "DEV phase completed",
                status=status,
            )

            return PhaseResult(
                success=True,
                phase_id="dev",
                message="Development completed via BMAD workflow",
                metadata={"agent_status": status},
            )

        except Exception as e:
            debug_error("bmad.methodology", f"Dev phase failed: {e}")
            logger.error(f"Dev phase failed: {e}")
            return PhaseResult(
                success=False,
                phase_id="dev",
                error=f"Dev phase failed: {str(e)}",
            )

    def _execute_review(self) -> PhaseResult:
        """Execute the code review phase via BMAD code-review workflow.

        Uses Claude Agent SDK to run the BMAD code-review workflow which
        performs code review on implemented stories.

        Returns:
            PhaseResult with success status and artifacts

        Story Reference: Story 6.7 - Implement BMAD Code Review Workflow Integration
        """
        from apps.backend.agents.session import run_agent_session
        from apps.backend.core.client import create_client
        from apps.backend.task_logger import LogPhase

        debug_section("bmad.methodology", "REVIEW PHASE - code-review")

        if self._spec_dir is None:
            debug_error("bmad.methodology", "No spec_dir configured")
            return PhaseResult(
                success=False,
                phase_id="review",
                error="No spec_dir configured. Set spec_dir in task_config.metadata.",
            )

        project_dir = Path(self._project_dir)

        debug(
            "bmad.methodology",
            "Phase configuration",
            project_dir=str(project_dir),
            spec_dir=str(self._spec_dir),
        )

        self._invoke_progress_callback("Starting BMAD code-review workflow...", 10.0)

        try:
            model = (
                self._task_config.metadata.get("model", self._DEFAULT_AGENT_MODEL)
                if self._task_config
                else self._DEFAULT_AGENT_MODEL
            )

            self._invoke_progress_callback("Creating BMAD agent client...", 20.0)
            debug(
                "bmad.methodology",
                "Creating Claude Agent SDK client",
                model=model,
                agent_type="qa_reviewer",
            )
            client = create_client(
                project_dir,
                self._spec_dir,
                model=model,
                agent_type="qa_reviewer",  # Use QA reviewer permissions for code review
                max_thinking_tokens=None,
            )
            debug_success("bmad.methodology", "Client created successfully")

            prompt = "/bmad:bmm:workflows:code-review"

            debug(
                "bmad.methodology",
                "Invoking BMAD workflow via slash command",
                prompt=prompt,
            )

            self._invoke_progress_callback("Running code-review workflow...", 30.0)

            async def _run_review():
                debug("bmad.methodology", "Starting agent session...")
                async with client:
                    status, response = await run_agent_session(
                        client,
                        prompt,
                        self._spec_dir,
                        verbose=False,
                        phase=LogPhase.VALIDATION,
                    )
                    debug(
                        "bmad.methodology",
                        "Agent session completed",
                        status=status,
                        response_length=len(response) if response else 0,
                    )
                    return status, response

            status, response = self._run_async(_run_review())

            self._invoke_progress_callback("Code review workflow completed", 100.0)

            debug_success(
                "bmad.methodology",
                "REVIEW phase completed",
                status=status,
            )

            return PhaseResult(
                success=True,
                phase_id="review",
                message="Code review completed via BMAD workflow",
                metadata={"agent_status": status},
            )

        except Exception as e:
            debug_error("bmad.methodology", f"Code review failed: {e}")
            logger.error(f"Code review failed: {e}")
            return PhaseResult(
                success=False,
                phase_id="review",
                error=f"Code review failed: {str(e)}",
            )

    # =========================================================================
    # Protocol Implementation
    # =========================================================================

    def get_checkpoints(self) -> list[Checkpoint]:
        """Return checkpoint definitions for Semi-Auto mode.

        Returns checkpoints based on the current complexity level:
        - QUICK: after_epics, after_review (minimal checkpoints for speed)
        - STANDARD/COMPLEX: All checkpoints (after_prd, after_architecture,
          after_epics, after_story, after_review)

        Returns:
            List of Checkpoint objects enabled for the current complexity level

        Raises:
            RuntimeError: If runner has not been initialized

        Story Reference: Story 6.8 - Implement BMAD Complexity Level Support
        """
        self._ensure_initialized()

        # Filter checkpoints based on complexity level (Story 6.8)
        enabled_checkpoint_ids = self.get_enabled_checkpoints()
        filtered_checkpoints = [
            c for c in self._checkpoints if c.id in enabled_checkpoint_ids
        ]

        return filtered_checkpoints

    def get_artifacts(self) -> list[Artifact]:
        """Return artifact definitions produced by the BMAD methodology.

        Returns artifacts based on the current complexity level:
        - QUICK: Excludes PRD and Architecture artifacts
        - STANDARD/COMPLEX: All artifacts included

        Returns:
            List of Artifact objects for enabled phases

        Raises:
            RuntimeError: If runner has not been initialized

        Story Reference: Story 6.8 - Implement BMAD Complexity Level Support
        """
        self._ensure_initialized()

        # Filter artifacts based on complexity level (Story 6.8)
        # Only include artifacts for phases that are enabled
        enabled_phases = self.get_enabled_phases()
        filtered_artifacts = [
            a for a in self._artifacts if a.phase_id in enabled_phases
        ]

        return filtered_artifacts

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _ensure_initialized(self) -> None:
        """Ensure the runner has been initialized.

        Raises:
            RuntimeError: If runner has not been initialized
        """
        if not self._initialized:
            raise RuntimeError("BMADRunner not initialized. Call initialize() first.")

    # =========================================================================
    # Story 6.8: Complexity Level Support Methods
    # =========================================================================

    def get_complexity_level(self) -> ComplexityLevel:
        """Get the current complexity level.

        Returns the complexity level set during initialization. Defaults to
        STANDARD if not explicitly set.

        Returns:
            ComplexityLevel enum value (QUICK, STANDARD, or COMPLEX)

        Story Reference: Story 6.8 - Implement BMAD Complexity Level Support
        """
        return self._complexity or ComplexityLevel.STANDARD

    def is_phase_enabled(self, phase_id: str) -> bool:
        """Check if a phase is enabled for the current complexity level.

        Args:
            phase_id: ID of the phase to check (e.g., 'prd', 'architecture')

        Returns:
            True if the phase should be executed, False if it should be skipped

        Example:
            >>> runner.is_phase_enabled('prd')
            True  # Standard/Complex
            False # Quick

        Story Reference: Story 6.8 - Implement BMAD Complexity Level Support
        """
        complexity = self.get_complexity_level()
        enabled_phases = self.COMPLEXITY_PHASES.get(
            complexity, self.COMPLEXITY_PHASES[ComplexityLevel.STANDARD]
        )
        return phase_id in enabled_phases

    def get_enabled_phases(self) -> list[str]:
        """Get the list of phase IDs enabled for the current complexity level.

        Returns:
            List of phase IDs that should be executed

        Example:
            >>> runner.get_enabled_phases()
            ['analyze', 'epics', 'stories', 'dev', 'review']  # Quick
            ['analyze', 'prd', 'architecture', 'epics', 'stories', 'dev', 'review']  # Standard/Complex

        Story Reference: Story 6.8 - Implement BMAD Complexity Level Support
        """
        complexity = self.get_complexity_level()
        return self.COMPLEXITY_PHASES.get(
            complexity, self.COMPLEXITY_PHASES[ComplexityLevel.STANDARD]
        ).copy()

    def get_enabled_checkpoints(self) -> list[str]:
        """Get the list of checkpoint IDs enabled for the current complexity level.

        Quick complexity has fewer checkpoints for faster iteration.
        Standard and Complex have all checkpoints enabled.

        Returns:
            List of checkpoint IDs that should be active

        Story Reference: Story 6.8 - Implement BMAD Complexity Level Support
        """
        complexity = self.get_complexity_level()
        return self.COMPLEXITY_CHECKPOINTS.get(
            complexity, self.COMPLEXITY_CHECKPOINTS[ComplexityLevel.STANDARD]
        ).copy()

    def get_skipped_phases(self) -> list[str]:
        """Get the list of phase IDs that are skipped for the current complexity level.

        Useful for logging and reporting which phases are being skipped.

        Returns:
            List of phase IDs that will be skipped

        Example:
            >>> runner.get_skipped_phases()
            ['prd', 'architecture']  # Quick
            []  # Standard/Complex

        Story Reference: Story 6.8 - Implement BMAD Complexity Level Support
        """
        all_phases = self.COMPLEXITY_PHASES[ComplexityLevel.STANDARD]
        enabled_phases = self.get_enabled_phases()
        return [p for p in all_phases if p not in enabled_phases]

    @property
    def is_quick_mode(self) -> bool:
        """Check if running in Quick complexity mode.

        Returns:
            True if complexity level is QUICK

        Story Reference: Story 6.8 - Implement BMAD Complexity Level Support
        """
        return self.get_complexity_level() == ComplexityLevel.QUICK

    @property
    def is_complex_mode(self) -> bool:
        """Check if running in Complex complexity mode.

        Complex mode enables deeper analysis and validation in each phase.

        Returns:
            True if complexity level is COMPLEX

        Story Reference: Story 6.8 - Implement BMAD Complexity Level Support
        """
        return self.get_complexity_level() == ComplexityLevel.COMPLEX

    # =========================================================================
    # Story 6.9: Task-Scoped Output Directory Methods
    # =========================================================================

    def _init_output_dir(self) -> None:
        """Initialize the task-scoped output directory.

        Creates the BMAD output directory within the spec directory:
        `.auto-claude/specs/{task-id}/bmad/`

        This ensures artifacts from multiple parallel BMAD tasks don't conflict.

        Story Reference: Story 6.9 - Task-Scoped Output Directories
        """
        if self._spec_dir is None:
            logger.warning(
                "No spec_dir configured. BMAD artifacts will not be task-scoped."
            )
            return

        self._output_dir = self._spec_dir / self.BMAD_OUTPUT_SUBDIR
        self._ensure_output_dir()

    def _ensure_output_dir(self) -> None:
        """Ensure the output directory exists.

        Creates the output directory and any necessary parent directories
        if they don't exist.

        Story Reference: Story 6.9 - Task-Scoped Output Directories
        """
        if self._output_dir is not None:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"BMAD output directory ready: {self._output_dir}")

    @property
    def output_dir(self) -> Path | None:
        """Get the task-scoped output directory for BMAD artifacts.

        Returns:
            Path to the output directory (`.auto-claude/specs/{task-id}/bmad/`),
            or None if spec_dir is not configured.

        Story Reference: Story 6.9 - Task-Scoped Output Directories
        """
        return self._output_dir

    def get_artifact_path(self, artifact_name: str) -> Path | None:
        """Get the full path for a BMAD artifact.

        Constructs the path within the task-scoped output directory.
        If output_dir is not configured, returns None.

        Args:
            artifact_name: Name of the artifact file (e.g., 'analysis.json', 'prd.md')

        Returns:
            Full path to the artifact within the output directory,
            or None if output directory is not configured.

        Example:
            >>> runner.get_artifact_path('prd.md')
            Path('.auto-claude/specs/139-task-name/bmad/prd.md')

        Story Reference: Story 6.9 - Task-Scoped Output Directories
        """
        if self._output_dir is None:
            return None
        return self._output_dir / artifact_name

    def get_stories_dir(self) -> Path | None:
        """Get the stories subdirectory within the output directory.

        Creates the stories subdirectory if it doesn't exist.

        Returns:
            Path to the stories directory (`.auto-claude/specs/{task-id}/bmad/stories/`),
            or None if output directory is not configured.

        Story Reference: Story 6.9 - Task-Scoped Output Directories
        """
        if self._output_dir is None:
            return None

        stories_dir = self._output_dir / "stories"
        stories_dir.mkdir(parents=True, exist_ok=True)
        return stories_dir

    # =========================================================================
    # BMAD Skills Initialization
    # =========================================================================

    def _init_skills(self) -> None:
        """Initialize BMAD skills in the target project via symlink.

        Creates a symlink from the target project's `_bmad/` directory to the
        BMAD skills in the Auto Claude installation. This allows agents running
        in the target project to access BMAD workflows via slash commands.

        The source `_bmad/` folder is located relative to this methodology file:
        autonomous-coding/_bmad/

        The symlink is created at:
        {project_dir}/_bmad/ -> {auto_claude_root}/_bmad/

        Cross-platform handling:
        - macOS/Linux: Uses relative symlinks for portability
        - Windows: Uses directory junctions (no admin rights required)

        If symlink creation fails, logs a warning but does not fail the
        initialization - the methodology will continue but BMAD slash commands
        may not work.
        """
        debug("bmad.methodology", "Initializing BMAD skills symlink...")

        if not self._project_dir:
            debug_warning("bmad.methodology", "No project_dir configured. BMAD skills will not be linked.")
            logger.warning("No project_dir configured. BMAD skills will not be linked.")
            return

        project_dir = Path(self._project_dir)

        # Determine the Auto Claude root directory
        # This file is at: autonomous-coding/apps/backend/methodologies/bmad/methodology.py
        # So Auto Claude root is 5 levels up
        auto_claude_root = Path(__file__).parent.parent.parent.parent.parent

        # Source: _bmad/ folder in Auto Claude
        source_bmad = auto_claude_root / "_bmad"

        # Target: _bmad/ symlink in target project
        target_bmad = project_dir / "_bmad"

        debug(
            "bmad.methodology",
            "BMAD skills paths",
            source=str(source_bmad),
            target=str(target_bmad),
            source_exists=source_bmad.exists(),
        )

        # Verify source exists
        if not source_bmad.exists():
            debug_warning(
                "bmad.methodology",
                f"BMAD skills source not found at {source_bmad}",
            )
            logger.warning(
                f"BMAD skills source not found at {source_bmad}. "
                "BMAD slash commands may not work."
            )
            return

        # Skip if target already exists (don't overwrite)
        if target_bmad.exists():
            debug("bmad.methodology", f"BMAD skills already present at {target_bmad}")
            logger.debug(f"BMAD skills already present at {target_bmad}")
            return

        # Also skip if target is a symlink (even if broken)
        if target_bmad.is_symlink():
            debug("bmad.methodology", f"BMAD skills symlink already exists at {target_bmad} (possibly broken)")
            logger.debug(f"BMAD skills symlink already exists at {target_bmad} (possibly broken)")
            return

        try:
            if sys.platform == "win32":
                # On Windows, use directory junctions (no admin rights required)
                # Junctions require absolute paths
                debug("bmad.methodology", "Creating Windows junction for BMAD skills...")
                result = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(target_bmad), str(source_bmad.resolve())],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise OSError(result.stderr or "mklink /J failed")
                debug_success("bmad.methodology", f"Created BMAD skills junction: {target_bmad} -> {source_bmad}")
                logger.info(f"Created BMAD skills junction: {target_bmad} -> {source_bmad}")
            else:
                # On macOS/Linux, use relative symlinks for portability
                relative_source = os.path.relpath(source_bmad.resolve(), target_bmad.parent)
                debug("bmad.methodology", f"Creating symlink: {target_bmad} -> {relative_source}")
                os.symlink(relative_source, target_bmad)
                debug_success("bmad.methodology", f"Created BMAD skills symlink: {target_bmad} -> {relative_source}")
                logger.info(f"Created BMAD skills symlink: {target_bmad} -> {relative_source}")

        except OSError as e:
            # Symlink/junction creation can fail on some systems
            # Log warning but don't fail - methodology is still usable
            debug_error(
                "bmad.methodology",
                f"Could not create BMAD skills symlink: {e}",
            )
            logger.warning(
                f"Could not create BMAD skills symlink at {target_bmad}: {e}. "
                "BMAD slash commands may not work in the target project."
            )

    def _cleanup_skills_symlink(self) -> None:
        """Remove the BMAD skills symlink from the target project.

        Called during cleanup to remove the symlink created by _init_skills().
        This is optional - symlinks can be left in place if desired.
        """
        if not self._project_dir:
            return

        target_bmad = Path(self._project_dir) / "_bmad"

        # Only remove if it's a symlink (don't delete actual _bmad folders)
        if target_bmad.is_symlink():
            try:
                target_bmad.unlink()
                logger.debug(f"Removed BMAD skills symlink: {target_bmad}")
            except OSError as e:
                logger.warning(f"Could not remove BMAD skills symlink: {e}")

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

    def _invoke_progress_callback(self, message: str, percentage: float) -> None:
        """Invoke the current progress callback if set.

        Args:
            message: Human-readable progress message
            percentage: Progress within the current phase (0.0 to 100.0)
        """
        if self._current_progress_callback is not None:
            try:
                self._current_progress_callback(message, percentage)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    # =========================================================================
    # Initialization Methods
    # =========================================================================

    def _init_phases(self) -> None:
        """Initialize phase definitions for the BMAD methodology."""
        self._phases = [
            Phase(
                id="analyze",
                name="Project Analysis",
                description="Analyze project structure and gather context",
                order=1,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
            Phase(
                id="prd",
                name="PRD Creation",
                description="Create Product Requirements Document",
                order=2,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
            Phase(
                id="architecture",
                name="Architecture",
                description="Design and document system architecture",
                order=3,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
            Phase(
                id="epics",
                name="Epic & Story Creation",
                description="Create epics and break down into stories",
                order=4,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
            Phase(
                id="stories",
                name="Story Preparation",
                description="Prepare and refine stories for development",
                order=5,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
            Phase(
                id="dev",
                name="Development",
                description="Implement stories via dev-story workflow",
                order=6,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
            Phase(
                id="review",
                name="Code Review",
                description="Review implementation via code-review workflow",
                order=7,
                status=PhaseStatus.PENDING,
                is_optional=False,
            ),
        ]

    def _init_checkpoints(self) -> None:
        """Initialize checkpoint definitions for Semi-Auto mode."""
        self._checkpoints = [
            Checkpoint(
                id="after_prd",
                name="PRD Review",
                description="Review Product Requirements Document before architecture",
                phase_id="prd",
                status=CheckpointStatus.PENDING,
                requires_approval=True,
            ),
            Checkpoint(
                id="after_architecture",
                name="Architecture Review",
                description="Review architecture design before epic creation",
                phase_id="architecture",
                status=CheckpointStatus.PENDING,
                requires_approval=True,
            ),
            Checkpoint(
                id="after_epics",
                name="Epic Review",
                description="Review epics and stories before development",
                phase_id="epics",
                status=CheckpointStatus.PENDING,
                requires_approval=True,
            ),
            Checkpoint(
                id="after_story",
                name="Story Review",
                description="Review story implementation before continuing",
                phase_id="dev",
                status=CheckpointStatus.PENDING,
                requires_approval=True,
            ),
            Checkpoint(
                id="after_review",
                name="Final Review",
                description="Review code review results before completion",
                phase_id="review",
                status=CheckpointStatus.PENDING,
                requires_approval=True,
            ),
        ]

    def _init_artifacts(self) -> None:
        """Initialize artifact definitions for the BMAD methodology.

        Artifact paths are relative to the spec_dir and use the bmad/
        subdirectory for task-scoped storage.

        Story Reference: Story 6.9 - Task-Scoped Output Directories
        """
        # Use task-scoped paths within bmad/ subdirectory
        bmad_subdir = self.BMAD_OUTPUT_SUBDIR

        self._artifacts = [
            Artifact(
                id="analysis-json",
                artifact_type="json",
                name="Project Analysis",
                file_path=f"{bmad_subdir}/analysis.json",
                phase_id="analyze",
                content_type="application/json",
            ),
            Artifact(
                id="prd-md",
                artifact_type="markdown",
                name="Product Requirements Document",
                file_path=f"{bmad_subdir}/prd.md",
                phase_id="prd",
                content_type="text/markdown",
            ),
            Artifact(
                id="architecture-md",
                artifact_type="markdown",
                name="Architecture Document",
                file_path=f"{bmad_subdir}/architecture.md",
                phase_id="architecture",
                content_type="text/markdown",
            ),
            Artifact(
                id="epics-md",
                artifact_type="markdown",
                name="Epics Document",
                file_path=f"{bmad_subdir}/epics.md",
                phase_id="epics",
                content_type="text/markdown",
            ),
            Artifact(
                id="stories-md",
                artifact_type="markdown",
                name="Story Files",
                file_path=f"{bmad_subdir}/stories/*.md",
                phase_id="stories",
                content_type="text/markdown",
            ),
            Artifact(
                id="review-report-md",
                artifact_type="markdown",
                name="Review Report",
                file_path=f"{bmad_subdir}/review_report.md",
                phase_id="review",
                content_type="text/markdown",
            ),
        ]
