"""Asset Forge export package path planning."""

from __future__ import absolute_import

import os

from asset_forge.shared.path_utils import ensure_dir, normalize_path


def build_export_package(output_root, asset_name, use_asset_folder=True):
    """Return stable paths for an exported asset package."""
    package_dir = os.path.join(output_root, asset_name) if use_asset_folder else output_root
    ensure_dir(package_dir)
    return {
        "package_dir": normalize_path(package_dir),
        "fbx_path": normalize_path(os.path.join(package_dir, asset_name + ".fbx")),
        "manifest_path": normalize_path(os.path.join(package_dir, asset_name + "_manifest.json")),
        "export_report_path": normalize_path(os.path.join(package_dir, asset_name + "_export_report.json")),
        "import_report_path": normalize_path(os.path.join(package_dir, asset_name + "_import_report.json")),
        "end_to_end_report_path": normalize_path(os.path.join(package_dir, asset_name + "_end_to_end_report.json")),
    }
