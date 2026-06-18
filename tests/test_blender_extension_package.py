from __future__ import absolute_import

import unittest

from asset_forge.blender.extension_package_schema import (
    get_blender_extension_package_plan,
    read_blender_manifest,
    validate_blender_extension_package,
)


class BlenderExtensionPackageTest(unittest.TestCase):
    def test_blender_extension_package_is_valid(self):
        self.assertEqual(validate_blender_extension_package(), [])

    def test_manifest_uses_blender_extension_shape(self):
        plan = get_blender_extension_package_plan()
        manifest = read_blender_manifest(plan["manifest"])

        self.assertEqual(manifest["id"], "asset_forge")
        self.assertEqual(manifest["type"], "add-on")
        self.assertEqual(manifest["blender_version_min"], "4.2.0")
        self.assertIn("SPDX:MIT", manifest["license"])

    def test_blender_adapter_remains_gated(self):
        plan = get_blender_extension_package_plan()

        self.assertEqual(plan["status"], "packaging_gate")
        self.assertEqual(plan["support"], "roadmap")
        self.assertFalse(plan["real_exporter"])
        self.assertIn("contract only", plan["roadmap"])
        self.assertEqual(plan["required_entry_functions"], ["register", "unregister"])


if __name__ == "__main__":
    unittest.main()
