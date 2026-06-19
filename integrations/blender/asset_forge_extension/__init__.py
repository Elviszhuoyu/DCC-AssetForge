# -*- coding: utf-8 -*-
"""Blender extension entry point for Asset Forge."""

from __future__ import absolute_import

import os

try:
    from . import _asset_forge_bootstrap
except Exception:
    _asset_forge_bootstrap = None

if _asset_forge_bootstrap and hasattr(_asset_forge_bootstrap, "configure"):
    _asset_forge_bootstrap.configure()

from . import bridge


def _bootstrap_repo_root():
    if _asset_forge_bootstrap is not None:
        return getattr(_asset_forge_bootstrap, "REPO_ROOT", "")
    return ""


def register():
    """Register Asset Forge Blender extension classes and start the local bridge."""
    repo_root = _bootstrap_repo_root()
    log_path = os.path.join(repo_root, "AssetForgeReports", "logs", "latest_blender.log") if repo_root else ""
    return bridge.start_bridge(repo_root=repo_root, log_path=log_path)


def unregister():
    """Unregister Asset Forge Blender extension classes and stop the local bridge."""
    return bridge.unregister_extension()