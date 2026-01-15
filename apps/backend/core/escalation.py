"""Task Escalation Handling Module.

Story Reference: Story 4.5 - Implement Task Escalation Handling

This module provides escalation triggers, state management, and notification
functionality for handling tasks that cannot complete autonomously and require
user intervention.

Architecture Source: architecture.md#Escalation
"""

import json
import logging
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class EscalationReason(StrEnum):
    """Reasons why a task might be escalated.

    Story Reference: Story 4.5 Task 1 - Define escalation triggers

    These reasons map to the escalation triggers specified in the story:
    - MAX_RETRIES_EXCEEDED: Max retry exceeded for subtask
    - UNFIXABLE_QA_ISSUES: QA found issues that cannot be auto-fixed
    - EXTERNAL_SERVICE_FAILURE: External service failures (NFR20)
    - USER_DEFINED: User-defined escalation conditions
    - VALIDATION_FAILED: Validation phase failed after max iterations
    - UNKNOWN: Unknown or unclassified escalation reason
    """

    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    UNFIXABLE_QA_ISSUES = "unfixable_qa_issues"
    EXTERNAL_SERVICE_FAILURE = "external_service_failure"
    USER_DEFINED = "user_defined"
    VALIDATION_FAILED = "validation_failed"
    UNKNOWN = "unknown"


@dataclass
class EscalationTrigger:
    """Configuration for an escalation trigger.

    Story Reference: Story 4.5 Task 1 - User-defined escalation conditions

    Attributes:
        reason: The reason for escalation
        enabled: Whether this trigger is active
        threshold: Optional threshold value (e.g., max retries)
        description: Human-readable description of the trigger
    """

    reason: EscalationReason
    enabled: bool = True
    threshold: int | None = None
    description: str = ""


# Default escalation trigger configuration
DEFAULT_ESCALATION_TRIGGERS: list[EscalationTrigger] = [
    EscalationTrigger(
        reason=EscalationReason.MAX_RETRIES_EXCEEDED,
        enabled=True,
        threshold=3,
        description="Escalate when a subtask fails after maximum retry attempts",
    ),
    EscalationTrigger(
        reason=EscalationReason.UNFIXABLE_QA_ISSUES,
        enabled=True,
        description="Escalate when QA finds issues that cannot be automatically fixed",
    ),
    EscalationTrigger(
        reason=EscalationReason.EXTERNAL_SERVICE_FAILURE,
        enabled=True,
        description="Escalate when external services fail (NFR20 compliance)",
    ),
    EscalationTrigger(
        reason=EscalationReason.VALIDATION_FAILED,
        enabled=True,
        threshold=5,
        description="Escalate when validation fails after maximum iterations",
    ),
]


@dataclass
class EscalationInfo:
    """Information about an escalated task.

    Story Reference: Story 4.5 Task 2 - Store escalation reason

    This dataclass captures all details about an escalated task for
    display to the user and potential retry.

    Attributes:
        reason: Why the task was escalated
        failed_phase: The phase that was executing when escalation occurred
        error_message: Human-readable error description
        error_trace: Optional full stack trace
        attempted_fixes: List of fix attempts made before escalation
        context: Additional context at the point of failure
        created_at: When the escalation occurred
        guidance: Optional user guidance for retry (set on resume)
        subtask_id: Optional ID of the failing subtask
        iteration: Optional iteration number (for validation failures)
    """

    reason: EscalationReason
    failed_phase: str
    error_message: str
    error_trace: str | None = None
    attempted_fixes: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    guidance: str | None = None
    subtask_id: str | None = None
    iteration: int | None = None


def create_escalation_info(
    reason: EscalationReason,
    failed_phase: str,
    error_message: str,
    error_trace: str | None = None,
    attempted_fixes: list[str] | None = None,
    context: dict[str, Any] | None = None,
    subtask_id: str | None = None,
    iteration: int | None = None,
) -> EscalationInfo:
    """Create an EscalationInfo instance.

    Story Reference: Story 4.5 Task 2 - Store escalation reason

    Args:
        reason: Why the task is being escalated
        failed_phase: Phase that was executing (planning, coding, validation)
        error_message: Human-readable error description
        error_trace: Optional stack trace
        attempted_fixes: List of fixes attempted before escalation
        context: Additional context data
        subtask_id: Optional subtask ID for coding phase failures
        iteration: Optional iteration number for validation failures

    Returns:
        Populated EscalationInfo instance
    """
    return EscalationInfo(
        reason=reason,
        failed_phase=failed_phase,
        error_message=error_message,
        error_trace=error_trace,
        attempted_fixes=attempted_fixes or [],
        context=context or {},
        subtask_id=subtask_id,
        iteration=iteration,
    )


def save_escalation(task_dir: Path, info: EscalationInfo) -> Path:
    """Save escalation information to a JSON file.

    Story Reference: Story 4.5 Task 4 - Create escalation_log.json artifact

    Args:
        task_dir: Directory where task artifacts are stored
        info: EscalationInfo to save

    Returns:
        Path to the saved escalation.json file
    """
    escalation_path = task_dir / "escalation.json"

    data = asdict(info)
    # Convert datetime to ISO format string
    data["created_at"] = info.created_at.isoformat()
    # Convert enum to string
    data["reason"] = info.reason.value

    try:
        task_dir.mkdir(parents=True, exist_ok=True)
        escalation_path.write_text(json.dumps(data, indent=2))
        logger.info(f"Escalation saved to {escalation_path}")
    except OSError as e:
        logger.error(f"Failed to save escalation: {e}")
        raise

    return escalation_path


def load_escalation(task_dir: Path) -> EscalationInfo | None:
    """Load escalation information from a JSON file.

    Story Reference: Story 4.5 Task 2 - Store failed phase and context

    Args:
        task_dir: Directory where task artifacts are stored

    Returns:
        EscalationInfo if file exists, None otherwise
    """
    escalation_path = task_dir / "escalation.json"

    if not escalation_path.exists():
        return None

    try:
        data = json.loads(escalation_path.read_text())

        # Convert string back to datetime
        created_at = datetime.fromisoformat(data.pop("created_at"))
        # Convert string back to enum
        reason = EscalationReason(data.pop("reason"))

        return EscalationInfo(reason=reason, created_at=created_at, **data)
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.error(f"Failed to load escalation from {escalation_path}: {e}")
        return None


def clear_escalation(task_dir: Path) -> bool:
    """Clear escalation information after successful resume.

    Story Reference: Story 4.5 Task 7 - Clear escalation state on success

    Args:
        task_dir: Directory where task artifacts are stored

    Returns:
        True if escalation was cleared, False if no escalation existed
    """
    escalation_path = task_dir / "escalation.json"

    if not escalation_path.exists():
        return False

    try:
        # Archive the escalation file instead of deleting
        archive_path = task_dir / "escalation_resolved.json"
        escalation_path.rename(archive_path)
        logger.info(f"Escalation resolved and archived to {archive_path}")
        return True
    except OSError as e:
        logger.error(f"Failed to clear escalation: {e}")
        return False


def update_escalation_guidance(task_dir: Path, guidance: str) -> EscalationInfo | None:
    """Update escalation with user guidance before retry.

    Story Reference: Story 4.5 Task 6 - Store guidance with task

    Args:
        task_dir: Directory where task artifacts are stored
        guidance: User-provided guidance text

    Returns:
        Updated EscalationInfo if successful, None otherwise
    """
    info = load_escalation(task_dir)
    if info is None:
        logger.warning(f"No escalation found in {task_dir}")
        return None

    info.guidance = guidance
    save_escalation(task_dir, info)
    return info


def create_escalation_log(
    task_dir: Path,
    info: EscalationInfo,
) -> Path:
    """Create a detailed escalation_log.json artifact.

    Story Reference: Story 4.5 Task 4 - Create escalation_log.json artifact

    This creates a more detailed log file with full context, suitable
    for debugging and analysis.

    Args:
        task_dir: Directory where task artifacts are stored
        info: EscalationInfo with all escalation details

    Returns:
        Path to the created escalation_log.json file
    """
    log_path = task_dir / "escalation_log.json"

    log_data = {
        "escalation": {
            "reason": info.reason.value,
            "reason_description": _get_reason_description(info.reason),
            "failed_phase": info.failed_phase,
            "subtask_id": info.subtask_id,
            "iteration": info.iteration,
        },
        "error": {
            "message": info.error_message,
            "stack_trace": info.error_trace,
        },
        "context": {
            "attempted_fixes": info.attempted_fixes,
            "failure_context": info.context,
        },
        "timestamps": {
            "created_at": info.created_at.isoformat(),
        },
        "resolution": {
            "guidance": info.guidance,
            "status": "pending",
        },
    }

    try:
        task_dir.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(log_data, indent=2))
        logger.info(f"Escalation log created at {log_path}")
    except OSError as e:
        logger.error(f"Failed to create escalation log: {e}")
        raise

    return log_path


def _get_reason_description(reason: EscalationReason) -> str:
    """Get a human-readable description for an escalation reason."""
    descriptions = {
        EscalationReason.MAX_RETRIES_EXCEEDED: (
            "The task failed after the maximum number of retry attempts"
        ),
        EscalationReason.UNFIXABLE_QA_ISSUES: (
            "QA validation found issues that cannot be automatically fixed"
        ),
        EscalationReason.EXTERNAL_SERVICE_FAILURE: (
            "An external service required by the task failed or is unavailable"
        ),
        EscalationReason.USER_DEFINED: (
            "A user-defined escalation condition was triggered"
        ),
        EscalationReason.VALIDATION_FAILED: (
            "The validation phase failed after maximum iterations"
        ),
        EscalationReason.UNKNOWN: "The escalation reason could not be determined",
    }
    return descriptions.get(reason, "Unknown escalation reason")


def should_escalate_on_retry_failure(
    attempt: int,
    max_retries: int = 3,
    triggers: list[EscalationTrigger] | None = None,
) -> bool:
    """Check if a task should be escalated based on retry count.

    Story Reference: Story 4.5 Task 1 - Max retry exceeded for subtask

    Args:
        attempt: Current attempt number (1-based)
        max_retries: Maximum allowed retries
        triggers: Optional custom trigger configuration

    Returns:
        True if task should be escalated
    """
    if triggers is None:
        triggers = DEFAULT_ESCALATION_TRIGGERS

    for trigger in triggers:
        if trigger.reason == EscalationReason.MAX_RETRIES_EXCEEDED:
            if not trigger.enabled:
                return False
            threshold = trigger.threshold or max_retries
            return attempt >= threshold

    return attempt >= max_retries


def should_escalate_on_qa_failure(
    fixable: bool,
    triggers: list[EscalationTrigger] | None = None,
) -> bool:
    """Check if a task should be escalated based on QA results.

    Story Reference: Story 4.5 Task 1 - Unfixable QA issues

    Args:
        fixable: Whether the QA issues are auto-fixable
        triggers: Optional custom trigger configuration

    Returns:
        True if task should be escalated due to unfixable QA issues
    """
    if fixable:
        return False

    if triggers is None:
        triggers = DEFAULT_ESCALATION_TRIGGERS

    for trigger in triggers:
        if trigger.reason == EscalationReason.UNFIXABLE_QA_ISSUES:
            return trigger.enabled

    return True


def should_escalate_on_validation_failure(
    iteration: int,
    max_iterations: int = 5,
    triggers: list[EscalationTrigger] | None = None,
) -> bool:
    """Check if a task should be escalated based on validation iterations.

    Story Reference: Story 4.5 Task 1 - Define escalation triggers

    Args:
        iteration: Current validation iteration
        max_iterations: Maximum allowed iterations
        triggers: Optional custom trigger configuration

    Returns:
        True if task should be escalated due to validation failure
    """
    if triggers is None:
        triggers = DEFAULT_ESCALATION_TRIGGERS

    for trigger in triggers:
        if trigger.reason == EscalationReason.VALIDATION_FAILED:
            if not trigger.enabled:
                return False
            threshold = trigger.threshold or max_iterations
            return iteration >= threshold

    return iteration >= max_iterations


def emit_escalation_event(
    task_id: str,
    reason: EscalationReason,
    failed_phase: str,
    error_summary: str,
) -> None:
    """Emit an escalation event for frontend notification.

    Story Reference: Story 4.5 Task 3 - Send notification via IPC

    This uses the same stdout protocol as phase events so the frontend
    can parse and trigger notifications.

    Args:
        task_id: ID of the escalated task
        reason: Why the task was escalated
        failed_phase: The phase that failed
        error_summary: Brief error description
    """
    import json

    ESCALATION_MARKER_PREFIX = "__TASK_ESCALATION__:"

    payload = {
        "event": "task:escalated",
        "task_id": task_id,
        "reason": reason.value,
        "failed_phase": failed_phase,
        "error_summary": error_summary[:200],  # Truncate for notification
    }

    try:
        print(f"{ESCALATION_MARKER_PREFIX}{json.dumps(payload)}", flush=True)
    except (OSError, UnicodeEncodeError) as e:
        logger.error(f"Failed to emit escalation event: {e}")


def escalate_task(
    task_dir: Path,
    reason: EscalationReason,
    failed_phase: str,
    error: Exception | str,
    attempted_fixes: list[str] | None = None,
    context: dict[str, Any] | None = None,
    subtask_id: str | None = None,
    iteration: int | None = None,
    task_id: str | None = None,
) -> EscalationInfo:
    """Escalate a task and save all escalation artifacts.

    Story Reference: Story 4.5 Task 2 - Implement escalation state

    This is the main entry point for escalating a task. It:
    1. Creates EscalationInfo with all details
    2. Saves escalation.json for state tracking
    3. Creates escalation_log.json for debugging

    Args:
        task_dir: Directory where task artifacts are stored
        reason: Why the task is being escalated
        failed_phase: Phase that was executing (planning, coding, validation)
        error: The error that triggered escalation
        attempted_fixes: List of fixes attempted before escalation
        context: Additional context data
        subtask_id: Optional subtask ID for coding phase failures
        iteration: Optional iteration number for validation failures

    Returns:
        EscalationInfo instance with all escalation details
    """
    # Extract error message and trace
    if isinstance(error, Exception):
        error_message = str(error)
        error_trace = traceback.format_exc()
    else:
        error_message = error
        error_trace = None

    # Create escalation info
    info = create_escalation_info(
        reason=reason,
        failed_phase=failed_phase,
        error_message=error_message,
        error_trace=error_trace,
        attempted_fixes=attempted_fixes,
        context=context,
        subtask_id=subtask_id,
        iteration=iteration,
    )

    # Save escalation state
    save_escalation(task_dir, info)

    # Create detailed log
    create_escalation_log(task_dir, info)

    logger.warning(
        f"Task escalated: reason={reason.value}, phase={failed_phase}, "
        f"error={error_message[:100]}..."
    )

    # Emit escalation event for frontend notification
    if task_id:
        emit_escalation_event(task_id, reason, failed_phase, error_message)

    return info
