"""Unreal import pipeline orchestration."""

from __future__ import absolute_import

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
        if not prepared["can_import"]:
            report = self.logger.failed(manifest, prepared["issues"], "Manifest validation failed", prepared.get("preset"))
            self._write_log(log_path, report)
            return report

        report = self.logger.skipped(manifest, prepared["preset"], "Dry run passed")
        self._write_log(log_path, report)
        return report

    def import_from_manifest(self, manifest_path, log_path=None):
        prepared = self.reader.load(manifest_path, require_fbx_exists=True)
        manifest = prepared["manifest"]
        if not prepared["can_import"]:
            report = self.logger.failed(manifest, prepared["issues"], "Manifest validation failed", prepared.get("preset"))
            self._write_log(log_path, report)
            return report

        try:
            imported_assets = self.importer.import_static_mesh(manifest, prepared["preset"])
        except Exception as exc:
            report = self.logger.failed(manifest, [str(exc)], "Unreal import failed", prepared["preset"])
            self._write_log(log_path, report)
            return report

        report = self.logger.success(manifest, imported_assets, preset=prepared["preset"])
        self._write_log(log_path, report)
        return report

    def _write_log(self, log_path, report):
        if log_path:
            self.logger.write(log_path, report)


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
