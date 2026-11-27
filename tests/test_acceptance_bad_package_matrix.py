from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from asset_forge.shared.manifest_schema import read_manifest, write_manifest
from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.acceptance_runner import UnrealPackageAcceptanceFlow, run_asset_forge_package_acceptance
from asset_forge.unreal.package_acceptance import UnrealPackageAcceptanceValidator


class AcceptanceBadPackageMatrixTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_strict_gate_fails_missing_manifest(self):
        package_dir = os.path.join(self.temp_dir, "MissingManifest")
        os.makedirs(package_dir)

        report = run_asset_forge_package_acceptance(package_dir, strict=True)

        self.assertFalse(report["gate_passed"])
        self.assertIn("manifest", report["package_acceptance"]["next_action"])
        self.assertTrue(report["blocking_reasons"])
        self.assertEqual(report["user_guidance"]["decision"], "blocked")
        self.assertTrue(report["step_outcomes"])

    def test_strict_gate_fails_missing_fbx(self):
        package = create_offline_static_prop_package(self.temp_dir)
        os.remove(package["fbx_path"])

        report = run_asset_forge_package_acceptance(package["package_dir"], strict=True)

        self.assertFalse(report["gate_passed"])
        self.assertTrue(any("fbx_path" in item.get("message", "") for item in report["errors"]))
        self.assertFalse(report["can_import"])

    def test_strict_gate_fails_missing_required_normal(self):
        package = create_offline_static_prop_package(self.temp_dir)
        manifest = read_manifest(package["manifest_path"])
        manifest["textures"] = [item for item in manifest["textures"] if item["usage"] != "normal"]
        manifest["materials"][0]["textures"] = list(manifest["textures"])
        write_manifest(package["manifest_path"], manifest)

        report = run_asset_forge_package_acceptance(package["package_dir"], strict=True)

        self.assertFalse(report["gate_passed"])
        self.assertTrue(any("缺少必需贴图" in item.get("message", "") for item in report["warnings"]))

    def test_strict_gate_fails_unsupported_texture_format_warning(self):
        package = create_offline_static_prop_package(self.temp_dir)
        manifest = read_manifest(package["manifest_path"])
        manifest["textures"][0]["package_path"] = manifest["textures"][0]["package_path"].replace(".png", ".jpg")
        manifest["textures"][0]["path"] = manifest["textures"][0]["package_path"]
        manifest["textures"][0]["source_path"] = manifest["textures"][0]["package_path"]
        write_manifest(package["manifest_path"], manifest)

        report = run_asset_forge_package_acceptance(package["package_dir"], strict=True)

        self.assertFalse(report["gate_passed"])
        self.assertTrue(any("格式不在推荐列表" in item.get("message", "") for item in report["warnings"]))

    def test_strict_gate_fails_non_power_of_two_texture_size(self):
        package = create_offline_static_prop_package(self.temp_dir)
        manifest = read_manifest(package["manifest_path"])
        manifest["textures"][0]["width"] = 1000
        write_manifest(package["manifest_path"], manifest)

        report = run_asset_forge_package_acceptance(package["package_dir"], strict=True)

        self.assertFalse(report["gate_passed"])
        self.assertTrue(any("2 的幂" in item.get("message", "") for item in report["warnings"]))

    def test_strict_gate_fails_unknown_material_profile(self):
        package = create_offline_static_prop_package(self.temp_dir)
        manifest = read_manifest(package["manifest_path"])
        manifest["material_profile"] = "Unknown_Profile_For_Test"
        write_manifest(package["manifest_path"], manifest)

        report = run_asset_forge_package_acceptance(package["package_dir"], strict=True)

        self.assertFalse(report["gate_passed"])
        self.assertTrue(any("未知 material_profile" in item.get("message", "") for item in report["warnings"]))

    def test_strict_gate_fails_missing_parent_material(self):
        package = create_offline_static_prop_package(self.temp_dir)
        validator = UnrealPackageAcceptanceValidator(material_asset_bootstrap=MissingParentMaterialAssetBootstrap())
        flow = UnrealPackageAcceptanceFlow(acceptance_validator=validator)

        report = flow.run(package["package_dir"], strict=True)

        self.assertFalse(report["gate_passed"])
        self.assertTrue(any("缺少母材质" in item.get("message", "") for item in report["errors"]))


class AcceptanceWriteGateTest(unittest.TestCase):
    def setUp(self):
        self.validator = Mock()
        self.package = {"manifest_path": "prop_manifest.json", "summary": {"can_accept": True}}
        self.validator.validate.return_value = self.package
        self.bootstrap = self.validator.material_asset_bootstrap.bootstrap
        self.bootstrap.return_value = {"status": "success"}
        self.pipeline = Mock()
        self.pipeline.dry_run_manifest.return_value = {"status": "skipped"}
        self.pipeline.import_from_manifest.return_value = {"status": "success", "post_import_validation": {"status": "pass"}}
        self.flow = UnrealPackageAcceptanceFlow(self.validator, self.pipeline)

    def run_flow(self, **options):
        with patch("asset_forge.unreal.acceptance_runner.write_report"):
            return self.flow.run("sample", report_path="flow.json", **options)

    def test_wrong_engine_never_bootstraps_materials_in_the_wrong_project(self):
        self.package["engine_version_preflight"] = {"status": "error", "can_write_assets": False}
        self.package["summary"]["can_accept"] = False
        report = self.run_flow(run_import=True, auto_bootstrap_material_assets=True, require_import=True)
        self.bootstrap.assert_not_called()
        self.pipeline.import_from_manifest.assert_not_called()
        self.assertEqual(report["import"]["status"], "skipped")
        self.assertFalse(report["gate_passed"])

    def test_blocked_warning_prevents_material_bootstrap_and_import(self):
        self.package["warnings"] = ["review texture"]
        for options in ({"strict": True}, {"block_warnings": True}):
            with self.subTest(options=options):
                report = self.run_flow(run_import=True, auto_bootstrap_material_assets=True, **options)
                self.bootstrap.assert_not_called()
                self.pipeline.import_from_manifest.assert_not_called()
                self.assertFalse(report["gate_passed"])
                self.assertFalse(report["can_import"])
                self.assertEqual(report["import"]["status"], "skipped")

    def test_preflight_error_or_warning_prevents_strict_writes(self):
        for finding in ({"status": "failed"}, {"status": "skipped", "errors": ["invalid mesh"]},
                        {"status": "skipped", "warnings": ["review slot"]}):
            with self.subTest(finding=finding):
                self.pipeline.dry_run_manifest.return_value = finding
                report = self.run_flow(run_import=True, auto_bootstrap_material_assets=True, strict=True)
                self.bootstrap.assert_not_called()
                self.pipeline.import_from_manifest.assert_not_called()
                self.assertFalse(report["gate_passed"])

    def test_auto_materials_without_import_still_obeys_strict_gate(self):
        self.package["warnings"] = ["review texture"]
        report = self.run_flow(auto_bootstrap_material_assets=True, strict=True)
        self.bootstrap.assert_not_called()
        self.assertFalse(report["gate_passed"])

    def test_explicitly_allowed_warning_can_import_and_satisfy_postcondition(self):
        self.package["warnings"] = ["review texture"]
        report = self.run_flow(run_import=True, strict=True, block_warnings=False, require_import=True)
        self.pipeline.import_from_manifest.assert_called_once_with("prop_manifest.json")
        self.assertTrue(report["gate_passed"])

    def test_clean_preflight_cannot_satisfy_failed_post_import_check(self):
        self.pipeline.import_from_manifest.return_value["post_import_validation"]["status"] = "error"
        report = self.run_flow(run_import=True, strict=True, require_import=True)
        self.pipeline.import_from_manifest.assert_called_once()
        self.assertFalse(report["gate_passed"])

    def test_bootstrap_revalidation_can_block_mesh_write(self):
        self.validator.validate.side_effect = [self.package, dict(self.package, warnings=["after bootstrap"])]
        report = self.run_flow(run_import=True, strict=True, auto_bootstrap_material_assets=True)
        self.bootstrap.assert_called_once()
        self.pipeline.import_from_manifest.assert_not_called()
        self.assertFalse(report["gate_passed"])


class MissingParentMaterialAssetBootstrap(object):
    def inspect_assets(self):
        return {
            "status": "warning",
            "message": "默认材质资产缺失",
            "missing_assets": ["/AssetForge/Materials/M_AF_Props_Opaque"],
            "checks": [],
        }

    def validate_parent_materials(self, material_binding_plan):
        material = material_binding_plan["materials"][0]
        return {
            "status": "error",
            "can_create_material_instances": False,
            "message": "母材质缺失，无法安全创建材质实例",
            "checks": [
                {
                    "id": "parent_material_exists",
                    "status": "error",
                    "path": material["parent_material"],
                    "message": "缺少母材质：{0}".format(material["parent_material"]),
                }
            ],
            "missing_parent_materials": [material["parent_material"]],
        }


if __name__ == "__main__":
    unittest.main()
