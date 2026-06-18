from __future__ import absolute_import

import json
import os
import tempfile
import unittest

from scripts.unreal_collect_material_evidence import collect_material_evidence


class UnrealCollectMaterialEvidenceCliTest(unittest.TestCase):
    def test_top_level_visual_review_requires_screenshot_without_visual_pass(self):
        report = self._collect(_input_report())

        self.assertEqual(report["ta_visual_review_status"], "manual_validation_required")
        self.assertEqual(report["screenshot_evidence_status"], "not_provided")
        self.assertEqual(report["comment_box_persistence_status"], "needs_on_site_review")
        self.assertTrue(report["comment_box_cold_start_readback_required"])
        self.assertTrue(report["comment_box_real_ue_screenshot_required"])
        self.assertFalse(report["ta_visual_review"]["api_readback_is_visual_pass"])
        self.assertIn("cold-start Unreal", report["ta_visual_review_next_action"])
        self.assertEqual(report["import"]["ta_visual_review_status"], "manual_validation_required")
        self.assertEqual(report["summary"]["screenshot_evidence_status"], "not_provided")
        self.assertEqual(report["summary"]["comment_box_persistence_status"], "needs_on_site_review")

    def test_top_level_screenshot_alone_does_not_clear_comment_box_persistence(self):
        report = self._collect(_input_report(with_screenshot=True))

        self.assertEqual(report["ta_visual_review_status"], "manual_validation_required")
        self.assertEqual(report["screenshot_evidence_status"], "provided")
        self.assertEqual(report["comment_box_persistence_status"], "needs_on_site_review")
        self.assertTrue(report["comment_box_cold_start_readback_required"])
        self.assertFalse(report["comment_box_real_ue_screenshot_required"])
        self.assertFalse(report["ta_visual_review"]["api_readback_is_visual_pass"])
        self.assertEqual(report["import"]["ta_visual_review"]["status"], "manual_validation_required")
        self.assertEqual(report["summary"]["ta_visual_review_status"], "manual_validation_required")

    def test_cold_start_collection_flag_marks_comment_box_persistence(self):
        report = self._collect(_input_report(), cold_start_readback=True)

        self.assertEqual(report["comment_box_persistence_status"], "needs_on_site_review")
        self.assertFalse(report["comment_box_cold_start_readback_required"])
        self.assertTrue(report["comment_box_real_ue_screenshot_required"])
        self.assertIn("capture material graph screenshot", report["ta_visual_review_next_action"])
        self.assertEqual(
            report["import"]["real_ue_material_graph"]["materials"][0]["comment_blocks"]["persistence_boundary"],
            "fresh_unreal_process_readback",
        )

    def test_top_level_visual_review_is_ready_only_after_cold_start_readback_and_screenshot(self):
        report = self._collect(_input_report(with_screenshot=True, with_cold_start=True))

        self.assertEqual(report["ta_visual_review_status"], "ready_for_visual_review")
        self.assertEqual(report["screenshot_evidence_status"], "provided")
        self.assertEqual(report["comment_box_persistence_status"], "verified")
        self.assertFalse(report["comment_box_cold_start_readback_required"])
        self.assertFalse(report["comment_box_real_ue_screenshot_required"])
        self.assertFalse(report["ta_visual_review"]["api_readback_is_visual_pass"])

    def _collect(self, report, cold_start_readback=False):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, "import_report.json")
            output_path = os.path.join(temp_dir, "material_evidence_report.json")
            with open(input_path, "w", encoding="utf-8") as handle:
                json.dump(report, handle)

            result = collect_material_evidence(input_path, output_path, cold_start_readback=cold_start_readback)

            with open(output_path, "r", encoding="utf-8") as handle:
                written = json.load(handle)
            self.assertEqual(result, written)
            return result


def _input_report(with_screenshot=False, with_cold_start=False):
    real_graph = {"status": "pass", "source": "fixture", "materials": [_real_graph_material(with_cold_start=with_cold_start)]}
    if with_screenshot:
        real_graph["screenshot_evidence"] = {"status": "pass", "path": "M_AF_Props_Master.png"}
    return {
        "status": "success",
        "can_accept": True,
        "import": {
            "status": "success",
            "material_binding_plan": _material_binding_plan(),
            "parent_material_validation": {"status": "pass", "checks": [], "missing_parent_materials": []},
            "material_asset_bootstrap_report": {"material_network_reports": [_network_report()]},
            "material_parameter_report": _parameter_report(),
            "material_assignment_report": _assignment_report(),
            "material_sampler_policy_validation": {"status": "pass", "checks": []},
            "material_compile_log_evidence": {"status": "pass", "source": "fixture"},
            "real_ue_material_graph": real_graph,
        },
    }


def _material_binding_plan():
    return {
        "master_material": "/AssetForge/Materials/M_AF_Props_Master",
        "count": 1,
        "materials": [
            {
                "material_name": "M_Crate",
                "parent_material": "/AssetForge/Materials/M_AF_Props_Master",
                "target_asset_path": "/Game/Props/Materials/MI_M_Crate",
                "texture_parameters": {
                    "BaseColor": "/Game/Props/Textures/T_Crate_BaseColor",
                    "Normal": "/Game/Props/Textures/T_Crate_Normal",
                    "ARM": "/Game/Props/Textures/T_Crate_ARM",
                },
            }
        ],
    }


def _network_report():
    return {
        "material_path": "/AssetForge/Materials/M_AF_Props_Master",
        "nodes": [
            {"parameter": "BaseColor", "node_type": "TextureSampleParameter2D", "sampler_type": "color"},
            {"parameter": "Normal", "node_type": "TextureSampleParameter2D", "sampler_type": "normal"},
            {"parameter": "ARM", "node_type": "TextureSampleParameter2D", "sampler_type": "masks"},
        ],
    }


def _parameter_report():
    return {
        "status": "success",
        "texture_parameters": [
            {
                "name": "BaseColor",
                "applied": True,
                "material_instance_path": "/Game/Props/Materials/MI_M_Crate",
                "texture_asset_path": "/Game/Props/Textures/T_Crate_BaseColor",
            },
            {
                "name": "Normal",
                "applied": True,
                "material_instance_path": "/Game/Props/Materials/MI_M_Crate",
                "texture_asset_path": "/Game/Props/Textures/T_Crate_Normal",
            },
            {
                "name": "ARM",
                "applied": True,
                "material_instance_path": "/Game/Props/Materials/MI_M_Crate",
                "texture_asset_path": "/Game/Props/Textures/T_Crate_ARM",
            },
        ],
    }


def _assignment_report():
    return {
        "status": "success",
        "assigned": [
            {
                "static_mesh": "/Game/Props/SM_Crate_01",
                "slot_index": 0,
                "material_name": "M_Crate",
                "material_instance": "/Game/Props/Materials/MI_M_Crate",
                "verification_status": "pass",
            }
        ],
        "issues": [],
    }


def _real_graph_material(with_cold_start=False):
    comment_blocks = {
        "status": "pass",
        "expected_af_comments": 7,
        "expression_comments": 7,
        "linked_graph_comments": 7,
        "orphan_graph_comments": 0,
        "duplicate_comments": 0,
    }
    if with_cold_start:
        comment_blocks["cold_start_readback_status"] = "pass"
    return {
        "material_path": "/AssetForge/Materials/M_AF_Props_Master",
        "comment_blocks": comment_blocks,
    }


if __name__ == "__main__":
    unittest.main()
