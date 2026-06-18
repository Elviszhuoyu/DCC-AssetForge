from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.capability_matrix import create_capability_matrix
from asset_forge.unreal.north_star_readiness import create_north_star_readiness
from asset_forge.unreal.stage_validation_bundle import _field_validation_plan, collect_offline_evidence_bundle, collect_stage_validation_bundle
from asset_forge.unreal.ue_validation_checklist import create_ue_validation_checklist


class StageValidationBundleTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.package = create_offline_static_prop_package(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_collects_normal_package_stage_bundle_without_real_ue_claim(self):
        report = collect_stage_validation_bundle(self.package["package_dir"], command_args=["--stage-bundle"])

        self.assertEqual(report["stage"], "stage_validation_bundle")
        self.assertEqual(report["tas_102_real_ue_evidence"], "not_provided")
        self.assertIn("doctor", report["stages"])
        self.assertIn("contract_check", report["stages"])
        self.assertIn("dry_run", report["stages"])
        self.assertIn("plugin_install_smoke", report["stages"])
        self.assertIn("report_schema_validation", report["stages"])
        self.assertIn("capability_matrix", report["stages"])
        self.assertIn("report_paths", report)
        self.assertIn("dry_run", report["report_paths"])
        self.assertIn("plugin_install_smoke", report["report_paths"])
        self.assertEqual(report["stages"]["plugin_install_smoke"]["stage"], "plugin_install_smoke")
        self.assertIn("release_boundary", report["stages"]["plugin_install_smoke"])
        plan = dict((item["id"], item) for item in report["field_validation_plan"])
        self.assertEqual(plan["maya_screen_recording"]["status"], "manual_validation_required")
        self.assertEqual(plan["ue_gate_clicks"]["status"], "manual_validation_required")
        self.assertEqual(plan["material_preview_comment_box"]["status"], "manual_validation_required")
        self.assertEqual(plan["closed_editor_ubt_clean_install_smoke"]["status"], "manual_validation_required")
        self.assertEqual(plan["closed_editor_ubt_clean_install_smoke"]["release_boundary_status"], "dry_run")
        self.assertFalse(plan["closed_editor_ubt_clean_install_smoke"]["can_claim_clean_install"])
        self.assertEqual(report["stages"]["ue_validation_checklist"]["is_tas_102_completion_evidence"], False)
        self.assertIn("report_schema_validation", report)

    def test_collects_bad_package_bundle_with_stage_warnings(self):
        os.remove(self.package["fbx_path"])

        report = collect_stage_validation_bundle(self.package["package_dir"])

        self.assertEqual(report["stage"], "stage_validation_bundle")
        self.assertTrue(report["warnings"] or report["errors"])
        self.assertIn("package_acceptance", report["stage_summaries"])

    def test_bundle_records_missing_batch_stage(self):
        report = collect_stage_validation_bundle(self.package["package_dir"], include_batch=False)

        self.assertEqual(report["stages"]["batch_flow"]["status"], "missing")
        self.assertIn("未请求批量 flow", report["stages"]["batch_flow"]["next_action"])

    def test_offline_evidence_bundle_generates_reports_and_readiness(self):
        report_path = os.path.join(self.temp_dir, "offline_evidence_bundle_report.json")

        report = collect_offline_evidence_bundle(self.temp_dir, report_path, ["--offline-evidence-bundle"])
        readiness = report["stages"]["north_star_readiness"]
        readiness_items = dict((item["id"], item) for item in readiness["items"])

        self.assertEqual(report["stage"], "offline_evidence_bundle")
        self.assertTrue(os.path.exists(report_path))
        self.assertTrue(report["can_accept"])
        self.assertIn("sample_package", report)
        self.assertIn("contract_check", report["stages"])
        self.assertIn("dry_run", report["stages"])
        self.assertIn("accept_flow", report["stages"])
        self.assertIn("plugin_install_smoke", report["stages"])
        release_boundary = report["stages"]["plugin_install_smoke"]["release_boundary"]
        self.assertEqual(release_boundary["status"], "dry_run")
        self.assertFalse(release_boundary["can_claim_clean_install"])
        self.assertIn("run installer without --dry-run", " ".join(release_boundary["next_actions"]))
        plan = dict((item["id"], item) for item in report["field_validation_plan"])
        self.assertEqual(plan["closed_editor_ubt_clean_install_smoke"]["release_boundary_status"], "dry_run")
        self.assertIn("UBT", plan["closed_editor_ubt_clean_install_smoke"]["next_action"])
        self.assertIn("report_schema_validation", report["stages"])
        self.assertGreaterEqual(readiness["score"], 70)
        self.assertEqual(readiness_items["real_ue_validation"]["status"], "manual_validation_required")
        self.assertTrue(readiness_items["real_ue_validation"]["missing_evidence"])
        self.assertIn("manual_validation_required", report)

    def test_field_validation_plan_keeps_blocked_clean_install_context(self):
        plan = dict(
            (item["id"], item)
            for item in _field_validation_plan(
                {
                    "stages": {
                        "plugin_install_smoke": {
                            "release_boundary": {"status": "manual_validation_required", "can_claim_clean_install": False}
                        },
                        "clean_install_validation": {
                            "status": "blocked",
                            "assetforge_editor_linked": True,
                            "blocked_by_plugin": "UE_MCP_Bridge",
                            "blocker_summary": "duplicate JsonSerializer.cpp source filenames",
                            "ubt_log_path": "<USER_HOME>/AppData/Local/UnrealBuildTool/Log.txt",
                            "next_action": "Fix or disable UE_MCP_Bridge, then rerun closed-editor UBT.",
                        },
                    }
                }
            )
        )

        clean = plan["closed_editor_ubt_clean_install_smoke"]
        self.assertEqual(clean["status"], "blocked")
        self.assertEqual(clean["source_stages"], ["plugin_install_smoke", "clean_install_validation"])
        self.assertEqual(clean["release_boundary_status"], "manual_validation_required")
        self.assertFalse(clean["can_claim_clean_install"])
        self.assertTrue(clean["assetforge_editor_linked"])
        self.assertEqual(clean["blocked_by_plugin"], "UE_MCP_Bridge")
        self.assertIn("JsonSerializer", clean["blocker_summary"])
        self.assertIn("rerun closed-editor UBT", clean["next_action"])

    def test_readiness_uses_offline_evidence_but_keeps_real_ue_manual(self):
        empty = create_north_star_readiness()
        bundle = collect_offline_evidence_bundle(self.temp_dir)
        readiness = create_north_star_readiness(bundle, bundle["stages"]["capability_matrix"])
        items = dict((item["id"], item) for item in readiness["items"])

        self.assertGreater(readiness["score"], empty["score"])
        self.assertEqual(items["package_protocol"]["status"], "pass")
        self.assertEqual(items["reporting"]["status"], "pass")
        self.assertEqual(items["real_ue_validation"]["status"], "manual_validation_required")

    def test_capability_matrix_marks_real_ue_manual_required(self):
        report = create_capability_matrix()
        items = dict((item["id"], item) for item in report["items"])

        self.assertEqual(items["real_ue_plugin_content"]["status"], "manual_validation_required")
        self.assertEqual(items["import"]["status"], "blocked")
        self.assertTrue(items["real_ue_plugin_content"]["missing_evidence"])

    def test_ue_validation_checklist_is_not_tas_102_completion_evidence(self):
        report = create_ue_validation_checklist(self.package["package_dir"])

        self.assertEqual(report["stage"], "ue_validation_checklist")
        self.assertFalse(report["is_tas_102_completion_evidence"])
        self.assertTrue(all("command" in item for item in report["items"]))
        self.assertIn("不是 TAS-102 完成证据", report["disclaimer"])


if __name__ == "__main__":
    unittest.main()
