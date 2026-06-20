from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.manifest_schema import read_manifest, write_manifest
from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.package_acceptance import validate_asset_forge_package
from asset_forge.unreal.strategy_simulator import simulate_same_name_strategies


class SameNameStrategySimulationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_reuse_skip_overwrite_are_traceable(self):
        report = simulate_same_name_strategies(
            {"target_path": "/Game/Props", "asset_name": "SM_Crate", "existing_mesh_strategy": "overwrite"},
            {"existing_texture_strategy": "skip", "textures": [{"target_asset_path": "/Game/Props/T_Crate", "existing_texture_strategy": "skip"}]},
            {"existing_material_strategy": "reuse", "materials": [{"target_asset_path": "/Game/Props/M_Crate", "existing_material_strategy": "reuse"}]},
        )

        self.assertEqual(report["status"], "pass")
        actions = dict((item["kind"], item["action"]) for item in report["actions"])
        self.assertEqual(actions["static_mesh"], "would_overwrite")
        self.assertEqual(actions["texture"], "would_skip")
        self.assertEqual(actions["material_instance"], "would_reuse")

    def test_error_strategy_blocks_package_acceptance_gate(self):
        package = create_offline_static_prop_package(self.temp_dir)
        manifest = read_manifest(package["manifest_path"])
        manifest["existing_mesh_strategy"] = "error"
        write_manifest(package["manifest_path"], manifest)

        report = validate_asset_forge_package(package["package_dir"], strict=True)

        self.assertEqual(report["same_name_strategy_simulation"]["status"], "error")
        self.assertFalse(report["gate_passed"])
        self.assertTrue(any("error 策略" in reason or "阻断" in reason for reason in report["blocking_reasons"]))


if __name__ == "__main__":
    unittest.main()
