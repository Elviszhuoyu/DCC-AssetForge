from __future__ import absolute_import

import unittest

from asset_forge.unreal.capability_matrix import create_capability_matrix
from asset_forge.unreal.north_star_readiness import create_north_star_readiness
from asset_forge.unreal.portfolio_readiness import create_portfolio_readiness


MOJIBAKE_MARKERS = (
    u"\ufffd",
    chr(0x00C3),
    chr(0x00C2),
    chr(0x00E6),
    chr(0x00E7),
    chr(0x00E8),
    chr(0x00E5),
    chr(0x935A),
    chr(0x93C3),
    chr(0x6D93),
    chr(0x93B4),
)


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            for text in _walk_strings(item):
                yield text
    elif isinstance(value, list):
        for item in value:
            for text in _walk_strings(item):
                yield text


def _assert_no_mojibake(testcase, report):
    for text in _walk_strings(report):
        for marker in MOJIBAKE_MARKERS:
            testcase.assertNotIn(marker, text)


class PortfolioReadinessTest(unittest.TestCase):
    def test_default_report_is_product_facing_and_not_full_score(self):
        capability = create_capability_matrix()
        north_star = create_north_star_readiness(capability_matrix=capability)

        report = create_portfolio_readiness(north_star, capability)

        _assert_no_mojibake(self, report)
        self.assertEqual(report["stage"], "portfolio_readiness")
        self.assertLess(report["score"], 100)
        self.assertIn(report["quality_level"], ["functional_vertical_slice", "internal_alpha", "strong_portfolio_wip"])
        self.assertTrue(report["remaining_top_priorities"])
        self.assertTrue(any(item["id"] == "ue_gate_review_mode" for item in report["recommended_next_features"]))

    def test_structured_real_ue_evidence_raises_validation_dimension(self):
        capability = create_capability_matrix()
        north_star = create_north_star_readiness(
            {
                "tas_102_real_ue_evidence": {
                    "is_tas_102_completion_evidence": True,
                    "status": "pass",
                    "gate_passed": True,
                    "can_accept": True,
                    "post_import_validation": {"status": "pass"},
                }
            },
            capability,
        )

        report = create_portfolio_readiness(north_star, capability)
        dimensions = dict((item["id"], item) for item in report["dimensions"])

        self.assertGreaterEqual(dimensions["validation_evidence"]["score"], 90)

    def test_field_validation_gaps_cap_grade_and_stay_readable(self):
        capability = create_capability_matrix()
        north_star = create_north_star_readiness(capability_matrix=capability)
        evidence = {
            "stage": "offline_evidence_bundle",
            "stages": {
                "maya_ui_flow": {"status": "manual_validation_required"},
                "ue_gate_visual_review": {"status": "manual_validation_required"},
                "material_graph_evidence": {"status": "manual_validation_required"},
                "clean_install_validation": {"status": "manual_validation_required"},
            },
            "field_validation_plan": [
                {"id": "maya_screen_recording", "status": "manual_validation_required"},
                {"id": "ue_gate_clicks", "status": "manual_validation_required"},
                {"id": "material_preview_comment_box", "status": "manual_validation_required"},
                {"id": "closed_editor_ubt_clean_install_smoke", "status": "manual_validation_required"},
            ],
        }

        report = create_portfolio_readiness(north_star, capability, evidence)
        dimensions = dict((item["id"], item) for item in report["dimensions"])
        missing = dict((item["id"], item) for item in report["portfolio_missing_evidence"])

        _assert_no_mojibake(self, report)
        self.assertLess(report["score"], 80)
        self.assertEqual(report["quality_level"], "functional_vertical_slice")
        self.assertLess(dimensions["release_hygiene"]["score"], 90)
        self.assertEqual(len(missing), 4)
        self.assertIn("录制真实 Maya UI", missing["maya_screen_recording"]["next_action"])
        self.assertIn("field_validation_plan", report["risks"][-1])
        self.assertIn(report["next_action"], report["remaining_top_priorities"])

        action_center = report["portfolio_action_center"]
        action_by_id = dict((item["id"], item) for item in action_center)

        self.assertGreaterEqual(len(action_center), 2)
        self.assertLessEqual(len(action_center), 4)
        self.assertIn("score_cap", action_by_id)
        self.assertIn("field_evidence", action_by_id)
        self.assertIn("release_boundary", action_by_id)
        self.assertIn("封顶", action_by_id["score_cap"]["title"])
        self.assertIn("79", action_by_id["score_cap"]["reason"])
        self.assertIn("录制真实 Maya UI", action_by_id["score_cap"]["next_action"])
        self.assertIn("离线报告", action_by_id["field_evidence"]["reason"])
        self.assertIn("UBT", action_by_id["release_boundary"]["next_action"])

        review_sheet = report["portfolio_review_sheet"]
        self.assertIn("{0}/100".format(report["score"]), review_sheet["summary_line"])
        self.assertIn("functional_vertical_slice", review_sheet["summary_line"])
        self.assertIn("未接入截图/录屏清单", review_sheet["capture_line"])
        self.assertLessEqual(len(review_sheet["first_actions"]), 3)
        self.assertIn("录制真实 Maya UI", review_sheet["first_actions"][0])
        self.assertIn("真实 Maya/UE 截图", review_sheet["proof_boundary"])
        self.assertIn("关闭 Editor 后 UBT", review_sheet["proof_boundary"])

    def test_capture_summary_gaps_feed_missing_evidence(self):
        capability = create_capability_matrix()
        north_star = create_north_star_readiness(capability_matrix=capability)

        report = create_portfolio_readiness(
            north_star,
            capability,
            {
                "portfolio_evidence_manifest": {
                    "stage": "portfolio_evidence_manifest",
                    "capture_summary": {
                        "total_capture_count": 5,
                        "captured_capture_count": 1,
                        "missing_capture_count": 4,
                        "next_capture": "maya_scan_capture",
                    },
                }
            },
        )

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["quality_level"], "functional_vertical_slice")
        self.assertEqual(report["portfolio_capture_progress"]["total"], 5)
        self.assertEqual(report["portfolio_capture_progress"]["captured"], 1)
        self.assertEqual(report["portfolio_capture_progress"]["missing"], 4)
        self.assertEqual(report["portfolio_missing_evidence"][0]["source"], "portfolio_evidence_manifest")
        self.assertIn("截图/录屏清单", report["portfolio_missing_evidence"][0]["next_action"])
        action_by_id = dict((item["id"], item) for item in report["portfolio_action_center"])
        self.assertIn("capture_manifest", action_by_id)
        self.assertIn("maya_scan_capture", action_by_id["capture_manifest"]["next_action"])
        self.assertIn("截图/录屏清单", action_by_id["capture_manifest"]["next_action"])

        review_sheet = report["portfolio_review_sheet"]
        self.assertIn("已捕获 1/5", review_sheet["capture_line"])
        self.assertIn("缺 4", review_sheet["capture_line"])
        self.assertIn("maya_scan_capture", review_sheet["capture_line"])
        self.assertTrue(review_sheet["first_actions"])

    def test_material_comment_persistence_gap_gets_action_card_without_claiming_pass(self):
        capability = create_capability_matrix()
        north_star = create_north_star_readiness(capability_matrix=capability)

        report = create_portfolio_readiness(
            north_star,
            capability,
            {
                "material_graph_evidence": {
                    "stage": "material_graph_evidence",
                    "status": "warning",
                    "ta_visual_review": {
                        "comment_box_persistence_status": "needs_on_site_review",
                        "cold_start_readback_required": True,
                        "real_ue_screenshot_required": True,
                    },
                }
            },
        )

        action_by_id = dict((item["id"], item) for item in report["portfolio_action_center"])

        self.assertIn("material_comment_persistence", action_by_id)
        self.assertEqual(action_by_id["material_comment_persistence"]["status"], "manual_validation_required")
        self.assertIn("Comment Box", action_by_id["material_comment_persistence"]["reason"])
        self.assertIn("冷启动读回", action_by_id["material_comment_persistence"]["next_action"])
        self.assertIn("真实 UE 材质图截图", action_by_id["material_comment_persistence"]["next_action"])

    def test_dcc_support_roadmap_gets_boundary_card_without_raising_grade(self):
        capability = create_capability_matrix()
        north_star = create_north_star_readiness(capability_matrix=capability)

        report = create_portfolio_readiness(
            north_star,
            capability,
            {
                "dcc_support_summary": {
                    "implemented": ["Maya"],
                    "roadmap": ["Blender", "3ds Max"],
                }
            },
        )

        action_by_id = dict((item["id"], item) for item in report["portfolio_action_center"])

        self.assertIn("dcc_support_contract", action_by_id)
        self.assertEqual(action_by_id["dcc_support_contract"]["status"], "roadmap_contract")
        self.assertIn("Maya", action_by_id["dcc_support_contract"]["reason"])
        self.assertIn("Blender / 3ds Max", action_by_id["dcc_support_contract"]["reason"])
        self.assertIn("不要包装成已完成导出器", action_by_id["dcc_support_contract"]["next_action"])
        self.assertNotEqual(report["quality_level"], "portfolio_ready")


if __name__ == "__main__":
    unittest.main()
