from __future__ import absolute_import

import json
import os
import unittest

from asset_forge.unreal.material_package_schema import get_default_material_package_plan
from asset_forge.unreal.plugin_content_bootstrap import UnrealPluginContentBootstrap


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

    def test_bootstrap_reports_missing_plugin_assets_without_creating_project_content(self):
        report = UnrealPluginContentBootstrap(unreal_module=FakeUnreal(existing_assets=[])).validate()

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["content_mount"], "/AssetForge")
        self.assertIn("/AssetForge/Materials/M_AF_Props_Opaque", report["missing_assets"])
        self.assertNotIn("/Game/AssetForge/Materials/M_AF_Props_Opaque", report["missing_assets"])

    def test_bootstrap_passes_when_planned_plugin_assets_exist(self):
        plan = get_default_material_package_plan()
        existing_assets = []
        existing_assets.extend(material["path"] for material in plan["materials"])
        existing_assets.extend(function["path"] for function in plan["functions"])
        existing_assets.extend(collection["path"] for collection in plan["parameter_collections"])

        report = UnrealPluginContentBootstrap(unreal_module=FakeUnreal(existing_assets)).validate(plan)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["missing_assets"], [])


class FakeUnreal(object):
    class EditorAssetLibrary(object):
        existing_assets = set()

        @classmethod
        def does_asset_exist(cls, asset_path):
            return asset_path in cls.existing_assets

    def __init__(self, existing_assets):
        self.EditorAssetLibrary.existing_assets = set(existing_assets)


if __name__ == "__main__":
    unittest.main()
