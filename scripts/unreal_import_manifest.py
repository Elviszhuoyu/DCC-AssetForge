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


def import_manifest(manifest_path, log_path=None, dry_run=False, auto_bootstrap_material_assets=False):
    _ensure_project_root()
    from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline, dry_run_manifest

    if dry_run:
        return dry_run_manifest(manifest_path, log_path)
    pipeline = UnrealStaticMeshImportPipeline(auto_bootstrap_material_assets=auto_bootstrap_material_assets)
    return pipeline.import_from_manifest(manifest_path, log_path)


def import_latest_manifest(export_root, log_path=None, dry_run=False):
    _ensure_project_root()
    from asset_forge.unreal.pipeline import import_latest_manifest as run_latest

    return run_latest(export_root, log_path, dry_run)


def import_asset_forge_package(package_dir, dry_run=False, report_path=None, auto_bootstrap_material_assets=False):
    _ensure_project_root()
    from asset_forge.unreal.manifest_finder import find_latest_manifest
    from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline

    manifest_path = find_latest_manifest(package_dir)
    if not manifest_path:
        raise RuntimeError("资产包内未找到 Asset Forge manifest：{0}".format(package_dir))
    pipeline = UnrealStaticMeshImportPipeline(auto_bootstrap_material_assets=auto_bootstrap_material_assets)
    if dry_run:
        return pipeline.dry_run_manifest(manifest_path, report_path)
    return pipeline.import_from_manifest(manifest_path, report_path)


def validate_asset_forge_package(package_dir):
    _ensure_project_root()
    from asset_forge.unreal.package_acceptance import validate_asset_forge_package as run_validation

    return run_validation(package_dir)


def import_all_manifests(export_root, report_path=None, dry_run=False):
    _ensure_project_root()
    from asset_forge.unreal.pipeline import import_all_manifests as run_all

    return run_all(export_root, report_path, dry_run)


def get_editor_widget_action_plan():
    _ensure_project_root()
    from asset_forge.unreal.editor_widget_actions import get_action_plan

    return get_action_plan()


def get_editor_widget_launch_plan():
    _ensure_project_root()
    from asset_forge.unreal.editor_widget_launcher import get_widget_launch_plan

    return get_widget_launch_plan()


def launch_asset_forge_widget():
    _ensure_project_root()
    from asset_forge.unreal.editor_widget_launcher import launch_asset_forge_widget as run_launch

    return run_launch()


if __name__ == "__main__":
    _ensure_project_root()
    flags = {"--dry-run", "--latest", "--all", "--package", "--auto-materials"}
    args = [item for item in sys.argv[1:] if item not in flags]
    dry_run = "--dry-run" in sys.argv[1:]
    latest = "--latest" in sys.argv[1:]
    import_all = "--all" in sys.argv[1:]
    package = "--package" in sys.argv[1:]
    auto_materials = "--auto-materials" in sys.argv[1:]
    if len(args) < 1:
        raise RuntimeError("Usage: unreal_import_manifest.py <manifest_path_or_export_root> [log_path] [--dry-run] [--latest] [--all] [--package]")
    if import_all:
        report = import_all_manifests(args[0], args[1] if len(args) > 1 else None, dry_run)
    elif package:
        report = import_asset_forge_package(args[0], dry_run, args[1] if len(args) > 1 else None, auto_materials)
    elif latest:
        report = import_latest_manifest(args[0], args[1] if len(args) > 1 else None, dry_run)
    else:
        report = import_manifest(args[0], args[1] if len(args) > 1 else None, dry_run, auto_materials)
    print(report)
