"""Lightweight Maya Skeletal Mesh scan/validate/manifest pipeline."""

from __future__ import absolute_import

from asset_forge.maya.export_package import build_skeletal_export_package
from asset_forge.maya.skeletal_scanner import MayaSkeletalScanner
from asset_forge.shared.constants import SOURCE_DCC_MAYA, TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.manifest_schema import create_skeletal_mesh_manifest, write_manifest
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.report_schema import create_skeletal_package_report, write_report
from asset_forge.shared.skeletal_rule_validator import SkeletalMeshRuleValidator
from asset_forge.shared.skeletal_scan_schema import skeletal_manifest_fields_from_scan
from asset_forge.shared.rule_validator import checks_to_manifest_dict


class MayaSkeletalPipeline(object):
    """Phase 4 pipeline stub for Skeletal Mesh metadata only."""

    def __init__(self, scanner=None, validator=None):
        self.scanner = scanner or MayaSkeletalScanner()
        self.validator = validator or SkeletalMeshRuleValidator()

    def scan_asset(self, asset_root):
        return self.scanner.scan(asset_root)

    def validate_scan(self, scan_result, target_platform=TARGET_PLATFORM_HIGH_END_MOBILE):
        return self.validator.validate(scan_result, target_platform)

    def build_manifest(
        self,
        scan_result,
        validation_result,
        fbx_path,
        target_path,
        package_dir="",
        target_engine_version="",
    ):
        if not validation_result.get("can_export", False):
            raise RuntimeError("Skeletal Mesh has blocking validation errors")

        manifest_fields = skeletal_manifest_fields_from_scan(scan_result)
        return create_skeletal_mesh_manifest(
            scan_result.get("asset_name", ""),
            normalize_path(fbx_path),
            target_path,
            checks=checks_to_manifest_dict(validation_result),
            score=validation_result.get("score", 0),
            source_dcc=SOURCE_DCC_MAYA,
            target_platform=validation_result.get("target_platform", TARGET_PLATFORM_HIGH_END_MOBILE),
            target_engine_version=target_engine_version,
            package_dir=normalize_path(package_dir) if package_dir else "",
            **manifest_fields
        )

    def prepare_manifest(
        self,
        asset_root,
        fbx_path,
        target_path,
        target_platform=TARGET_PLATFORM_HIGH_END_MOBILE,
        package_dir="",
    ):
        scan_result = self.scan_asset(asset_root)
        validation_result = self.validate_scan(scan_result, target_platform)
        manifest = self.build_manifest(scan_result, validation_result, fbx_path, target_path, package_dir)
        return {
            "scan": scan_result,
            "validation": validation_result,
            "manifest": manifest,
        }

    def prepare_package_metadata(
        self,
        asset_root,
        output_root,
        target_path,
        target_platform=TARGET_PLATFORM_HIGH_END_MOBILE,
        use_asset_folder=True,
    ):
        scan_result = self.scan_asset(asset_root)
        validation_result = self.validate_scan(scan_result, target_platform)
        if not validation_result.get("can_export", False):
            raise RuntimeError("Skeletal Mesh has blocking validation errors")

        asset_name = scan_result.get("asset_name", "Asset")
        package = build_skeletal_export_package(output_root, asset_name, use_asset_folder)
        manifest = self.build_manifest(
            scan_result,
            validation_result,
            package["fbx_path"],
            target_path,
            package_dir=package["package_dir"],
        )
        package_report = create_skeletal_package_report(scan_result, validation_result, manifest, package)

        write_manifest(package["manifest_path"], manifest, pretty=True)
        write_report(package["package_report_path"], package_report)
        return {
            "scan": scan_result,
            "validation": validation_result,
            "package": package,
            "manifest": manifest,
            "package_report": package_report,
            "manifest_path": package["manifest_path"],
            "package_report_path": package["package_report_path"],
        }
