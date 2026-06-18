from __future__ import absolute_import

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package


class AcceptanceCliMatrixTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.package = create_offline_static_prop_package(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_stage_acceptance_commands_emit_json_successfully(self):
        commands = [
            ["--validate-package", self.package["package_dir"]],
            ["--validate-all-packages", self.temp_dir],
            ["--accept-flow", self.package["package_dir"]],
            ["--accept-flow-all", self.temp_dir],
            ["--stage-bundle", self.package["package_dir"]],
            ["--contract-check", self.package["package_dir"]],
            ["--offline-evidence-bundle", self.temp_dir],
            ["--capability-matrix"],
            ["--ue-checklist", self.package["package_dir"]],
            ["--north-star-readiness"],
            ["--portfolio-readiness"],
            ["--pretest-check"],
            ["--package", "--dry-run", self.package["package_dir"]],
        ]

        for args in commands:
            result = self._run(args)
            self.assertEqual(result.returncode, 0, args)
            report = json.loads(result.stdout)
            self.assertIn("stage", report)

    def test_offline_evidence_bundle_feeds_north_star_readiness(self):
        bundle_path = os.path.join(self.temp_dir, "offline_evidence_bundle_report.json")
        bundle_result = self._run(["--offline-evidence-bundle", self.temp_dir, bundle_path])

        self.assertEqual(bundle_result.returncode, 0)
        self.assertTrue(os.path.exists(bundle_path))

        readiness_result = self._run(["--north-star-readiness", bundle_path])
        self.assertEqual(readiness_result.returncode, 0)
        readiness = json.loads(readiness_result.stdout)
        items = dict((item["id"], item) for item in readiness["items"])

        self.assertEqual(readiness["stage"], "north_star_readiness")
        self.assertGreaterEqual(readiness["score"], 70)
        self.assertEqual(items["real_ue_validation"]["status"], "manual_validation_required")

        portfolio_result = self._run(["--portfolio-readiness", bundle_path])
        self.assertEqual(portfolio_result.returncode, 0)
        self.assertIn('"portfolio_action_center"', portfolio_result.stdout)
        self.assertIn("录制真实 Maya UI", portfolio_result.stdout)
        portfolio = json.loads(portfolio_result.stdout)
        action_by_id = dict((item["id"], item) for item in portfolio["portfolio_action_center"])

        self.assertEqual(portfolio["stage"], "portfolio_readiness")
        self.assertIn("quality_level", portfolio)
        self.assertEqual(portfolio["quality_level"], "functional_vertical_slice")
        self.assertLess(portfolio["score"], 80)
        self.assertNotEqual(portfolio["quality_level"], "portfolio_ready")
        self.assertIn("score_cap", action_by_id)
        self.assertIn("field_evidence", action_by_id)
        self.assertIn("录制真实 Maya UI", action_by_id["score_cap"]["next_action"])
        self.assertEqual(action_by_id["field_evidence"]["status"], "manual_validation_required")
        self.assertTrue(portfolio["remaining_top_priorities"])

    def test_capability_matrix_marks_roadmap_dcc_targets_as_contract_only(self):
        result = self._run(["--capability-matrix"])

        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        items = dict((item["id"], item) for item in report["items"])
        dcc = items["dcc_compatibility_contract"]

        self.assertEqual(dcc["status"], "manual_validation_required")
        self.assertIn("Maya is the MVP real export path.", dcc["evidence"])
        self.assertIn("Blender and 3ds Max are roadmap/contract-only DCC targets.", dcc["evidence"])
        self.assertIn("No Blender/3ds Max real-chain validation is claimed in MVP.", dcc["missing_evidence"])

    def test_strict_accept_flow_returns_non_zero_and_json_on_gate_fail(self):
        result = self._run(["--accept-flow", "--strict", self.package["package_dir"]])

        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["stage"], "package_acceptance_flow")
        self.assertFalse(report["gate_passed"])
        self.assertTrue(report["blocking_reasons"])

    def test_doctor_command_emits_json_report(self):
        result = self._run(["--doctor"])

        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["stage"], "asset_forge_doctor")
        self.assertIn("summary", report)
        self.assertIn("gate_passed", report)
        self.assertIn("pre_validation_summary", report)
        self.assertIn("needs_real_unreal", report["pre_validation_summary"])
        check_ids = [item["id"] for item in report["checks"]]
        self.assertIn("writable_directory", check_ids)
        self.assertIn("encoding_mojibake", check_ids)
        self.assertIn("latest_unreal_log", check_ids)

    def test_pretest_check_alias_emits_doctor_report(self):
        result = self._run(["--pretest-check"])

        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["stage"], "asset_forge_doctor")
        self.assertIn("pretest_summary", report)
        self.assertIn("manual_validation_required", report)

    def _run(self, args):
        env = os.environ.copy()
        env["ASSET_FORGE_LOG_ROOT"] = self.temp_dir
        return subprocess.run(
            [sys.executable, "scripts/unreal_import_manifest.py"] + args,
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )


if __name__ == "__main__":
    unittest.main()
