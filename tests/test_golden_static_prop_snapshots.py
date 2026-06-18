from __future__ import absolute_import

import shutil
import tempfile
import unittest

from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.acceptance_runner import run_asset_forge_package_acceptance
from asset_forge.unreal.package_acceptance import validate_asset_forge_package
from asset_forge.unreal.stage_validation_bundle import collect_stage_validation_bundle


class GoldenStaticPropSnapshotsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.package = create_offline_static_prop_package(self.temp_dir, "SM_AF_Golden_Crate")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_golden_package_acceptance_snapshot_key_fields(self):
        report = validate_asset_forge_package(self.package["package_dir"])

        self.assertEqual(report["stage"], "package_acceptance")
        self.assertEqual(report["asset_name"], "SM_AF_Golden_Crate")
        self.assertEqual(report["manifest_lint"]["status"], "pass")
        self.assertIn("material_profile_contract_validation", report)
        self.assertIn("report_path", report)

    def test_golden_accept_flow_snapshot_key_fields(self):
        report = run_asset_forge_package_acceptance(self.package["package_dir"])

        self.assertEqual(report["stage"], "package_acceptance_flow")
        self.assertEqual(report["package_acceptance"]["asset_name"], "SM_AF_Golden_Crate")
        self.assertEqual(report["dry_run"]["status"], "skipped")
        self.assertFalse(report["run_import"])

    def test_golden_stage_bundle_snapshot_key_fields(self):
        report = collect_stage_validation_bundle(self.package["package_dir"], command_args=["--stage-bundle"])

        self.assertEqual(report["stage"], "stage_validation_bundle")
        self.assertIn("north_star_readiness", report["stages"])
        self.assertEqual(report["tas_102_real_ue_evidence"], "not_provided")


if __name__ == "__main__":
    unittest.main()
