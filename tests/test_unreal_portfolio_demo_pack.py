from __future__ import absolute_import

import os
import tempfile
import unittest

from asset_forge.unreal.portfolio_demo_pack import create_portfolio_demo_pack


class UnrealPortfolioDemoPackTest(unittest.TestCase):
    def test_default_capture_root_hint_points_to_capture_manifest_root(self):
        report = create_portfolio_demo_pack(evidence_path={"stage": "offline_evidence_bundle"})
        hint = report["portfolio_capture_root_hint"]

        self.assertEqual(hint["path"], "AssetForgeReports/portfolio_captures")
        self.assertFalse(os.path.isabs(hint["path"]))
        self.assertEqual(hint["source"], "capture_manifest_expected_evidence_root")
        self.assertIn("evidence_root", hint["reason"])
        self.assertEqual(report["status"], "warning")

    def test_recording_runbook_maps_three_minute_portfolio_story(self):
        report = create_portfolio_demo_pack(
            evidence_path={
                "stage": "offline_evidence_bundle",
                "evidence_root": "C:/Showcase/portfolio_captures",
                "field_validation_plan": [
                    {"id": "maya_screen_recording", "status": "manual_validation_required"},
                    {"id": "ue_gate_clicks", "status": "manual_validation_required"},
                ],
            }
        )

        runbook = report["recording_runbook"]
        maya_segment = _runbook_item(report, "maya_scan")
        ue_segment = _runbook_item(report, "ue_gate")

        self.assertEqual(len(runbook), 6)
        self.assertEqual([item["duration"] for item in runbook], ["0:00-0:20", "0:20-0:55", "0:55-1:25", "1:25-2:05", "2:05-2:40", "2:40-3:00"])
        self.assertEqual(runbook[0]["goal"], "先讲清楚痛点和目标")
        self.assertEqual(maya_segment["related_steps"], ["maya_scan"])
        self.assertEqual(maya_segment["step_statuses"]["maya_scan"], _step(report, "maya_scan")["status"])
        self.assertTrue(maya_segment["next_action"])
        self.assertIn("steps.maya_scan.field_validation_refs", maya_segment["evidence_fields"])
        self.assertEqual(maya_segment["capture_hint"], "C:/Showcase/portfolio_captures/02_maya_scan.mp4")
        self.assertIn("UE Gate", ue_segment["goal"])
        self.assertIn("steps.ue_gate_review.field_validation_refs", ue_segment["evidence_fields"])
        self.assertFalse(any(item.get("status") == "pass" for item in runbook))

    def test_capture_root_hint_uses_existing_evidence_root_or_report_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_root = os.path.join(temp_dir, "AssetForgeReports", "portfolio_captures")
            report = create_portfolio_demo_pack(
                evidence_path={
                    "stage": "offline_evidence_bundle",
                    "evidence_root": evidence_root,
                }
            )

            self.assertEqual(report["portfolio_capture_root_hint"]["path"], evidence_root.replace("\\", "/"))
            self.assertEqual(report["status"], "warning")

            report_path = os.path.join(temp_dir, "AssetForgeReports", "portfolio_demo_pack.json")
            report_from_path = create_portfolio_demo_pack(evidence_path={"stage": "offline_evidence_bundle"}, report_path=report_path)

            self.assertEqual(
                report_from_path["portfolio_capture_root_hint"]["path"],
                os.path.join(temp_dir, "AssetForgeReports", "portfolio_captures").replace("\\", "/"),
            )
            self.assertEqual(report_from_path["status"], "warning")

    def test_plugin_install_smoke_dry_run_is_showable_warning(self):
        report = create_portfolio_demo_pack(
            evidence_path={
                "stage": "offline_evidence_bundle",
                "stages": {
                    "clean_install_validation": {
                        "status": "warning",
                        "screenshots": {
                            "maya_main": "E:/Captures/maya_main.png",
                            "ue_gate": "E:/Captures/ue_gate.png",
                        },
                    },
                    "plugin_install_smoke": {
                        "status": "skipped",
                        "target_plugin_dir": "C:/Temp/CleanProject/Plugins/AssetForge",
                        "requires_cpp_compile": True,
                        "dry_run": True,
                        "source_hash": "a" * 64,
                        "source_hash_algorithm": "sha256",
                        "planned_copied_file_count": 116,
                        "copied_file_count": 0,
                        "can_build_after_editor_closed": True,
                        "blocked_by_running_editor": "not_checked",
                        "install_smoke": {
                            "requires_cpp_compile": True,
                            "source_hash": "a" * 64,
                            "planned_copied_file_count": 116,
                            "copied_file_count": 0,
                            "release_boundary": {
                                "status": "manual_validation_required",
                                "can_claim_clean_install": False,
                                "next_actions": ["close UE Editor, then run UBT for the target project"],
                            },
                            "build_readiness": {
                                "status": "manual_validation_required",
                                "native_editor_module": "AssetForgeEditor",
                                "target_binary": "C:/Temp/CleanProject/Plugins/AssetForge/Binaries/Win64/UnrealEditor-AssetForgeEditor.dll",
                            },
                        },
                    }
                },
            }
        )

        clean_install = _step(report, "clean_install")
        clean_install_action = _next_demo_action(report, "clean_install")

        self.assertEqual(clean_install["status"], "warning")
        self.assertTrue(any("target_plugin_dir=" in item for item in clean_install["evidence_refs"]))
        self.assertTrue(any("source_hash=" in item for item in clean_install["evidence_refs"]))
        self.assertTrue(any("can_build_after_editor_closed=True" in item for item in clean_install["evidence_refs"]))
        self.assertIn("plugin_install_smoke:dry_run=True", clean_install["evidence_refs"])
        self.assertIn("plugin_install_smoke:install_smoke.copied_file_count=0", clean_install["evidence_refs"])
        self.assertIn("plugin_install_smoke:release_boundary.can_claim_clean_install=False", clean_install["evidence_refs"])
        self.assertIn("plugin_install_smoke:build_readiness.native_editor_module=AssetForgeEditor", clean_install["evidence_refs"])
        self.assertIn("clean_install_validation:screenshot.maya_main=E:/Captures/maya_main.png", clean_install["evidence_refs"])
        self.assertIn("clean_install_validation:screenshot.ue_gate=E:/Captures/ue_gate.png", clean_install["evidence_refs"])
        self.assertEqual(clean_install_action["step_id"], "clean_install")
        self.assertEqual(clean_install_action["title"], clean_install["title"])
        self.assertEqual(clean_install_action["missing_action"], clean_install["missing_action"])
        self.assertEqual(clean_install_action["operator_checklist"], clean_install["operator_checklist"][0])
        self.assertEqual(clean_install_action["field_validation_refs"], [])

    def test_field_validation_plan_refs_are_mapped_to_story_steps(self):
        report = create_portfolio_demo_pack(
            evidence_path={
                "stage": "offline_evidence_bundle",
                "stages": {
                    "plugin_install_smoke": {
                        "status": "skipped",
                        "dry_run": True,
                        "source_hash": "b" * 64,
                        "install_smoke": {
                            "release_boundary": {
                                "status": "dry_run",
                                "can_claim_clean_install": False,
                            },
                        },
                    }
                },
                "field_validation_plan": [
                    {"id": "maya_screen_recording", "status": "manual_validation_required"},
                    {"id": "ue_gate_clicks", "status": "manual_validation_required"},
                    {"id": "material_preview_comment_box", "status": "manual_validation_required"},
                    {
                        "id": "closed_editor_ubt_clean_install_smoke",
                        "status": "blocked",
                        "release_boundary_status": "manual_validation_required",
                        "can_claim_clean_install": False,
                        "assetforge_editor_linked": True,
                        "blocked_by_plugin": "UE_MCP_Bridge",
                        "blocker_summary": "duplicate JsonSerializer.cpp source filenames",
                        "ubt_log_path": "D:/AssetForgeFixtures/UnrealBuildTool/Log.txt",
                    },
                ],
            }
        )

        maya_scan = _step(report, "maya_scan")
        ue_gate = _step(report, "ue_gate_review")
        material_result = _step(report, "material_result")
        clean_install = _step(report, "clean_install")
        actions = dict((item["step_id"], item) for item in report["next_demo_actions"])

        self.assertIn("field_validation_plan:maya_screen_recording", maya_scan["field_validation_refs"])
        self.assertIn("field_validation_plan:ue_gate_clicks", ue_gate["field_validation_refs"])
        self.assertIn("field_validation_plan:material_preview_comment_box", material_result["field_validation_refs"])
        self.assertIn("field_validation_plan:closed_editor_ubt_clean_install_smoke", clean_install["field_validation_refs"])
        self.assertIn(
            "field_validation_plan:closed_editor_ubt_clean_install_smoke.release_boundary_status=manual_validation_required",
            clean_install["field_validation_refs"],
        )
        self.assertIn(
            "field_validation_plan:closed_editor_ubt_clean_install_smoke.can_claim_clean_install=False",
            clean_install["field_validation_refs"],
        )
        self.assertIn(
            "field_validation_plan:closed_editor_ubt_clean_install_smoke.assetforge_editor_linked=True",
            clean_install["field_validation_refs"],
        )
        self.assertIn(
            "field_validation_plan:closed_editor_ubt_clean_install_smoke.blocked_by_plugin=UE_MCP_Bridge",
            clean_install["field_validation_refs"],
        )
        self.assertTrue(any("blocker_summary=duplicate JsonSerializer" in item for item in clean_install["field_validation_refs"]))
        self.assertEqual(clean_install["status"], "warning")
        self.assertIn("operator_checklist", clean_install)
        self.assertEqual(
            [item["step_id"] for item in report["next_demo_actions"]],
            ["maya_scan", "package_export", "ue_gate_review", "material_result", "clean_install"],
        )
        self.assertIn("field_validation_plan:maya_screen_recording", actions["maya_scan"]["field_validation_refs"])
        self.assertIn("field_validation_plan:ue_gate_clicks", actions["ue_gate_review"]["field_validation_refs"])
        self.assertIn("field_validation_plan:material_preview_comment_box", actions["material_result"]["field_validation_refs"])
        self.assertIn(
            "field_validation_plan:closed_editor_ubt_clean_install_smoke.can_claim_clean_install=False",
            actions["clean_install"]["field_validation_refs"],
        )
        self.assertIn(
            "field_validation_plan:closed_editor_ubt_clean_install_smoke.blocked_by_plugin=UE_MCP_Bridge",
            actions["clean_install"]["field_validation_refs"],
        )

    def test_gate_source_evidence_keeps_report_review_showable(self):
        report = create_portfolio_demo_pack(
            evidence_path={
                "stage": "offline_evidence_bundle",
                "notes": ["HandleOpenReportClicked", "打开报告"],
            }
        )

        ue_gate = _step(report, "ue_gate_review")

        self.assertEqual(ue_gate["status"], "warning")
        self.assertIn("source:HandleOpenReportClicked", ue_gate["evidence_refs"])
        self.assertIn("source:打开报告", ue_gate["evidence_refs"])

    def test_gate_stage_keeps_open_report_click_refs(self):
        report = create_portfolio_demo_pack(
            evidence_path={
                "stage": "offline_evidence_bundle",
                "stages": {
                    "ue_gate_visual_review": {
                        "status": "warning",
                        "report_path": "C:/Temp/reports/ue_gate_review.json",
                        "opened_report_path": "C:/Temp/reports/import_report.json",
                        "open_report_action": "HandleOpenReportClicked",
                    }
                },
            }
        )

        ue_gate = _step(report, "ue_gate_review")

        self.assertIn("ue_gate_visual_review:opened_report_path=C:/Temp/reports/import_report.json", ue_gate["evidence_refs"])
        self.assertIn("ue_gate_visual_review:open_report_action=HandleOpenReportClicked", ue_gate["evidence_refs"])

    def test_material_graph_evidence_refs_surface_visual_review_boundary(self):
        report = create_portfolio_demo_pack(
            evidence_path={
                "stage": "offline_evidence_bundle",
                "stages": {
                    "material_graph_evidence": {
                        "status": "warning",
                        "real_ue_evidence": "provided",
                        "ta_visual_review": {
                            "status": "manual_validation_required",
                            "screenshot_evidence": "not_provided",
                            "next_action": "capture material graph screenshot or viewport evidence for TA review",
                        },
                        "checks": [
                            {
                                "id": "material_comment_blocks",
                                "status": "pass",
                                "linked_graph_comments": 7,
                                "comment_block_summary": "expected=7, expression_comments=7, linked_graph_comments=7",
                                "visual_review_risk": "low",
                            }
                        ],
                    }
                },
            }
        )

        material_result = _step(report, "material_result")

        self.assertEqual(material_result["status"], "warning")
        self.assertIn("material_graph_evidence:real_ue_evidence=provided", material_result["evidence_refs"])
        self.assertIn("material_graph_evidence:ta_visual_review.status=manual_validation_required", material_result["evidence_refs"])
        self.assertIn("material_graph_evidence:material_comment_blocks.linked_graph_comments=7", material_result["evidence_refs"])
        self.assertTrue(material_result["missing_action"])

    def test_material_result_surfaces_comment_box_cold_start_persistence_boundary(self):
        report = create_portfolio_demo_pack(
            evidence_path={
                "stage": "offline_evidence_bundle",
                "stages": {
                    "accept_flow": {
                        "status": "pass",
                        "report_path": "C:/Temp/accept_flow_report.json",
                    }
                },
                "material_graph_evidence_report": {
                    "status": "pass",
                    "ta_visual_review": {
                        "comment_box_persistence_status": "cold_start_readback_required",
                    },
                    "checks": [
                        {
                            "id": "material_comment_blocks",
                            "status": "pass",
                            "linked_graph_comments": 7,
                        }
                    ],
                },
            }
        )

        material_result = _step(report, "material_result")
        material_segment = _runbook_item(report, "material_result")
        action = _next_demo_action(report, "material_result")

        self.assertEqual(material_result["status"], "warning")
        self.assertIn(
            "material_graph_evidence_report:ta_visual_review.comment_box_persistence_status=cold_start_readback_required",
            material_result["evidence_refs"],
        )
        self.assertIn(
            "material_result:comment_box_persistence_boundary=current_session_readback_is_not_cold_start_persistence",
            material_result["evidence_refs"],
        )
        self.assertIn("当前会话读回不等于冷启动持久化通过", material_result["missing_action"])
        self.assertIn("当前会话读回不等于冷启动持久化通过", material_result["operator_checklist"][0])
        self.assertIn("当前会话读回不等于冷启动持久化通过", material_segment["talking_points"][0])
        self.assertEqual(action["operator_checklist"], material_result["operator_checklist"][0])

    def test_nested_stage_values_do_not_spill_into_evidence_refs(self):
        report = create_portfolio_demo_pack(
            evidence_path={
                "stage": "offline_evidence_bundle",
                "stages": {
                    "accept_flow": {
                        "status": "pass",
                        "report_path": "C:/Temp/accept_flow_report.json",
                        "dry_run": {"stage": "unreal_import", "materials": [{"name": "HugeNestedPayload"}]},
                    }
                },
            }
        )

        package_export = _step(report, "package_export")

        self.assertIn("accept_flow:C:/Temp/accept_flow_report.json", package_export["evidence_refs"])
        self.assertFalse(any("HugeNestedPayload" in item for item in package_export["evidence_refs"]))
        self.assertFalse(any(item.startswith("accept_flow:dry_run={") for item in package_export["evidence_refs"]))

    def test_each_storyboard_step_has_operator_checklist(self):
        report = create_portfolio_demo_pack(evidence_path={"stage": "offline_evidence_bundle"})

        steps = dict((item["id"], item) for item in report["steps"])

        self.assertEqual(set(steps), set(["pain_point", "maya_scan", "package_export", "ue_gate_review", "material_result", "clean_install"]))
        for step in steps.values():
            self.assertIn("operator_checklist", step)
            self.assertIsInstance(step["operator_checklist"], list)
            self.assertTrue(step["operator_checklist"])
            self.assertTrue(all(isinstance(item, str) and item for item in step["operator_checklist"]))
        self.assertTrue(any("repair actions" in item for item in steps["maya_scan"]["operator_checklist"]))
        self.assertTrue(any("打开报告" in item for item in steps["ue_gate_review"]["operator_checklist"]))
        self.assertTrue(any("贴图绑定" in item for item in steps["material_result"]["operator_checklist"]))
        self.assertTrue(any("UBT" in item for item in steps["clean_install"]["operator_checklist"]))


def _step(report, step_id):
    for item in report["steps"]:
        if item["id"] == step_id:
            return item
    raise AssertionError("missing step: {0}".format(step_id))


def _next_demo_action(report, step_id):
    for item in report["next_demo_actions"]:
        if item["step_id"] == step_id:
            return item
    raise AssertionError("missing next demo action: {0}".format(step_id))


def _runbook_item(report, step_id):
    for item in report["recording_runbook"]:
        if item["id"] == step_id:
            return item
    raise AssertionError("missing runbook item: {0}".format(step_id))


if __name__ == "__main__":
    unittest.main()
