from __future__ import absolute_import

import copy
import os
import shutil
import tempfile
import unittest

from asset_forge.shared.material_profile_contract import validate_material_profile_contract
from asset_forge.shared.material_profile_schema import get_default_material_profile
from asset_forge.shared.manifest_schema import read_manifest, write_manifest
from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.package_acceptance import validate_asset_forge_package


class MaterialProfileContractTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_legal_profile_contract_passes_with_material_plan(self):
        profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")
        profile["material_network_status"] = "verified_pbr"
        plan = {
            "materials": [
                {
                    "target_asset_path": "/Game/Props/Materials/M_Crate",
                    "slots": {"base_color": "/Game/T_BaseColor"},
                    "texture_parameters": {"BaseColor": "/Game/T_BaseColor"},
                    "scalar_parameters": dict(profile["scalar_parameters"]),
                    "vector_parameters": dict(profile["vector_parameters"]),
                }
            ]
        }

        report = validate_material_profile_contract(profile, plan)

        self.assertEqual(report["status"], "pass")

    def test_missing_texture_parameter_warns(self):
        profile = copy.deepcopy(get_default_material_profile("Props_Opaque_PainterUE_ARM"))
        profile["texture_rules"][0]["parameter"] = ""

        report = validate_material_profile_contract(profile, {"materials": []})

        self.assertEqual(report["status"], "warning")
        self.assertTrue(any("缺少材质参数映射" in item["message"] for item in report["warnings"]))

    def test_bad_master_material_path_errors(self):
        profile = copy.deepcopy(get_default_material_profile("Props_Opaque_PainterUE_ARM"))
        profile["master_material"] = "/Game/AssetForge/Materials/M_Bad"

        report = validate_material_profile_contract(profile, {"materials": []})

        self.assertEqual(report["status"], "error")
        self.assertTrue(any("/AssetForge" in item["message"] for item in report["errors"]))

    def test_package_acceptance_includes_material_profile_contract(self):
        package = create_offline_static_prop_package(self.temp_dir)
        manifest = read_manifest(package["manifest_path"])
        manifest["material_profile"] = {
            "name": "Bad_Profile",
            "master_material": "/Game/AssetForge/M_Bad",
            "material_instance_dir": "{target_path}/Materials",
            "texture_dir": "{target_path}/Textures",
            "texture_rules": [],
            "scalar_parameters": {},
        }
        write_manifest(package["manifest_path"], manifest)

        report = validate_asset_forge_package(package["package_dir"])

        self.assertEqual(report["material_profile_contract_validation"]["status"], "error")
        self.assertIn("material_profile_contract", report["summary"]["blocking_checks"])

    def test_package_acceptance_warning_summary_excludes_pass_contract_messages(self):
        package = create_offline_static_prop_package(self.temp_dir)

        report = validate_asset_forge_package(package["package_dir"])

        warning_messages = [
            item["message"]
            for item in report["summary"]["warnings"]
            if item.get("source") == "material_profile_contract"
        ]
        self.assertTrue(warning_messages)
        self.assertFalse(any("base_color->BaseColor" in message for message in warning_messages))


if __name__ == "__main__":
    unittest.main()
