from __future__ import absolute_import

import unittest

from asset_forge.unreal.editor_widget_launcher import UnrealEditorWidgetLauncher
from scripts.unreal_import_manifest import get_editor_widget_launch_plan, launch_asset_forge_widget


class UnrealEditorWidgetLauncherTest(unittest.TestCase):
    def test_launch_plan_reports_missing_widget_asset(self):
        launcher = UnrealEditorWidgetLauncher(FakeUnreal(existing_assets=[]))

        plan = launcher.launch_plan()

        self.assertEqual(plan["status"], "missing_asset")
        self.assertFalse(plan["asset_exists"])
        self.assertIn("import_package", plan["actions"])
        self.assertTrue(plan["issues"])

    def test_launch_plan_is_ready_when_widget_asset_exists(self):
        launcher = UnrealEditorWidgetLauncher(FakeUnreal(existing_assets=["/AssetForge/Editor/EUW_AssetForgeBridge"]))

        plan = launcher.launch_plan()

        self.assertEqual(plan["status"], "ready")
        self.assertTrue(plan["asset_exists"])
        self.assertEqual(plan["issues"], [])

    def test_launch_uses_editor_utility_subsystem_when_available(self):
        fake_unreal = FakeUnreal(existing_assets=["/AssetForge/Editor/EUW_AssetForgeBridge"])
        launcher = UnrealEditorWidgetLauncher(fake_unreal)

        report = launcher.launch()

        self.assertEqual(report["status"], "launched")
        self.assertEqual(fake_unreal.subsystem.spawned[0], "asset:/AssetForge/Editor/EUW_AssetForgeBridge")

    def test_script_entrypoints_expose_widget_launch_plan(self):
        plan = get_editor_widget_launch_plan()
        report = launch_asset_forge_widget()

        self.assertEqual(plan["asset_path"], "/AssetForge/Editor/EUW_AssetForgeBridge")
        self.assertEqual(report["status"], "missing_asset")


class FakeUnreal(object):
    class EditorUtilitySubsystem(object):
        pass

    class EditorAssetLibrary(object):
        existing_assets = set()

        @classmethod
        def does_asset_exist(cls, asset_path):
            return asset_path in cls.existing_assets

        @classmethod
        def load_asset(cls, asset_path):
            return "asset:" + asset_path

    def __init__(self, existing_assets):
        self.EditorAssetLibrary.existing_assets = set(existing_assets)
        self.subsystem = FakeEditorUtilitySubsystem()

    def get_editor_subsystem(self, subsystem_class):
        return self.subsystem


class FakeEditorUtilitySubsystem(object):
    def __init__(self):
        self.spawned = []

    def spawn_and_register_tab(self, widget_asset):
        self.spawned.append(widget_asset)


if __name__ == "__main__":
    unittest.main()
