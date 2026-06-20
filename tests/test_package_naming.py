from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.package_naming import resolve_package_naming


class PackageNamingTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_overwrite_mode_uses_asset_name_as_package_name(self):
        naming = resolve_package_naming(self.temp_dir, "SM_B_Blender")

        self.assertEqual(naming["asset_name"], "SM_B_Blender")
        self.assertEqual(naming["package_name"], "SM_B_Blender")
        self.assertEqual(naming["version_mode"], "overwrite")
        self.assertFalse(naming["will_overwrite"])

    def test_auto_increment_creates_first_version_package(self):
        naming = resolve_package_naming(self.temp_dir, "SM_B_Blender", version_mode="auto_increment")

        self.assertEqual(naming["package_name"], "SM_B_Blender_v001")
        self.assertEqual(naming["version_number"], 1)
        self.assertEqual(naming["version_label"], "v001")

    def test_auto_increment_continues_from_existing_versions(self):
        os.makedirs(os.path.join(self.temp_dir, "SM_B_Blender_v001"))
        os.makedirs(os.path.join(self.temp_dir, "SM_B_Blender_v002"))

        naming = resolve_package_naming(self.temp_dir, "SM_B_Blender", version_mode="auto_increment")

        self.assertEqual(naming["package_name"], "SM_B_Blender_v003")

    def test_manual_package_name_is_the_base_for_versioning(self):
        naming = resolve_package_naming(
            self.temp_dir,
            "SM_B_Blender",
            package_name_override="Client Preview",
            version_mode="auto_increment",
            version_padding=2,
        )

        self.assertEqual(naming["asset_name"], "SM_B_Blender")
        self.assertEqual(naming["base_package_name"], "Client_Preview")
        self.assertEqual(naming["package_name"], "Client_Preview_v01")
        self.assertEqual(naming["naming_source"], "manual_package_name")


if __name__ == "__main__":
    unittest.main()
