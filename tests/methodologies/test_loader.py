"""Tests for methodology plugin loader implementation.

Tests lazy loading, entry point resolution, Protocol verification, caching,
and error isolation for methodology plugins.
"""

import tempfile
from pathlib import Path

import pytest

from apps.backend.methodologies.exceptions import (
    PluginLoadError,
    ProtocolViolationError,
)
from apps.backend.methodologies.loader import (
    REQUIRED_PROTOCOL_METHODS,
    MethodologyLoader,
)
from apps.backend.methodologies.registry import MethodologyRegistryImpl, RegistryEntry


class TestLoaderModule:
    """Test that the loader module exists and exports correctly."""

    def test_loader_module_importable(self):
        """Test that loader module can be imported."""
        from apps.backend.methodologies import loader

        assert loader is not None

    def test_methodology_loader_exists(self):
        """Test that MethodologyLoader class exists."""
        from apps.backend.methodologies.loader import MethodologyLoader

        assert MethodologyLoader is not None

    def test_required_protocol_methods_defined(self):
        """Test that REQUIRED_PROTOCOL_METHODS is defined."""
        from apps.backend.methodologies.loader import REQUIRED_PROTOCOL_METHODS

        assert isinstance(REQUIRED_PROTOCOL_METHODS, list)
        assert "initialize" in REQUIRED_PROTOCOL_METHODS
        assert "get_phases" in REQUIRED_PROTOCOL_METHODS
        assert "execute_phase" in REQUIRED_PROTOCOL_METHODS
        assert "get_checkpoints" in REQUIRED_PROTOCOL_METHODS
        assert "get_artifacts" in REQUIRED_PROTOCOL_METHODS


class TestMethodologyLoaderInit:
    """Test MethodologyLoader initialization."""

    def test_loader_accepts_registry(self):
        """Test loader can be initialized with a registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text("methodologies: []")
            registry = MethodologyRegistryImpl(registry_path=registry_path)

            loader = MethodologyLoader(registry)
            assert loader is not None

    def test_loader_has_empty_cache_initially(self):
        """Test that loader starts with empty cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text("methodologies: []")
            registry = MethodologyRegistryImpl(registry_path=registry_path)

            loader = MethodologyLoader(registry)
            assert loader._cache == {}
            assert loader._manifest_cache == {}


def _create_valid_plugin(plugin_dir: Path, name: str = "test-plugin") -> Path:
    """Helper to create a valid plugin structure for testing.

    Args:
        plugin_dir: Directory to create the plugin in
        name: Name of the plugin

    Returns:
        Path to the plugin directory
    """
    plugin_path = plugin_dir / name
    plugin_path.mkdir(parents=True, exist_ok=True)

    # Create manifest.yaml
    manifest_content = f"""name: {name}
version: "1.0.0"
entry_point: runner.TestRunner
description: Test methodology plugin
author: Test Author
phases:
  - id: discovery
    name: Discovery
    description: Discover requirements
  - id: implementation
    name: Implementation
    description: Implement features
"""
    (plugin_path / "manifest.yaml").write_text(manifest_content)

    # Create runner.py with valid MethodologyRunner implementation
    runner_content = """
class TestRunner:
    def initialize(self, context):
        self.context = context

    def get_phases(self):
        return []

    def execute_phase(self, phase_id):
        return None

    def get_checkpoints(self):
        return []

    def get_artifacts(self):
        return []
"""
    (plugin_path / "runner.py").write_text(runner_content)

    return plugin_path


def _create_invalid_protocol_plugin(plugin_dir: Path, name: str = "invalid-plugin") -> Path:
    """Helper to create a plugin that doesn't implement the Protocol correctly.

    Args:
        plugin_dir: Directory to create the plugin in
        name: Name of the plugin

    Returns:
        Path to the plugin directory
    """
    plugin_path = plugin_dir / name
    plugin_path.mkdir(parents=True, exist_ok=True)

    # Create manifest.yaml
    manifest_content = f"""name: {name}
version: "1.0.0"
entry_point: runner.IncompleteRunner
description: Invalid plugin
phases:
  - id: test
    name: Test
"""
    (plugin_path / "manifest.yaml").write_text(manifest_content)

    # Create runner.py with incomplete implementation (missing methods)
    runner_content = """
class IncompleteRunner:
    def initialize(self, context):
        self.context = context

    # Missing: get_phases, execute_phase, get_checkpoints, get_artifacts
"""
    (plugin_path / "runner.py").write_text(runner_content)

    return plugin_path


def _create_import_error_plugin(plugin_dir: Path, name: str = "error-plugin") -> Path:
    """Helper to create a plugin with import errors.

    Args:
        plugin_dir: Directory to create the plugin in
        name: Name of the plugin

    Returns:
        Path to the plugin directory
    """
    plugin_path = plugin_dir / name
    plugin_path.mkdir(parents=True, exist_ok=True)

    # Create manifest.yaml
    manifest_content = f"""name: {name}
version: "1.0.0"
entry_point: runner.BrokenRunner
description: Plugin with import error
phases:
  - id: test
    name: Test
"""
    (plugin_path / "manifest.yaml").write_text(manifest_content)

    # Create runner.py with syntax error
    runner_content = """
import nonexistent_module  # This will cause ImportError

class BrokenRunner:
    pass
"""
    (plugin_path / "runner.py").write_text(runner_content)

    return plugin_path


class TestLazyLoading:
    """Test lazy loading functionality (AC #1, #4)."""

    def test_load_methodology_returns_runner(self):
        """Test that load_methodology returns a runner instance (AC #1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create valid plugin
            plugin_path = _create_valid_plugin(Path(tmpdir), "test-methodology")

            # Setup registry
            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: test-methodology
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            # Load the methodology
            runner = loader.load_methodology("test-methodology")

            assert runner is not None
            # Verify it has the required methods
            assert hasattr(runner, "initialize")
            assert hasattr(runner, "get_phases")
            assert hasattr(runner, "execute_phase")
            assert hasattr(runner, "get_checkpoints")
            assert hasattr(runner, "get_artifacts")

    def test_load_methodology_validates_manifest(self):
        """Test that manifest is validated during loading (AC #1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "valid-manifest")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: valid-manifest
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            # Should not raise - manifest is valid
            runner = loader.load_methodology("valid-manifest")
            assert runner is not None

    def test_load_methodology_caches_runner(self):
        """Test that runner is cached after first load (AC #1, #4)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "cached-methodology")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: cached-methodology
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            # First load
            runner1 = loader.load_methodology("cached-methodology")

            # Second load should return same instance
            runner2 = loader.load_methodology("cached-methodology")

            assert runner1 is runner2

    def test_cached_instance_no_reimport(self):
        """Test that cached instance returns without reimport (AC #4)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "no-reimport")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: no-reimport
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            # First load
            loader.load_methodology("no-reimport")

            # Verify it's in cache
            assert loader.is_loaded("no-reimport")

            # Modify the file (if reimport happened, this would affect the class)
            (plugin_path / "runner.py").write_text("""
# Modified content - this should not be used if caching works
raise RuntimeError("This should not be executed on cached call")
""")

            # Second load should use cache, not reimport
            runner2 = loader.load_methodology("no-reimport")
            assert runner2 is not None

    def test_load_unregistered_methodology_raises(self):
        """Test that loading unregistered methodology raises PluginLoadError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text("methodologies: []")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            with pytest.raises(PluginLoadError) as exc_info:
                loader.load_methodology("nonexistent")

            assert "not registered" in str(exc_info.value)


class TestEntryPointResolution:
    """Test entry point parsing and module loading (AC #1, #2)."""

    def test_parse_simple_entry_point(self):
        """Test parsing simple entry point format: module.ClassName."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text("methodologies: []")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            module_name, class_name = loader._parse_entry_point("runner.TestRunner")
            assert module_name == "runner"
            assert class_name == "TestRunner"

    def test_parse_nested_entry_point(self):
        """Test parsing nested entry point: package.module.ClassName."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text("methodologies: []")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            module_name, class_name = loader._parse_entry_point(
                "package.submodule.MyRunner"
            )
            assert module_name == "package.submodule"
            assert class_name == "MyRunner"

    def test_parse_invalid_entry_point_no_dot(self):
        """Test that entry point without dot raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text("methodologies: []")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            with pytest.raises(ValueError) as exc_info:
                loader._parse_entry_point("InvalidEntryPoint")

            assert "must contain at least one dot" in str(exc_info.value)

    def test_parse_invalid_entry_point_empty_parts(self):
        """Test that entry point with empty parts raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text("methodologies: []")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            with pytest.raises(ValueError):
                loader._parse_entry_point(".ClassName")

            with pytest.raises(ValueError):
                loader._parse_entry_point("module.")

    def test_invalid_entry_point_raises_plugin_load_error(self):
        """Test that invalid entry point raises PluginLoadError during load (AC #2).

        Note: The manifest schema validation catches invalid entry_point format
        at the manifest loading stage, which is better than catching it later.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create plugin with invalid entry point format
            plugin_path = Path(tmpdir) / "bad-entry"
            plugin_path.mkdir()
            (plugin_path / "manifest.yaml").write_text("""name: bad-entry
version: "1.0.0"
entry_point: NoDotsHere
phases:
  - id: test
    name: Test
""")
            (plugin_path / "runner.py").write_text("class Runner: pass")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: bad-entry
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            with pytest.raises(PluginLoadError) as exc_info:
                loader.load_methodology("bad-entry")

            assert "bad-entry" in str(exc_info.value)
            # entry_point validation happens at manifest level (snake_case in error)
            assert "entry_point" in str(exc_info.value)

    def test_missing_module_raises_plugin_load_error(self):
        """Test that missing module raises PluginLoadError (AC #2)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create plugin without the runner module
            plugin_path = Path(tmpdir) / "missing-module"
            plugin_path.mkdir()
            (plugin_path / "manifest.yaml").write_text("""name: missing-module
version: "1.0.0"
entry_point: nonexistent.Runner
phases:
  - id: test
    name: Test
""")
            # Don't create the module file

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: missing-module
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            with pytest.raises(PluginLoadError) as exc_info:
                loader.load_methodology("missing-module")

            assert "missing-module" in str(exc_info.value)

    def test_missing_class_raises_plugin_load_error(self):
        """Test that missing class in module raises PluginLoadError (AC #2)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = Path(tmpdir) / "missing-class"
            plugin_path.mkdir()
            (plugin_path / "manifest.yaml").write_text("""name: missing-class
version: "1.0.0"
entry_point: runner.NonExistentClass
phases:
  - id: test
    name: Test
""")
            # Create runner.py without the expected class
            (plugin_path / "runner.py").write_text("""
class DifferentClass:
    pass
""")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: missing-class
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            with pytest.raises(PluginLoadError) as exc_info:
                loader.load_methodology("missing-class")

            assert "NonExistentClass" in str(exc_info.value)
            assert "not found" in str(exc_info.value)

    def test_nested_entry_point_loads_successfully(self):
        """Test loading a runner from a nested module path (e.g., package.submodule.Runner)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create plugin with nested module structure
            plugin_path = Path(tmpdir) / "nested-plugin"
            plugin_path.mkdir()
            (plugin_path / "manifest.yaml").write_text("""name: nested-plugin
version: "1.0.0"
entry_point: runners.impl.NestedRunner
phases:
  - id: test
    name: Test
""")
            # Create nested directory structure
            runners_dir = plugin_path / "runners"
            runners_dir.mkdir()
            (runners_dir / "__init__.py").write_text("")

            # The loader's _resolve_module_path converts "runners.impl" to "runners/impl.py"
            # We create both possible resolution paths to ensure the test works regardless
            # of which path resolution strategy is used:
            # 1. runners/impl/impl.py (package with nested module)
            # 2. runners/impl.py (direct module file - this is what the loader actually uses)
            impl_dir = runners_dir / "impl"
            impl_dir.mkdir()
            (impl_dir / "__init__.py").write_text("")
            (impl_dir / "impl.py").write_text("""
class NestedRunner:
    def initialize(self, context):
        self.context = context

    def get_phases(self):
        return []

    def execute_phase(self, phase_id):
        return None

    def get_checkpoints(self):
        return []

    def get_artifacts(self):
        return []
""")
            # This is the path the loader actually uses: plugin_path/runners/impl.py
            # for entry_point "runners.impl.NestedRunner"
            (runners_dir / "impl.py").write_text("""
class NestedRunner:
    def initialize(self, context):
        self.context = context

    def get_phases(self):
        return []

    def execute_phase(self, phase_id):
        return None

    def get_checkpoints(self):
        return []

    def get_artifacts(self):
        return []
""")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: nested-plugin
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            # Load the methodology with nested entry point
            runner = loader.load_methodology("nested-plugin")

            assert runner is not None
            assert hasattr(runner, "initialize")
            assert hasattr(runner, "get_phases")


class TestProtocolVerification:
    """Test Protocol verification (AC #3)."""

    def test_valid_protocol_implementation_passes(self):
        """Test that valid Protocol implementation loads successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "valid-protocol")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: valid-protocol
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            # Should not raise
            runner = loader.load_methodology("valid-protocol")
            assert runner is not None

    def test_missing_methods_raises_protocol_violation_error(self):
        """Test that missing Protocol methods raises ProtocolViolationError (AC #3)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_invalid_protocol_plugin(
                Path(tmpdir), "incomplete-protocol"
            )

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: incomplete-protocol
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            with pytest.raises(ProtocolViolationError) as exc_info:
                loader.load_methodology("incomplete-protocol")

            error = exc_info.value
            # Verify error includes methodology name
            assert "incomplete-protocol" in str(error)
            # Verify error lists missing methods (AC #3)
            assert "get_phases" in str(error)
            assert error.missing_methods is not None
            assert len(error.missing_methods) > 0

    def test_protocol_violation_lists_all_missing_methods(self):
        """Test that ProtocolViolationError lists all missing methods (AC #3)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create plugin missing multiple methods
            plugin_path = Path(tmpdir) / "multi-missing"
            plugin_path.mkdir()
            (plugin_path / "manifest.yaml").write_text("""name: multi-missing
version: "1.0.0"
entry_point: runner.PartialRunner
phases:
  - id: test
    name: Test
""")
            # Only implement initialize - missing all others
            (plugin_path / "runner.py").write_text("""
class PartialRunner:
    def initialize(self, context):
        pass
    # Missing: get_phases, execute_phase, get_checkpoints, get_artifacts
""")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: multi-missing
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            with pytest.raises(ProtocolViolationError) as exc_info:
                loader.load_methodology("multi-missing")

            error = exc_info.value
            missing = error.missing_methods
            # Should have 4 missing methods
            assert "get_phases" in missing
            assert "execute_phase" in missing
            assert "get_checkpoints" in missing
            assert "get_artifacts" in missing


class TestErrorIsolation:
    """Test error isolation between plugins (AC #2, #3)."""

    def test_broken_plugin_doesnt_affect_valid_plugin(self):
        """Test that a broken plugin doesn't prevent loading valid plugins (AC #2)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create valid plugin
            valid_path = _create_valid_plugin(Path(tmpdir), "valid-plugin")

            # Create broken plugin
            broken_path = _create_import_error_plugin(Path(tmpdir), "broken-plugin")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: valid-plugin
    path: "{valid_path}"
    version: "1.0.0"
    verified: true
    enabled: true
  - name: broken-plugin
    path: "{broken_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            # Valid plugin should load successfully
            runner = loader.load_methodology("valid-plugin")
            assert runner is not None

            # Broken plugin should fail with PluginLoadError
            with pytest.raises(PluginLoadError):
                loader.load_methodology("broken-plugin")

            # Valid plugin should still be loaded and accessible
            cached_runner = loader.load_methodology("valid-plugin")
            assert cached_runner is runner

    def test_error_includes_methodology_name(self):
        """Test that errors include the methodology name (AC #2)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_path = _create_import_error_plugin(Path(tmpdir), "named-broken")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: named-broken
    path: "{broken_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            with pytest.raises(PluginLoadError) as exc_info:
                loader.load_methodology("named-broken")

            assert "named-broken" in str(exc_info.value)


class TestCaching:
    """Test caching functionality (AC #4)."""

    def test_is_loaded_returns_false_before_load(self):
        """Test is_loaded returns False for unloaded methodology."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "not-loaded")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: not-loaded
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            assert loader.is_loaded("not-loaded") is False

    def test_is_loaded_returns_true_after_load(self):
        """Test is_loaded returns True after methodology is loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "is-loaded")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: is-loaded
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            loader.load_methodology("is-loaded")
            assert loader.is_loaded("is-loaded") is True

    def test_clear_cache_removes_all_entries(self):
        """Test that clear_cache removes all cached runners."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "clearable")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: clearable
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            loader.load_methodology("clearable")
            assert loader.is_loaded("clearable")

            loader.clear_cache()
            assert not loader.is_loaded("clearable")

    def test_clear_methodology_removes_specific_entry(self):
        """Test that clear_methodology removes only specified methodology."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = _create_valid_plugin(Path(tmpdir), "keep-me")
            path2 = _create_valid_plugin(Path(tmpdir), "remove-me")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: keep-me
    path: "{path1}"
    version: "1.0.0"
    verified: true
    enabled: true
  - name: remove-me
    path: "{path2}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            loader.load_methodology("keep-me")
            loader.load_methodology("remove-me")

            loader.clear_methodology("remove-me")

            assert loader.is_loaded("keep-me")
            assert not loader.is_loaded("remove-me")

    def test_clear_cache_cleans_sys_modules(self):
        """Test that clear_cache removes loaded modules from sys.modules."""
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "sys-modules-test")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: sys-modules-test
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            loader.load_methodology("sys-modules-test")

            # Check that module was added to sys.modules
            module_name = "_auto_claude_plugins_.sys-modules-test.runner"
            assert module_name in sys.modules

            # Clear cache should also clean sys.modules
            loader.clear_cache()

            # Module should be removed from sys.modules
            assert module_name not in sys.modules

    def test_clear_methodology_cleans_sys_modules(self):
        """Test that clear_methodology removes the specific module from sys.modules."""
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = _create_valid_plugin(Path(tmpdir), "keep-module")
            path2 = _create_valid_plugin(Path(tmpdir), "remove-module")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: keep-module
    path: "{path1}"
    version: "1.0.0"
    verified: true
    enabled: true
  - name: remove-module
    path: "{path2}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            loader.load_methodology("keep-module")
            loader.load_methodology("remove-module")

            keep_module = "_auto_claude_plugins_.keep-module.runner"
            remove_module = "_auto_claude_plugins_.remove-module.runner"

            assert keep_module in sys.modules
            assert remove_module in sys.modules

            loader.clear_methodology("remove-module")

            # Only the removed methodology's module should be gone
            assert keep_module in sys.modules
            assert remove_module not in sys.modules

            # Cleanup
            loader.clear_cache()


class TestManifestLoading:
    """Test manifest loading during plugin load."""

    def test_get_manifest_returns_manifest(self):
        """Test get_manifest returns the manifest without loading runner."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "manifest-only")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: manifest-only
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            manifest = loader.get_manifest("manifest-only")

            assert manifest is not None
            assert manifest.name == "manifest-only"
            assert manifest.version == "1.0.0"
            assert manifest.entry_point == "runner.TestRunner"
            # Runner should NOT be loaded yet
            assert not loader.is_loaded("manifest-only")

    def test_get_manifest_caches_manifest(self):
        """Test that manifest is cached after first retrieval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "cached-manifest")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: cached-manifest
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            manifest1 = loader.get_manifest("cached-manifest")
            manifest2 = loader.get_manifest("cached-manifest")

            assert manifest1 is manifest2

    def test_get_manifest_unregistered_raises(self):
        """Test get_manifest raises PluginLoadError for unregistered methodology."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text("methodologies: []")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            with pytest.raises(PluginLoadError) as exc_info:
                loader.get_manifest("nonexistent")

            assert "not registered" in str(exc_info.value)


class TestDisabledPlugins:
    """Test handling of disabled plugins."""

    def test_load_disabled_plugin_raises_error(self):
        """Test that loading a disabled plugin raises PluginLoadError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "disabled-plugin")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: disabled-plugin
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: false
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            with pytest.raises(PluginLoadError) as exc_info:
                loader.load_methodology("disabled-plugin")

            assert "disabled" in str(exc_info.value)


class TestRegistryIntegration:
    """Test integration with registry's get_methodology method."""

    def test_registry_get_methodology_uses_loader(self):
        """Test that registry.get_methodology() uses the loader correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "registry-integration")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: registry-integration
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)

            # This should use the loader internally
            runner = registry.get_methodology("registry-integration")

            assert runner is not None
            assert hasattr(runner, "initialize")
            assert hasattr(runner, "get_phases")

    def test_registry_get_methodology_caches(self):
        """Test that registry.get_methodology() caches runners."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _create_valid_plugin(Path(tmpdir), "cache-via-registry")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: cache-via-registry
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)

            runner1 = registry.get_methodology("cache-via-registry")
            runner2 = registry.get_methodology("cache-via-registry")

            assert runner1 is runner2

    def test_registry_get_methodology_not_found_raises(self):
        """Test that registry.get_methodology() raises for unknown methodology."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text("methodologies: []")
            registry = MethodologyRegistryImpl(registry_path=registry_path)

            with pytest.raises(PluginLoadError):
                registry.get_methodology("unknown")


class TestInstantiationErrors:
    """Test handling of runner instantiation errors."""

    def test_instantiation_error_raises_plugin_load_error(self):
        """Test that runner instantiation error raises PluginLoadError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = Path(tmpdir) / "init-error"
            plugin_path.mkdir()
            (plugin_path / "manifest.yaml").write_text("""name: init-error
version: "1.0.0"
entry_point: runner.ErrorRunner
phases:
  - id: test
    name: Test
""")
            # Create runner that raises in __init__
            (plugin_path / "runner.py").write_text("""
class ErrorRunner:
    def __init__(self):
        raise RuntimeError("Intentional init error")

    def initialize(self, context):
        pass

    def get_phases(self):
        return []

    def execute_phase(self, phase_id):
        return None

    def get_checkpoints(self):
        return []

    def get_artifacts(self):
        return []
""")

            registry_path = Path(tmpdir) / "registry.yaml"
            registry_path.write_text(f"""methodologies:
  - name: init-error
    path: "{plugin_path}"
    version: "1.0.0"
    verified: true
    enabled: true
""")
            registry = MethodologyRegistryImpl(registry_path=registry_path)
            loader = MethodologyLoader(registry)

            with pytest.raises(PluginLoadError) as exc_info:
                loader.load_methodology("init-error")

            assert "instantiate" in str(exc_info.value).lower()
            assert "init-error" in str(exc_info.value)
