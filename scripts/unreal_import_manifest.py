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


def import_manifest(manifest_path, log_path=None):
    _ensure_project_root()
    from asset_forge.unreal.pipeline import import_manifest as run_import

    return run_import(manifest_path, log_path)


if __name__ == "__main__":
    _ensure_project_root()
    if len(sys.argv) < 2:
        raise RuntimeError("Usage: unreal_import_manifest.py <manifest_path> [log_path]")
    report = import_manifest(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(report)
