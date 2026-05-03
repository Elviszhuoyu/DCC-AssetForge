"""Validate Asset Forge Unreal plugin content without creating project assets."""

from __future__ import absolute_import

import io
import json
import os

from asset_forge.unreal.material_package_schema import get_default_material_package_plan
from asset_forge.unreal.unreal_bridge import get_unreal


class UnrealPluginContentBootstrap(object):
    """Check the UE plugin descriptor, content folders, and planned assets."""

    def __init__(self, unreal_module=None, descriptor_path=None):
        self.unreal = unreal_module or get_unreal()
        self.descriptor_path = descriptor_path or self._default_descriptor_path()

    def validate(self, plan=None):
        active_plan = plan or get_default_material_package_plan()
        checks = []
        checks.append(self._descriptor_check())
        checks.extend(self._directory_checks(active_plan))
        checks.extend(self._asset_checks(active_plan))

        return {
            "status": self._status(checks),
            "plugin_name": "AssetForge",
            "content_mount": active_plan.get("content_mount", active_plan.get("root", "")),
            "disk_content_root": active_plan.get("disk_content_root", ""),
            "descriptor_path": self.descriptor_path.replace("\\", "/"),
            "unreal_available": self.unreal is not None,
            "checks": checks,
            "missing_assets": [item["path"] for item in checks if item["id"] == "asset_exists" and item["status"] == "warning"],
        }

    def _default_descriptor_path(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        return os.path.join(repo_root, "Plugins", "AssetForge", "AssetForge.uplugin")

    def _descriptor_check(self):
        if not os.path.exists(self.descriptor_path):
            return self._check("plugin_descriptor", "error", self.descriptor_path, "Missing AssetForge.uplugin")

        with io.open(self.descriptor_path, "r", encoding="utf-8") as stream:
            descriptor = json.load(stream)

        if not descriptor.get("CanContainContent", False):
            return self._check("plugin_descriptor", "error", self.descriptor_path, "AssetForge.uplugin must set CanContainContent=true")
        return self._check("plugin_descriptor", "pass", self.descriptor_path, "AssetForge.uplugin can contain content")

    def _directory_checks(self, plan):
        checks = []
        content_root = os.path.dirname(self.descriptor_path)
        for directory in ["Content", "Content/Materials", "Content/MaterialFunctions", "Content/ParameterCollections"]:
            path = os.path.join(content_root, directory)
            status = "pass" if os.path.isdir(path) else "error"
            message = "Directory exists" if status == "pass" else "Missing plugin content directory"
            checks.append(self._check("plugin_directory", status, path, message))
        return checks

    def _asset_checks(self, plan):
        asset_paths = []
        asset_paths.extend(material.get("path", "") for material in plan.get("materials", []))
        asset_paths.extend(function.get("path", "") for function in plan.get("functions", []))
        asset_paths.extend(collection.get("path", "") for collection in plan.get("parameter_collections", []))
        asset_paths = [path for path in asset_paths if path]

        if self.unreal is None:
            return [
                self._check(
                    "asset_exists",
                    "warning",
                    path,
                    "Unreal module unavailable; asset existence check skipped",
                )
                for path in asset_paths
            ]

        return [self._asset_exists_check(path) for path in asset_paths]

    def _asset_exists_check(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        exists = False
        if library and hasattr(library, "does_asset_exist"):
            exists = bool(library.does_asset_exist(asset_path))
        elif library and hasattr(library, "load_asset"):
            exists = bool(library.load_asset(asset_path))

        status = "pass" if exists else "warning"
        message = "Plugin asset exists" if exists else "Missing plugin asset"
        return self._check("asset_exists", status, asset_path, message)

    def _status(self, checks):
        if any(item["status"] == "error" for item in checks):
            return "error"
        if any(item["status"] == "warning" for item in checks):
            return "warning"
        return "pass"

    def _check(self, check_id, status, path, message):
        return {
            "id": check_id,
            "status": status,
            "path": path.replace("\\", "/"),
            "message": message,
        }


def validate_assetforge_plugin_content(unreal_module=None):
    return UnrealPluginContentBootstrap(unreal_module).validate()
