from __future__ import absolute_import

import json
import os
import unittest

from asset_forge.unreal.material_package_schema import get_default_material_package_plan


class UnrealPluginSkeletonTest(unittest.TestCase):
    def test_assetforge_plugin_descriptor_matches_material_mount(self):
        plugin_path = os.path.join("Plugins", "AssetForge", "AssetForge.uplugin")

        with open(plugin_path, "r", encoding="utf-8") as stream:
            descriptor = json.load(stream)
        plan = get_default_material_package_plan()

        self.assertEqual(descriptor["FriendlyName"], "Asset Forge")
        self.assertTrue(descriptor["CanContainContent"])
        self.assertEqual(plan["content_mount"], "/AssetForge")
        self.assertEqual(plan["disk_content_root"], "Plugins/AssetForge/Content")

    def test_plugin_content_directories_exist_for_default_material_package(self):
        expected_dirs = [
            os.path.join("Plugins", "AssetForge", "Content", "Materials"),
            os.path.join("Plugins", "AssetForge", "Content", "MaterialFunctions"),
            os.path.join("Plugins", "AssetForge", "Content", "ParameterCollections"),
        ]

        for directory in expected_dirs:
            self.assertTrue(os.path.isdir(directory), directory)


if __name__ == "__main__":
    unittest.main()
