from __future__ import absolute_import

import unittest

from asset_forge.unreal.material_showcase import (
    REQUIRED_SHOWCASE_ROLES,
    SHOWCASE_LEVEL_PATH,
    UnrealMaterialShowcaseBuilder,
    build_material_showcase_report,
    get_default_material_showcase_plan,
    validate_material_showcase_plan,
)


class UnrealMaterialShowcaseTest(unittest.TestCase):
    def test_default_showcase_covers_every_product_preset_role(self):
        plan = get_default_material_showcase_plan()
        roles = {
            entry["role"]
            for row in plan["rows"]
            for entry in row["entries"]
        }

        self.assertEqual(plan["level_path"], SHOWCASE_LEVEL_PATH)
        self.assertEqual(validate_material_showcase_plan(plan), [])
        self.assertTrue(REQUIRED_SHOWCASE_ROLES.issubset(roles))

    def test_showcase_report_is_product_ready(self):
        report = build_material_showcase_report()

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["issue_count"], 0)
        self.assertEqual(report["category_count"], 3)
        self.assertEqual(report["entry_count"], len(REQUIRED_SHOWCASE_ROLES))
        self.assertIn("props_emissive", report["roles"])
        self.assertIn("environment_tile_floor", report["roles"])
        self.assertIn("character_skin", report["roles"])

    def test_showcase_rejects_missing_role(self):
        plan = get_default_material_showcase_plan()
        plan["rows"][0]["entries"] = [
            entry for entry in plan["rows"][0]["entries"] if entry["role"] != "props_emissive"
        ]

        issues = validate_material_showcase_plan(plan)

        self.assertTrue(any("props_emissive" in issue for issue in issues))

    def test_builder_skips_existing_showcase_level_without_deleting_world_asset(self):
        fake_unreal = FakeUnrealForExistingShowcase()

        report = UnrealMaterialShowcaseBuilder(unreal_module=fake_unreal).build()

        self.assertEqual(report["status"], "skipped")
        self.assertEqual(report["level_path"], SHOWCASE_LEVEL_PATH)
        self.assertEqual(report["entry_count"], len(REQUIRED_SHOWCASE_ROLES))
        self.assertEqual(fake_unreal.EditorAssetLibrary.deleted_assets, [])
        self.assertEqual(fake_unreal.EditorLevelLibrary.created_levels, [])


class FakeUnrealForExistingShowcase(object):
    class EditorAssetLibrary(object):
        deleted_assets = []

        @classmethod
        def make_directory(cls, directory):
            cls.directory = directory

        @classmethod
        def does_asset_exist(cls, asset_path):
            return asset_path == SHOWCASE_LEVEL_PATH

        @classmethod
        def delete_asset(cls, asset_path):
            cls.deleted_assets.append(asset_path)
            return True

    class EditorLevelLibrary(object):
        created_levels = []

        @classmethod
        def new_level(cls, level_path):
            cls.created_levels.append(level_path)

    def __init__(self):
        self.EditorAssetLibrary.deleted_assets = []
        self.EditorLevelLibrary.created_levels = []


if __name__ == "__main__":
    unittest.main()
