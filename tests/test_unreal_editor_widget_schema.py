from __future__ import absolute_import

import os
import unittest

from asset_forge.unreal.editor_widget_schema import get_editor_widget_plan, validate_editor_widget_plan


class UnrealEditorWidgetSchemaTest(unittest.TestCase):
    def test_editor_widget_plan_uses_plugin_content_path(self):
        plan = get_editor_widget_plan()

        self.assertEqual(validate_editor_widget_plan(plan), [])
        self.assertEqual(plan["asset_type"], "EditorUtilityWidgetBlueprint")
        self.assertEqual(plan["asset_path"], "/AssetForge/Editor/EUW_AssetForgeBridge")
        self.assertFalse(plan["asset_path"].startswith("/Game/"))
        self.assertTrue(plan["disk_directory"].startswith("Plugins/AssetForge/Content"))
        self.assertTrue(os.path.isdir(plan["disk_directory"]))

    def test_editor_widget_plan_binds_package_actions(self):
        plan = get_editor_widget_plan()
        action_ids = [item["id"] for item in plan["actions"]]

        self.assertIn("select_package", action_ids)
        self.assertIn("dry_run_package", action_ids)
        self.assertIn("import_package", action_ids)
        self.assertEqual(plan["action_count"], len(action_ids))

    def test_editor_widget_plan_records_official_sources(self):
        plan = get_editor_widget_plan()

        self.assertTrue(all(source.startswith("https://dev.epicgames.com/") for source in plan["official_sources"]))


if __name__ == "__main__":
    unittest.main()
