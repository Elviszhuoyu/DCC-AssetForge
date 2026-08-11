# -*- coding: utf-8 -*-
"""Blender extension entry point for the DCC AssetForge workbench."""

from __future__ import absolute_import

bl_info = {
    "name": "DCC AssetForge",
    "author": "DCC AssetForge Contributors",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > DCC AssetForge",
    "description": "DCC AssetForge workbench for auditable static-prop packages.",
    "category": "Import-Export",
}

try:
    from . import _asset_forge_bootstrap
except Exception:
    _asset_forge_bootstrap = None

if _asset_forge_bootstrap and hasattr(_asset_forge_bootstrap, "configure"):
    _asset_forge_bootstrap.configure()


def register():
    """Register DCC AssetForge Blender workbench classes."""
    from . import ui

    return ui.register()


def unregister():
    """Unregister DCC AssetForge Blender workbench classes."""
    try:
        from . import ui
    except Exception:
        return None
    return ui.unregister()
