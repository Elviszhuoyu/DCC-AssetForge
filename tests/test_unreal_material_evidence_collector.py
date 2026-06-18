from __future__ import absolute_import

import unittest

from asset_forge.unreal.material_evidence_collector import UnrealMaterialEvidenceCollector


class UnrealMaterialEvidenceCollectorTest(unittest.TestCase):
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


class FakeCommentLibrary(object):
    def __init__(self, description):
        self.description = description

    def describe_asset_forge_comment_blocks(self, material_asset):
        if isinstance(self.description, Exception):
            raise self.description
        return self.description


if __name__ == "__main__":
    unittest.main()
