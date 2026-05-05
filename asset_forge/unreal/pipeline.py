"""Unreal import pipeline orchestration."""

from __future__ import absolute_import

import os

from asset_forge.shared.constants import UNREAL_IMPORT_STATUS_FAILED
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.report_schema import create_batch_report, create_end_to_end_report, read_report, write_report
from asset_forge.unreal.fbx_importer import UnrealStaticMeshFbxImporter
from asset_forge.unreal.import_logger import UnrealImportLogger
from asset_forge.unreal.material_binding_planner import UnrealMaterialBindingPlanner
from asset_forge.unreal.material_instance_creator import UnrealMaterialInstanceCreator
from asset_forge.unreal.material_slot_assigner import UnrealMaterialSlotAssigner
from asset_forge.unreal.manifest_finder import find_latest_manifest, find_manifest_files
from asset_forge.unreal.manifest_reader import UnrealManifestReader
from asset_forge.unreal.package_validator import UnrealPackageValidator
from asset_forge.unreal.plugin_content_bootstrap import UnrealPluginContentBootstrap
from asset_forge.unreal.post_import_validator import UnrealPostImportValidator
from asset_forge.unreal.texture_import_planner import UnrealTextureImportPlanner
from asset_forge.unreal.texture_importer import UnrealTextureImporter


class UnrealStaticMeshImportPipeline(object):
    """Read manifest, resolve preset, import FBX, and return a report."""

    def __init__(
        self,
        reader=None,
        importer=None,
        logger=None,
        post_import_validator=None,
        package_validator=None,
        texture_import_planner=None,
        texture_importer=None,
        material_binding_planner=None,
        material_instance_creator=None,
        material_slot_assigner=None,
        plugin_content_bootstrap=None,
    ):
        self.reader = reader or UnrealManifestReader()
        self.importer = importer or UnrealStaticMeshFbxImporter()
        self.logger = logger or UnrealImportLogger()
        self.post_import_validator = post_import_validator or UnrealPostImportValidator()
        self.package_validator = package_validator or UnrealPackageValidator()
        self.texture_import_planner = texture_import_planner or UnrealTextureImportPlanner()
        self.texture_importer = texture_importer or UnrealTextureImporter()
        self.material_binding_planner = material_binding_planner or UnrealMaterialBindingPlanner()
        self.material_instance_creator = material_instance_creator or UnrealMaterialInstanceCreator()
        self.material_slot_assigner = material_slot_assigner or UnrealMaterialSlotAssigner()
        self.plugin_content_bootstrap = plugin_content_bootstrap or UnrealPluginContentBootstrap()

    def dry_run_manifest(self, manifest_path, log_path=None):
        prepared = self.reader.load(manifest_path, require_fbx_exists=True)
        manifest = prepared["manifest"]
        active_log_path = log_path or self._default_import_report_path(manifest, manifest_path)
        if not prepared["can_import"]:
            report = self.logger.failed(manifest, prepared["issues"], "Manifest 校验失败", prepared.get("preset"))
            self._attach_package_validation(report, manifest)
            self._attach_plugin_content_validation(report)
            self._attach_texture_import_plan(report, manifest)
            self._attach_material_binding_plan(report, manifest)
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        report = self.logger.skipped(manifest, prepared["preset"], "预检查通过，未执行导入")
        self._attach_package_validation(report, manifest)
        self._attach_plugin_content_validation(report)
        self._attach_texture_import_plan(report, manifest)
        self._attach_material_binding_plan(report, manifest)
        self._write_log(active_log_path, report)
        self._write_end_to_end_report(manifest, manifest_path, report)
        return report

    def import_from_manifest(self, manifest_path, log_path=None):
        prepared = self.reader.load(manifest_path, require_fbx_exists=True)
        manifest = prepared["manifest"]
        active_log_path = log_path or self._default_import_report_path(manifest, manifest_path)
        if not prepared["can_import"]:
            report = self.logger.failed(manifest, prepared["issues"], "Manifest 校验失败", prepared.get("preset"))
            self._attach_package_validation(report, manifest)
            self._attach_plugin_content_validation(report)
            self._attach_texture_import_plan(report, manifest)
            self._attach_material_binding_plan(report, manifest)
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        try:
            imported_assets = self.importer.import_static_mesh(manifest, prepared["preset"])
        except Exception as exc:
            report = self.logger.failed(manifest, [str(exc)], "Unreal 导入失败", prepared["preset"])
            self._attach_package_validation(report, manifest)
            self._attach_plugin_content_validation(report)
            self._attach_texture_import_plan(report, manifest)
            self._attach_material_binding_plan(report, manifest)
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        report = self.logger.success(manifest, imported_assets, preset=prepared["preset"])
        self._attach_package_validation(report, manifest)
        self._attach_plugin_content_validation(report)
        self._attach_texture_import_plan(report, manifest)
        self._attach_material_binding_plan(report, manifest)
        self._import_planned_textures(report)
        self._create_material_instances(report)
        self._assign_material_slots(report)
        report = self._attach_post_import_validation(report, manifest, imported_assets)
        self._write_log(active_log_path, report)
        self._write_end_to_end_report(manifest, manifest_path, report)
        return report

    def _write_log(self, log_path, report):
        if log_path:
            self.logger.write(log_path, report)

    def _default_import_report_path(self, manifest, manifest_path):
        package_dir = manifest.get("package_dir") or os.path.dirname(os.path.abspath(manifest_path))
        asset_name = manifest.get("asset_name", "asset")
        return os.path.join(package_dir, asset_name + "_import_report.json")

    def _default_export_report_path(self, manifest, manifest_path):
        package_dir = manifest.get("package_dir") or os.path.dirname(os.path.abspath(manifest_path))
        asset_name = manifest.get("asset_name", "asset")
        return os.path.join(package_dir, asset_name + "_export_report.json")

    def _default_end_to_end_report_path(self, manifest, manifest_path):
        package_dir = manifest.get("package_dir") or os.path.dirname(os.path.abspath(manifest_path))
        asset_name = manifest.get("asset_name", "asset")
        return os.path.join(package_dir, asset_name + "_end_to_end_report.json")

    def _write_end_to_end_report(self, manifest, manifest_path, import_report):
        export_report_path = self._default_export_report_path(manifest, manifest_path)
        export_report = read_report(export_report_path) if os.path.exists(export_report_path) else {}
        report = create_end_to_end_report(export_report, import_report)
        write_report(self._default_end_to_end_report_path(manifest, manifest_path), report)

    def _attach_post_import_validation(self, report, manifest, imported_assets):
        validation = self.post_import_validator.validate(manifest, imported_assets)
        report["post_import_validation"] = validation
        if not validation.get("can_accept", False):
            issues = [item["message"] for item in validation.get("checks", []) if item.get("status") == "error"]
            report["status"] = UNREAL_IMPORT_STATUS_FAILED
            report["message"] = "导入完成，但导入后校验存在错误"
            report["issues"] = report.get("issues", []) + issues
        return report

    def _attach_package_validation(self, report, manifest):
        report["package_validation"] = self.package_validator.validate(manifest)
        return report

    def _attach_plugin_content_validation(self, report):
        report["plugin_content_validation"] = self.plugin_content_bootstrap.validate()
        return report

    def _attach_texture_import_plan(self, report, manifest):
        report["texture_import_plan"] = self.texture_import_planner.plan(manifest)
        return report

    def _attach_material_binding_plan(self, report, manifest):
        report["material_binding_plan"] = self.material_binding_planner.plan(
            manifest,
            report.get("texture_import_plan", {}),
            manifest.get("material_profile"),
        )
        return report

    def _import_planned_textures(self, report):
        plan = report.get("texture_import_plan", {})
        report["imported_textures"] = []
        report["texture_import_issues"] = []
        if not plan.get("count", 0):
            return report

        try:
            report["imported_textures"] = self.texture_importer.import_textures(plan)
        except Exception as exc:
            report["texture_import_issues"].append("贴图导入失败：{0}".format(exc))
        return report

    def _create_material_instances(self, report):
        report["created_material_instances"] = []
        report["material_instance_issues"] = []
        plan = report.get("material_binding_plan", {})
        if not plan.get("count", 0):
            return report
        if hasattr(self.material_instance_creator, "is_available") and not self.material_instance_creator.is_available():
            return report
        if hasattr(self.material_instance_creator, "is_available"):
            blockers = self._material_instance_blockers(report)
            if blockers:
                report["material_instance_issues"].extend(blockers)
                return report

        try:
            report["created_material_instances"] = self.material_instance_creator.create_from_plan(plan)
        except Exception as exc:
            report["material_instance_issues"].append("材质实例创建失败：{0}".format(exc))
        return report

    def _material_instance_blockers(self, report):
        plugin_validation = report.get("plugin_content_validation", {})
        missing_assets = set(plugin_validation.get("missing_assets", []))
        plan = report.get("material_binding_plan", {})
        blockers = []
        for material in plan.get("materials", []):
            parent = material.get("parent_material", "")
            if parent and parent in missing_assets:
                blockers.append("缺少母材质 {0}，已跳过材质实例：{1}".format(parent, material.get("target_asset_path", "")))
        return blockers

    def _assign_material_slots(self, report):
        report["material_assignment_report"] = {
            "status": "skipped",
            "assigned": [],
            "issues": [],
        }
        if hasattr(self.material_slot_assigner, "is_available") and not self.material_slot_assigner.is_available():
            report["material_assignment_report"]["issues"].append("当前环境不可用 Unreal Python 模块，跳过材质槽绑定")
            return report

        try:
            report["material_assignment_report"] = self.material_slot_assigner.assign_from_report(report)
        except Exception as exc:
            report["material_assignment_report"]["status"] = "warning"
            report["material_assignment_report"]["issues"].append("材质槽绑定失败：{0}".format(exc))
        return report


class UnrealBatchImportPipeline(object):
    """Batch dry-run or import every manifest under an export root."""

    def __init__(self, item_pipeline=None):
        self.item_pipeline = item_pipeline or UnrealStaticMeshImportPipeline()

    def run(self, export_root, dry_run=False, report_path=None):
        manifests = find_manifest_files(export_root)
        reports = []
        for manifest_path in manifests:
            if dry_run:
                reports.append(self.item_pipeline.dry_run_manifest(manifest_path))
            else:
                reports.append(self.item_pipeline.import_from_manifest(manifest_path))

        batch_report = create_batch_report(export_root, dry_run, reports)
        write_report(report_path or self._default_batch_report_path(export_root, dry_run), batch_report)
        return batch_report

    def _default_batch_report_path(self, export_root, dry_run):
        file_name = "batch_dry_run_report.json" if dry_run else "batch_import_report.json"
        return normalize_path(os.path.join(export_root, file_name))


def import_manifest(manifest_path, log_path=None):
    """Convenience entry point for Unreal Python Script Editor."""
    return UnrealStaticMeshImportPipeline().import_from_manifest(manifest_path, log_path)


def dry_run_manifest(manifest_path, log_path=None):
    """Validate a manifest and resolve preset without importing."""
    return UnrealStaticMeshImportPipeline().dry_run_manifest(manifest_path, log_path)


def import_latest_manifest(export_root, log_path=None, dry_run=False):
    """Find and import the newest manifest under an export root."""
    manifest_path = find_latest_manifest(export_root)
    if not manifest_path:
        raise RuntimeError("未找到 Asset Forge manifest：{0}".format(export_root))
    pipeline = UnrealStaticMeshImportPipeline()
    if dry_run:
        return pipeline.dry_run_manifest(manifest_path, log_path)
    return pipeline.import_from_manifest(manifest_path, log_path)


def import_asset_forge_package(package_dir, dry_run=False, report_path=None):
    """Import or dry-run the newest manifest in one Asset Forge package folder."""
    manifest_path = find_latest_manifest(package_dir)
    if not manifest_path:
        raise RuntimeError("资产包内未找到 Asset Forge manifest：{0}".format(package_dir))

    active_report_path = report_path or os.path.join(os.path.abspath(package_dir), "package_import_report.json")
    pipeline = UnrealStaticMeshImportPipeline()
    if dry_run:
        return pipeline.dry_run_manifest(manifest_path, active_report_path)
    return pipeline.import_from_manifest(manifest_path, active_report_path)


def import_all_manifests(export_root, report_path=None, dry_run=False):
    """Import or dry-run every manifest under an export root."""
    return UnrealBatchImportPipeline().run(export_root, dry_run, report_path)
