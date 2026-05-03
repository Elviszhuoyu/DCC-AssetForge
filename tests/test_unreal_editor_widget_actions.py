from __future__ import absolute_import

import unittest

from asset_forge.unreal.editor_widget_actions import UnrealEditorWidgetActions
from scripts.unreal_import_manifest import get_editor_widget_action_plan


class UnrealEditorWidgetActionsTest(unittest.TestCase):
    def test_action_plan_exposes_expected_button_ids(self):
        action_ids = [item["id"] for item in UnrealEditorWidgetActions(FakePipeline()).action_plan()]

        self.assertEqual(
            action_ids,
            [
                "select_manifest",
                "dry_run_manifest",
                "import_manifest",
                "import_latest",
                "dry_run_all",
                "import_all",
            ],
        )

    def test_actions_delegate_to_pipeline(self):
        pipeline = FakePipeline()
        actions = UnrealEditorWidgetActions(pipeline)

        self.assertEqual(actions.dry_run_selected_manifest("manifest.json"), {"method": "dry_run_manifest"})
        self.assertEqual(actions.import_selected_manifest("manifest.json"), {"method": "import_manifest"})
        self.assertEqual(actions.import_latest_export("Exports"), {"method": "import_latest_manifest"})
        self.assertEqual(actions.dry_run_all_exports("Exports"), {"method": "import_all_manifests", "dry_run": True})
        self.assertEqual(actions.import_all_exports("Exports"), {"method": "import_all_manifests", "dry_run": False})
        self.assertEqual(
            pipeline.calls,
            [
                ("dry_run_manifest", "manifest.json", None),
                ("import_manifest", "manifest.json", None),
                ("import_latest_manifest", "Exports", None, False),
                ("import_all_manifests", "Exports", None, True),
                ("import_all_manifests", "Exports", None, False),
            ],
        )

    def test_script_exposes_editor_widget_action_plan(self):
        action_ids = [item["id"] for item in get_editor_widget_action_plan()]

        self.assertIn("import_all", action_ids)


class FakePipeline(object):
    def __init__(self):
        self.calls = []

    def dry_run_manifest(self, manifest_path, log_path=None):
        self.calls.append(("dry_run_manifest", manifest_path, log_path))
        return {"method": "dry_run_manifest"}

    def import_manifest(self, manifest_path, log_path=None):
        self.calls.append(("import_manifest", manifest_path, log_path))
        return {"method": "import_manifest"}

    def import_latest_manifest(self, export_root, log_path=None, dry_run=False):
        self.calls.append(("import_latest_manifest", export_root, log_path, dry_run))
        return {"method": "import_latest_manifest"}

    def import_all_manifests(self, export_root, report_path=None, dry_run=False):
        self.calls.append(("import_all_manifests", export_root, report_path, dry_run))
        return {"method": "import_all_manifests", "dry_run": dry_run}


if __name__ == "__main__":
    unittest.main()
