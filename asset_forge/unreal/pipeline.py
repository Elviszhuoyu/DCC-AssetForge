"""Unreal import pipeline orchestration."""

from __future__ import absolute_import

import os

from asset_forge.shared.constants import UNREAL_IMPORT_STATUS_FAILED
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.report_schema import create_batch_report, create_end_to_end_report, read_report, write_report
from asset_forge.unreal.fbx_importer import UnrealStaticMeshFbxImporter
from asset_forge.unreal.import_logger import UnrealImportLogger
from asset_forge.unreal.material_binding_planner import UnrealMaterialBindingPlanner
from asset_forge.unreal.manifest_finder import find_latest_manifest, find_manifest_files
from asset_forge.unreal.manifest_reader import UnrealManifestReader
from asset_forge.unreal.package_validator import UnrealPackageValidator
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
    ):
        self.reader = reader or UnrealManifestReader()
        self.importer = importer or UnrealStaticMeshFbxImporter()
        self.logger = logger or UnrealImportLogger()
        self.post_import_validator = post_import_validator or UnrealPostImportValidator()
        self.package_validator = package_validator or UnrealPackageValidator()
        self.texture_import_planner = texture_import_planner or UnrealTextureImportPlanner()
        self.texture_importer = texture_importer or UnrealTextureImporter()
        self.material_binding_planner = material_binding_planner or UnrealMaterialBindingPlanner()

    def dry_run_manifest(self, manifest_path, log_path=None):
        prepared = self.reader.load(manifest_path, require_fbx_exists=True)
        manifest = prepared["manifest"]
        active_log_path = log_path or self._default_import_report_path(manifest, manifest_path)
        if not prepared["can_import"]:
            report = self.logger.failed(manifest, prepared["issues"], "Manifest validation failed", prepared.get("preset"))
            self._attach_package_validation(report, manifest)
            self._attach_texture_import_plan(report, manifest)
            self._attach_material_binding_plan(report, manifest)
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        report = self.logger.skipped(manifest, prepared["preset"], "Dry run passed")
        self._attach_package_validation(report, manifest)
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
            report = self.logger.failed(manifest, prepared["issues"], "Manifest validation failed", prepared.get("preset"))
            self._attach_package_validation(report, manifest)
            self._attach_texture_import_plan(report, manifest)
            self._attach_material_binding_plan(report, manifest)
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        try:
            imported_assets = self.importer.import_static_mesh(manifest, prepared["preset"])
        except Exception as exc:
            report = self.logger.failed(manifest, [str(exc)], "Unreal import failed", prepared["preset"])
            self._attach_package_validation(report, manifest)
            self._attach_texture_import_plan(report, manifest)
            self._attach_material_binding_plan(report, manifest)
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        report = self.logger.success(manifest, imported_assets, preset=prepared["preset"])
        self._attach_package_validation(report, manifest)
        self._attach_texture_import_plan(report, manifest)
        self._attach_material_binding_plan(report, manifest)
        self._import_planned_textures(report)
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
            report["message"] = "Imported with post-import validation errors"
            report["issues"] = report.get("issues", []) + issues
        return report

    def _attach_package_validation(self, report, manifest):
        report["package_validation"] = self.package_validator.validate(manifest)
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
            report["texture_import_issues"].append(str(exc))
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
        raise RuntimeError("No Asset Forge manifest found under: {0}".format(export_root))
    pipeline = UnrealStaticMeshImportPipeline()
    if dry_run:
        return pipeline.dry_run_manifest(manifest_path, log_path)
    return pipeline.import_from_manifest(manifest_path, log_path)


def import_all_manifests(export_root, report_path=None, dry_run=False):
    """Import or dry-run every manifest under an export root."""
    return UnrealBatchImportPipeline().run(export_root, dry_run, report_path)
