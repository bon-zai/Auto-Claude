"""Manifest loader and dataclasses for methodology plugins.

This module provides the manifest loading functionality with JSON Schema validation.
It defines dataclasses representing the manifest structure and validates
manifest.yaml files against a schema before creating typed objects.

Architecture Source: architecture.md#Manifest-Schema
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import jsonschema
import yaml

from apps.backend.methodologies.exceptions import ManifestValidationError


def _is_valid_uri(uri: str) -> bool:
    """Check if a string is a valid HTTP/HTTPS URI.

    For manifest metadata fields (homepage, repository), we only accept
    HTTP and HTTPS schemes as these are the standard web URLs.

    Args:
        uri: String to validate as URI

    Returns:
        True if valid HTTP/HTTPS URI, False otherwise
    """
    try:
        result = urlparse(uri)
        # Must have http/https scheme and netloc
        return result.scheme in ("http", "https") and bool(result.netloc)
    except (ValueError, AttributeError):
        return False


# Create a format checker with URI validation
_format_checker = jsonschema.FormatChecker()


@_format_checker.checks("uri", raises=jsonschema.FormatError)
def _check_uri(instance: str) -> bool:
    """Custom URI format checker for jsonschema."""
    if not isinstance(instance, str):
        return True  # Non-strings handled by type validation
    if not _is_valid_uri(instance):
        raise jsonschema.FormatError(f"'{instance}' is not a valid URI")
    return True


@dataclass
class PhaseDefinition:
    """Definition of a methodology phase from manifest.yaml.

    Represents a phase entry in the manifest's phases list.
    Each phase defines a distinct stage in the methodology pipeline.

    Attributes:
        id: Unique identifier for the phase
        name: Human-readable name for display
        description: Optional detailed description of the phase
        artifacts: List of artifact IDs produced by this phase
    """

    id: str
    name: str
    description: str = ""
    artifacts: list[str] = field(default_factory=list)


@dataclass
class CheckpointDefinition:
    """Definition of a checkpoint from manifest.yaml.

    Represents a checkpoint entry for Semi-Auto pause points.
    Checkpoints define where the methodology pauses for user review.

    Attributes:
        id: Unique identifier for the checkpoint
        phase: ID of the phase this checkpoint follows
        description: What the user should review at this checkpoint
    """

    id: str
    phase: str
    description: str = ""


@dataclass
class ArtifactDefinition:
    """Definition of an artifact from manifest.yaml.

    Represents an artifact entry that defines methodology outputs.

    Attributes:
        id: Unique identifier for the artifact
        name: Human-readable name for display
        type: Type of artifact (markdown, json, yaml, etc.)
        path: File path string relative to spec directory (e.g., "spec.md")
    """

    id: str
    name: str
    type: str = "markdown"
    path: str = ""


@dataclass
class MethodologyManifest:
    """Complete manifest for a methodology plugin.

    Contains all configuration from a methodology's manifest.yaml file.
    This dataclass is created after successful schema validation.

    Note: PhaseDefinition represents the static manifest structure, while
    Phase (from protocols.py) represents runtime state with status tracking.
    Conversion between these types occurs during plugin loading (Story 1.4).

    Attributes:
        name: Unique identifier for the methodology (required)
        version: Semantic version string (required)
        entry_point: Module.ClassName for the runner (required)
        phases: List of phase definitions (required)
        description: Human-readable description (optional)
        author: Author name or organization (optional)
        checkpoints: List of checkpoint definitions (optional)
        artifacts: List of artifact definitions (optional)
        min_auto_claude_version: Minimum Auto Claude version required (optional)
        runtime: Runtime requirement e.g. "python3.12" (optional)
        complexity_levels: Supported complexity levels (optional)
        execution_modes: Supported execution modes (optional)
        license: License identifier e.g. "MIT" (optional)
        homepage: Project homepage URL (optional)
        repository: Source repository URL (optional)
        keywords: List of keywords for discovery (optional)
    """

    name: str
    version: str
    entry_point: str
    phases: list[PhaseDefinition]
    description: str = ""
    author: str = ""
    checkpoints: list[CheckpointDefinition] = field(default_factory=list)
    artifacts: list[ArtifactDefinition] = field(default_factory=list)
    min_auto_claude_version: str = ""
    runtime: str = ""
    complexity_levels: list[str] = field(default_factory=list)
    execution_modes: list[str] = field(default_factory=list)
    license: str = ""
    homepage: str = ""
    repository: str = ""
    keywords: list[str] = field(default_factory=list)


def _parse_phases(phases_data: list[dict[str, Any]]) -> list[PhaseDefinition]:
    """Parse phase definitions from manifest data.

    Args:
        phases_data: List of phase dictionaries from YAML

    Returns:
        List of PhaseDefinition dataclass instances
    """
    return [
        PhaseDefinition(
            id=phase["id"],
            name=phase["name"],
            description=phase.get("description", ""),
            artifacts=phase.get("artifacts", []),
        )
        for phase in phases_data
    ]


def _parse_checkpoints(
    checkpoints_data: list[dict[str, Any]] | None,
) -> list[CheckpointDefinition]:
    """Parse checkpoint definitions from manifest data.

    Args:
        checkpoints_data: List of checkpoint dictionaries from YAML, or None

    Returns:
        List of CheckpointDefinition dataclass instances
    """
    if not checkpoints_data:
        return []
    return [
        CheckpointDefinition(
            id=cp["id"],
            phase=cp["phase"],
            description=cp.get("description", ""),
        )
        for cp in checkpoints_data
    ]


def _parse_artifacts(
    artifacts_data: list[dict[str, Any]] | None,
) -> list[ArtifactDefinition]:
    """Parse artifact definitions from manifest data.

    Args:
        artifacts_data: List of artifact dictionaries from YAML, or None

    Returns:
        List of ArtifactDefinition dataclass instances
    """
    if not artifacts_data:
        return []
    return [
        ArtifactDefinition(
            id=art["id"],
            name=art["name"],
            type=art.get("type", "markdown"),
            path=art.get("path", ""),
        )
        for art in artifacts_data
    ]


def _validate_duplicate_ids(
    items: list[dict[str, Any]] | None,
    item_type: str,
) -> list[str]:
    """Check for duplicate IDs in a list of items.

    Args:
        items: List of item dictionaries with 'id' fields
        item_type: Type name for error messages (e.g., "phase", "checkpoint")

    Returns:
        List of error messages for duplicate IDs
    """
    if not items:
        return []

    # Skip if items is not a list (schema validation will catch this)
    if not isinstance(items, list):
        return []

    errors: list[str] = []
    seen_ids: set[str] = set()

    for item in items:
        # Skip if item is not a dict (schema validation will catch this)
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if item_id:
            if item_id in seen_ids:
                errors.append(f"Duplicate {item_type} ID: '{item_id}'")
            else:
                seen_ids.add(item_id)

    return errors


def _validate_checkpoint_references(
    checkpoints: list[dict[str, Any]] | None,
    phases: list[dict[str, Any]],
) -> list[str]:
    """Validate that checkpoint phase references exist.

    Args:
        checkpoints: List of checkpoint dictionaries
        phases: List of phase dictionaries

    Returns:
        List of error messages for invalid references
    """
    if not checkpoints:
        return []

    errors: list[str] = []
    phase_ids = {phase.get("id") for phase in phases if phase.get("id")}

    for checkpoint in checkpoints:
        checkpoint_id = checkpoint.get("id", "unknown")
        phase_ref = checkpoint.get("phase")
        if phase_ref and phase_ref not in phase_ids:
            errors.append(
                f"Checkpoint '{checkpoint_id}' references non-existent phase: '{phase_ref}'"
            )

    return errors


def _validate_manifest(manifest_data: dict[str, Any], path: Path) -> list[str]:
    """Validate manifest data against JSON Schema and semantic rules.

    Performs:
    1. JSON Schema validation (structure, types, formats)
    2. Duplicate ID validation (phases, checkpoints, artifacts)
    3. Cross-reference validation (checkpoint → phase references)

    Args:
        manifest_data: Parsed YAML data dictionary
        path: Path to the manifest file (for error messages)

    Returns:
        List of validation error messages (empty if valid)
    """
    # Load the JSON Schema
    schema_path = Path(__file__).parent / "schemas" / "manifest.schema.json"
    if not schema_path.exists():
        return [f"Schema file not found: {schema_path}"]

    try:
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid schema JSON: {e}"]

    # Collect all validation errors
    errors: list[str] = []

    # 1. JSON Schema validation with format checking (for URI validation)
    validator = jsonschema.Draft7Validator(schema, format_checker=_format_checker)

    for error in validator.iter_errors(manifest_data):
        # Format error message with path and description
        if error.path:
            field_path = ".".join(str(p) for p in error.path)
            errors.append(f"{field_path}: {error.message}")
        else:
            errors.append(error.message)

    # 2. Duplicate ID validation
    phases = manifest_data.get("phases", [])
    checkpoints = manifest_data.get("checkpoints")
    artifacts = manifest_data.get("artifacts")

    errors.extend(_validate_duplicate_ids(phases, "phase"))
    errors.extend(_validate_duplicate_ids(checkpoints, "checkpoint"))
    errors.extend(_validate_duplicate_ids(artifacts, "artifact"))

    # 3. Cross-reference validation
    errors.extend(_validate_checkpoint_references(checkpoints, phases))

    return errors


def load_manifest(path: Path) -> MethodologyManifest:
    """Load and validate a methodology manifest.

    Reads a manifest.yaml file, validates it against the JSON Schema,
    and returns a MethodologyManifest dataclass with all fields populated.

    Args:
        path: Path to the manifest.yaml file

    Returns:
        MethodologyManifest dataclass with validated data

    Raises:
        ManifestValidationError: If manifest is missing, malformed, or invalid
        FileNotFoundError: If the manifest file doesn't exist
    """
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")

    # Read and parse YAML
    try:
        with open(path, encoding="utf-8") as f:
            manifest_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ManifestValidationError(path, [f"Invalid YAML: {e}"]) from e

    if not manifest_data or not isinstance(manifest_data, dict):
        raise ManifestValidationError(path, ["Manifest must be a YAML object"])

    # Validate against JSON Schema
    errors = _validate_manifest(manifest_data, path)
    if errors:
        raise ManifestValidationError(path, errors)

    # Parse and create dataclass
    return MethodologyManifest(
        name=manifest_data["name"],
        version=manifest_data["version"],
        entry_point=manifest_data["entry_point"],
        phases=_parse_phases(manifest_data["phases"]),
        description=manifest_data.get("description", ""),
        author=manifest_data.get("author", ""),
        checkpoints=_parse_checkpoints(manifest_data.get("checkpoints")),
        artifacts=_parse_artifacts(manifest_data.get("artifacts")),
        min_auto_claude_version=manifest_data.get("min_auto_claude_version", ""),
        runtime=manifest_data.get("runtime", ""),
        complexity_levels=manifest_data.get("complexity_levels", []),
        execution_modes=manifest_data.get("execution_modes", []),
        license=manifest_data.get("license", ""),
        homepage=manifest_data.get("homepage", ""),
        repository=manifest_data.get("repository", ""),
        keywords=manifest_data.get("keywords", []),
    )
