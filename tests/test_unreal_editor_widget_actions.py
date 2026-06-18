# -*- coding: utf-8 -*-

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
                "refresh_packages",
                "scan_export_directory",
                "ensure_widget_asset",
                "read_widget_tree",
                "select_manifest",
                "select_package",
                "dry_run_manifest",
                "import_manifest",
                "dry_run_package",
                "preview_package_gate",
                "open_report",
                "import_package",
                "dry_run_all",
                "import_all",
            ],
        )

    def test_action_plan_uses_chinese_gate_ui_labels(self):
        plan = UnrealEditorWidgetActions(FakePipeline()).action_plan()
        labels = [item["label"] for item in plan]
        descriptions = [item["description"] for item in plan]

        self.assertIn("刷新包体", labels)
        self.assertIn("生成入审报告", labels)
        self.assertIn("预演导入计划", labels)
        self.assertIn("正式导入", labels)
        self.assertTrue(any("入审报告" in item or "预演导入计划" in item for item in descriptions))

    def test_actions_delegate_to_pipeline(self):
        pipeline = FakePipeline()
        actions = UnrealEditorWidgetActions(pipeline, package_gate_preview=fake_gate_preview, package_import=fake_package_import)

        self.assertEqual(actions.refresh_package_history("Exports", "__missing_maya__", "__missing_unreal__")["status"], "empty")
        self.assertEqual(actions.scan_export_directory("__missing_export__")["status"], "empty")
        self.assertEqual(actions.preview_selected_package_gate("Package"), {"method": "preview_package_gate"})
        self.assertEqual(actions.open_report("__missing_report__")["status"], "missing")
        self.assertEqual(actions.dry_run_selected_manifest("manifest.json"), {"method": "dry_run_manifest"})
        self.assertEqual(actions.import_selected_manifest("manifest.json"), {"method": "import_manifest"})
        self.assertEqual(actions.dry_run_selected_package("Package"), {"method": "import_asset_forge_package", "dry_run": True})
        self.assertEqual(actions.import_selected_package("Package"), {"method": "import_approved_package_dir"})
        blocked_latest = actions.import_latest_export("Exports")
        self.assertEqual(blocked_latest["status"], "blocked")
        self.assertFalse(blocked_latest["can_import"])
        self.assertEqual(actions.import_latest_export("Exports", dry_run=True), {"method": "import_latest_manifest"})
        self.assertEqual(actions.dry_run_all_exports("Exports"), {"method": "import_all_manifests", "dry_run": True})
        self.assertEqual(actions.import_all_exports("Exports"), {"method": "import_all_manifests", "dry_run": False})
        self.assertEqual(
            pipeline.calls,
            [
                ("dry_run_manifest", "manifest.json", None),
                ("import_manifest", "manifest.json", None),
                ("import_asset_forge_package", "Package", True, None),
                ("import_latest_manifest", "Exports", None, True),
                ("import_all_manifests", "Exports", None, True),
                ("import_all_manifests", "Exports", None, False),
            ],
        )

    def test_script_exposes_editor_widget_action_plan(self):
        action_ids = [item["id"] for item in get_editor_widget_action_plan()]

        self.assertIn("import_all", action_ids)
        self.assertIn("preview_package_gate", action_ids)
        self.assertNotIn("import_latest", action_ids)

    def test_open_report_uses_injected_opener_for_existing_report(self):
        import os
        import shutil
        import tempfile

        temp_dir = tempfile.mkdtemp()
        try:
            report_path = os.path.join(temp_dir, "package_acceptance_flow_report.json")
            with open(report_path, "w", encoding="utf-8") as stream:
                stream.write("{}\n")
            opened = []
            actions = UnrealEditorWidgetActions(FakePipeline(), report_opener=opened.append)

            report = actions.open_report(report_path)

            self.assertEqual(report["status"], "opened")
            self.assertTrue(report["can_open"])
            self.assertEqual(opened, [report_path.replace("\\", "/")])
        finally:
            shutil.rmtree(temp_dir)


def fake_gate_preview(package_dir, report_path=None):
    return {"method": "preview_package_gate"}


def fake_package_import(package_dir, report_path=None):
    return {"method": "import_approved_package_dir"}


class FakePipeline(object):
    def __init__(self):
        self.calls = []

    def dry_run_manifest(self, manifest_path, log_path=None):
        self.calls.append(("dry_run_manifest", manifest_path, log_path))
        return {"method": "dry_run_manifest"}

    def import_manifest(self, manifest_path, log_path=None):
        self.calls.append(("import_manifest", manifest_path, log_path))
        return {"method": "import_manifest"}

    def import_asset_forge_package(self, package_dir, dry_run=False, report_path=None):
        self.calls.append(("import_asset_forge_package", package_dir, dry_run, report_path))
        return {"method": "import_asset_forge_package", "dry_run": dry_run}

    def import_latest_manifest(self, export_root, log_path=None, dry_run=False):
        self.calls.append(("import_latest_manifest", export_root, log_path, dry_run))
        return {"method": "import_latest_manifest"}

    def import_all_manifests(self, export_root, report_path=None, dry_run=False):
        self.calls.append(("import_all_manifests", export_root, report_path, dry_run))
        return {"method": "import_all_manifests", "dry_run": dry_run}


if __name__ == "__main__":
    unittest.main()
