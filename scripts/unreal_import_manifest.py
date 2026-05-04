"""Unreal Python entry point for importing one Asset Forge manifest."""

from __future__ import absolute_import

import os
import sys


def _ensure_project_root():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root


def import_manifest(manifest_path, log_path=None, dry_run=False):
    _ensure_project_root()
    from asset_forge.unreal.pipeline import dry_run_manifest, import_manifest as run_import

    if dry_run:
        return dry_run_manifest(manifest_path, log_path)
    return run_import(manifest_path, log_path)


def import_latest_manifest(export_root, log_path=None, dry_run=False):
    _ensure_project_root()
    from asset_forge.unreal.pipeline import import_latest_manifest as run_latest

    return run_latest(export_root, log_path, dry_run)


def import_asset_forge_package(package_dir, dry_run=False, report_path=None):
    _ensure_project_root()
    from asset_forge.unreal.pipeline import import_asset_forge_package as run_package

    return run_package(package_dir, dry_run, report_path)


def import_all_manifests(export_root, report_path=None, dry_run=False):
    _ensure_project_root()
    from asset_forge.unreal.pipeline import import_all_manifests as run_all

    return run_all(export_root, report_path, dry_run)


def get_editor_widget_action_plan():
    _ensure_project_root()
    from asset_forge.unreal.editor_widget_actions import get_action_plan

    return get_action_plan()


if __name__ == "__main__":
    _ensure_project_root()
    args = [item for item in sys.argv[1:] if item not in ("--dry-run", "--latest", "--all")]
    dry_run = "--dry-run" in sys.argv[1:]
    latest = "--latest" in sys.argv[1:]
    import_all = "--all" in sys.argv[1:]
    package = "--package" in sys.argv[1:]
    if len(args) < 1:
        raise RuntimeError("Usage: unreal_import_manifest.py <manifest_path_or_export_root> [log_path] [--dry-run] [--latest] [--all] [--package]")
    if import_all:
        report = import_all_manifests(args[0], args[1] if len(args) > 1 else None, dry_run)
    elif package:
        report = import_asset_forge_package(args[0], dry_run, args[1] if len(args) > 1 else None)
    elif latest:
        report = import_latest_manifest(args[0], args[1] if len(args) > 1 else None, dry_run)
    else:
        report = import_manifest(args[0], args[1] if len(args) > 1 else None, dry_run)
    print(report)
