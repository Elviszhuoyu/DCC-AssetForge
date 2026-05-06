from __future__ import absolute_import

import unittest

from asset_forge.unreal.material_asset_bootstrap import UnrealMaterialAssetBootstrap


class UnrealMaterialAssetBootstrapTest(unittest.TestCase):
    def test_plan_includes_default_material_assets(self):
        plan = UnrealMaterialAssetBootstrap(unreal_module=FakeUnreal()).plan()

        self.assertEqual(plan["content_mount"], "/AssetForge")
        self.assertEqual(plan["asset_count"], 6)
        self.assertIn("/AssetForge/Materials", plan["directories"])
        self.assertEqual(plan["assets"][0]["factory"], "MaterialFactoryNew")
        self.assertEqual(plan["assets"][0]["asset_class"], "Material")

    def test_bootstrap_creates_missing_assets_and_sets_blend_modes(self):
        fake_unreal = FakeUnreal()

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).bootstrap()

        self.assertEqual(report["status"], "success")
        self.assertIn("/AssetForge/Materials/M_AF_Props_Opaque", report["created_assets"])
        self.assertIn("/AssetForge/ParameterCollections/MPC_AF_Global", report["created_assets"])
        self.assertIn("/AssetForge/Materials", fake_unreal.EditorAssetLibrary.directories)
        opaque = fake_unreal.AssetToolsHelpers.asset_tools.assets["/AssetForge/Materials/M_AF_Props_Opaque"]
        masked = fake_unreal.AssetToolsHelpers.asset_tools.assets["/AssetForge/Materials/M_AF_Props_Masked"]
        self.assertEqual(opaque.blend_mode, "opaque")
        self.assertEqual(masked.blend_mode, "masked")
        self.assertIn("/AssetForge/Materials/M_AF_Props_Opaque", fake_unreal.EditorAssetLibrary.saved)

    def test_bootstrap_skips_existing_assets(self):
        fake_unreal = FakeUnreal(existing_assets=["/AssetForge/Materials/M_AF_Props_Opaque"])

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).bootstrap()

        self.assertIn("/AssetForge/Materials/M_AF_Props_Opaque", report["existing_assets"])
        self.assertNotIn("/AssetForge/Materials/M_AF_Props_Opaque", report["created_assets"])

    def test_inspect_assets_reports_existing_and_missing_counts(self):
        fake_unreal = FakeUnreal(existing_assets=["/AssetForge/Materials/M_AF_Props_Opaque"])

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).inspect_assets()

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["planned_count"], 6)
        self.assertEqual(report["existing_count"], 1)
        self.assertEqual(report["missing_count"], 5)
        self.assertIn("/AssetForge/Materials/M_AF_Props_Opaque", report["existing_assets"])
        self.assertIn("/AssetForge/Materials/M_AF_Props_Masked", report["missing_assets"])

    def test_dry_run_does_not_create_assets(self):
        fake_unreal = FakeUnreal()

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).bootstrap(dry_run=True)

        self.assertEqual(report["status"], "skipped")
        self.assertEqual(report["asset_validation"]["missing_count"], 6)
        self.assertEqual(fake_unreal.AssetToolsHelpers.asset_tools.assets, {})


class FakeAsset(object):
    pass


class FakeAssetTools(object):
    def __init__(self):
        self.assets = {}

    def create_asset(self, asset_name, package_path, asset_class, factory):
        asset = FakeAsset()
        asset.asset_name = asset_name
        asset.package_path = package_path
        asset.asset_class = asset_class
        asset.factory = factory
        self.assets[package_path + "/" + asset_name] = asset
        return asset


class FakeAssetToolsHelpers(object):
    asset_tools = FakeAssetTools()

    @classmethod
    def get_asset_tools(cls):
        return cls.asset_tools


class FakeUnreal(object):
    AssetToolsHelpers = FakeAssetToolsHelpers
    Material = "Material"
    MaterialFunction = "MaterialFunction"
    MaterialParameterCollection = "MaterialParameterCollection"

    class MaterialFactoryNew(object):
        pass

    class MaterialFunctionFactoryNew(object):
        pass

    class MaterialParameterCollectionFactoryNew(object):
        pass

    class BlendMode(object):
        BLEND_OPAQUE = "opaque"
        BLEND_MASKED = "masked"
        BLEND_TRANSLUCENT = "translucent"

    class EditorAssetLibrary(object):
        existing_assets = set()
        directories = []
        saved = []

        @classmethod
        def does_asset_exist(cls, asset_path):
            return asset_path in cls.existing_assets

        @classmethod
        def make_directory(cls, directory):
            cls.directories.append(directory)

        @classmethod
        def save_asset(cls, asset_path):
            cls.saved.append(asset_path)

    def __init__(self, existing_assets=None):
        self.AssetToolsHelpers.asset_tools = FakeAssetTools()
        self.EditorAssetLibrary.existing_assets = set(existing_assets or [])
        self.EditorAssetLibrary.directories = []
        self.EditorAssetLibrary.saved = []


if __name__ == "__main__":
    unittest.main()
