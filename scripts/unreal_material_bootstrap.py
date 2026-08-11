"""Unreal Python helper for bootstrapping DCC AssetForge material assets."""

from __future__ import absolute_import

import os
import sys


def _ensure_project_root():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root


def plan_material_assets():
    _ensure_project_root()
    from asset_forge.unreal.material_asset_bootstrap import plan_default_material_assets

    return plan_default_material_assets()


def bootstrap_material_assets(dry_run=False):
    _ensure_project_root()
    from asset_forge.unreal.material_asset_bootstrap import bootstrap_default_material_assets

    return bootstrap_default_material_assets(dry_run)


if __name__ == "__main__":
    _ensure_project_root()
    print(bootstrap_material_assets("--dry-run" in sys.argv[1:]))
