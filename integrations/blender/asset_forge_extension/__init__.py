# -*- coding: utf-8 -*-
"""Blender extension entry point for Asset Forge."""

from __future__ import absolute_import

from . import bridge


def register():
    """Register Asset Forge Blender extension classes and start the local bridge."""
    return bridge.register_extension()


def unregister():
    """Unregister Asset Forge Blender extension classes and stop the local bridge."""
    return bridge.unregister_extension()