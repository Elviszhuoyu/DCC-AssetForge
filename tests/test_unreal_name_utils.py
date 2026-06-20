from __future__ import absolute_import

import unittest

from asset_forge.unreal.name_utils import sanitize_unreal_asset_name


class UnrealNameUtilsTest(unittest.TestCase):
    def test_sanitizes_material_and_texture_asset_names(self):
        self.assertEqual(sanitize_unreal_asset_name("Wood Crate.Material"), "Wood_Crate_Material")
        self.assertEqual(sanitize_unreal_asset_name("01_Base Color", "T_Texture"), "T_Texture_01_Base_Color")
        self.assertEqual(sanitize_unreal_asset_name("", "M_Asset"), "M_Asset")


if __name__ == "__main__":
    unittest.main()
