"""Native Auto Claude methodology plugin.

This plugin packages the existing Auto Claude implementation as a methodology
that can be loaded through the plugin framework.

Architecture Source: architecture.md#Native-Plugin-Structure
"""

from apps.backend.methodologies.native.methodology import NativeRunner

__all__ = ["NativeRunner"]
