"""Methodology plugin loader with lazy loading and error isolation.

This module provides lazy loading of methodology plugins with proper error isolation.
A broken plugin doesn't crash the entire application - errors are raised only when
that specific plugin is requested.

Architecture Source: architecture.md#Plugin-Loading
"""

import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from apps.backend.methodologies.exceptions import (
    PluginLoadError,
    ProtocolViolationError,
)
from apps.backend.methodologies.manifest import MethodologyManifest, load_manifest
from apps.backend.methodologies.protocols import MethodologyRunner

if TYPE_CHECKING:
    from apps.backend.methodologies.registry import MethodologyRegistryImpl

logger = logging.getLogger(__name__)

#: Methods that a MethodologyRunner must implement to satisfy the Protocol.
#: These are the core methods defined in protocols.py that enable the framework
#: to initialize runners, discover phases/checkpoints/artifacts, and execute phases.
#: See: apps/backend/methodologies/protocols.py::MethodologyRunner
REQUIRED_PROTOCOL_METHODS: list[str] = [
    "initialize",
    "get_phases",
    "execute_phase",
    "get_checkpoints",
    "get_artifacts",
]


class MethodologyLoader:
    """Lazy loader for methodology plugins with error isolation.

    This class handles the dynamic loading of methodology plugins from their
    entry points. It validates that loaded classes implement the MethodologyRunner
    Protocol and caches instances for subsequent calls.

    Key features:
    - Lazy loading: plugins are only loaded when requested
    - Error isolation: a broken plugin doesn't affect others
    - Caching: instances are cached after first load
    - Protocol verification: ensures classes implement MethodologyRunner

    Thread Safety:
        This class is NOT thread-safe. The cache operations (check and store)
        are not atomic. In concurrent scenarios, the same methodology could be
        loaded multiple times before caching. For the Auto Claude desktop app,
        this is acceptable as methodology loading happens on the main thread.
        If concurrent loading is needed in the future, add threading.Lock
        protection around cache operations in load_methodology().

    Architecture Source: architecture.md#Plugin-Loading

    Example:
        registry = MethodologyRegistryImpl()
        loader = MethodologyLoader(registry)

        # First call loads and caches the plugin
        runner = loader.load_methodology("native")

        # Second call returns cached instance (no reimport)
        same_runner = loader.load_methodology("native")
        assert runner is same_runner
    """

    def __init__(self, registry: "MethodologyRegistryImpl") -> None:
        """Initialize the loader with a registry reference.

        Args:
            registry: The methodology registry to look up plugin paths
        """
        self._registry = registry
        self._cache: dict[str, MethodologyRunner] = {}
        self._manifest_cache: dict[str, MethodologyManifest] = {}
        self._loaded_modules: set[str] = set()  # Track sys.modules entries for cleanup

    def load_methodology(self, name: str) -> MethodologyRunner:
        """Load and return a methodology runner by name.

        Lazily loads the methodology plugin the first time it's requested.
        Subsequent calls return the cached instance.

        Args:
            name: Name of the methodology to load (e.g., "native", "bmad")

        Returns:
            MethodologyRunner instance for the methodology

        Raises:
            PluginLoadError: If methodology is not registered or fails to load
            ProtocolViolationError: If the loaded class doesn't implement
                the MethodologyRunner Protocol correctly
        """
        # Return cached instance if available
        if name in self._cache:
            logger.debug(f"Returning cached runner for methodology '{name}'")
            return self._cache[name]

        logger.info(f"Loading methodology '{name}'")

        # Get the registry entry
        entry = self._registry.get_entry(name)
        if entry is None:
            raise PluginLoadError(f"Methodology '{name}' is not registered")

        if not entry.enabled:
            raise PluginLoadError(f"Methodology '{name}' is disabled")

        plugin_path = Path(entry.path)
        if not plugin_path.exists():
            raise PluginLoadError(
                f"Plugin directory not found for methodology '{name}': {plugin_path}"
            )

        # Load and validate the manifest
        manifest = self._load_manifest(name, plugin_path)

        # Import the module and get the runner class
        runner_class = self._load_runner_class(name, plugin_path, manifest.entry_point)

        # Verify the class implements the Protocol
        self._verify_protocol(name, runner_class)

        # Instantiate the runner
        try:
            runner = runner_class()
        except Exception as e:
            raise PluginLoadError(
                f"Failed to instantiate runner for methodology '{name}': {e}"
            ) from e

        # Cache the instance
        self._cache[name] = runner
        logger.info(f"Successfully loaded and cached methodology '{name}'")

        return runner

    def _load_manifest(self, name: str, plugin_path: Path) -> MethodologyManifest:
        """Load and cache the manifest for a methodology.

        Args:
            name: Name of the methodology (for error messages)
            plugin_path: Path to the plugin directory

        Returns:
            Validated MethodologyManifest

        Raises:
            PluginLoadError: If manifest cannot be loaded or validated
        """
        if name in self._manifest_cache:
            return self._manifest_cache[name]

        manifest_path = plugin_path / "manifest.yaml"
        if not manifest_path.exists():
            raise PluginLoadError(
                f"No manifest.yaml found for methodology '{name}' at {plugin_path}"
            )

        try:
            manifest = load_manifest(manifest_path)
            self._manifest_cache[name] = manifest
            return manifest
        except FileNotFoundError as e:
            raise PluginLoadError(
                f"Manifest file not found for methodology '{name}': {e}"
            ) from e
        except Exception as e:
            raise PluginLoadError(
                f"Failed to load manifest for methodology '{name}': {e}"
            ) from e

    def _load_runner_class(
        self, name: str, plugin_path: Path, entry_point: str
    ) -> type:
        """Load the runner class from the entry point.

        Entry point format: "module_name.ClassName"
        Example: "methodology.NativeRunner"

        Args:
            name: Name of the methodology (for error messages)
            plugin_path: Path to the plugin directory
            entry_point: Entry point string (module.ClassName)

        Returns:
            The runner class (not instantiated)

        Raises:
            PluginLoadError: If module cannot be imported or class not found
        """
        # Parse the entry point
        try:
            module_name, class_name = self._parse_entry_point(entry_point)
        except ValueError as e:
            raise PluginLoadError(
                f"Invalid entry point format for methodology '{name}': "
                f"'{entry_point}'. Expected format: 'module.ClassName'. Error: {e}"
            ) from e

        # Import the module dynamically
        module = self._import_module(name, plugin_path, module_name)

        # Get the class from the module
        if not hasattr(module, class_name):
            raise PluginLoadError(
                f"Runner class '{class_name}' not found in module '{module_name}' "
                f"for methodology '{name}'"
            )

        runner_class = getattr(module, class_name)

        if not isinstance(runner_class, type):
            raise PluginLoadError(
                f"Entry point '{entry_point}' for methodology '{name}' "
                f"does not reference a class (got {type(runner_class).__name__})"
            )

        return runner_class

    def _parse_entry_point(self, entry_point: str) -> tuple[str, str]:
        """Parse an entry point string into module and class names.

        Args:
            entry_point: Entry point string (module.ClassName or module.submodule.ClassName)

        Returns:
            Tuple of (module_name, class_name)

        Raises:
            ValueError: If entry point format is invalid
        """
        if "." not in entry_point:
            raise ValueError(
                f"Entry point must contain at least one dot separating "
                f"module and class name, got: '{entry_point}'"
            )

        # Split on the last dot to separate module path from class name
        parts = entry_point.rsplit(".", 1)
        module_name = parts[0]
        class_name = parts[1]

        if not module_name or not class_name:
            raise ValueError(f"Invalid entry point format: '{entry_point}'")

        return module_name, class_name

    def _import_module(
        self, name: str, plugin_path: Path, module_name: str
    ) -> ModuleType:
        """Import a module from the plugin directory.

        Uses importlib to dynamically load the module from the plugin's
        directory structure.

        Args:
            name: Name of the methodology (for error messages)
            plugin_path: Path to the plugin directory
            module_name: Name of the module to import (can include dots for submodules)

        Returns:
            The imported module

        Raises:
            PluginLoadError: If module cannot be imported
        """
        module_file = self._resolve_module_path(plugin_path, module_name)

        if not module_file.exists():
            # Try looking for __init__.py in a package
            module_parts = module_name.split(".")
            package_dir = plugin_path / Path(*module_parts)
            init_file = package_dir / "__init__.py"
            if init_file.exists():
                module_file = init_file
            else:
                raise PluginLoadError(
                    f"Module file not found for methodology '{name}': "
                    f"expected '{module_file}' or '{init_file}'"
                )

        # Create a unique module name to avoid conflicts
        unique_module_name = f"_auto_claude_plugins_.{name}.{module_name}"

        try:
            spec = importlib.util.spec_from_file_location(
                unique_module_name, module_file
            )
            if spec is None or spec.loader is None:
                raise PluginLoadError(
                    f"Failed to create module spec for methodology '{name}': "
                    f"could not load '{module_file}'"
                )

            module = importlib.util.module_from_spec(spec)

            # Add to sys.modules before exec to handle circular imports
            sys.modules[unique_module_name] = module
            self._loaded_modules.add(unique_module_name)

            # Execute the module
            spec.loader.exec_module(module)

            return module

        except PluginLoadError:
            # Re-raise PluginLoadError as-is
            raise
        except Exception as e:
            # Clean up sys.modules on failure
            if unique_module_name in sys.modules:
                del sys.modules[unique_module_name]
            self._loaded_modules.discard(unique_module_name)
            raise PluginLoadError(
                f"Failed to import module '{module_name}' for methodology '{name}': {e}"
            ) from e

    def _resolve_module_path(self, plugin_path: Path, module_name: str) -> Path:
        """Resolve module name to file path within plugin directory.

        Handles both simple modules (runner) and nested modules (package.submodule).

        Args:
            plugin_path: Root path of the plugin
            module_name: Module name, possibly with dots for nesting

        Returns:
            Path to the module file (.py)
        """
        module_parts = module_name.split(".")

        if len(module_parts) == 1:
            # Simple module: runner -> plugin_path/runner.py
            return plugin_path / f"{module_name}.py"

        # Nested module: package.submodule -> plugin_path/package/submodule.py
        parent_path = plugin_path / Path(*module_parts[:-1])
        return parent_path / f"{module_parts[-1]}.py"

    def _verify_protocol(self, name: str, runner_class: type) -> None:
        """Verify that a class implements the MethodologyRunner Protocol.

        Checks that the class has all required methods defined in
        REQUIRED_PROTOCOL_METHODS. This ensures the runner will work
        correctly with the framework's execution pipeline.

        Args:
            name: Name of the methodology (for error messages)
            runner_class: The runner class to verify

        Raises:
            ProtocolViolationError: If required methods are missing
        """
        missing_methods: list[str] = []

        # Check for required methods
        for method_name in REQUIRED_PROTOCOL_METHODS:
            if not hasattr(runner_class, method_name):
                missing_methods.append(method_name)
            elif not callable(getattr(runner_class, method_name)):
                missing_methods.append(f"{method_name} (not callable)")

        if missing_methods:
            raise ProtocolViolationError(
                message=(
                    f"Methodology '{name}' runner class '{runner_class.__name__}' "
                    f"does not implement the MethodologyRunner Protocol correctly. "
                    f"Missing methods: {', '.join(missing_methods)}"
                ),
                methodology_name=name,
                missing_methods=missing_methods,
            )

        logger.debug(
            f"Protocol verification passed for methodology '{name}' "
            f"runner class '{runner_class.__name__}'"
        )

    def get_manifest(self, name: str) -> MethodologyManifest:
        """Get the manifest for a methodology without loading the runner.

        Useful for getting metadata about a methodology without fully loading it.

        Args:
            name: Name of the methodology

        Returns:
            MethodologyManifest for the methodology

        Raises:
            PluginLoadError: If methodology is not registered or manifest invalid
        """
        if name in self._manifest_cache:
            return self._manifest_cache[name]

        entry = self._registry.get_entry(name)
        if entry is None:
            raise PluginLoadError(f"Methodology '{name}' is not registered")

        plugin_path = Path(entry.path)
        return self._load_manifest(name, plugin_path)

    def is_loaded(self, name: str) -> bool:
        """Check if a methodology runner is already loaded and cached.

        Args:
            name: Name of the methodology

        Returns:
            True if the runner is in the cache, False otherwise
        """
        return name in self._cache

    def clear_cache(self) -> None:
        """Clear all cached runner instances, manifests, and loaded modules.

        Removes all cached data and cleans up sys.modules entries that were
        added during plugin imports. Primarily useful for testing to ensure
        fresh loads.
        """
        self._cache.clear()
        self._manifest_cache.clear()

        # Clean up sys.modules entries to prevent memory leaks
        for module_name in self._loaded_modules:
            if module_name in sys.modules:
                del sys.modules[module_name]
        self._loaded_modules.clear()

        logger.debug("Cleared methodology loader cache and sys.modules entries")

    def clear_methodology(self, name: str) -> None:
        """Clear a specific methodology from the cache.

        Also removes any sys.modules entries associated with this methodology.

        Args:
            name: Name of the methodology to clear
        """
        if name in self._cache:
            del self._cache[name]
        if name in self._manifest_cache:
            del self._manifest_cache[name]

        # Clean up sys.modules entries for this methodology
        prefix = f"_auto_claude_plugins_.{name}."
        modules_to_remove = [
            mod for mod in self._loaded_modules if mod.startswith(prefix)
        ]
        for module_name in modules_to_remove:
            if module_name in sys.modules:
                del sys.modules[module_name]
            self._loaded_modules.discard(module_name)

        logger.debug(f"Cleared methodology '{name}' from cache")
