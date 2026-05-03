"""Unreal import pipeline orchestration."""

from __future__ import absolute_import

import os

from asset_forge.shared.report_schema import create_end_to_end_report, read_report, write_report
from asset_forge.unreal.fbx_importer import UnrealStaticMeshFbxImporter
from asset_forge.unreal.import_logger import UnrealImportLogger
from asset_forge.unreal.manifest_finder import find_latest_manifest
from asset_forge.unreal.manifest_reader import UnrealManifestReader


class UnrealStaticMeshImportPipeline(object):
    """Read manifest, resolve preset, import FBX, and return a report."""

    def __init__(self, reader=None, importer=None, logger=None):
        self.reader = reader or UnrealManifestReader()
        self.importer = importer or UnrealStaticMeshFbxImporter()
        self.logger = logger or UnrealImportLogger()

    def dry_run_manifest(self, manifest_path, log_path=None):
        prepared = self.reader.load(manifest_path, require_fbx_exists=True)
        manifest = prepared["manifest"]
        active_log_path = log_path or self._default_import_report_path(manifest, manifest_path)
        if not prepared["can_import"]:
            report = self.logger.failed(manifest, prepared["issues"], "Manifest validation failed", prepared.get("preset"))
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        report = self.logger.skipped(manifest, prepared["preset"], "Dry run passed")
        self._write_log(active_log_path, report)
        self._write_end_to_end_report(manifest, manifest_path, report)
        return report

    def import_from_manifest(self, manifest_path, log_path=None):
        prepared = self.reader.load(manifest_path, require_fbx_exists=True)
        manifest = prepared["manifest"]
        active_log_path = log_path or self._default_import_report_path(manifest, manifest_path)
        if not prepared["can_import"]:
            report = self.logger.failed(manifest, prepared["issues"], "Manifest validation failed", prepared.get("preset"))
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        try:
            imported_assets = self.importer.import_static_mesh(manifest, prepared["preset"])
        except Exception as exc:
            report = self.logger.failed(manifest, [str(exc)], "Unreal import failed", prepared["preset"])
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        report = self.logger.success(manifest, imported_assets, preset=prepared["preset"])
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
