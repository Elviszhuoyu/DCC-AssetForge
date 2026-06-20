from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.manifest_schema import read_manifest, write_manifest
from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.package_acceptance import validate_asset_forge_package
from asset_forge.unreal.slot_binding_preflight import validate_static_mesh_slot_bindings


class SlotBindingPreflightTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_slot_binding_preflight_passes_full_match(self):
        manifest = {"material_slots": [{"name": "M_Crate"}]}
        plan = {"materials": [{"material_name": "M_Crate"}]}

        report = validate_static_mesh_slot_bindings(manifest, plan)

        self.assertEqual(report["status"], "pass")

    def test_slot_name_mismatch_warns(self):
        report = validate_static_mesh_slot_bindings(
            {"material_slots": [{"name": "M_Crate"}]},
            {"materials": [{"material_name": "M_Barrel"}]},
        )

        self.assertEqual(report["status"], "warning")
        self.assertTrue(any("无法匹配" in item["message"] for item in report["warnings"]))

    def test_missing_material_instance_plan_errors(self):
        report = validate_static_mesh_slot_bindings({"material_slots": [{"name": "M_Crate"}]}, {"materials": []})

        self.assertEqual(report["status"], "error")
        self.assertTrue(any("缺少材质实例计划" in item["message"] for item in report["errors"]))

    def test_package_acceptance_includes_slot_binding_preflight(self):
        package = create_offline_static_prop_package(self.temp_dir)
        manifest = read_manifest(package["manifest_path"])
        manifest["material_slots"] = [{"name": "M_Does_Not_Match"}]
        write_manifest(package["manifest_path"], manifest)

        report = validate_asset_forge_package(package["package_dir"])

        self.assertEqual(report["slot_binding_preflight"]["status"], "warning")
        self.assertIn("slot_binding_preflight", report["summary"]["warning_checks"])


if __name__ == "__main__":
    unittest.main()
