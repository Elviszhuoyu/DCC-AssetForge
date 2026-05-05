"""Command line helper for installing the Asset Forge UE plugin package."""

from __future__ import absolute_import

import os
import sys


def _ensure_project_root():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root


def plan_install(project_path, source_plugin_dir=None):
    _ensure_project_root()
    from asset_forge.unreal.plugin_installer import plan_assetforge_plugin_install

    return plan_assetforge_plugin_install(project_path, source_plugin_dir)


def install(project_path, source_plugin_dir=None, enable_in_project=True, dry_run=False):
    _ensure_project_root()
    from asset_forge.unreal.plugin_installer import install_assetforge_plugin

    return install_assetforge_plugin(project_path, source_plugin_dir, enable_in_project, dry_run)


if __name__ == "__main__":
    _ensure_project_root()
    args = [item for item in sys.argv[1:] if item not in ("--dry-run", "--no-enable")]
    if not args:
        raise RuntimeError("用法：unreal_plugin_install.py <uproject_or_project_dir> [--dry-run] [--no-enable]")
    report = install(
        args[0],
        enable_in_project="--no-enable" not in sys.argv[1:],
        dry_run="--dry-run" in sys.argv[1:],
    )
    print(report)
