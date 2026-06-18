from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

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
