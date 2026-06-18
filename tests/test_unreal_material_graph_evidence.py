from __future__ import absolute_import

import unittest

from asset_forge.unreal.material_graph_evidence import build_material_graph_evidence_report


class MaterialGraphEvidenceTest(unittest.TestCase):
    def test_report_warns_when_comment_box_persistence_still_needs_cold_start(self):
        report = build_material_graph_evidence_report(
            material_binding_plan=_material_binding_plan(),
            parent_material_validation={"status": "pass", "checks": [], "missing_parent_materials": []},
            material_network_reports=[_network_report()],
            material_parameter_report=_parameter_report(),
            material_assignment_report=_assignment_report(),
            material_sampler_policy_validation={"status": "pass", "checks": []},
            compile_log_evidence={"status": "pass", "source": "UE Output Log"},
            real_ue_material_graph={"status": "pass", "source": "ObjectIterator", "materials": [_real_graph_material()]},
        )

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["real_ue_evidence"], "provided")
        self.assertEqual(report["ta_visual_review"]["status"], "manual_validation_required")
        self.assertFalse(report["ta_visual_review"]["api_readback_is_visual_pass"])
        self.assertEqual(report["ta_visual_review"]["comment_box_persistence_status"], "needs_on_site_review")
        self.assertTrue(report["ta_visual_review"]["cold_start_readback_required"])
        self.assertTrue(report["ta_visual_review"]["real_ue_screenshot_required"])
        self.assertIn("capture material graph screenshot or viewport evidence for TA review", report["manual_validation_required"])
        self.assertTrue(self._has_check(report, "required_texture_parameter", "pass", "BaseColor"))
        self.assertTrue(self._has_check(report, "sampler_type_expected", "pass", "Normal"))
        self.assertTrue(self._has_check(report, "mi_texture_override_applied", "pass", "ARM"))
        self.assertTrue(self._has_check(report, "material_comment_blocks", "pass"))
        self.assertTrue(self._has_check(report, "material_comment_box_persistence", "warning"))

    def test_screenshot_evidence_alone_does_not_prove_comment_box_persistence(self):
        graph = {"status": "pass", "materials": [_real_graph_material()], "screenshot_evidence": {"status": "pass", "path": "M_AF_Props_Master.png"}}

        report = build_material_graph_evidence_report(
            material_binding_plan=_material_binding_plan(),
            parent_material_validation={"status": "pass", "checks": [], "missing_parent_materials": []},
            material_network_reports=[_network_report()],
            material_parameter_report=_parameter_report(),
            material_assignment_report=_assignment_report(),
            material_sampler_policy_validation={"status": "pass", "checks": []},
            compile_log_evidence={"status": "pass", "source": "UE Output Log"},
            real_ue_material_graph=graph,
        )

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["ta_visual_review"]["status"], "manual_validation_required")
        self.assertEqual(report["ta_visual_review"]["screenshot_evidence"], "provided")
        self.assertEqual(report["ta_visual_review"]["comment_box_persistence_status"], "needs_on_site_review")
        self.assertTrue(report["ta_visual_review"]["cold_start_readback_required"])
        self.assertFalse(report["ta_visual_review"]["real_ue_screenshot_required"])
        self.assertFalse(report["ta_visual_review"]["api_readback_is_visual_pass"])

    def test_cold_start_readback_without_screenshot_asks_for_visual_evidence(self):
        graph = {"status": "pass", "materials": [_real_graph_material({"cold_start_readback_status": "pass"})]}

        report = build_material_graph_evidence_report(
            material_binding_plan=_material_binding_plan(),
            parent_material_validation={"status": "pass", "checks": [], "missing_parent_materials": []},
            material_network_reports=[_network_report()],
            material_parameter_report=_parameter_report(),
            material_assignment_report=_assignment_report(),
            material_sampler_policy_validation={"status": "pass", "checks": []},
            compile_log_evidence={"status": "pass", "source": "UE Output Log"},
            real_ue_material_graph=graph,
        )

        check = self._find_check(report, "material_comment_box_persistence", "warning")
        self.assertIn("cold-start readback", check["message"])
        self.assertFalse(check["cold_start_readback_required"])
        self.assertTrue(check["real_ue_screenshot_required"])

    def test_cold_start_readback_and_screenshot_make_graph_ready_for_visual_review_not_visual_pass(self):
        graph = {
            "status": "pass",
            "materials": [_real_graph_material({"cold_start_readback_status": "pass"})],
            "screenshot_evidence": {"status": "pass", "path": "M_AF_Props_Master.png"},
        }

        report = build_material_graph_evidence_report(
            material_binding_plan=_material_binding_plan(),
            parent_material_validation={"status": "pass", "checks": [], "missing_parent_materials": []},
            material_network_reports=[_network_report()],
            material_parameter_report=_parameter_report(),
            material_assignment_report=_assignment_report(),
            material_sampler_policy_validation={"status": "pass", "checks": []},
            compile_log_evidence={"status": "pass", "source": "UE Output Log"},
            real_ue_material_graph=graph,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["ta_visual_review"]["status"], "ready_for_visual_review")
        self.assertEqual(report["ta_visual_review"]["comment_box_persistence_status"], "verified")
        self.assertFalse(report["ta_visual_review"]["cold_start_readback_required"])
        self.assertFalse(report["ta_visual_review"]["real_ue_screenshot_required"])
        self.assertFalse(report["ta_visual_review"]["api_readback_is_visual_pass"])

    def test_offline_report_keeps_real_ue_fields_manual(self):
        report = build_material_graph_evidence_report(
            material_binding_plan=_material_binding_plan(),
            parent_material_validation={"status": "pass", "checks": [], "missing_parent_materials": []},
            material_network_reports=[_network_report()],
            material_sampler_policy_validation={"status": "pass", "checks": []},
        )

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["real_ue_evidence"], "not_provided")
        self.assertIn("capture real UE material compile log after import", report["manual_validation_required"])
        self.assertIn("run UE import and capture material_parameter_report", report["manual_validation_required"])
        self.assertTrue(self._has_check(report, "compile_log_evidence", "warning"))

    def test_missing_parent_is_error(self):
        report = build_material_graph_evidence_report(
            material_binding_plan=_material_binding_plan(),
            parent_material_validation={
                "status": "error",
                "checks": [{"status": "error", "parent_material": "/AssetForge/Materials/M_AF_Props_Master"}],
                "missing_parent_materials": ["/AssetForge/Materials/M_AF_Props_Master"],
            },
            material_network_reports=[_network_report()],
            material_sampler_policy_validation={"status": "pass", "checks": []},
        )

        self.assertEqual(report["status"], "error")
        self.assertTrue(self._has_check(report, "parent_material_exists", "error"))

    def test_missing_required_parameter_is_error(self):
        network = _network_report()
        network["nodes"] = [item for item in network["nodes"] if item["parameter"] != "ARM"]

        report = build_material_graph_evidence_report(
            material_binding_plan=_material_binding_plan(),
            parent_material_validation={"status": "pass", "checks": [], "missing_parent_materials": []},
            material_network_reports=[network],
            material_sampler_policy_validation={"status": "pass", "checks": []},
        )

        self.assertEqual(report["status"], "error")
        self.assertTrue(self._has_check(report, "required_texture_parameter", "error", "ARM"))

    def test_wrong_mi_texture_asset_path_is_error(self):
        parameter_report = _parameter_report()
        parameter_report["texture_parameters"][1]["texture_asset_path"] = "/Game/Props/Textures/T_Wrong_Normal"

        report = build_material_graph_evidence_report(
            material_binding_plan=_material_binding_plan(),
            parent_material_validation={"status": "pass", "checks": [], "missing_parent_materials": []},
            material_network_reports=[_network_report()],
            material_parameter_report=parameter_report,
            material_assignment_report=_assignment_report(),
            material_sampler_policy_validation={"status": "pass", "checks": []},
            compile_log_evidence={"status": "pass"},
            real_ue_material_graph={"status": "pass"},
        )

        self.assertEqual(report["status"], "error")
        self.assertTrue(self._has_check(report, "mi_texture_override_asset_path", "error", "Normal"))

    def test_wrong_slot_material_instance_is_error(self):
        assignment_report = _assignment_report()
        assignment_report["assigned"][0]["material_instance"] = "/Game/Props/Materials/MI_Wrong"

        report = build_material_graph_evidence_report(
            material_binding_plan=_material_binding_plan(),
            parent_material_validation={"status": "pass", "checks": [], "missing_parent_materials": []},
            material_network_reports=[_network_report()],
            material_parameter_report=_parameter_report(),
            material_assignment_report=assignment_report,
            material_sampler_policy_validation={"status": "pass", "checks": []},
            compile_log_evidence={"status": "pass"},
            real_ue_material_graph={"status": "pass"},
        )

        self.assertEqual(report["status"], "error")
        self.assertTrue(self._has_check(report, "slot_binding_material_instance", "error"))

    def test_expression_comments_without_graph_links_are_warning(self):
        report = build_material_graph_evidence_report(
            material_binding_plan=_material_binding_plan(),
            parent_material_validation={"status": "pass", "checks": [], "missing_parent_materials": []},
            material_network_reports=[_network_report()],
            material_parameter_report=_parameter_report(),
            material_assignment_report=_assignment_report(),
            material_sampler_policy_validation={"status": "pass", "checks": []},
            compile_log_evidence={"status": "pass"},
            real_ue_material_graph={
                "status": "pass",
                "materials": [
                    _real_graph_material(
                        {
                            "status": "warning",
                            "expected_af_comments": 7,
                            "expression_comments": 7,
                            "linked_graph_comments": 0,
                            "orphan_graph_comments": 0,
                            "duplicate_comments": 0,
                        }
                    )
                ],
            },
        )

        self.assertEqual(report["status"], "warning")
        self.assertTrue(self._has_check(report, "material_comment_blocks", "warning"))
        check = self._find_check(report, "material_comment_blocks", "warning")
        self.assertEqual(check["visual_review_risk"], "high")
        self.assertIn("none are linked", check["message"])
        self.assertIn("linked_graph_comments=0", check["comment_block_summary"])
        self.assertEqual(report["ta_visual_review"]["decision_label"], "材质图可读性需要人工复核")
        self.assertIn("capture material graph screenshot or viewport evidence for TA review", report["manual_validation_required"])

    def test_zero_size_graph_comment_nodes_are_blocking_even_when_linked(self):
        report = build_material_graph_evidence_report(
            material_binding_plan=_material_binding_plan(),
            parent_material_validation={"status": "pass", "checks": [], "missing_parent_materials": []},
            material_network_reports=[_network_report()],
            material_parameter_report=_parameter_report(),
            material_assignment_report=_assignment_report(),
            material_sampler_policy_validation={"status": "pass", "checks": []},
            compile_log_evidence={"status": "pass"},
            real_ue_material_graph={
                "status": "pass",
                "materials": [
                    _real_graph_material(
                        {
                            "status": "error",
                            "expected_af_comments": 7,
                            "expression_comments": 7,
                            "linked_graph_comments": 7,
                            "graph_comment_dimension_rows": 7,
                            "visible_graph_comments_with_size": 0,
                            "invalid_graph_comment_dimensions": 7,
                            "orphan_graph_comments": 0,
                            "duplicate_comments": 0,
                        }
                    )
                ],
            },
        )

        self.assertEqual(report["status"], "error")
        check = self._find_check(report, "material_comment_blocks", "error")
        self.assertIsNotNone(check)
        self.assertEqual(check["invalid_graph_comment_dimensions"], 7)
        self.assertEqual(check["visible_graph_comments_with_size"], 0)
        self.assertIn("zero-size bounds", check["message"])
        self.assertEqual(report["ta_visual_review"]["status"], "blocked")

    def test_comment_block_readback_error_is_blocking(self):
        report = build_material_graph_evidence_report(
            material_binding_plan=_material_binding_plan(),
            parent_material_validation={"status": "pass", "checks": [], "missing_parent_materials": []},
            material_network_reports=[_network_report()],
            material_parameter_report=_parameter_report(),
            material_assignment_report=_assignment_report(),
            material_sampler_policy_validation={"status": "pass", "checks": []},
            compile_log_evidence={"status": "pass"},
            real_ue_material_graph={
                "status": "pass",
                "materials": [
                    _real_graph_material(
                        {
                            "status": "error",
                            "message": "C++ comment block readback failed",
                            "raw": "trace",
                        }
                    )
                ],
            },
        )

        self.assertEqual(report["status"], "error")
        self.assertTrue(self._has_check(report, "material_comment_blocks", "error"))

    def _has_check(self, report, check_id, status, parameter=None):
        return self._find_check(report, check_id, status, parameter) is not None

    def _find_check(self, report, check_id, status, parameter=None):
        for item in report.get("checks", []):
            if item.get("id") != check_id or item.get("status") != status:
                continue
            if parameter is None or item.get("parameter") == parameter:
                return item
        return None


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


def _real_graph_material(comment_blocks=None):
    base_comment_blocks = {
        "status": "pass",
        "expected_af_comments": 7,
        "expression_comments": 7,
        "linked_graph_comments": 7,
        "orphan_graph_comments": 0,
        "duplicate_comments": 0,
    }
    if comment_blocks:
        base_comment_blocks.update(comment_blocks)
    return {
        "material_path": "/AssetForge/Materials/M_AF_Props_Master",
        "comment_blocks": base_comment_blocks,
    }


if __name__ == "__main__":
    unittest.main()
