from __future__ import absolute_import

import unittest

from asset_forge.unreal.material_evidence_collector import UnrealMaterialEvidenceCollector
from asset_forge.unreal.material_graph_evidence import build_material_graph_evidence_report


class UnrealMaterialEvidenceCollectorTest(unittest.TestCase):
    def test_compile_evidence_uses_cached_results_and_reports_actual_errors(self):
        parent = "/AssetForge/Materials/M_Parent"
        engine = FakeUnreal("")
        engine.load_asset = lambda path: FakeMaterial()
        collector = UnrealMaterialEvidenceCollector(engine)
        library = engine.AssetForgeMaterialCommentLibrary

        evidence = collector._collect_compile_log([parent])
        self.assertEqual(evidence["status"], "pass")
        self.assertEqual(evidence["readback_materials"], [parent])
        self.assertEqual(evidence["recompiled_materials"], [])

        library.compile_errors = ["shader failed"]
        evidence = collector._collect_compile_log([parent])
        self.assertEqual(evidence["status"], "error")
        self.assertEqual(evidence["messages"], [{"severity": "error", "text": parent + ": shader failed"}])

        library.compile_errors = None
        evidence = collector._collect_compile_log([parent])
        self.assertEqual(evidence["status"], "skipped")
        self.assertEqual(evidence["unavailable_materials"], [parent])

    def test_legacy_native_bridge_is_not_used_for_mutating_parent_readback(self):
        engine = FakeUnreal("")
        engine.AssetForgeMaterialCommentLibrary = LegacyMutatingCommentLibrary()
        engine.load_asset = lambda path: FakeMaterial()
        collector = UnrealMaterialEvidenceCollector(engine)

        self.assertEqual(collector._comment_blocks_summary(FakeMaterial())["status"], "not_provided")
        evidence = collector._collect_compile_log(["/AssetForge/Materials/M_Parent"])
        self.assertEqual(evidence["status"], "skipped")
        self.assertEqual(evidence["readback_materials"], [])

    def test_closed_material_graph_reports_unavailable_visual_readback(self):
        engine = FakeUnreal(
            "SUMMARY expected_af_comments=7|expression_comments=7|linked_graph_comments=0"
            "|orphan_graph_comments=0|duplicate_comments=0|graph_readback_available=0"
        )
        summary = UnrealMaterialEvidenceCollector(engine)._comment_blocks_summary(FakeMaterial())

        self.assertEqual(summary["status"], "not_provided")
        self.assertEqual(summary["expression_comments"], 7)
        self.assertEqual(summary["visual_review_risk"], "unknown")
        self.assertEqual(summary["next_action"], "open the material graph and rerun comment readback")

    def test_project_parent_uses_planned_parameters_and_leaves_visual_review_open(self):
        parent = "/Game/Studio/M_Custom"
        plan = {"master_material": "/Game/Studio/M_Unused", "materials": [{
            "parent_material": parent, "texture_parameters": {"surface": "T_Color", "Detail": "T_Normal"},
        }]}
        engine = FakeUnreal(RuntimeError("project graph comments must not be read"))
        engine.load_asset = lambda path: FakeMaterial() if path == parent else None
        class Parameters(object):
            @staticmethod
            def get_texture_parameter_names(asset):
                return ["Surface", "Detail"]
        engine.MaterialEditingLibrary = Parameters
        collector = UnrealMaterialEvidenceCollector(engine)
        graph = collector.collect({"material_binding_plan": plan})["real_ue_material_graph"]
        self.assertEqual(graph["status"], "pass", graph["issues"])
        self.assertEqual([m["material_path"] for m in graph["materials"]], [parent])
        evidence = build_material_graph_evidence_report(plan, real_ue_material_graph=graph)
        self.assertEqual(evidence["required_texture_parameters"], ["Detail", "surface"])
        visual = evidence["ta_visual_review"]
        self.assertEqual(visual["status"], "manual_validation_required")
        self.assertEqual(visual["comment_box_persistence_status"], "not_applicable")
        self.assertEqual(visual["comment_block_checks"], 0)
        plan["materials"][0]["texture_parameters"]["Missing"] = "T_Absent"
        graph = collector.collect({"material_binding_plan": plan})["real_ue_material_graph"]
        self.assertEqual(graph["status"], "error")
        self.assertEqual(graph["materials"][0]["missing_texture_parameters"], ["Missing"])

    def test_comment_block_summary_passes_when_all_graph_comments_are_linked(self):
        collector = UnrealMaterialEvidenceCollector(
            FakeUnreal(
                "SUMMARY expected_af_comments=7|expression_comments=7|linked_graph_comments=7|orphan_graph_comments=0|duplicate_comments=0"
            )
        )

        summary = collector._comment_blocks_summary(FakeMaterial())

        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["expected_af_comments"], 7)
        self.assertEqual(summary["linked_graph_comments"], 7)
        self.assertEqual(summary["visual_review_risk"], "low")
        self.assertEqual(summary["next_action"], "capture a material graph screenshot for TA visual review")
        self.assertEqual(summary["persistence_status"], "needs_cold_start_readback")
        self.assertEqual(summary["cold_start_readback_status"], "not_verified")
        self.assertTrue(summary["cold_start_readback_required"])
        self.assertTrue(summary["real_ue_screenshot_required"])
        self.assertIn("linked_graph_comments=7", summary["summary"])

    def test_comment_block_summary_warns_when_expression_comments_are_not_visible_graph_comments(self):
        collector = UnrealMaterialEvidenceCollector(
            FakeUnreal(
                "SUMMARY expected_af_comments=7|expression_comments=7|linked_graph_comments=0|orphan_graph_comments=0|duplicate_comments=0"
            )
        )

        summary = collector._comment_blocks_summary(FakeMaterial())

        self.assertEqual(summary["status"], "warning")
        self.assertEqual(summary["linked_graph_comments"], 0)
        self.assertEqual(summary["visual_review_risk"], "high")
        self.assertIn("visible comment boxes", summary["next_action"])
        self.assertEqual(summary["persistence_boundary"], "current_session_readback_only")

    def test_comment_block_summary_errors_when_linked_graph_comments_have_zero_size(self):
        collector = UnrealMaterialEvidenceCollector(
            FakeUnreal(
                "SUMMARY expected_af_comments=7|expression_comments=7|linked_graph_comments=7|orphan_graph_comments=0|duplicate_comments=0\n"
                "GRAPH AF 01 UV 坐标|X=-1260|Y=-980|NodeWidth=0|NodeHeight=0|StoredFontSize=18|VisualFontSize=20\n"
                "GRAPH AF 02 BaseColor 基础色|X=-1080|Y=-560|NodeWidth=0|NodeHeight=0|StoredFontSize=18|VisualFontSize=20\n"
                "GRAPH AF 03 Normal 法线|X=-1080|Y=-60|NodeWidth=0|NodeHeight=0|StoredFontSize=18|VisualFontSize=20\n"
                "GRAPH AF 04 ARM / ORM 打包 PBR|X=-1080|Y=340|NodeWidth=0|NodeHeight=0|StoredFontSize=18|VisualFontSize=20\n"
                "GRAPH AF 05 Imperfection 瑕疵|X=-1080|Y=900|NodeWidth=0|NodeHeight=0|StoredFontSize=18|VisualFontSize=20\n"
                "GRAPH AF 06 Emissive 自发光|X=-1080|Y=1320|NodeWidth=0|NodeHeight=0|StoredFontSize=18|VisualFontSize=20\n"
                "GRAPH AF 07 Opacity / Mask 透明与镂空|X=-1080|Y=1760|NodeWidth=0|NodeHeight=0|StoredFontSize=18|VisualFontSize=20"
            )
        )

        summary = collector._comment_blocks_summary(FakeMaterial())

        self.assertEqual(summary["status"], "error")
        self.assertEqual(summary["linked_graph_comments"], 7)
        self.assertEqual(summary["visible_graph_comments_with_size"], 0)
        self.assertEqual(summary["invalid_graph_comment_dimensions"], 7)
        self.assertEqual(summary["visual_review_risk"], "high")
        self.assertIn("comment box dimensions", summary["next_action"])

    def test_comment_block_summary_marks_cold_start_readback_when_cpp_reports_it(self):
        collector = UnrealMaterialEvidenceCollector(
            FakeUnreal(
                "SUMMARY expected_af_comments=7|expression_comments=7|linked_graph_comments=7|orphan_graph_comments=0|duplicate_comments=0|cold_start_readback_status=pass"
            )
        )

        summary = collector._comment_blocks_summary(FakeMaterial())

        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["cold_start_readback_status"], "pass")
        self.assertFalse(summary["cold_start_readback_required"])
        self.assertEqual(summary["persistence_status"], "cold_start_readback_provided")
        self.assertTrue(summary["real_ue_screenshot_required"])

    def test_comment_block_summary_errors_when_cpp_readback_fails(self):
        collector = UnrealMaterialEvidenceCollector(FakeUnreal(RuntimeError("comment readback failed")))

        summary = collector._comment_blocks_summary(FakeMaterial())

        self.assertEqual(summary["status"], "error")
        self.assertIn("comment readback failed", summary["message"])


class FakeMaterial(object):
    pass


class FakeUnreal(object):
    def __init__(self, description):
        self.AssetForgeMaterialCommentLibrary = FakeCommentLibrary(description)
        self.MaterialEditingLibrary = LegacyMutatingCommentLibrary()


class LegacyMutatingCommentLibrary(object):
    def describe_asset_forge_comment_blocks(self, material_asset):
        raise AssertionError("Evidence collection must not rebuild the shared parent graph")

    def recompile_material(self, material_asset):
        raise AssertionError("Evidence collection must not recompile the shared parent")


class FakeCommentLibrary(LegacyMutatingCommentLibrary):
    def __init__(self, description):
        self.description = description
        self.compile_errors = []

    def read_asset_forge_comment_blocks(self, material_asset):
        if isinstance(self.description, Exception):
            raise self.description
        return self.description

    def try_read_asset_forge_material_compile_errors(self, material_asset):
        return self.compile_errors


if __name__ == "__main__":
    unittest.main()
