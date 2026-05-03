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


if __name__ == "__main__":
    _ensure_project_root()
    args = [item for item in sys.argv[1:] if item != "--dry-run"]
    dry_run = "--dry-run" in sys.argv[1:]
    if len(args) < 1:
        raise RuntimeError("Usage: unreal_import_manifest.py <manifest_path> [log_path] [--dry-run]")
    report = import_manifest(args[0], args[1] if len(args) > 1 else None, dry_run)
    print(report)
