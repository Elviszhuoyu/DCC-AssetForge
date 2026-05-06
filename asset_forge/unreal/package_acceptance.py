"""Unified acceptance report for one Asset Forge export package."""

from __future__ import absolute_import

import os

from asset_forge.shared.material_profile_validator import validate_material_texture_coverage
from asset_forge.shared.path_utils import normalize_path
from asset_forge.unreal.manifest_finder import find_latest_manifest
from asset_forge.unreal.manifest_reader import UnrealManifestReader
from asset_forge.unreal.material_asset_bootstrap import UnrealMaterialAssetBootstrap
from asset_forge.unreal.material_binding_planner import UnrealMaterialBindingPlanner
from asset_forge.unreal.package_validator import UnrealPackageValidator
from asset_forge.unreal.plugin_content_bootstrap import UnrealPluginContentBootstrap
from asset_forge.unreal.plugin_mount_preflight import UnrealPluginMountPreflight
from asset_forge.unreal.texture_import_planner import UnrealTextureImportPlanner


class UnrealPackageAcceptanceValidator(object):
    """Build one report that says whether an exported package is ready."""

    def __init__(
        self,
        reader=None,
        package_validator=None,
        plugin_content_bootstrap=None,
        material_asset_bootstrap=None,
        texture_import_planner=None,
        material_binding_planner=None,
        plugin_mount_preflight=None,
    ):
        self.reader = reader or UnrealManifestReader()
        self.package_validator = package_validator or UnrealPackageValidator()
        self.plugin_content_bootstrap = plugin_content_bootstrap or UnrealPluginContentBootstrap()
        self.material_asset_bootstrap = material_asset_bootstrap or UnrealMaterialAssetBootstrap()
        self.texture_import_planner = texture_import_planner or UnrealTextureImportPlanner()
        self.material_binding_planner = material_binding_planner or UnrealMaterialBindingPlanner()
        self.plugin_mount_preflight = plugin_mount_preflight or UnrealPluginMountPreflight(content_bootstrap=self.plugin_content_bootstrap)

    def validate(self, manifest_or_package_path):
        manifest_path = self._resolve_manifest_path(manifest_or_package_path)
        if not manifest_path:
            return self._missing_manifest_report(manifest_or_package_path)

        prepared = self.reader.load(manifest_path, require_fbx_exists=True)
        manifest = prepared.get("manifest", {})
        package_validation = self.package_validator.validate(manifest)
        plugin_content_validation = self.plugin_content_bootstrap.validate()
        plugin_mount = self.plugin_mount_preflight.check()
        material_asset_validation = self.material_asset_bootstrap.inspect_assets()
        texture_plan = self.texture_import_planner.plan(manifest)
        material_plan = self.material_binding_planner.plan(manifest, texture_plan, manifest.get("material_profile"))
        material_profile_validation = validate_material_texture_coverage(manifest.get("material_profile"), manifest.get("textures", []))

        checks = [
            self._check("manifest", "pass" if prepared.get("can_import") else "error", "Manifest", prepared.get("issues", [])),
            self._check("package", package_validation.get("status"), "导出包资源", self._messages(package_validation)),
            self._check("plugin_mount", plugin_mount.get("status"), "UE 插件挂载", [plugin_mount.get("message", "")]),
            self._check("plugin_content", plugin_content_validation.get("status"), "UE 插件内容", self._messages(plugin_content_validation)),
            self._check("material_assets", material_asset_validation.get("status"), "默认材质资产", [material_asset_validation.get("message", "")]),
            self._check("material_profile", material_profile_validation.get("status"), "Material Profile", self._messages(material_profile_validation)),
        ]
        summary = self._summary(checks)
        return {
            "status": "pass" if summary["can_accept"] else "warning",
            "stage": "package_acceptance",
            "manifest_path": normalize_path(manifest_path),
            "asset_name": manifest.get("asset_name", ""),
            "target_path": manifest.get("target_path", ""),
            "checks": checks,
            "summary": summary,
            "manifest_validation": prepared,
            "package_validation": package_validation,
            "plugin_mount_preflight": plugin_mount,
            "plugin_content_validation": plugin_content_validation,
            "material_asset_validation": material_asset_validation,
            "texture_import_plan": texture_plan,
            "material_binding_plan": material_plan,
            "material_profile_validation": material_profile_validation,
        }

    def _resolve_manifest_path(self, manifest_or_package_path):
        if os.path.isfile(manifest_or_package_path):
            return manifest_or_package_path
        if os.path.isdir(manifest_or_package_path):
            return find_latest_manifest(manifest_or_package_path)
        return ""

    def _missing_manifest_report(self, path):
        check = self._check("manifest", "error", "Manifest", ["未找到 Asset Forge manifest：{0}".format(path)])
        return {
            "status": "warning",
            "stage": "package_acceptance",
            "manifest_path": "",
            "asset_name": "",
            "target_path": "",
            "checks": [check],
            "summary": self._summary([check]),
        }

    def _check(self, check_id, status, label, messages):
        return {
            "id": check_id,
            "label": label,
            "status": status or "warning",
            "messages": [message for message in messages if message],
        }

    def _messages(self, report):
        messages = []
        for item in report.get("checks", []):
            if item.get("message"):
                messages.append(item.get("message"))
        if report.get("issues"):
            messages.extend([str(item) for item in report.get("issues", [])])
        return messages

    def _summary(self, checks):
        errors = [item for item in checks if item.get("status") == "error"]
        warnings = [item for item in checks if item.get("status") == "warning"]
        return {
            "can_accept": not errors,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "blocking_checks": [item["id"] for item in errors],
            "warning_checks": [item["id"] for item in warnings],
        }


def validate_asset_forge_package(manifest_or_package_path):
    return UnrealPackageAcceptanceValidator().validate(manifest_or_package_path)
