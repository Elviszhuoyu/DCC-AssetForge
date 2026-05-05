from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.material_profile_schema import get_default_material_profile
from asset_forge.shared.texture_folder_scanner import TextureFolderScanner


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

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)
        usages = [texture["usage"] for texture in result["textures"]]

        self.assertEqual(result["issues"], [])
        self.assertEqual(usages, ["base_color", "normal"])

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

        result = TextureFolderScanner().scan(self.temp_dir, "SM_Crate_01", self.profile)
        usages = [texture["usage"] for texture in result["textures"]]

        self.assertEqual(result["issues"], [])
        self.assertEqual(usages, ["base_color", "normal"])

    def test_recursive_scan_finds_nested_painter_textures(self):
        nested = os.path.join(self.temp_dir, "PainterExport", "Textures")
        os.makedirs(nested)
        self._write_texture("README.txt")
        self._write_texture_at(nested, "SM_Crate_01_BaseColor.png")
        self._write_texture_at(nested, "SM_Crate_01_Normal.png")

        result = TextureFolderScanner(recursive=True).scan(self.temp_dir, "SM_Crate_01", self.profile)

        self.assertTrue(result["recursive"])
        self.assertEqual([texture["usage"] for texture in result["textures"]], ["base_color", "normal"])

    def _write_texture(self, file_name):
        path = os.path.join(self.temp_dir, file_name)
        return self._write_texture_at(self.temp_dir, file_name)

    def _write_texture_at(self, directory, file_name):
        path = os.path.join(directory, file_name)
        with open(path, "wb") as stream:
            stream.write(b"fake texture")
        return path


if __name__ == "__main__":
    unittest.main()
