from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.report_artifacts import REPORT_DIR_NAME
from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.acceptance_runner import run_asset_forge_package_acceptance
from asset_forge.unreal.doctor import run_asset_forge_doctor
from asset_forge.unreal.package_acceptance import validate_asset_forge_package
from asset_forge.unreal.stage_validation_bundle import collect_stage_validation_bundle


class ReportArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.package = create_offline_static_prop_package(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_package_acceptance_writes_default_artifact_path(self):
        report = validate_asset_forge_package(self.package["package_dir"])

        self.assertIn(REPORT_DIR_NAME, report["report_path"])
        self.assertTrue(report["report_path"].endswith("/package_acceptance_report.json"))
        self.assertTrue(os.path.exists(report["report_path"]))
        self.assertIn("created_at_utc", report)
        self.assertEqual(report["report_artifact"]["file_name"], "package_acceptance_report.json")

    def test_explicit_accept_flow_report_path_is_preserved_and_normalized(self):
        explicit_path = os.path.join(self.temp_dir, "CustomReports", "accept.json")

        report = run_asset_forge_package_acceptance(self.package["package_dir"], explicit_path)

        self.assertEqual(report["report_path"], explicit_path.replace("\\", "/"))
        self.assertTrue(os.path.exists(explicit_path))

    def test_stage_bundle_and_doctor_have_stable_artifact_names(self):
        bundle = collect_stage_validation_bundle(self.package["package_dir"])
        doctor = run_asset_forge_doctor(self.temp_dir)

        self.assertTrue(bundle["report_path"].endswith("/AssetForgeReports/stage_validation_bundle.json"))
        self.assertTrue(doctor["report_path"].endswith("/AssetForgeReports/asset_forge_doctor_report.json"))


if __name__ == "__main__":
    unittest.main()
