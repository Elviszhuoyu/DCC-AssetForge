from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.maya.export_package import build_export_package
from asset_forge.shared.constants import TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.manifest_schema import create_manifest, write_manifest
from asset_forge.unreal.package_acceptance import UnrealPackageAcceptanceValidator


class UnrealPackageAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.package = build_export_package(self.temp_dir, "SM_Crate_01")
        with open(self.package["fbx_path"], "wb") as stream:
            stream.write(b"fake fbx")
        self.manifest = create_manifest(
            "SM_Crate_01",
            self.package["fbx_path"],
            "/Game/Props",
            target_platform=TARGET_PLATFORM_HIGH_END_MOBILE,
            package_dir=self.package["package_dir"],
            material_profile="Props_Opaque_PainterUE_ARM",
            materials=[{"name": "M_Crate", "textures": []}],
            textures=[],
        )
        write_manifest(self.package["manifest_path"], self.manifest)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_acceptance_report_collects_preflight_sections(self):
        validator = UnrealPackageAcceptanceValidator(
            plugin_content_bootstrap=FakePluginContentBootstrap(),
            material_asset_bootstrap=FakeMaterialAssetBootstrap(),
        )

        report = validator.validate(self.package["package_dir"])

        self.assertEqual(report["stage"], "package_acceptance")
        self.assertEqual(report["asset_name"], "SM_Crate_01")
        self.assertIn("plugin_mount_preflight", report)
        self.assertIn("material_asset_validation", report)
        self.assertIn("texture_import_plan", report)
        self.assertIn("material_binding_plan", report)
        self.assertIn("packed_channel_validation", report)
        self.assertTrue(report["summary"]["can_accept"])
        self.assertIn("material_profile", report["summary"]["warning_checks"])

    def test_acceptance_report_can_be_written_to_disk(self):
        report_path = os.path.join(self.temp_dir, "acceptance_report.json")
        validator = UnrealPackageAcceptanceValidator(
            plugin_content_bootstrap=FakePluginContentBootstrap(),
            material_asset_bootstrap=FakeMaterialAssetBootstrap(),
        )

        report = validator.validate(self.package["package_dir"], report_path)

        self.assertEqual(report["stage"], "package_acceptance")
        self.assertTrue(os.path.exists(report_path))

    def test_acceptance_report_blocks_missing_manifest(self):
        validator = UnrealPackageAcceptanceValidator(
            plugin_content_bootstrap=FakePluginContentBootstrap(),
            material_asset_bootstrap=FakeMaterialAssetBootstrap(),
        )

        report = validator.validate(os.path.join(self.temp_dir, "Missing"))

        self.assertEqual(report["stage"], "package_acceptance")
        self.assertFalse(report["summary"]["can_accept"])
        self.assertEqual(report["summary"]["blocking_checks"], ["manifest"])


class FakePluginContentBootstrap(object):
    def validate(self):
        return {
            "status": "pass",
            "plugin_name": "AssetForge",
            "content_mount": "/AssetForge",
            "descriptor_path": "<LEGACY_WORK_DRIVE>/UEProject/Plugins/AssetForge/AssetForge.uplugin",
            "unreal_available": True,
            "missing_assets": [],
            "checks": [
                {"id": "plugin_descriptor", "status": "pass", "path": "", "message": "AssetForge.uplugin 可用"},
                {"id": "content_mount", "status": "pass", "path": "/AssetForge", "message": "AssetForge 插件内容根已挂载"},
            ],
        }


class FakeMaterialAssetBootstrap(object):
    def inspect_assets(self):
        return {
            "status": "pass",
            "message": "默认材质资产已就绪",
            "planned_count": 6,
            "existing_count": 6,
            "missing_count": 0,
            "existing_assets": ["/AssetForge/Materials/M_AF_Props_Opaque"],
            "missing_assets": [],
            "assets": [],
        }


if __name__ == "__main__":
    unittest.main()
