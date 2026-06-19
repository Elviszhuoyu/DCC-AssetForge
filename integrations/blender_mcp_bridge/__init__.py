# -*- coding: utf-8 -*-
"""Independent Blender MCP Bridge add-on."""

from __future__ import absolute_import

bl_info = {
    "name": "Blender MCP Bridge",
    "author": "TA_MyTools",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > MCP Bridge",
    "description": "Independent local MCP bridge for safe Codex-to-Blender automation.",
    "category": "System",
}

try:
    from . import _blender_mcp_bootstrap
except Exception:
    _blender_mcp_bootstrap = None

if _blender_mcp_bootstrap and hasattr(_blender_mcp_bootstrap, "configure"):
    _blender_mcp_bootstrap.configure()

from . import bridge


def _bootstrap_repo_root():
    if _blender_mcp_bootstrap is not None:
        return getattr(_blender_mcp_bootstrap, "REPO_ROOT", "")
    return ""


def register():
    from . import ui

    ui.register()
    return None


def unregister():
    bridge.unregister_extension()
    try:
        from . import ui
    except Exception:
        return None
    return ui.unregister()
