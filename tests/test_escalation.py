#!/usr/bin/env python3
"""
Tests for Task Escalation Module
================================

Story Reference: Story 4.5 - Implement Task Escalation Handling

Tests the core/escalation.py module including:
- EscalationReason enum
- EscalationTrigger dataclass
- EscalationInfo dataclass
- Escalation functions (save, load, clear, update)
- Trigger check functions
- Event emission
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "backend"))

from core.escalation import (
    DEFAULT_ESCALATION_TRIGGERS,
    EscalationInfo,
    EscalationReason,
    EscalationTrigger,
    clear_escalation,
    create_escalation_info,
    create_escalation_log,
    emit_escalation_event,
    escalate_task,
    load_escalation,
    save_escalation,
    should_escalate_on_qa_failure,
    should_escalate_on_retry_failure,
    should_escalate_on_validation_failure,
    update_escalation_guidance,
)


class TestEscalationReasonEnum:
    """Tests for EscalationReason enum values."""

    def test_all_reasons_have_string_values(self):
        """All reasons have valid string values."""
        for reason in EscalationReason:
            assert isinstance(reason.value, str)
            assert len(reason.value) > 0

    def test_reason_values_are_lowercase(self):
        """Reason values are lowercase snake_case."""
        for reason in EscalationReason:
            assert reason.value == reason.value.lower()

    def test_expected_reasons_exist(self):
        """Expected escalation reasons exist."""
        expected = {
            "max_retries_exceeded",
            "unfixable_qa_issues",
            "external_service_failure",
            "user_defined",
            "validation_failed",
            "unknown",
        }
        actual = {r.value for r in EscalationReason}
        assert expected == actual

    def test_reason_is_string_subclass(self):
        """EscalationReason inherits from str."""
        assert issubclass(EscalationReason, str)


class TestEscalationTrigger:
    """Tests for EscalationTrigger dataclass."""

    def test_basic_creation(self):
        """Create a basic trigger."""
        trigger = EscalationTrigger(
            reason=EscalationReason.MAX_RETRIES_EXCEEDED,
            enabled=True,
            threshold=3,
            description="Test trigger",
        )
        assert trigger.reason == EscalationReason.MAX_RETRIES_EXCEEDED
        assert trigger.enabled is True
        assert trigger.threshold == 3
        assert trigger.description == "Test trigger"

    def test_default_values(self):
        """Default values are applied."""
        trigger = EscalationTrigger(reason=EscalationReason.UNKNOWN)
        assert trigger.enabled is True
        assert trigger.threshold is None
        assert trigger.description == ""


class TestDefaultTriggers:
    """Tests for default escalation trigger configuration."""

    def test_default_triggers_exist(self):
        """Default triggers are defined."""
        assert len(DEFAULT_ESCALATION_TRIGGERS) > 0

    def test_max_retries_trigger(self):
        """Max retries trigger is configured."""
        trigger = next(
            (t for t in DEFAULT_ESCALATION_TRIGGERS
             if t.reason == EscalationReason.MAX_RETRIES_EXCEEDED),
            None
        )
        assert trigger is not None
        assert trigger.enabled is True
        assert trigger.threshold == 3

    def test_unfixable_qa_trigger(self):
        """Unfixable QA trigger is configured."""
        trigger = next(
            (t for t in DEFAULT_ESCALATION_TRIGGERS
             if t.reason == EscalationReason.UNFIXABLE_QA_ISSUES),
            None
        )
        assert trigger is not None
        assert trigger.enabled is True

    def test_validation_failed_trigger(self):
        """Validation failed trigger is configured."""
        trigger = next(
            (t for t in DEFAULT_ESCALATION_TRIGGERS
             if t.reason == EscalationReason.VALIDATION_FAILED),
            None
        )
        assert trigger is not None
        assert trigger.threshold == 5


class TestEscalationInfo:
    """Tests for EscalationInfo dataclass."""

    def test_basic_creation(self):
        """Create basic escalation info."""
        info = EscalationInfo(
            reason=EscalationReason.MAX_RETRIES_EXCEEDED,
            failed_phase="coding",
            error_message="Test error",
        )
        assert info.reason == EscalationReason.MAX_RETRIES_EXCEEDED
        assert info.failed_phase == "coding"
        assert info.error_message == "Test error"
        assert isinstance(info.created_at, datetime)

    def test_default_values(self):
        """Default values are applied."""
        info = EscalationInfo(
            reason=EscalationReason.UNKNOWN,
            failed_phase="planning",
            error_message="Error",
        )
        assert info.error_trace is None
        assert info.attempted_fixes == []
        assert info.context == {}
        assert info.guidance is None
        assert info.subtask_id is None
        assert info.iteration is None

    def test_full_creation(self):
        """Create with all fields."""
        info = EscalationInfo(
            reason=EscalationReason.VALIDATION_FAILED,
            failed_phase="validation",
            error_message="Validation failed",
            error_trace="Stack trace here",
            attempted_fixes=["Fix 1", "Fix 2"],
            context={"key": "value"},
            guidance="Try this approach",
            subtask_id="subtask-1",
            iteration=3,
        )
        assert info.error_trace == "Stack trace here"
        assert len(info.attempted_fixes) == 2
        assert info.context["key"] == "value"
        assert info.guidance == "Try this approach"
        assert info.subtask_id == "subtask-1"
        assert info.iteration == 3


class TestCreateEscalationInfo:
    """Tests for create_escalation_info helper."""

    def test_basic_creation(self):
        """Create basic info with helper."""
        info = create_escalation_info(
            reason=EscalationReason.MAX_RETRIES_EXCEEDED,
            failed_phase="coding",
            error_message="Failed after 3 attempts",
        )
        assert info.reason == EscalationReason.MAX_RETRIES_EXCEEDED
        assert info.failed_phase == "coding"
        assert info.error_message == "Failed after 3 attempts"

    def test_optional_parameters(self):
        """Optional parameters work correctly."""
        info = create_escalation_info(
            reason=EscalationReason.UNFIXABLE_QA_ISSUES,
            failed_phase="qa_review",
            error_message="Cannot fix",
            error_trace="Traceback...",
            attempted_fixes=["Attempt 1"],
            context={"qa_iteration": 2},
            subtask_id="fix-1",
        )
        assert info.error_trace == "Traceback..."
        assert info.attempted_fixes == ["Attempt 1"]
        assert info.context["qa_iteration"] == 2
        assert info.subtask_id == "fix-1"


class TestSaveLoadEscalation:
    """Tests for saving and loading escalation state."""

    def test_save_escalation(self, tmp_path):
        """Save escalation to file."""
        info = create_escalation_info(
            reason=EscalationReason.MAX_RETRIES_EXCEEDED,
            failed_phase="coding",
            error_message="Test error",
        )
        path = save_escalation(tmp_path, info)

        assert path.exists()
        assert path.name == "escalation.json"

        # Verify content
        data = json.loads(path.read_text())
        assert data["reason"] == "max_retries_exceeded"
        assert data["failed_phase"] == "coding"
        assert data["error_message"] == "Test error"

    def test_load_escalation(self, tmp_path):
        """Load escalation from file."""
        info = create_escalation_info(
            reason=EscalationReason.VALIDATION_FAILED,
            failed_phase="validation",
            error_message="Validation error",
            iteration=5,
        )
        save_escalation(tmp_path, info)

        loaded = load_escalation(tmp_path)
        assert loaded is not None
        assert loaded.reason == EscalationReason.VALIDATION_FAILED
        assert loaded.failed_phase == "validation"
        assert loaded.iteration == 5

    def test_load_nonexistent(self, tmp_path):
        """Load returns None for missing file."""
        loaded = load_escalation(tmp_path)
        assert loaded is None

    def test_clear_escalation(self, tmp_path):
        """Clear escalation archives the file."""
        info = create_escalation_info(
            reason=EscalationReason.UNKNOWN,
            failed_phase="planning",
            error_message="Error",
        )
        save_escalation(tmp_path, info)

        result = clear_escalation(tmp_path)
        assert result is True

        # Original file should be gone
        assert not (tmp_path / "escalation.json").exists()
        # Archive should exist
        assert (tmp_path / "escalation_resolved.json").exists()

    def test_clear_nonexistent(self, tmp_path):
        """Clear returns False for missing file."""
        result = clear_escalation(tmp_path)
        assert result is False


class TestUpdateEscalationGuidance:
    """Tests for updating escalation with guidance."""

    def test_update_guidance(self, tmp_path):
        """Update escalation with user guidance."""
        info = create_escalation_info(
            reason=EscalationReason.UNFIXABLE_QA_ISSUES,
            failed_phase="qa_review",
            error_message="Cannot fix type error",
        )
        save_escalation(tmp_path, info)

        updated = update_escalation_guidance(tmp_path, "Try using type assertion")
        assert updated is not None
        assert updated.guidance == "Try using type assertion"

        # Verify persistence
        loaded = load_escalation(tmp_path)
        assert loaded.guidance == "Try using type assertion"

    def test_update_nonexistent(self, tmp_path):
        """Update returns None for missing escalation."""
        result = update_escalation_guidance(tmp_path, "Some guidance")
        assert result is None


class TestCreateEscalationLog:
    """Tests for creating detailed escalation log."""

    def test_create_log(self, tmp_path):
        """Create escalation log file."""
        info = create_escalation_info(
            reason=EscalationReason.MAX_RETRIES_EXCEEDED,
            failed_phase="coding",
            error_message="Failed to implement feature",
            error_trace="Traceback: ...",
            attempted_fixes=["Fix attempt 1", "Fix attempt 2"],
            context={"subtask": "add-auth"},
            subtask_id="subtask-1",
        )
        path = create_escalation_log(tmp_path, info)

        assert path.exists()
        assert path.name == "escalation_log.json"

        data = json.loads(path.read_text())
        assert "escalation" in data
        assert "error" in data
        assert "context" in data
        assert data["escalation"]["reason"] == "max_retries_exceeded"
        assert data["error"]["message"] == "Failed to implement feature"
        assert len(data["context"]["attempted_fixes"]) == 2


class TestShouldEscalateOnRetryFailure:
    """Tests for retry failure escalation trigger."""

    def test_escalate_on_max_retries(self):
        """Escalate when max retries exceeded."""
        assert should_escalate_on_retry_failure(3, max_retries=3) is True

    def test_no_escalate_before_max(self):
        """Don't escalate before max retries."""
        assert should_escalate_on_retry_failure(2, max_retries=3) is False

    def test_custom_threshold(self):
        """Custom threshold from trigger config."""
        triggers = [
            EscalationTrigger(
                reason=EscalationReason.MAX_RETRIES_EXCEEDED,
                threshold=5,
            )
        ]
        assert should_escalate_on_retry_failure(5, triggers=triggers) is True
        assert should_escalate_on_retry_failure(4, triggers=triggers) is False

    def test_disabled_trigger(self):
        """Disabled trigger doesn't escalate."""
        triggers = [
            EscalationTrigger(
                reason=EscalationReason.MAX_RETRIES_EXCEEDED,
                enabled=False,
                threshold=3,
            )
        ]
        assert should_escalate_on_retry_failure(10, triggers=triggers) is False


class TestShouldEscalateOnQAFailure:
    """Tests for QA failure escalation trigger."""

    def test_escalate_unfixable(self):
        """Escalate for unfixable issues."""
        assert should_escalate_on_qa_failure(fixable=False) is True

    def test_no_escalate_fixable(self):
        """Don't escalate for fixable issues."""
        assert should_escalate_on_qa_failure(fixable=True) is False

    def test_disabled_trigger(self):
        """Disabled trigger doesn't escalate."""
        triggers = [
            EscalationTrigger(
                reason=EscalationReason.UNFIXABLE_QA_ISSUES,
                enabled=False,
            )
        ]
        assert should_escalate_on_qa_failure(fixable=False, triggers=triggers) is False


class TestShouldEscalateOnValidationFailure:
    """Tests for validation failure escalation trigger."""

    def test_escalate_on_max_iterations(self):
        """Escalate when max iterations exceeded."""
        assert should_escalate_on_validation_failure(5, max_iterations=5) is True

    def test_no_escalate_before_max(self):
        """Don't escalate before max iterations."""
        assert should_escalate_on_validation_failure(3, max_iterations=5) is False

    def test_custom_threshold(self):
        """Custom threshold from trigger config."""
        triggers = [
            EscalationTrigger(
                reason=EscalationReason.VALIDATION_FAILED,
                threshold=10,
            )
        ]
        assert should_escalate_on_validation_failure(10, triggers=triggers) is True


class TestEmitEscalationEvent:
    """Tests for escalation event emission."""

    def test_emits_valid_json(self, capsys):
        """Emits valid JSON with marker prefix."""
        emit_escalation_event(
            task_id="task-123",
            reason=EscalationReason.MAX_RETRIES_EXCEEDED,
            failed_phase="coding",
            error_summary="Test error",
        )
        captured = capsys.readouterr()

        assert "__TASK_ESCALATION__:" in captured.out
        json_str = captured.out.strip().replace("__TASK_ESCALATION__:", "")
        payload = json.loads(json_str)
        assert payload["event"] == "task:escalated"
        assert payload["task_id"] == "task-123"
        assert payload["reason"] == "max_retries_exceeded"
        assert payload["failed_phase"] == "coding"

    def test_truncates_long_error(self, capsys):
        """Long error summaries are truncated."""
        long_error = "x" * 500
        emit_escalation_event(
            task_id="task-123",
            reason=EscalationReason.UNKNOWN,
            failed_phase="planning",
            error_summary=long_error,
        )
        captured = capsys.readouterr()

        json_str = captured.out.strip().replace("__TASK_ESCALATION__:", "")
        payload = json.loads(json_str)
        assert len(payload["error_summary"]) <= 200


class TestEscalateTask:
    """Tests for the main escalate_task function."""

    def test_escalate_task_creates_files(self, tmp_path):
        """Escalate task creates both escalation files."""
        info = escalate_task(
            task_dir=tmp_path,
            reason=EscalationReason.MAX_RETRIES_EXCEEDED,
            failed_phase="coding",
            error="Test error message",
            task_id="task-123",
        )

        assert (tmp_path / "escalation.json").exists()
        assert (tmp_path / "escalation_log.json").exists()
        assert info.reason == EscalationReason.MAX_RETRIES_EXCEEDED
        assert info.failed_phase == "coding"
        assert info.error_message == "Test error message"

    def test_escalate_task_with_exception(self, tmp_path):
        """Escalate task handles Exception objects."""
        try:
            raise ValueError("Test exception")
        except ValueError as e:
            info = escalate_task(
                task_dir=tmp_path,
                reason=EscalationReason.EXTERNAL_SERVICE_FAILURE,
                failed_phase="planning",
                error=e,
            )

        assert info.error_message == "Test exception"
        assert info.error_trace is not None
        assert "ValueError" in info.error_trace

    def test_escalate_task_with_context(self, tmp_path):
        """Escalate task with context and attempted fixes."""
        info = escalate_task(
            task_dir=tmp_path,
            reason=EscalationReason.VALIDATION_FAILED,
            failed_phase="validation",
            error="Validation failed",
            attempted_fixes=["Fix 1", "Fix 2"],
            context={"iteration": 5},
            iteration=5,
        )

        assert info.attempted_fixes == ["Fix 1", "Fix 2"]
        assert info.context["iteration"] == 5
        assert info.iteration == 5

    def test_escalate_task_emits_event(self, tmp_path, capsys):
        """Escalate task emits IPC event when task_id provided."""
        escalate_task(
            task_dir=tmp_path,
            reason=EscalationReason.MAX_RETRIES_EXCEEDED,
            failed_phase="coding",
            error="Test error",
            task_id="task-emit-test",
        )

        captured = capsys.readouterr()
        assert "__TASK_ESCALATION__:" in captured.out
        assert "task-emit-test" in captured.out

    def test_escalate_task_no_event_without_task_id(self, tmp_path, capsys):
        """Escalate task doesn't emit event without task_id."""
        escalate_task(
            task_dir=tmp_path,
            reason=EscalationReason.UNKNOWN,
            failed_phase="planning",
            error="Test",
        )

        captured = capsys.readouterr()
        assert "__TASK_ESCALATION__:" not in captured.out


class TestRoundTrip:
    """Integration tests for full escalation lifecycle."""

    def test_full_lifecycle(self, tmp_path):
        """Test complete escalation → guidance → retry lifecycle."""
        # 1. Escalate task
        info = escalate_task(
            task_dir=tmp_path,
            reason=EscalationReason.UNFIXABLE_QA_ISSUES,
            failed_phase="qa_review",
            error="Cannot auto-fix type errors",
            attempted_fixes=["Added type annotation", "Tried type casting"],
            subtask_id="subtask-auth",
        )
        assert info.guidance is None

        # 2. User provides guidance
        updated = update_escalation_guidance(tmp_path, "Use 'any' type as workaround")
        assert updated.guidance == "Use 'any' type as workaround"

        # 3. Verify guidance persisted
        loaded = load_escalation(tmp_path)
        assert loaded.guidance == "Use 'any' type as workaround"
        assert loaded.attempted_fixes == ["Added type annotation", "Tried type casting"]
        assert loaded.subtask_id == "subtask-auth"

        # 4. Clear after successful retry
        cleared = clear_escalation(tmp_path)
        assert cleared is True

        # 5. Verify cleared
        assert load_escalation(tmp_path) is None
        assert (tmp_path / "escalation_resolved.json").exists()
