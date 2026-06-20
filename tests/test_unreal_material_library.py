from __future__ import absolute_import

import unittest

from asset_forge.shared.material_profile_schema import get_default_material_profile
from asset_forge.unreal.material_library import GRAPH_COMMENT_BLOCKS, resolve_material_variant


class UnrealMaterialLibraryTest(unittest.TestCase):
    def setUp(self):
        self.profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")

    def test_selects_prebuilt_optional_variants_from_texture_usages(self):
        cases = [
            ("emissive", "/AssetForge/Materials/M_AF_Props_Master"),
            ("imperfection_mask", "/AssetForge/Materials/M_AF_Props_Master"),
        ]
        for usage, expected in cases:
            result = resolve_material_variant(self.profile, [{"usage": usage}])
            self.assertEqual(result["selected_material_variant"], expected)

    def test_special_variants_are_not_selected_without_profile_opt_in(self):
        for usage in ("height", "decal", "glass", "world_aligned"):
            result = resolve_material_variant(self.profile, [{"usage": usage}])
            self.assertEqual(result["selected_material_variant"], "/AssetForge/Materials/M_AF_Props_Master")

    def test_special_variants_can_be_selected_with_explicit_profile_opt_in(self):
        profile = dict(self.profile)
        profile["enabled_material_variants"] = ["pom", "decal", "glass", "world_aligned"]
        cases = [
            ("height", "/AssetForge/Materials/M_AF_Environment_Master"),
            ("decal", "/AssetForge/Materials/M_AF_Props_Master"),
            ("glass", "/AssetForge/Materials/M_AF_Props_Master"),
            ("world_aligned", "/AssetForge/Materials/M_AF_Environment_Master"),
        ]
        for usage, expected in cases:
            result = resolve_material_variant(profile, [{"usage": usage}])
            self.assertEqual(result["selected_material_variant"], expected)

    def test_translucent_profile_uses_glass_family_not_legacy_props(self):
        profile = get_default_material_profile("Props_Translucent_PainterUE_ARM")
        result = resolve_material_variant(profile, [{"usage": "opacity"}])

        self.assertEqual(result["selected_material_variant"], "/AssetForge/Materials/M_AF_Props_Master")

    def test_graph_comment_blocks_are_short_readable_chinese(self):
        comment_texts = [item["text"] for item in GRAPH_COMMENT_BLOCKS]

        self.assertEqual(len(comment_texts), 7)
        self.assertTrue(all("\n" not in text for text in comment_texts))
        self.assertTrue(all(len(text) <= 16 for text in comment_texts))
        for text in ("AF 02 基础色", "AF 03 法线", "AF 05 瑕疵", "AF 06 自发光", "AF 07 镂空遮罩"):
            self.assertIn(text, comment_texts)


if __name__ == "__main__":
    unittest.main()
