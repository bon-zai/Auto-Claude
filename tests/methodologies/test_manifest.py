"""Unit tests for the manifest loader and schema validation.

Tests for apps/backend/methodologies/manifest.py covering:
- Valid manifest loading
- Missing required fields error
- Invalid field types error
- Optional fields handling
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from apps.backend.methodologies.exceptions import ManifestValidationError
from apps.backend.methodologies.manifest import (
    ArtifactDefinition,
    CheckpointDefinition,
    MethodologyManifest,
    PhaseDefinition,
    load_manifest,
)


@pytest.fixture
def valid_manifest_data() -> dict[str, Any]:
    """Return a valid manifest data dictionary."""
    return {
        "name": "test-methodology",
        "version": "1.0.0",
        "description": "Test methodology for unit tests",
        "author": "Test Author",
        "entry_point": "methodology.TestRunner",
        "phases": [
            {
                "id": "discovery",
                "name": "Discovery",
                "description": "Gather project context",
                "artifacts": ["context.json"],
            },
            {
                "id": "planning",
                "name": "Planning",
                "description": "Create implementation plan",
            },
        ],
        "checkpoints": [
            {
                "id": "after_planning",
                "phase": "planning",
                "description": "Review implementation plan",
            }
        ],
        "artifacts": [
            {
                "id": "spec",
                "name": "Specification",
                "type": "markdown",
                "path": "spec.md",
            }
        ],
    }


@pytest.fixture
def minimal_manifest_data() -> dict[str, Any]:
    """Return a minimal valid manifest with only required fields."""
    return {
        "name": "minimal-test",
        "version": "0.1.0",
        "entry_point": "module.Runner",
        "phases": [
            {
                "id": "main",
                "name": "Main Phase",
            }
        ],
    }


@pytest.fixture
def manifest_file(tmp_path: Path, valid_manifest_data: dict[str, Any]) -> Path:
    """Create a valid manifest file in a temp directory."""
    manifest_path = tmp_path / "manifest.yaml"
    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.dump(valid_manifest_data, f)
    return manifest_path


@pytest.fixture
def minimal_manifest_file(
    tmp_path: Path, minimal_manifest_data: dict[str, Any]
) -> Path:
    """Create a minimal manifest file in a temp directory."""
    manifest_path = tmp_path / "manifest.yaml"
    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.dump(minimal_manifest_data, f)
    return manifest_path


class TestLoadManifestValid:
    """Tests for loading valid manifests."""

    def test_load_valid_manifest_returns_dataclass(
        self, manifest_file: Path
    ) -> None:
        """Test that a valid manifest returns a MethodologyManifest."""
        result = load_manifest(manifest_file)

        assert isinstance(result, MethodologyManifest)

    def test_load_valid_manifest_required_fields(
        self, manifest_file: Path
    ) -> None:
        """Test that required fields are correctly populated."""
        result = load_manifest(manifest_file)

        assert result.name == "test-methodology"
        assert result.version == "1.0.0"
        assert result.entry_point == "methodology.TestRunner"
        assert len(result.phases) == 2

    def test_load_valid_manifest_optional_fields(
        self, manifest_file: Path
    ) -> None:
        """Test that optional fields are correctly populated."""
        result = load_manifest(manifest_file)

        assert result.description == "Test methodology for unit tests"
        assert result.author == "Test Author"
        assert len(result.checkpoints) == 1
        assert len(result.artifacts) == 1

    def test_load_valid_manifest_phase_definitions(
        self, manifest_file: Path
    ) -> None:
        """Test that phase definitions are correctly parsed."""
        result = load_manifest(manifest_file)

        discovery = result.phases[0]
        assert isinstance(discovery, PhaseDefinition)
        assert discovery.id == "discovery"
        assert discovery.name == "Discovery"
        assert discovery.description == "Gather project context"
        assert discovery.artifacts == ["context.json"]

        planning = result.phases[1]
        assert planning.id == "planning"
        assert planning.artifacts == []  # Default empty list

    def test_load_valid_manifest_checkpoint_definitions(
        self, manifest_file: Path
    ) -> None:
        """Test that checkpoint definitions are correctly parsed."""
        result = load_manifest(manifest_file)

        checkpoint = result.checkpoints[0]
        assert isinstance(checkpoint, CheckpointDefinition)
        assert checkpoint.id == "after_planning"
        assert checkpoint.phase == "planning"
        assert checkpoint.description == "Review implementation plan"

    def test_load_valid_manifest_artifact_definitions(
        self, manifest_file: Path
    ) -> None:
        """Test that artifact definitions are correctly parsed."""
        result = load_manifest(manifest_file)

        artifact = result.artifacts[0]
        assert isinstance(artifact, ArtifactDefinition)
        assert artifact.id == "spec"
        assert artifact.name == "Specification"
        assert artifact.type == "markdown"
        assert artifact.path == "spec.md"

    def test_load_minimal_manifest(self, minimal_manifest_file: Path) -> None:
        """Test loading a manifest with only required fields."""
        result = load_manifest(minimal_manifest_file)

        assert result.name == "minimal-test"
        assert result.version == "0.1.0"
        assert result.entry_point == "module.Runner"
        assert len(result.phases) == 1
        assert result.description == ""  # Default empty string
        assert result.author == ""
        assert result.checkpoints == []  # Default empty list
        assert result.artifacts == []


class TestLoadManifestMissingRequiredFields:
    """Tests for error handling when required fields are missing."""

    def test_missing_name_field(self, tmp_path: Path) -> None:
        """Test that missing 'name' field raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path
        assert any("name" in error for error in exc_info.value.errors)

    def test_missing_version_field(self, tmp_path: Path) -> None:
        """Test that missing 'version' field raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path
        assert any("version" in error for error in exc_info.value.errors)

    def test_missing_entry_point_field(self, tmp_path: Path) -> None:
        """Test that missing 'entry_point' field raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "phases": [{"id": "main", "name": "Main"}],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path
        assert any("entry_point" in error for error in exc_info.value.errors)

    def test_missing_phases_field(self, tmp_path: Path) -> None:
        """Test that missing 'phases' field raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path
        assert any("phases" in error for error in exc_info.value.errors)

    def test_multiple_missing_fields(self, tmp_path: Path) -> None:
        """Test that multiple missing fields are all reported."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "description": "Missing required fields",
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path
        # Should have multiple errors for name, version, entry_point, phases
        assert len(exc_info.value.errors) >= 4


class TestLoadManifestInvalidFieldTypes:
    """Tests for error handling when field types are invalid."""

    def test_invalid_name_type(self, tmp_path: Path) -> None:
        """Test that non-string 'name' raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": 123,  # Should be string
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path
        assert any("name" in error.lower() for error in exc_info.value.errors)

    def test_invalid_version_format(self, tmp_path: Path) -> None:
        """Test that invalid version format raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "not-a-version",  # Should be semver
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path
        assert any("version" in error.lower() for error in exc_info.value.errors)

    def test_invalid_entry_point_format(self, tmp_path: Path) -> None:
        """Test that invalid entry_point format raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "invalid",  # Should be module.ClassName
            "phases": [{"id": "main", "name": "Main"}],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path
        assert any("entry_point" in error.lower() for error in exc_info.value.errors)

    def test_invalid_phases_type(self, tmp_path: Path) -> None:
        """Test that non-array 'phases' raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": "not-an-array",  # Should be array
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path
        assert any("phases" in error.lower() for error in exc_info.value.errors)

    def test_empty_phases_array(self, tmp_path: Path) -> None:
        """Test that empty 'phases' array raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [],  # Should have at least one phase
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path
        assert any("phases" in error.lower() for error in exc_info.value.errors)

    def test_phase_missing_required_fields(self, tmp_path: Path) -> None:
        """Test that phase missing 'id' or 'name' raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"description": "Missing id and name"}],  # Missing required
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path
        assert len(exc_info.value.errors) > 0

    def test_checkpoint_missing_required_fields(self, tmp_path: Path) -> None:
        """Test that checkpoint missing required fields raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "checkpoints": [{"description": "Missing id and phase"}],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path
        assert len(exc_info.value.errors) > 0


class TestLoadManifestOptionalFields:
    """Tests for handling of optional fields."""

    def test_optional_description_not_present(
        self, minimal_manifest_file: Path
    ) -> None:
        """Test that missing optional 'description' defaults to empty string."""
        result = load_manifest(minimal_manifest_file)
        assert result.description == ""

    def test_optional_author_not_present(
        self, minimal_manifest_file: Path
    ) -> None:
        """Test that missing optional 'author' defaults to empty string."""
        result = load_manifest(minimal_manifest_file)
        assert result.author == ""

    def test_optional_checkpoints_not_present(
        self, minimal_manifest_file: Path
    ) -> None:
        """Test that missing optional 'checkpoints' defaults to empty list."""
        result = load_manifest(minimal_manifest_file)
        assert result.checkpoints == []

    def test_optional_artifacts_not_present(
        self, minimal_manifest_file: Path
    ) -> None:
        """Test that missing optional 'artifacts' defaults to empty list."""
        result = load_manifest(minimal_manifest_file)
        assert result.artifacts == []

    def test_phase_optional_description(self, tmp_path: Path) -> None:
        """Test that phase without 'description' defaults to empty string."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],  # No description
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        result = load_manifest(manifest_path)
        assert result.phases[0].description == ""

    def test_phase_optional_artifacts(self, tmp_path: Path) -> None:
        """Test that phase without 'artifacts' defaults to empty list."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],  # No artifacts
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        result = load_manifest(manifest_path)
        assert result.phases[0].artifacts == []

    def test_artifact_optional_type_default(self, tmp_path: Path) -> None:
        """Test that artifact without 'type' defaults to 'markdown'."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "artifacts": [{"id": "doc", "name": "Document"}],  # No type
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        result = load_manifest(manifest_path)
        assert result.artifacts[0].type == "markdown"


class TestLoadManifestErrorMessages:
    """Tests for error message quality."""

    def test_error_includes_manifest_path(self, tmp_path: Path) -> None:
        """Test that error message includes the manifest file path."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {"description": "Missing required fields"}
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert str(manifest_path) in str(exc_info.value)
        assert exc_info.value.path == manifest_path

    def test_error_lists_all_missing_fields(self, tmp_path: Path) -> None:
        """Test that all missing fields are listed in error."""
        manifest_path = tmp_path / "manifest.yaml"
        # Use a dict with some valid content so it passes the "is dict" check
        # but fails schema validation for missing required fields
        data = {"description": "Missing all required fields"}
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        # Should report name, version, entry_point, phases as missing
        assert len(exc_info.value.errors) >= 4


class TestLoadManifestArchitectureFields:
    """Tests for architecture-defined optional fields."""

    def test_manifest_with_all_architecture_fields(self, tmp_path: Path) -> None:
        """Test loading manifest with all architecture-defined optional fields."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "full-featured",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "min_auto_claude_version": "3.0.0",
            "runtime": "python3.12",
            "complexity_levels": ["quick", "standard", "complex"],
            "execution_modes": ["full_auto", "semi_auto"],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        result = load_manifest(manifest_path)

        assert result.min_auto_claude_version == "3.0.0"
        assert result.runtime == "python3.12"
        assert result.complexity_levels == ["quick", "standard", "complex"]
        assert result.execution_modes == ["full_auto", "semi_auto"]

    def test_architecture_fields_default_when_not_present(
        self, minimal_manifest_file: Path
    ) -> None:
        """Test that architecture fields default to empty when not present."""
        result = load_manifest(minimal_manifest_file)

        assert result.min_auto_claude_version == ""
        assert result.runtime == ""
        assert result.complexity_levels == []
        assert result.execution_modes == []

    def test_invalid_complexity_level_rejected(self, tmp_path: Path) -> None:
        """Test that invalid complexity level values are rejected."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "complexity_levels": ["invalid_level"],  # Not in enum
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("complexity_levels" in error.lower() for error in exc_info.value.errors)

    def test_invalid_execution_mode_rejected(self, tmp_path: Path) -> None:
        """Test that invalid execution mode values are rejected."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "execution_modes": ["invalid_mode"],  # Not in enum
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("execution_modes" in error.lower() for error in exc_info.value.errors)


class TestLoadManifestUTF8:
    """Tests for UTF-8 and Unicode handling."""

    def test_manifest_with_utf8_author(self, tmp_path: Path) -> None:
        """Test loading manifest with UTF-8 author name."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "author": "André Mikalsen",
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True)

        result = load_manifest(manifest_path)
        assert result.author == "André Mikalsen"

    def test_manifest_with_utf8_description(self, tmp_path: Path) -> None:
        """Test loading manifest with UTF-8 description containing special chars."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "description": "Méthodologie für die Entwicklung — создание проектов",
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True)

        result = load_manifest(manifest_path)
        assert "Méthodologie" in result.description
        assert "создание" in result.description

    def test_manifest_with_utf8_keywords(self, tmp_path: Path) -> None:
        """Test loading manifest with UTF-8 keywords."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "keywords": ["développement", "テスト", "测试"],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True)

        result = load_manifest(manifest_path)
        assert "développement" in result.keywords
        assert "テスト" in result.keywords
        assert "测试" in result.keywords

    def test_manifest_with_utf8_bom(self, tmp_path: Path) -> None:
        """Test loading manifest with UTF-8 BOM marker."""
        manifest_path = tmp_path / "manifest.yaml"
        content = """\
name: test-plugin
version: "1.0.0"
entry_point: module.Runner
phases:
  - id: main
    name: Main
"""
        # Write with UTF-8 BOM
        with open(manifest_path, "wb") as f:
            f.write(b"\xef\xbb\xbf")  # UTF-8 BOM
            f.write(content.encode("utf-8"))

        result = load_manifest(manifest_path)
        assert result.name == "test-plugin"


class TestLoadManifestDuplicateIdValidation:
    """Tests for duplicate ID validation."""

    def test_duplicate_phase_ids_rejected(self, tmp_path: Path) -> None:
        """Test that duplicate phase IDs are rejected."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [
                {"id": "main", "name": "Main Phase 1"},
                {"id": "main", "name": "Main Phase 2"},  # Duplicate ID
            ],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("duplicate" in error.lower() and "phase" in error.lower()
                   for error in exc_info.value.errors)

    def test_duplicate_checkpoint_ids_rejected(self, tmp_path: Path) -> None:
        """Test that duplicate checkpoint IDs are rejected."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "checkpoints": [
                {"id": "cp1", "phase": "main", "description": "First"},
                {"id": "cp1", "phase": "main", "description": "Second"},  # Duplicate
            ],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("duplicate" in error.lower() and "checkpoint" in error.lower()
                   for error in exc_info.value.errors)

    def test_duplicate_artifact_ids_rejected(self, tmp_path: Path) -> None:
        """Test that duplicate artifact IDs are rejected."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "artifacts": [
                {"id": "doc", "name": "Document 1"},
                {"id": "doc", "name": "Document 2"},  # Duplicate
            ],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("duplicate" in error.lower() and "artifact" in error.lower()
                   for error in exc_info.value.errors)

    def test_unique_ids_across_types_allowed(self, tmp_path: Path) -> None:
        """Test that same ID in different types is allowed (phase, checkpoint, artifact)."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main Phase"}],
            "checkpoints": [{"id": "main", "phase": "main"}],  # Same ID, different type
            "artifacts": [{"id": "main", "name": "Main Doc"}],  # Same ID, different type
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        result = load_manifest(manifest_path)
        assert result.phases[0].id == "main"
        assert result.checkpoints[0].id == "main"
        assert result.artifacts[0].id == "main"


class TestLoadManifestCrossReferenceValidation:
    """Tests for cross-reference validation."""

    def test_checkpoint_references_nonexistent_phase(self, tmp_path: Path) -> None:
        """Test that checkpoint referencing non-existent phase is rejected."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "checkpoints": [
                {"id": "cp1", "phase": "nonexistent_phase"}  # Invalid reference
            ],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("nonexistent_phase" in error for error in exc_info.value.errors)
        assert any("cp1" in error for error in exc_info.value.errors)

    def test_checkpoint_references_valid_phase(self, tmp_path: Path) -> None:
        """Test that checkpoint referencing valid phase is accepted."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [
                {"id": "discovery", "name": "Discovery"},
                {"id": "planning", "name": "Planning"},
            ],
            "checkpoints": [
                {"id": "after_discovery", "phase": "discovery"},
                {"id": "after_planning", "phase": "planning"},
            ],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        result = load_manifest(manifest_path)
        assert len(result.checkpoints) == 2
        assert result.checkpoints[0].phase == "discovery"
        assert result.checkpoints[1].phase == "planning"


class TestLoadManifestURIValidation:
    """Tests for URI format validation."""

    def test_valid_homepage_uri(self, tmp_path: Path) -> None:
        """Test that valid homepage URI is accepted."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "homepage": "https://example.com/project",
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        result = load_manifest(manifest_path)
        assert result.homepage == "https://example.com/project"

    def test_valid_repository_uri(self, tmp_path: Path) -> None:
        """Test that valid repository URI is accepted."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "repository": "https://github.com/user/repo",
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        result = load_manifest(manifest_path)
        assert result.repository == "https://github.com/user/repo"

    def test_invalid_homepage_uri_rejected(self, tmp_path: Path) -> None:
        """Test that invalid homepage URI is rejected."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "homepage": "not-a-valid-uri",  # Invalid URI
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("homepage" in error.lower() for error in exc_info.value.errors)

    def test_invalid_repository_uri_rejected(self, tmp_path: Path) -> None:
        """Test that invalid repository URI is rejected."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "repository": "also-not-valid",  # Invalid URI
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("repository" in error.lower() for error in exc_info.value.errors)

    def test_non_http_uri_rejected(self, tmp_path: Path) -> None:
        """Test that non-HTTP/HTTPS URIs are rejected."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "homepage": "ftp://example.com/project",  # FTP not allowed
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("homepage" in error.lower() for error in exc_info.value.errors)

    def test_file_uri_rejected(self, tmp_path: Path) -> None:
        """Test that file:// URIs are rejected."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "repository": "file:///path/to/repo",  # file:// not allowed
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("repository" in error.lower() for error in exc_info.value.errors)


class TestLoadManifestMetadataFields:
    """Tests for optional metadata fields (license, homepage, repository, keywords)."""

    def test_manifest_with_all_metadata_fields(self, tmp_path: Path) -> None:
        """Test loading manifest with all metadata fields populated."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "license": "MIT",
            "homepage": "https://example.com/project",
            "repository": "https://github.com/user/repo",
            "keywords": ["testing", "automation", "ci-cd"],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        result = load_manifest(manifest_path)

        assert result.license == "MIT"
        assert result.homepage == "https://example.com/project"
        assert result.repository == "https://github.com/user/repo"
        assert result.keywords == ["testing", "automation", "ci-cd"]

    def test_metadata_fields_default_when_not_present(
        self, minimal_manifest_file: Path
    ) -> None:
        """Test that metadata fields default to empty when not present."""
        result = load_manifest(minimal_manifest_file)

        assert result.license == ""
        assert result.homepage == ""
        assert result.repository == ""
        assert result.keywords == []


class TestLoadManifestSchemaIntegration:
    """Integration tests for the production schema file."""

    def test_production_schema_file_exists_and_loads(self) -> None:
        """Test that the production schema file exists and is valid JSON."""
        import json
        from apps.backend.methodologies.manifest import Path as ManifestPath

        schema_path = ManifestPath(__file__).parent.parent.parent / \
            "apps" / "backend" / "methodologies" / "schemas" / "manifest.schema.json"

        assert schema_path.exists(), f"Schema file not found: {schema_path}"

        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)

        # Verify schema has expected structure
        assert schema.get("type") == "object"
        assert "required" in schema
        assert "properties" in schema
        assert set(schema["required"]) == {"name", "version", "entry_point", "phases"}

    def test_production_schema_validates_valid_manifest(self, tmp_path: Path) -> None:
        """Test that a valid manifest passes validation with production schema."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "production-test",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main Phase"}],
            "description": "Testing production schema",
            "author": "Test Author",
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        # Should not raise
        result = load_manifest(manifest_path)
        assert result.name == "production-test"


class TestLoadManifestSchemaErrors:
    """Tests for schema-related error conditions."""

    def test_malformed_schema_json_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that malformed schema JSON produces appropriate error."""
        # Create a malformed schema file
        malformed_schema_path = tmp_path / "malformed.schema.json"
        with open(malformed_schema_path, "w", encoding="utf-8") as f:
            f.write("{invalid json syntax")

        # Patch the schema path
        from apps.backend.methodologies import manifest as manifest_module
        original_file = manifest_module.__file__

        # Create the schemas directory structure
        schemas_dir = tmp_path / "schemas"
        schemas_dir.mkdir()
        schema_file = schemas_dir / "manifest.schema.json"
        with open(schema_file, "w", encoding="utf-8") as f:
            f.write("{invalid json")

        # Create a valid manifest
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        # Monkeypatch __file__ to point to our temp directory
        monkeypatch.setattr(manifest_module, "__file__", str(tmp_path / "manifest.py"))

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("schema" in error.lower() and "json" in error.lower()
                   for error in exc_info.value.errors)

    def test_schema_file_not_found_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that missing schema file produces appropriate error."""
        from apps.backend.methodologies import manifest as manifest_module

        # Create a valid manifest
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        # Monkeypatch __file__ to point to a directory without schemas/
        monkeypatch.setattr(manifest_module, "__file__", str(tmp_path / "manifest.py"))

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("schema" in error.lower() and "not found" in error.lower()
                   for error in exc_info.value.errors)


class TestLoadManifestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Test that non-existent file raises FileNotFoundError."""
        non_existent = tmp_path / "does-not-exist.yaml"

        with pytest.raises(FileNotFoundError):
            load_manifest(non_existent)

    def test_invalid_yaml_syntax(self, tmp_path: Path) -> None:
        """Test that invalid YAML raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write("invalid: yaml: syntax: [")

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("yaml" in error.lower() for error in exc_info.value.errors)

    def test_empty_file(self, tmp_path: Path) -> None:
        """Test that empty file raises ManifestValidationError."""
        manifest_path = tmp_path / "manifest.yaml"
        manifest_path.touch()

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert exc_info.value.path == manifest_path

    def test_manifest_with_extra_fields(self, tmp_path: Path) -> None:
        """Test that extra unrecognized fields are rejected by schema."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
            "unknown_field": "should fail",  # Extra field
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert len(exc_info.value.errors) > 0

    def test_version_with_prerelease(self, tmp_path: Path) -> None:
        """Test that version with prerelease identifier is valid."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "test-plugin",
            "version": "1.0.0-alpha.1",  # Valid semver with prerelease
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        result = load_manifest(manifest_path)
        assert result.version == "1.0.0-alpha.1"

    def test_name_kebab_case_validation(self, tmp_path: Path) -> None:
        """Test that name must be kebab-case format."""
        manifest_path = tmp_path / "manifest.yaml"
        data = {
            "name": "InvalidName",  # Should be kebab-case
            "version": "1.0.0",
            "entry_point": "module.Runner",
            "phases": [{"id": "main", "name": "Main"}],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        with pytest.raises(ManifestValidationError) as exc_info:
            load_manifest(manifest_path)

        assert any("name" in error.lower() for error in exc_info.value.errors)
