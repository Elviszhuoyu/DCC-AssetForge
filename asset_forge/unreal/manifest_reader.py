"""Manifest entry point for Unreal-side import tools."""

from __future__ import absolute_import

import os

from asset_forge.shared.manifest_schema import read_manifest, validate_manifest
from asset_forge.shared.material_profile_schema import get_material_profile, read_material_profiles, validate_material_profile
from asset_forge.shared.unreal_path import sanitize_unreal_package_path
from asset_forge.unreal.import_presets import UnrealImportPresetManager
from asset_forge.unreal.material_binding_planner import UnrealMaterialBindingPlanner


class UnrealManifestReader(object):
    """Read manifest.json and prepare it for Unreal import."""

    def __init__(self, preset_manager=None):
        self.preset_manager = preset_manager or UnrealImportPresetManager()

    def load(self, path, require_fbx_exists=True):
        manifest = read_manifest(path)
        manifest = self._normalize_manifest_paths(manifest)
        issues = validate_manifest(manifest)
        issues.extend(self._validate_paths(manifest, require_fbx_exists))
        # Runtime-only: resolve the exported contract while retaining its name for reports.
        manifest.pop("resolved_material_profile", None)
        name = manifest.get("material_profile")
        if isinstance(name, str) and name:
            snapshot = manifest.get("material_profiles_snapshot_path")
            if snapshot:
                relative = os.path.basename(snapshot) if os.path.isabs(snapshot) else snapshot
                adjacent = os.path.join(os.path.dirname(os.path.abspath(path)), relative)
                if not os.path.isabs(snapshot) or os.path.isfile(adjacent):
                    snapshot = adjacent
                    manifest["material_profiles_snapshot_path"] = adjacent
            if snapshot and os.path.isfile(snapshot):
                try:
                    profiles = read_material_profiles(snapshot)
                    if not isinstance(profiles, dict) or not isinstance(profiles.get("profiles"), list):
                        raise ValueError("Expected a profiles array")
                    profile = get_material_profile(name, profiles)
                    if not profile:
                        issues.append("Profile is absent from the package snapshot: {0}".format(name))
                    else:
                        issues.extend(validate_material_profile(profile))
                        manifest["resolved_material_profile"] = profile
                except (ValueError, TypeError, AttributeError, OSError) as exc:
                    issues.append("Cannot read material profile snapshot: {0}".format(exc))
            elif snapshot:
                issues.append("Declared material profile snapshot is missing: {0}".format(snapshot))
            elif not get_material_profile(name):
                issues.append("Unknown material profile: {0}".format(name))

        profile = manifest.get("resolved_material_profile") or (name if isinstance(name, dict) else get_material_profile(name))
        if not issues and profile and "material_slot_variants" in profile:
            try:
                UnrealMaterialBindingPlanner.slot_variant_routes(profile, manifest.get("materials", []), manifest.get("material_slots", []))
            except ValueError as exc:
                issues.append(str(exc))

        preset = None
        if not issues:
            try:
                preset = self.preset_manager.get_for_manifest(manifest)
            except KeyError as exc:
                issues.append(str(exc))

        return {
            "manifest": manifest,
            "preset": preset,
            "issues": issues,
            "can_import": not issues,
        }

    def _validate_paths(self, manifest, require_fbx_exists):
        issues = []
        fbx_path = manifest.get("fbx_path", "")
        target_path = manifest.get("target_path", "")

        if not fbx_path:
            issues.append("manifest 缺少 fbx_path")
        elif require_fbx_exists and not os.path.isfile(fbx_path):
            issues.append("fbx_path 指向的文件不存在：{0}".format(fbx_path))

        if not target_path:
            issues.append("manifest 缺少 target_path")
        else:
            try:
                sanitize_unreal_package_path(target_path)
            except ValueError as exc:
                issues.append(str(exc))

        return issues

    def _normalize_manifest_paths(self, manifest):
        normalized = dict(manifest)
        fbx_path = normalized.get("fbx_path")
        if fbx_path:
            normalized["fbx_path"] = os.path.abspath(fbx_path).replace("\\", "/")
        target_path = normalized.get("target_path")
        if target_path:
            try:
                normalized["target_path"] = sanitize_unreal_package_path(target_path)
            except ValueError:
                normalized["target_path"] = str(target_path or "").replace("\\", "/").strip()
        return normalized


def load_manifest_for_import(path, require_fbx_exists=True):
    """Read and validate a manifest before Unreal import."""
    result = UnrealManifestReader().load(path, require_fbx_exists)
    return result["manifest"], result["issues"]


def prepare_manifest_for_import(path, require_fbx_exists=True):
    """Read manifest and resolve an Unreal import preset."""
    return UnrealManifestReader().load(path, require_fbx_exists)
