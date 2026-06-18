"""Asset Forge export package path planning."""

from __future__ import absolute_import

import os

from asset_forge.shared.path_utils import ensure_dir, normalize_path


def build_export_package(output_root, asset_name, use_asset_folder=True):
    """Return stable paths for an exported asset package."""
    active_output_root = os.path.abspath(output_root)
    use_nested_asset_folder = bool(use_asset_folder) and os.path.basename(active_output_root) != asset_name
    package_dir = os.path.join(output_root, asset_name) if use_nested_asset_folder else output_root
    ensure_dir(package_dir)
    return {
        "package_dir": normalize_path(package_dir),
        "fbx_path": normalize_path(os.path.join(package_dir, asset_name + ".fbx")),
        "manifest_path": normalize_path(os.path.join(package_dir, asset_name + "_manifest.json")),
        "export_report_path": normalize_path(os.path.join(package_dir, asset_name + "_export_report.json")),
        "import_report_path": normalize_path(os.path.join(package_dir, asset_name + "_import_report.json")),
        "end_to_end_report_path": normalize_path(os.path.join(package_dir, asset_name + "_end_to_end_report.json")),
        "material_profiles_snapshot_path": normalize_path(os.path.join(package_dir, "material_profiles_snapshot.json")),
    }


def build_skeletal_export_package(output_root, asset_name, use_asset_folder=True):
    """Return planned package paths for a future Skeletal Mesh export."""
    package = build_export_package(output_root, asset_name, use_asset_folder)
    skeleton_dir = os.path.join(package["package_dir"], "Skeleton")
    animations_dir = os.path.join(package["package_dir"], "Animations")
    morph_targets_dir = os.path.join(package["package_dir"], "MorphTargets")
    for directory in [skeleton_dir, animations_dir, morph_targets_dir]:
        ensure_dir(directory)
    package.update(
        {
            "asset_type": "skeletal_mesh",
            "skeleton_dir": normalize_path(skeleton_dir),
            "animations_dir": normalize_path(animations_dir),
            "morph_targets_dir": normalize_path(morph_targets_dir),
            "package_report_path": normalize_path(os.path.join(package["package_dir"], asset_name + "_package_report.json")),
            "skeleton_manifest_path": normalize_path(os.path.join(skeleton_dir, asset_name + "_skeleton.json")),
            "animation_manifest_path": normalize_path(os.path.join(animations_dir, asset_name + "_animations.json")),
            "morph_target_manifest_path": normalize_path(os.path.join(morph_targets_dir, asset_name + "_morph_targets.json")),
        }
    )
    return package
