"""Manifest entry point for Unreal-side import tools."""

from __future__ import absolute_import

import os

from asset_forge.shared.manifest_schema import read_manifest, validate_manifest
from asset_forge.unreal.import_presets import UnrealImportPresetManager


class UnrealManifestReader(object):
    """Read manifest.json and prepare it for Unreal import."""

    def __init__(self, preset_manager=None):
        self.preset_manager = preset_manager or UnrealImportPresetManager()

    def load(self, path, require_fbx_exists=True):
        manifest = read_manifest(path)
        issues = validate_manifest(manifest)
        issues.extend(self._validate_paths(manifest, require_fbx_exists))

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
            issues.append("missing fbx_path")
        elif require_fbx_exists and not os.path.exists(fbx_path):
            issues.append("fbx_path does not exist: {0}".format(fbx_path))

        if not target_path:
            issues.append("missing target_path")
        elif not target_path.startswith("/Game"):
            issues.append("target_path must start with /Game: {0}".format(target_path))

        return issues


def load_manifest_for_import(path, require_fbx_exists=True):
    """Read and validate a manifest before Unreal import."""
    result = UnrealManifestReader().load(path, require_fbx_exists)
    return result["manifest"], result["issues"]


def prepare_manifest_for_import(path, require_fbx_exists=True):
    """Read manifest and resolve an Unreal import preset."""
    return UnrealManifestReader().load(path, require_fbx_exists)
