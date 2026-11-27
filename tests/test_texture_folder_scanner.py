from __future__ import absolute_import

import os
import shutil
import struct
import tempfile
import unittest

from asset_forge.shared.material_profile_schema import get_default_material_profile
from asset_forge.shared.texture_folder_scanner import TextureFolderScanner, parse_texture_set_selection


class TextureFolderScannerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_scans_painter_unreal_texture_names(self):
        self._write_texture("SM_Crate_01_BaseColor.png")
        self._write_texture("SM_Crate_01_Normal.png")
        self._write_texture("SM_Crate_01_ARM.png")
        self._write_texture("SM_Crate_01_Emissive.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)
        textures_by_usage = dict((texture["usage"], texture) for texture in result["textures"])

        self.assertEqual(result["issues"], [])
        self.assertEqual(result["profile"], "Props_Opaque_PainterUE_ARM")
        self.assertEqual(textures_by_usage["base_color"]["source_type"], "texture_folder")
        self.assertEqual(textures_by_usage["base_color"]["parameter"], "BaseColor")
        self.assertTrue(textures_by_usage["base_color"]["srgb"])
        self.assertFalse(textures_by_usage["normal"]["srgb"])
        self.assertEqual(textures_by_usage["packed_arm"]["channels"]["r"], "ao")
        self.assertEqual(textures_by_usage["packed_arm"]["channels"]["g"], "roughness")
        self.assertEqual(textures_by_usage["packed_arm"]["channels"]["b"], "metallic")

    def test_missing_required_textures_report_warnings(self):
        self._write_texture("SM_Crate_01_ARM.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)
        issue_usages = [issue["usage"] for issue in result["issues"]]

        self.assertIn("base_color", issue_usages)
        self.assertIn("normal", issue_usages)
        self.assertEqual(len(result["textures"]), 1)

    def test_optional_textures_are_not_required(self):
        self._write_texture("SM_Crate_01_BaseColor.png")
        self._write_texture("SM_Crate_01_Normal.png")
        self._write_texture("SM_Crate_01_ARM.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)
        usages = [texture["usage"] for texture in result["textures"]]

        self.assertEqual(result["issues"], [])
        self.assertEqual(usages, ["base_color", "normal", "packed_arm"])

    def test_ignores_other_asset_textures_and_reports_unrecognized(self):
        self._write_texture("SM_Crate_01_BaseColor.png")
        self._write_texture("SM_Crate_01_Normal.png")
        self._write_texture("SM_Barrel_01_BaseColor.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)

        self.assertEqual(len(result["textures"]), 2)
        self.assertEqual(len(result["unrecognized"]), 1)
        self.assertTrue(result["unrecognized"][0].endswith("/SM_Barrel_01_BaseColor.png"))

    def test_duplicate_matches_keep_first_and_warn(self):
        self._write_texture("SM_Crate_01_BaseColor.png")
        self._write_texture("SM_Crate_01_BC.png")
        self._write_texture("SM_Crate_01_Normal.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)

        self.assertEqual(result["issues"][0]["usage"], "base_color")
        self.assertEqual(result["textures"][0]["usage"], "base_color")

    def test_matches_suffixes_case_insensitively(self):
        self._write_texture("sm_crate_01_basecolor.PNG")
        self._write_texture("sm_crate_01_normal.TGA")
        self._write_texture("sm_crate_01_oRm.tga")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)
        usages = [texture["usage"] for texture in result["textures"]]

        self.assertEqual(result["issues"], [])
        self.assertEqual(usages, ["base_color", "normal", "packed_arm"])

    def test_reads_png_and_tga_dimensions_from_headers(self):
        self._write_png_header("SM_Crate_01_BaseColor.png", 128, 64)
        self._write_tga_header("SM_Crate_01_Normal.tga", 256, 128)

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)
        textures_by_usage = dict((texture["usage"], texture) for texture in result["textures"])

        self.assertEqual(textures_by_usage["base_color"]["width"], 128)
        self.assertEqual(textures_by_usage["base_color"]["height"], 64)
        self.assertEqual(textures_by_usage["normal"]["width"], 256)
        self.assertEqual(textures_by_usage["normal"]["height"], 128)
        self.assertEqual(textures_by_usage["normal"]["texture_metadata_status"], "pass")

    def test_recursive_scan_finds_nested_painter_textures(self):
        nested = os.path.join(self.temp_dir, "PainterExport", "Textures")
        os.makedirs(nested)
        self._write_texture("README.txt")
        self._write_texture_at(nested, "SM_Crate_01_BaseColor.png")
        self._write_texture_at(nested, "SM_Crate_01_Normal.png")

        result = TextureFolderScanner(recursive=True).scan(self.temp_dir, "SM_Crate_01", self.profile)

        self.assertTrue(result["recursive"])
        self.assertEqual([texture["usage"] for texture in result["textures"]], ["base_color", "normal"])

    def test_valid_texture_directory_records_counts_and_naming_pass(self):
        self._write_texture("T_SM_Crate_01_BaseColor.png")
        self._write_texture("T_SM_Crate_01_Normal.png")
        self._write_texture("T_SM_Crate_01_ARM.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)

        self.assertEqual(result["directory_status"], "valid")
        self.assertTrue(result["can_use_directory"])
        self.assertEqual(result["matched_count"], 3)
        self.assertEqual(result["required_missing"], [])
        self.assertEqual(result["texture_naming_validation"]["status"], "pass")
        self.assertEqual(result["naming_warnings"], [])
        self.assertEqual(result["rename_suggestions"], [])

    def test_missing_t_prefix_warns_but_directory_can_still_be_used(self):
        self._write_texture("SM_Crate_01_BaseColor.png")
        self._write_texture("SM_Crate_01_Normal.png")
        self._write_texture("SM_Crate_01_ARM.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)

        self.assertEqual(result["issues"], [])
        self.assertEqual(result["directory_status"], "valid")
        self.assertTrue(result["can_use_directory"])
        self.assertEqual(result["texture_naming_validation"]["status"], "warning")
        self.assertEqual(len(result["rename_suggestions"]), 3)
        self.assertFalse(result["rename_suggestions"][0]["will_modify_disk"])
        self.assertIn("是否添加 T_ 前缀", result["rename_suggestions"][0]["message"])

    def test_missing_required_texture_records_missing_usage(self):
        self._write_texture("T_SM_Crate_01_BaseColor.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)

        self.assertEqual(result["directory_status"], "incomplete")
        self.assertFalse(result["can_use_directory"])
        self.assertIn("normal", result["required_missing"])
        self.assertTrue(any(issue["usage"] == "normal" for issue in result["issues"]))

    def test_painter_full_orm_suffix_matches_packed_arm_with_t_prefix(self):
        self._write_texture("T_HK416_D_B_a1_BaseColor.png")
        self._write_texture("T_HK416_D_B_a1_Normal.png")
        self._write_texture("T_HK416_D_B_a1_OcclusionRoughnessMetallic.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_B_a", self.profile)
        textures_by_usage = dict((texture["usage"], texture) for texture in result["textures"])

        self.assertEqual(result["texture_naming_validation"]["status"], "pass")
        self.assertIn("packed_arm", textures_by_usage)
        self.assertEqual(textures_by_usage["packed_arm"]["parameter"], "ARM")

    def test_imperfection_mask_usage_matches_hard_surface_profile(self):
        self._write_texture("T_SM_Crate_01_BaseColor.png")
        self._write_texture("T_SM_Crate_01_Normal.png")
        self._write_texture("T_SM_Crate_01_ARM.png")
        self._write_texture("T_SM_Crate_01_Imperfection.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)
        textures_by_usage = dict((texture["usage"], texture) for texture in result["textures"])

        self.assertEqual(result["directory_status"], "valid")
        self.assertIn("imperfection_mask", textures_by_usage)
        self.assertEqual(textures_by_usage["imperfection_mask"]["parameter"], "ImperfectionMask")
        self.assertFalse(textures_by_usage["imperfection_mask"]["srgb"])
        self.assertEqual(textures_by_usage["imperfection_mask"]["compression"], "masks")
        self.assertEqual(textures_by_usage["imperfection_mask"]["channels"]["g"], "edge_wear")
        self.assertIn("imperfection_mask", result["material_feature_hints"])
        self.assertIn("dirty_wear", result["variant_candidates"])

    def test_emissive_and_height_usages_emit_variant_hints(self):
        self._write_texture("T_SM_Crate_01_BaseColor.png")
        self._write_texture("T_SM_Crate_01_Normal.png")
        self._write_texture("T_SM_Crate_01_ARM.png")
        self._write_texture("T_SM_Crate_01_Emissive.png")
        self._write_texture("T_SM_Crate_01_Height.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)
        textures_by_usage = dict((texture["usage"], texture) for texture in result["textures"])

        self.assertIn("emissive", textures_by_usage)
        self.assertTrue(textures_by_usage["emissive"]["srgb"])
        self.assertIn("height", textures_by_usage)
        self.assertFalse(textures_by_usage["height"]["srgb"])
        self.assertIn("emissive", result["material_feature_hints"])
        self.assertIn("height", result["material_feature_hints"])
        self.assertIn("emissive", result["variant_candidates"])
        self.assertIn("pom", result["variant_candidates"])

    def test_duplicate_ambiguous_matches_are_reported_separately(self):
        self._write_texture("T_SM_Crate_01_BaseColor.png")
        self._write_texture("SM_Crate_01_BaseColor.png")
        self._write_texture("T_SM_Crate_01_Normal.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)

        self.assertTrue(any(item["usage"] == "base_color" for item in result["duplicate_matches"]))
        self.assertTrue(any(issue["usage"] == "base_color" for issue in result["issues"]))
        self.assertEqual(result["unrecognized_count"], 0)

    def test_matches_painter_full_orm_suffix_without_asset_prefix(self):
        self._write_texture("HK416_D_B_a1_BaseColor.png")
        self._write_texture("HK416_D_B_a1_Normal.png")
        self._write_texture("HK416_D_B_a1_OcclusionRoughnessMetallic.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_B_a", self.profile)
        textures_by_usage = dict((texture["usage"], texture) for texture in result["textures"])

        self.assertEqual(textures_by_usage["base_color"]["match_mode"], "asset_tokens")
        self.assertEqual(textures_by_usage["packed_arm"]["parameter"], "ARM")
        self.assertIn("packed_arm", textures_by_usage)

    def test_suffix_only_shared_texture_match_warns_about_ambiguity(self):
        self._write_texture("HK416_D_B_a1_BaseColor.png")
        self._write_texture("HK416_D_B_b1_BaseColor.png")
        self._write_texture("HK416_D_B_a1_Normal.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_B_e", self.profile)

        self.assertEqual(result["selected_texture_set"], "")
        self.assertTrue(result["texture_sets"])
        self.assertTrue(result["requires_texture_set_selection"])
        self.assertEqual(result["matched_count"], 0)

    def test_texture_set_token_prioritizes_matching_candidate(self):
        self._write_texture("HK416_D_B_a1_BaseColor.png")
        self._write_texture("HK416_D_B_a1_Normal.png")
        self._write_texture("HK416_D_B_a1_OcclusionRoughnessMetallic.png")
        self._write_texture("HK416_D_B_d1_BaseColor.png")
        self._write_texture("HK416_D_B_d1_Normal.png")
        self._write_texture("HK416_D_B_d1_OcclusionRoughnessMetallic.png")

        result = TextureFolderScanner().scan(self.temp_dir, "SM_B_e", self.profile, texture_set_token="d1")
        names_by_usage = dict((texture["usage"], os.path.basename(texture["path"])) for texture in result["textures"])

        self.assertEqual(result["matched_count"], 3)
        self.assertEqual(names_by_usage["base_color"], "HK416_D_B_d1_BaseColor.png")
        self.assertEqual(names_by_usage["normal"], "HK416_D_B_d1_Normal.png")
        self.assertEqual(names_by_usage["packed_arm"], "HK416_D_B_d1_OcclusionRoughnessMetallic.png")
        self.assertIn({"name": "HK416D", "source": "texture_set", "source_value": "HK416_D_B_d1", "confidence": "medium"}, result["asset_name_candidates"])
        self.assertTrue(all("texture_set_token" in texture["match_mode"] for texture in result["textures"]))
        self.assertIn("base_color", result["candidates_by_usage"])

    def test_parse_texture_set_selection_supports_common_separators(self):
        self.assertEqual(parse_texture_set_selection("a1、d1, b1；c1\nx1"), ["a1", "d1", "b1", "c1", "x1"])

    def test_multi_texture_set_selection_returns_all_selected_textures(self):
        for name in [
            "HK416_D_B_a1_BaseColor.png",
            "HK416_D_B_a1_Normal.png",
            "HK416_D_B_a1_OcclusionRoughnessMetallic.png",
            "HK416_D_B_d1_BaseColor.png",
            "HK416_D_B_d1_Normal.png",
            "HK416_D_B_d1_OcclusionRoughnessMetallic.png",
        ]:
            self._write_texture(name)

        result = TextureFolderScanner().scan(self.temp_dir, "SM_B_e", self.profile, texture_set_token="a1、d1")

        self.assertEqual(result["matched_count"], 6)
        self.assertEqual(result["selected_texture_set_short_names"], ["a1", "d1"])
        self.assertEqual(len([texture for texture in result["textures"] if texture["usage"] == "base_color"]), 2)

    def test_texture_set_token_asset_family_selects_all_matching_sets(self):
        for set_name in ["a1", "b1", "d1"]:
            for suffix in ["BaseColor", "Normal", "OcclusionRoughnessMetallic"]:
                self._write_texture("HK416_D_B_{0}_{1}.png".format(set_name, suffix))
        for suffix in ["BaseColor", "Normal", "OcclusionRoughnessMetallic"]:
            self._write_texture("HK416_D_H_a_{0}.png".format(suffix))

        result = TextureFolderScanner().scan(self.temp_dir, "SM_B", self.profile, texture_set_token="B")

        self.assertEqual(result["matched_count"], 9)
        self.assertEqual(result["selected_texture_set_short_names"], ["a1", "b1", "d1"])
        self.assertEqual(len([texture for texture in result["textures"] if texture["usage"] == "base_color"]), 3)
        self.assertNotIn("a", result["selected_texture_set_short_names"])

    def test_full_texture_set_name_selection_is_case_insensitive(self):
        for name in [
            "HK416_D_B_a1_BaseColor.png",
            "HK416_D_B_a1_Normal.png",
            "HK416_D_B_d1_BaseColor.png",
            "HK416_D_B_d1_Normal.png",
        ]:
            self._write_texture(name)

        result = TextureFolderScanner().scan(self.temp_dir, "SM_B_e", self.profile, texture_set_token="HK416_D_B_A1, HK416_D_B_D1")

        self.assertEqual(result["matched_count"], 4)
        self.assertEqual(result["selected_texture_sets"], ["HK416_D_B_a1", "HK416_D_B_d1"])

    def test_multiple_complete_texture_sets_require_selection_when_token_empty(self):
        for name in [
            "HK416_D_B_a1_BaseColor.png",
            "HK416_D_B_a1_Normal.png",
            "HK416_D_B_d1_BaseColor.png",
            "HK416_D_B_d1_Normal.png",
        ]:
            self._write_texture(name)

        result = TextureFolderScanner().scan(self.temp_dir, "SM_B_e", self.profile)

        self.assertEqual(result["directory_status"], "incomplete")
        self.assertTrue(result["requires_texture_set_selection"])
        self.assertFalse(result["can_use_directory"])
        self.assertEqual(result["matched_count"], 0)
        self.assertEqual(result["selected_texture_set_short_names"], [])
        self.assertFalse(result["auto_selected_texture_sets"])
        self.assertTrue(any(issue.get("id") == "texture_set_selection_required" for issue in result["issues"]))

    def test_unmatched_texture_set_token_does_not_fall_back_to_other_sets(self):
        for name in [
            "HK416_D_B_b1_BaseColor.png",
            "HK416_D_B_b1_Normal.png",
            "HK416_D_B_d1_BaseColor.png",
            "HK416_D_B_d1_Normal.png",
        ]:
            self._write_texture(name)

        result = TextureFolderScanner().scan(self.temp_dir, "SM_B", self.profile, texture_set_token="a1")

        self.assertEqual(result["directory_status"], "incomplete")
        self.assertTrue(result["requires_texture_set_selection"])
        self.assertFalse(result["can_use_directory"])
        self.assertEqual(result["matched_count"], 0)
        self.assertTrue(any(issue.get("id") == "texture_set_selection_unmatched" for issue in result["issues"]))

    def test_texture_prefix_rename_plan_skips_existing_target(self):
        source = self._write_texture("SM_Crate_01_BaseColor.png")
        self._write_texture("T_SM_Crate_01_BaseColor.png")
        scan = {"textures": [{"path": source, "source_path": source, "usage": "base_color"}]}

        result = TextureFolderScanner().plan_texture_prefix_renames(scan, "T_")

        self.assertEqual(result["planned_count"], 0)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(result["actions"][0]["reason"], "target_exists")

    def test_texture_prefix_plan_requires_selected_set_when_requested(self):
        source = self._write_texture("HK416_D_B_a1_BaseColor.png")
        scan = {"textures": [{"path": source, "source_path": source, "usage": "base_color"}]}

        result = TextureFolderScanner().plan_texture_prefix_renames(scan, "T_", require_selected_set=True)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["planned_count"], 0)

    def test_texture_prefix_plan_is_idempotent_and_only_selected_set(self):
        for name in [
            "HK416_D_B_a1_BaseColor.png",
            "HK416_D_B_a1_Normal.png",
            "T_HK416_D_B_a1_OcclusionRoughnessMetallic.png",
            "HK416_D_B_d1_BaseColor.png",
            "HK416_D_B_d1_Normal.png",
        ]:
            self._write_texture(name)

        scan = TextureFolderScanner().scan(self.temp_dir, "SM_B_e", self.profile, texture_set_token="a1")
        result = TextureFolderScanner().plan_texture_prefix_renames(scan, "T_", require_selected_set=True)
        target_names = [os.path.basename(action["target_path"]) for action in result["actions"]]

        self.assertEqual(result["planned_count"], 2)
        self.assertEqual(result["skipped_count"], 1)
        self.assertIn("T_HK416_D_B_a1_BaseColor.png", target_names)
        self.assertIn("T_HK416_D_B_a1_Normal.png", target_names)
        self.assertNotIn("T_HK416_D_B_d1_BaseColor.png", target_names)
        self.assertTrue(any(action["reason"] == "already_prefixed" for action in result["actions"]))

    def _write_texture(self, file_name):
        path = os.path.join(self.temp_dir, file_name)
        return self._write_texture_at(self.temp_dir, file_name)

    def _write_texture_at(self, directory, file_name):
        path = os.path.join(directory, file_name)
        with open(path, "wb") as stream:
            stream.write(b"fake texture")
        return path

    def _write_png_header(self, file_name, width, height):
        path = os.path.join(self.temp_dir, file_name)
        with open(path, "wb") as stream:
            stream.write(b"\x89PNG\r\n\x1a\n")
            stream.write(struct.pack(">I", 13))
            stream.write(b"IHDR")
            stream.write(struct.pack(">II", width, height))
            stream.write(b"\x08\x06\x00\x00\x00")
        return path

    def _write_tga_header(self, file_name, width, height):
        path = os.path.join(self.temp_dir, file_name)
        header = bytearray(18)
        header[2] = 2
        header[12:14] = struct.pack("<H", width)
        header[14:16] = struct.pack("<H", height)
        header[16] = 32
        with open(path, "wb") as stream:
            stream.write(bytes(header))
        return path


if __name__ == "__main__":
    unittest.main()
