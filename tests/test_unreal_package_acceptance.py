from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.maya.export_package import build_export_package
from asset_forge.shared.constants import TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.manifest_schema import create_manifest, write_manifest
from asset_forge.shared.material_profile_schema import write_material_profiles
from asset_forge.unreal.package_acceptance import UnrealPackageAcceptanceValidator, validate_all_asset_forge_packages


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
        self.assertIn("material_binding_contract", report)
        self.assertIn("material_graph_evidence_report", report)
        self.assertIn("release_dependency_audit", report)
        self.assertIn("engine_version_preflight", report)
        self.assertEqual(report["material_graph_evidence_report"]["real_ue_evidence"], "not_provided")
        self.assertIn("material_binding_contract", report["summary"]["warning_checks"])
        self.assertIn("material_graph_evidence", report["summary"]["warning_checks"])
        self.assertIn("release_dependency_audit", report["summary"]["warning_checks"])
        self.assertIn("engine_version_preflight", report["summary"]["warning_checks"])
        self.assertEqual(report["release_dependency_audit"]["status"], "warning")
        self.assertTrue(report["summary"]["can_accept"])
        self.assertIn("material_profile", report["summary"]["warning_checks"])
        self.assertEqual(report["import_strategy_summary"]["existing_mesh_strategy"], "overwrite")
        self.assertEqual(report["import_strategy_summary"]["existing_texture_strategy"], "overwrite")
        self.assertEqual(report["import_strategy_summary"]["existing_material_strategy"], "reuse")
        self.assertEqual(report["import_policy_summary"]["status"], "manual_validation_required")
        self.assertIn("static_mesh_import_policy", report["import_policy_summary"])
        self.assertIn("texture_import_policy", report["import_policy_summary"])
        self.assertIn("manual_validation_required", report)

    def test_acceptance_report_can_be_written_to_disk(self):
        report_path = os.path.join(self.temp_dir, "acceptance_report.json")
        validator = UnrealPackageAcceptanceValidator(
            plugin_content_bootstrap=FakePluginContentBootstrap(),
            material_asset_bootstrap=FakeMaterialAssetBootstrap(),
        )

        report = validator.validate(self.package["package_dir"], report_path)

        self.assertEqual(report["stage"], "package_acceptance")
        self.assertTrue(os.path.exists(report_path))

    def test_batch_acceptance_validates_every_manifest_under_root(self):
        report_path = os.path.join(self.temp_dir, "batch_acceptance_report.json")

        report = validate_all_asset_forge_packages(self.temp_dir, report_path)

        self.assertEqual(report["stage"], "batch_package_acceptance")
        self.assertEqual(report["total"], 1)
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

    def test_acceptance_report_blocks_missing_parent_material(self):
        validator = UnrealPackageAcceptanceValidator(
            plugin_content_bootstrap=FakePluginContentBootstrap(),
            material_asset_bootstrap=MissingParentMaterialAssetBootstrap(),
        )

        report = validator.validate(self.package["package_dir"])

        self.assertEqual(report["parent_material_validation"]["status"], "error")
        self.assertFalse(report["summary"]["can_accept"])
        self.assertIn("parent_materials", report["summary"]["blocking_checks"])
        self.assertIn("material_graph_evidence", report["summary"]["blocking_checks"])
        self.assertIn("缺少母材质", report["parent_material_validation"]["checks"][0]["message"])

    def test_material_profile_snapshot_missing_reports_warning(self):
        validator = UnrealPackageAcceptanceValidator(
            plugin_content_bootstrap=FakePluginContentBootstrap(),
            material_asset_bootstrap=FakeMaterialAssetBootstrap(),
        )

        report = validator.validate(self.package["package_dir"])

        self.assertEqual(report["material_profile_snapshot_validation"]["status"], "warning")
        self.assertIn("material_profile_snapshot", report["summary"]["warning_checks"])

    def test_material_profile_not_in_snapshot_reports_warning(self):
        snapshot_path = os.path.join(self.temp_dir, "material_profiles_snapshot.json")
        write_material_profiles(snapshot_path, {"version": "0.1", "profiles": []})
        self.manifest["material_profiles_snapshot_path"] = snapshot_path
        write_manifest(self.package["manifest_path"], self.manifest)
        validator = UnrealPackageAcceptanceValidator(
            plugin_content_bootstrap=FakePluginContentBootstrap(),
            material_asset_bootstrap=FakeMaterialAssetBootstrap(),
        )

        report = validator.validate(self.package["package_dir"])

        self.assertEqual(report["material_profile_snapshot_validation"]["status"], "warning")
        self.assertIn("不在快照", report["material_profile_snapshot_validation"]["checks"][0]["message"])


class FakePluginContentBootstrap(object):
    def validate(self):
        return {
            "status": "pass",
            "plugin_name": "AssetForge",
            "content_mount": "/AssetForge",
            "descriptor_path": "D:/AssetForgeFixtures/UEProject/Plugins/AssetForge/AssetForge.uplugin",
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
            "planned_count": 21,
            "existing_count": 21,
            "missing_count": 0,
            "existing_assets": [
                "/AssetForge/Materials/M_AF_HardSurface_Master",
                "/AssetForge/Materials/M_AF_Props_Opaque",
            ],
            "missing_assets": [],
            "assets": [],
        }


class MissingParentMaterialAssetBootstrap(FakeMaterialAssetBootstrap):
    def validate_parent_materials(self, material_binding_plan):
        material = material_binding_plan["materials"][0]
        return {
            "status": "error",
            "can_create_material_instances": False,
            "message": "母材质缺失，无法安全创建材质实例",
            "checks": [
                {
                    "id": "parent_material_exists",
                    "label": "母材质",
                    "status": "error",
                    "path": material["parent_material"],
                    "parent_material": material["parent_material"],
                    "target_asset_path": material["target_asset_path"],
                    "message": "缺少母材质：{0}".format(material["parent_material"]),
                }
            ],
            "missing_parent_materials": [material["parent_material"]],
        }


if __name__ == "__main__":
    unittest.main()
