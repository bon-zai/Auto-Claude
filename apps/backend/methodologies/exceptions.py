"""Exception hierarchy for the plugin framework.

Defines all custom exceptions used by the methodologies/plugin system.
Following architecture-defined patterns from Error-Handling-Patterns.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # No additional type imports needed


class AutoClaudeError(Exception):
    """Base exception for all Auto Claude errors.

    All framework-level exceptions should inherit from this class
    to enable catching all Auto Claude errors with a single except clause.
    """

    pass


class PluginError(AutoClaudeError):
    """Base exception for plugin-related errors.

    All plugin-specific exceptions should inherit from this class.
    Use this for general plugin failures that don't fit other categories.
    """

    pass


class ManifestValidationError(PluginError):
    """Raised when manifest.yaml is invalid.

    This exception is raised when:
    - manifest.yaml is missing required fields
    - Field values have incorrect types
    - Schema validation fails
    - Version constraints cannot be satisfied

    Attributes:
        path: Path to the invalid manifest file
        errors: List of validation error messages
    """

    def __init__(self, path: Path | str, errors: list[str]) -> None:
        """Initialize with manifest path and error details.

        Args:
            path: Path to the invalid manifest file
            errors: List of validation error messages
        """
        self.path: Path = path if isinstance(path, Path) else Path(path)
        self.errors: list[str] = errors
        if errors:
            error_summary = "\n  - " + "\n  - ".join(errors)
        else:
            error_summary = " (no details)"
        super().__init__(f"Invalid manifest at {path}:{error_summary}")


class PluginLoadError(PluginError):
    """Raised when plugin module fails to load.

    This exception is raised when:
    - Plugin directory structure is invalid
    - Required Python modules cannot be imported
    - Plugin entry point is missing or invalid
    - Dependencies are missing
    """

    pass


class ProtocolViolationError(PluginError):
    """Raised when a plugin violates its Protocol contract.

    This exception is raised when:
    - A plugin doesn't implement all required Protocol methods
    - Method signatures don't match the Protocol definition
    - Return types don't match expected types
    - Runtime behavior violates Protocol semantics

    Attributes:
        methodology_name: Name of the methodology that violated the Protocol
        missing_methods: List of method names that are missing or invalid
    """

    def __init__(
        self,
        message: str,
        methodology_name: str = "",
        missing_methods: list[str] | None = None,
    ) -> None:
        """Initialize with violation details.

        Args:
            message: Human-readable error message
            methodology_name: Name of the methodology that violated the Protocol
            missing_methods: List of method names that are missing or invalid
        """
        self.methodology_name = methodology_name
        self.missing_methods = missing_methods or []
        super().__init__(message)
