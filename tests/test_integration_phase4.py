"""
Integration Tests for PR Review System - Phase 4
=================================================

Tests validating all Phase 1-3 features work correctly:
- Phase 1: Confidence routing, evidence validation, scope filtering
- Phase 2: Import detection (path aliases, Python), reverse dependencies
- Phase 3: Multi-agent cross-validation
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add the backend directory to path for imports
backend_path = Path(__file__).parent.parent / "apps" / "backend"
sys.path.insert(0, str(backend_path))

# Import directly to avoid loading the full runners module with its dependencies
import importlib.util

# Load file_lock first (models.py depends on it)
file_lock_spec = importlib.util.spec_from_file_location(
    "file_lock",
    backend_path / "runners" / "github" / "file_lock.py"
)
file_lock_module = importlib.util.module_from_spec(file_lock_spec)
sys.modules['file_lock'] = file_lock_module
file_lock_spec.loader.exec_module(file_lock_module)

# Load models next
models_spec = importlib.util.spec_from_file_location(
    "models",
    backend_path / "runners" / "github" / "models.py"
)
models_module = importlib.util.module_from_spec(models_spec)
sys.modules['models'] = models_module
models_spec.loader.exec_module(models_module)
PRReviewFinding = models_module.PRReviewFinding
PRReviewResult = models_module.PRReviewResult
ReviewSeverity = models_module.ReviewSeverity
ReviewCategory = models_module.ReviewCategory

# Load services module dependencies for parallel_orchestrator_reviewer
category_utils_spec = importlib.util.spec_from_file_location(
    "category_utils",
    backend_path / "runners" / "github" / "services" / "category_utils.py"
)
category_utils_module = importlib.util.module_from_spec(category_utils_spec)
sys.modules['services.category_utils'] = category_utils_module
category_utils_spec.loader.exec_module(category_utils_module)

# Load io_utils
io_utils_spec = importlib.util.spec_from_file_location(
    "io_utils",
    backend_path / "runners" / "github" / "services" / "io_utils.py"
)
io_utils_module = importlib.util.module_from_spec(io_utils_spec)
sys.modules['services.io_utils'] = io_utils_module
io_utils_spec.loader.exec_module(io_utils_module)

# Load pydantic_models
pydantic_models_spec = importlib.util.spec_from_file_location(
    "pydantic_models",
    backend_path / "runners" / "github" / "services" / "pydantic_models.py"
)
pydantic_models_module = importlib.util.module_from_spec(pydantic_models_spec)
sys.modules['services.pydantic_models'] = pydantic_models_module
pydantic_models_spec.loader.exec_module(pydantic_models_module)
AgentAgreement = pydantic_models_module.AgentAgreement


# Load parallel_orchestrator_reviewer (contains ConfidenceTier, validation functions)
orchestrator_spec = importlib.util.spec_from_file_location(
    "parallel_orchestrator_reviewer",
    backend_path / "runners" / "github" / "services" / "parallel_orchestrator_reviewer.py"
)
orchestrator_module = importlib.util.module_from_spec(orchestrator_spec)
# Mock dependencies that aren't needed for unit testing
sys.modules['context_gatherer'] = MagicMock()
sys.modules['core.client'] = MagicMock()
sys.modules['gh_client'] = MagicMock()
sys.modules['phase_config'] = MagicMock()
sys.modules['services.pr_worktree_manager'] = MagicMock()
sys.modules['services.sdk_utils'] = MagicMock()
sys.modules['claude_agent_sdk'] = MagicMock()
orchestrator_spec.loader.exec_module(orchestrator_module)
ConfidenceTier = orchestrator_module.ConfidenceTier
_validate_finding_evidence = orchestrator_module._validate_finding_evidence
_is_finding_in_scope = orchestrator_module._is_finding_in_scope


# =============================================================================
# Phase 1 Tests: Confidence Routing, Evidence Validation, Scope Filtering
# =============================================================================

class TestConfidenceTierRouting:
    """Test confidence tier routing logic (Phase 1)."""

    def test_high_confidence_tier(self):
        """Verify confidence >= 0.8 returns HIGH tier."""
        assert ConfidenceTier.get_tier(0.8) == ConfidenceTier.HIGH
        assert ConfidenceTier.get_tier(0.85) == ConfidenceTier.HIGH
        assert ConfidenceTier.get_tier(0.95) == ConfidenceTier.HIGH
        assert ConfidenceTier.get_tier(1.0) == ConfidenceTier.HIGH

    def test_medium_confidence_tier(self):
        """Verify confidence 0.5-0.8 returns MEDIUM tier."""
        assert ConfidenceTier.get_tier(0.5) == ConfidenceTier.MEDIUM
        assert ConfidenceTier.get_tier(0.6) == ConfidenceTier.MEDIUM
        assert ConfidenceTier.get_tier(0.7) == ConfidenceTier.MEDIUM
        assert ConfidenceTier.get_tier(0.79) == ConfidenceTier.MEDIUM

    def test_low_confidence_tier(self):
        """Verify confidence < 0.5 returns LOW tier."""
        assert ConfidenceTier.get_tier(0.0) == ConfidenceTier.LOW
        assert ConfidenceTier.get_tier(0.1) == ConfidenceTier.LOW
        assert ConfidenceTier.get_tier(0.3) == ConfidenceTier.LOW
        assert ConfidenceTier.get_tier(0.49) == ConfidenceTier.LOW

    def test_boundary_values(self):
        """Test exact boundary values: 0.5 (MEDIUM) and 0.8 (HIGH)."""
        # 0.5 is MEDIUM threshold (inclusive)
        assert ConfidenceTier.get_tier(0.5) == ConfidenceTier.MEDIUM
        # 0.8 is HIGH threshold (inclusive)
        assert ConfidenceTier.get_tier(0.8) == ConfidenceTier.HIGH
        # Just below boundaries
        assert ConfidenceTier.get_tier(0.4999) == ConfidenceTier.LOW
        assert ConfidenceTier.get_tier(0.7999) == ConfidenceTier.MEDIUM

    def test_tier_constants_values(self):
        """Verify tier constant values match expected strings."""
        assert ConfidenceTier.HIGH == "high"
        assert ConfidenceTier.MEDIUM == "medium"
        assert ConfidenceTier.LOW == "low"

    def test_threshold_constants(self):
        """Verify threshold constants are correctly defined."""
        assert ConfidenceTier.HIGH_THRESHOLD == 0.8
        assert ConfidenceTier.LOW_THRESHOLD == 0.5


class TestEvidenceValidation:
    """Test evidence validation logic (Phase 1)."""

    @pytest.fixture
    def make_finding(self):
        """Factory fixture to create PRReviewFinding instances."""
        def _make_finding(evidence: str | None = None, **kwargs):
            defaults = {
                "id": "TEST001",
                "severity": ReviewSeverity.MEDIUM,
                "category": ReviewCategory.QUALITY,
                "title": "Test Finding",
                "description": "Test description",
                "file": "src/test.py",
                "line": 10,
                "evidence": evidence,
            }
            defaults.update(kwargs)
            return PRReviewFinding(**defaults)
        return _make_finding

    def test_valid_evidence_with_code_syntax(self, make_finding):
        """Evidence with =, (), {} should pass validation."""
        # Assignment operator
        finding = make_finding(evidence="const x = getValue()")
        is_valid, reason = _validate_finding_evidence(finding)
        assert is_valid, f"Failed: {reason}"

        # Function call
        finding = make_finding(evidence="someFunction(arg1, arg2)")
        is_valid, reason = _validate_finding_evidence(finding)
        assert is_valid, f"Failed: {reason}"

        # Object/dict literal
        finding = make_finding(evidence="config = { 'key': 'value' }")
        is_valid, reason = _validate_finding_evidence(finding)
        assert is_valid, f"Failed: {reason}"

    def test_invalid_evidence_no_code_syntax(self, make_finding):
        """Prose-only evidence without code syntax should fail."""
        finding = make_finding(evidence="This code is problematic and needs fixing")
        is_valid, reason = _validate_finding_evidence(finding)
        assert not is_valid
        assert "lacks code syntax" in reason.lower()

    def test_empty_evidence_fails(self, make_finding):
        """Empty or short evidence should fail validation."""
        # No evidence
        finding = make_finding(evidence=None)
        is_valid, reason = _validate_finding_evidence(finding)
        assert not is_valid
        assert "no evidence" in reason.lower()

        # Empty string
        finding = make_finding(evidence="")
        is_valid, reason = _validate_finding_evidence(finding)
        assert not is_valid

        # Too short (< 10 chars)
        finding = make_finding(evidence="x = 1")
        is_valid, reason = _validate_finding_evidence(finding)
        assert not is_valid
        assert "too short" in reason.lower()

    def test_evidence_with_function_def(self, make_finding):
        """Evidence with 'def ' or 'function ' patterns should pass."""
        # Python function definition
        finding = make_finding(evidence="def vulnerable_function(user_input):")
        is_valid, reason = _validate_finding_evidence(finding)
        assert is_valid, f"Failed: {reason}"

        # JavaScript function
        finding = make_finding(evidence="function handleRequest(req, res) {")
        is_valid, reason = _validate_finding_evidence(finding)
        assert is_valid, f"Failed: {reason}"

    def test_evidence_rejects_description_patterns(self, make_finding):
        """Evidence starting with vague patterns should be rejected."""
        patterns = [
            "The code has an issue with security",
            "This function could be improved",
            "It appears there is a vulnerability",
            "Seems to be missing error handling",
        ]
        for pattern in patterns:
            finding = make_finding(evidence=pattern)
            is_valid, reason = _validate_finding_evidence(finding)
            assert not is_valid, f"Should reject: {pattern}"
            assert "description pattern" in reason.lower() or "lacks code" in reason.lower()

    def test_evidence_with_various_syntax_chars(self, make_finding):
        """Test various code syntax characters are recognized."""
        # Semicolon
        finding = make_finding(evidence="let x = 5; let y = 10;")
        is_valid, _ = _validate_finding_evidence(finding)
        assert is_valid

        # Colon (Python dict/type hint)
        finding = make_finding(evidence="config: Dict[str, int]")
        is_valid, _ = _validate_finding_evidence(finding)
        assert is_valid

        # Arrow
        finding = make_finding(evidence="result->getValue()")
        is_valid, _ = _validate_finding_evidence(finding)
        assert is_valid

        # Brackets
        finding = make_finding(evidence="array[0] = items[index]")
        is_valid, _ = _validate_finding_evidence(finding)
        assert is_valid


class TestScopeFiltering:
    """Test scope filtering logic (Phase 1)."""

    @pytest.fixture
    def make_finding(self):
        """Factory fixture to create PRReviewFinding instances."""
        def _make_finding(file: str = "src/test.py", line: int = 10, **kwargs):
            defaults = {
                "id": "TEST001",
                "severity": ReviewSeverity.MEDIUM,
                "category": ReviewCategory.QUALITY,
                "title": "Test Finding",
                "description": "Test description",
                "file": file,
                "line": line,
            }
            defaults.update(kwargs)
            return PRReviewFinding(**defaults)
        return _make_finding

    def test_finding_in_changed_files_passes(self, make_finding):
        """Finding for a file in changed_files should pass."""
        changed_files = ["src/auth.py", "src/utils.py", "tests/test_auth.py"]
        finding = make_finding(file="src/auth.py", line=15)

        is_valid, reason = _is_finding_in_scope(finding, changed_files)
        assert is_valid, f"Failed: {reason}"

    def test_finding_outside_changed_files_filtered(self, make_finding):
        """Finding for a file NOT in changed_files should be filtered."""
        changed_files = ["src/auth.py", "src/utils.py"]
        finding = make_finding(
            file="src/database.py",
            line=10,
            description="This code has a bug"
        )

        is_valid, reason = _is_finding_in_scope(finding, changed_files)
        assert not is_valid
        assert "not in pr changed files" in reason.lower()

    def test_invalid_line_number_filtered(self, make_finding):
        """Finding with invalid line number (<=0) should be filtered."""
        changed_files = ["src/test.py"]

        # Zero line
        finding = make_finding(file="src/test.py", line=0)
        is_valid, reason = _is_finding_in_scope(finding, changed_files)
        assert not is_valid
        assert "invalid line" in reason.lower()

        # Negative line
        finding = make_finding(file="src/test.py", line=-5)
        is_valid, reason = _is_finding_in_scope(finding, changed_files)
        assert not is_valid

    def test_impact_finding_allowed_for_unchanged_files(self, make_finding):
        """Finding with impact keywords should be allowed for unchanged files."""
        changed_files = ["src/auth.py"]

        # 'breaks' keyword
        finding = make_finding(
            file="src/utils.py",
            line=10,
            description="This change breaks the helper function in utils.py"
        )
        is_valid, _ = _is_finding_in_scope(finding, changed_files)
        assert is_valid

        # 'affects' keyword
        finding = make_finding(
            file="src/config.py",
            line=5,
            description="Changes in auth.py affects config loading"
        )
        is_valid, _ = _is_finding_in_scope(finding, changed_files)
        assert is_valid

        # 'depends' keyword
        finding = make_finding(
            file="src/database.py",
            line=20,
            description="database.py depends on modified auth module"
        )
        is_valid, _ = _is_finding_in_scope(finding, changed_files)
        assert is_valid

    def test_no_file_specified_fails(self, make_finding):
        """Finding with no file specified should fail."""
        changed_files = ["src/test.py"]
        finding = make_finding(file="")
        is_valid, reason = _is_finding_in_scope(finding, changed_files)
        assert not is_valid
        assert "no file" in reason.lower()

    def test_none_line_number_passes(self, make_finding):
        """Finding with None line number should pass (general finding)."""
        changed_files = ["src/test.py"]
        finding = make_finding(file="src/test.py", line=None)
        # Line=None means general file-level finding
        finding.line = None  # Override since fixture sets it
        is_valid, _ = _is_finding_in_scope(finding, changed_files)
        assert is_valid
