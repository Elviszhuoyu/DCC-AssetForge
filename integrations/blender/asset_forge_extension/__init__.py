"""Blender extension entry point for Asset Forge."""

from __future__ import absolute_import


def register():
    """Register Asset Forge Blender extension classes.

    The Blender adapter implementation is intentionally gated behind Phase 5.
    This entry point exists so the package shape follows Blender extension
    requirements before feature work starts.
    """
    return None


def unregister():
    """Unregister Asset Forge Blender extension classes."""
    return None
