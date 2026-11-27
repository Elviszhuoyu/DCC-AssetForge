# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock, patch

from asset_forge.maya import workbench_feedback, workbench_locator
from asset_forge.maya.pipeline import MayaStaticPropPipeline
from asset_forge.maya.workbench_diagnostics import ACTIONS, GATE_RULES, RULES, describe
from asset_forge.shared.constants import ASSET_TYPE_STATIC_PROP
from asset_forge.shared.rule_validator import StaticPropRuleValidator
from asset_forge.shared.rules_schema import get_default_rules


class MayaDiagnosticContractTest(unittest.TestCase):
    def test_registered_rules_have_renderable_diagnostics_and_actions(self):
        base = get_default_rules()[ASSET_TYPE_STATIC_PROP]["checks"]
        self.assertEqual({check["id"] for check in base} | set(GATE_RULES), set(RULES))
        for rule, (_, _, _, action) in RULES.items():
            with self.subTest(rule=rule):
                self.assertIn(action, ACTIONS)
                for status in ("pass", "warning", "error", "info"):
                    row = dict(id=rule, status=status, value=7, limit=0)
                    diag = describe(row, {}, {}, "SM_A", has_components=True)
                    self.assertTrue(all(diag[key] for key in ("title", "summary", "export_impact", "fix_guidance")))
                    self.assertIn(diag["severity"], {"blocked", "warning", "pass", "needs_review"})
                    self.assertIn(diag["action_kind"], ACTIONS)
                if action == "components":
                    self.assertEqual(describe(row, {}, {})["action_kind"], "focus")

    def test_uv_name_does_not_substitute_for_second_channel_or_offer_component_location(self):
        mesh = "|SM_ViveController|shape"
        scan = dict(asset_root="|SM_ViveController", uv_sets={mesh: ["LightMapUV"]},
                    uv_coordinate_counts={mesh: [48]})
        validation = dict(can_export=True, checks=[dict(id="lightmap_uv", status="warning", value=False, limit=True,
                                                      affected_meshes=[mesh])])
        rows = workbench_locator.issue_rows(scan, validation)
        self.assertIn("当前有 1 套 UV", rows[0]["diagnostic"]["summary"])
        self.assertIn("LightMapUV", rows[0]["diagnostic"]["summary"])
        self.assertIn("Lumen", rows[0]["diagnostic"]["export_impact"])
        self.assertEqual(rows[0]["diagnostic"]["action_kind"], "uv")
        self.assertFalse(rows[0]["components"])
        feedback = workbench_feedback.check_result(validation, rows)
        self.assertEqual(feedback["badge"], "1 个警告")
        self.assertNotIn("定位", feedback["next"])

    def test_rule_severity_follows_project_override(self):
        rules = get_default_rules()
        for rule in rules[ASSET_TYPE_STATIC_PROP]["checks"]:
            if rule["id"] == "triangle_budget":
                rule["severity"] = "error"
        result = StaticPropRuleValidator(rules).validate(
            dict(asset_name="SM_A", mesh_count=1, frozen_transform=True, has_uv0=True,
                 has_lightmap_uv=True, triangles=15001))
        self.assertFalse(result["can_export"])
        self.assertEqual(next(row for row in result["checks"] if row["id"] == "triangle_budget")["status"], "error")

    def test_mixed_geometry_locates_edges_from_endpoints_and_faces_from_triangles(self):
        mesh = "|SM_C|shape"
        face = {"face_index": 309, "polygon_size": 4, "triangle_indices": [0]}
        measurements = {mesh: {"faces": [face], "zero_length_edges": [545]}}
        checks = [dict(id=rule, status="warning", value=1, limit=0, affected_meshes=[mesh], mesh_results=measurements)
                  for rule in ("zero_area_triangles", "zero_length_edges")]
        rows = {row["rule"]: row for row in workbench_locator.issue_rows({}, {"checks": checks})}
        self.assertEqual(rows["zero_area_triangles"]["faces"], [face])
        self.assertEqual(rows["zero_length_edges"]["faces"], [])
        cmds = Mock()
        cmds.listRelatives.return_value = ["|SM_C"]
        cmds.polyListComponentConversion.return_value = []
        endpoints = [mesh + ".vtx[2]", mesh + ".vtx[3]"]
        cmds.ls.return_value = endpoints
        with patch.object(workbench_locator, "_model_panel", return_value=None), \
             patch.object(workbench_locator, "_vertices", return_value=endpoints) as edges, \
             patch.object(workbench_locator, "_triangle_vertices", return_value=[mesh + ".vtx[77]"]) as triangles:
            edge_location = workbench_locator.locate(cmds, rows["zero_length_edges"])
            self.assertEqual(edges.call_args_list[0].args, (cmds, [mesh + ".e[545]"]))
            triangles.assert_not_called()
            self.assertEqual(edge_location["vertices"], endpoints)
            face_location = workbench_locator.locate(cmds, rows["zero_area_triangles"])
            triangles.assert_called_once_with(rows["zero_area_triangles"])
            self.assertEqual(face_location["vertices"], [mesh + ".vtx[77]"])

    def test_default_selection_is_the_reported_face_or_edge_with_independent_anchors(self):
        mesh = "|SM_Sample|shape"
        vertices = [mesh + ".vtx[1]", mesh + ".vtx[2]"]
        cmds = Mock()
        cmds.listRelatives.return_value = ["|SM_Sample"]
        cmds.polyListComponentConversion.return_value = []
        cmds.camera.return_value = False
        with patch.object(workbench_locator, "_model_panel", return_value="modelPanel4"), \
             patch.object(workbench_locator, "_vertices", return_value=vertices), \
             patch.object(workbench_locator, "_mark_vertices") as mark:
            for rule, token in (("zero_area_triangles", "f"), ("zero_length_edges", "e")):
                with self.subTest(rule=rule):
                    selection = [mesh + ".{0}[12]".format(token)]
                    row = dict(rule=rule, mesh=mesh, kind=token, components=[12], faces=[])
                    cmds.ls.return_value = selection
                    cmds.select.reset_mock()
                    workbench_locator.locate(cmds, row)
                    cmds.select.assert_called_once_with(selection, replace=True)
                    cmds.selectType.assert_called_with(
                        polymeshVertex=False, polymeshFace=(token == "f"), polymeshEdge=(token == "e"))
                    mark.assert_called_with(cmds, "modelPanel4", vertices)
            cmds.select.reset_mock()
            workbench_locator.locate(cmds, row, "vertices")
            cmds.select.assert_called_once_with(vertices, replace=True)
            cmds.selectType.assert_called_with(polymeshVertex=True, polymeshFace=False, polymeshEdge=False)


    def test_material_assignment_uses_original_faces_and_required_texture_is_blocking(self):
        pipeline = MayaStaticPropPipeline()
        scan = dict(material_assignment={"|SM_A|shape": {"face_indices": [2, 4]}}, asset_root="|SM_A",
                    material_profile_validation={"checks": [{"usage": "normal"}, {"usage": "base_color"}]},
                    material_texture_bindings=[dict(status="bound", material_name="M_A", texture_usages=["base_color"])])
        validation = pipeline._attach_mesh_and_texture_diagnostics(
            scan, dict(checks=[], summary={"errors": 0, "warnings": 0, "passes": 0}, can_export=True))
        self.assertFalse(validation["can_export"])
        self.assertEqual(validation["summary"]["errors"], 2)
        rows = {row["rule"]: row for row in workbench_locator.issue_rows(scan, validation)}
        self.assertEqual(rows["material_assignment"]["components"], [2, 4])
        self.assertEqual(rows["material_assignment"]["diagnostic"]["component_label"], "选中受影响面")
        self.assertIn("法线", rows["required_texture"]["diagnostic"]["summary"])

    def test_binding_warnings_are_visible_and_can_follow_strict_export_policy(self):
        pipeline = MayaStaticPropPipeline()
        scan = dict(material_texture_binding_risks=[dict(id="shared_texture_file", severity="warning",
                                                         path="T_A.png", materials=["M_A", "M_B"])])
        seed = dict(can_export=True, checks=[], summary={"errors": 0, "warnings": 0})
        permissive = pipeline._attach_material_texture_binding_gate(scan, seed)
        strict = pipeline._attach_material_texture_binding_gate(scan, dict(seed, allow_warning_export=False))
        self.assertTrue(permissive["can_export"])
        self.assertEqual(permissive["checks"][0]["status"], "warning")
        self.assertFalse(strict["can_export"])
