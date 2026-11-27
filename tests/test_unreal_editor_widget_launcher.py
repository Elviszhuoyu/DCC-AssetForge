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
        launcher = UnrealEditorWidgetLauncher(FakeUnreal(existing_assets=["/AssetForge/Editor/EUW_AssetForgeGate"]))

        plan = launcher.launch_plan()

        self.assertEqual(plan["status"], "ready")
        self.assertTrue(plan["asset_exists"])
        self.assertEqual(plan["issues"], [])

    def test_launch_plan_creates_widget_asset_before_fallback(self):
        fake_unreal = FakeGeneratingUnreal(existing_assets=[])
        launcher = UnrealEditorWidgetLauncher(fake_unreal)

        plan = launcher.launch_plan()

        self.assertEqual(plan["status"], "ready")
        self.assertTrue(plan["asset_exists"])
        self.assertTrue(plan["widget_asset_report"]["created"])
        self.assertFalse(plan["fallback_available"])

    def test_native_launch_uses_the_unified_tab_without_generating_a_widget(self):
        from unittest.mock import Mock

        fake = FakeUnreal(existing_assets=[])
        fake.AssetForgeEditorMaterialCommentLibrary = object()
        fake.SystemLibrary = Mock()
        fake.subsystem.does_tab_exist = Mock(return_value=True)
        launcher = UnrealEditorWidgetLauncher(fake)
        launcher._ensure_widget_asset = Mock(side_effect=AssertionError("unexpected EUW creation"))
        self.assertEqual(launcher.launch_plan()["tab_id"], "AssetForge.GateWorkbench")
        fake.SystemLibrary.execute_console_command.assert_not_called()
        result = launcher.launch()
        self.assertEqual(result["status"], "launched")
        fake.SystemLibrary.execute_console_command.assert_called_once_with(None, "AssetForge.OpenGate")
        fake.subsystem.does_tab_exist.assert_called_once_with("AssetForge.GateWorkbench")
        fake.subsystem.does_tab_exist.return_value = False
        self.assertEqual(launcher.launch()["status"], "error")

    def test_launch_uses_editor_utility_subsystem_when_available(self):
        fake_unreal = FakeUnreal(existing_assets=["/AssetForge/Editor/EUW_AssetForgeGate"])
        launcher = UnrealEditorWidgetLauncher(fake_unreal)

        report = launcher.launch()

        self.assertEqual(report["status"], "launched")
        self.assertIs(fake_unreal.subsystem.spawned[0], fake_unreal.EditorAssetLibrary.assets["/AssetForge/Editor/EUW_AssetForgeGate"])

    def test_script_entrypoints_expose_widget_launch_plan(self):
        plan = get_editor_widget_launch_plan()
        report = launch_asset_forge_widget()

        self.assertEqual(plan["asset_path"], "/AssetForge/Editor/EUW_AssetForgeGate")
        self.assertEqual(report["status"], "missing_asset")

    def test_missing_widget_asset_launches_python_gate_and_imports_after_preflight(self):
        fake_unreal = FakeUnreal(existing_assets=[])
        fake_actions = FakeActions()
        launcher = UnrealEditorWidgetLauncher(
            fake_unreal,
            actions=fake_actions,
            gate_state_builder=fake_gate_state_builder,
        )

        report = launcher.launch()

        self.assertEqual(report["status"], "imported")
        self.assertEqual(report["ui_mode"], "python_dialog_gate")
        self.assertEqual(report["selected_package_dir"], "E:/Exports/SM_Crate")
        self.assertIn("profile_status", report["displayed_sections"])
        self.assertEqual(fake_actions.imported[0], "E:/Exports/SM_Crate")
        self.assertTrue(fake_unreal.EditorDialog.messages)

    def test_python_gate_closed_confirmation_does_not_import(self):
        fake_unreal = FakeUnreal(existing_assets=[])
        fake_unreal.EditorDialog.return_value = None
        fake_actions = FakeActions()
        launcher = UnrealEditorWidgetLauncher(
            fake_unreal,
            actions=fake_actions,
            gate_state_builder=fake_gate_state_builder,
        )

        report = launcher.launch()

        self.assertEqual(report["status"], "ready_to_import")
        self.assertEqual(fake_actions.imported, [])


class FakeUnreal(object):
    class EditorUtilitySubsystem(object):
        pass

    class EditorAssetLibrary(object):
        existing_assets = set()
        assets = {}

        @classmethod
        def does_asset_exist(cls, asset_path):
            return asset_path in cls.existing_assets

        @classmethod
        def load_asset(cls, asset_path):
            return cls.assets.get(asset_path) or "asset:" + asset_path

        @classmethod
        def save_asset(cls, asset_path, only_if_is_dirty=False):
            return True

    def __init__(self, existing_assets):
        self.EditorAssetLibrary.existing_assets = set(existing_assets)
        self.EditorAssetLibrary.assets = {}
        for asset_path in existing_assets:
            if asset_path.endswith("EUW_AssetForgeGate"):
                widget_asset = FakeWidgetAsset()
                self.EditorAssetLibrary.assets[asset_path] = widget_asset
                self.EditorAssetLibrary.assets[asset_path + ".EUW_AssetForgeGate"] = widget_asset
                self.EditorAssetLibrary.existing_assets.add(asset_path + ".EUW_AssetForgeGate")
        self.subsystem = FakeEditorUtilitySubsystem()
        self.EditorDialog = FakeEditorDialog()
        self.DesktopPlatform = FakeDesktopPlatform()

    class VerticalBox(object):
        pass

    class HorizontalBox(object):
        pass

    class TextBlock(object):
        pass

    class Button(object):
        pass

    class ScrollBox(object):
        pass

    class EditableTextBox(object):
        pass

    class ComboBoxString(object):
        pass

    class ListView(object):
        pass

    class CheckBox(object):
        pass

    class Text(object):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return self.value

    class AppMsgType(object):
        OK = "ok"
        YES_NO = "yes_no"

    class AppReturnType(object):
        YES = "yes"
        NO = "no"

    def get_editor_subsystem(self, subsystem_class):
        return self.subsystem


class FakeGeneratingUnreal(FakeUnreal):
    class EditorUtilityWidgetBlueprintFactory(object):
        pass

    def __init__(self, existing_assets):
        super(FakeGeneratingUnreal, self).__init__(existing_assets)
        self.AssetToolsHelpers = FakeAssetToolsHelpers(self.EditorAssetLibrary)


class FakeAssetToolsHelpers(object):
    def __init__(self, library):
        self.library = library

    def get_asset_tools(self):
        return FakeAssetTools(self.library)


class FakeAssetTools(object):
    def __init__(self, library):
        self.library = library

    def create_asset(self, name, package_path, asset_class, factory):
        asset_path = package_path + "/" + name
        asset = FakeWidgetAsset()
        self.library.existing_assets.add(asset_path)
        self.library.existing_assets.add(asset_path + "." + name)
        self.library.assets[asset_path] = asset
        self.library.assets[asset_path + "." + name] = asset
        return asset


class FakeWidgetAsset(object):
    def __init__(self):
        self.widget_tree = FakeWidgetTree()


class FakeWidgetTree(object):
    def __init__(self):
        self.root_widget = None

    def construct_widget(self, widget_class, name):
        return FakeWidget(name)

    def find_widget(self, name):
        return self._walk(self.root_widget, name)

    def set_editor_property(self, property_name, value):
        if property_name == "root_widget":
            self.root_widget = value

    def _walk(self, widget, name):
        if widget is None:
            return None
        if widget.name == name:
            return widget
        for child in widget.children:
            found = self._walk(child, name)
            if found is not None:
                return found
        return None


class FakeWidget(object):
    def __init__(self, name):
        self.name = name
        self.children = []

    def add_child(self, child):
        self.children.append(child)

    def set_text(self, text):
        self.text = str(text)

    def set_editor_property(self, property_name, value):
        setattr(self, property_name, value)


class FakeEditorUtilitySubsystem(object):
    def __init__(self):
        self.spawned = []

    def spawn_and_register_tab(self, widget_asset):
        self.spawned.append(widget_asset)


class FakeEditorDialog(object):
    def __init__(self):
        self.messages = []
        self.return_value = "yes"

    def show_message(self, title, message, msg_type=None):
        self.messages.append((title, message, msg_type))
        return self.return_value


class FakeDesktopPlatform(object):
    def open_directory_dialog(self, *args):
        return (True, "E:/Exports/SM_Crate")


class FakeActions(object):
    def __init__(self):
        self.imported = []

    def import_selected_package(self, package_dir, report_path=None):
        self.imported.append(package_dir)
        return {"status": "success", "report_path": report_path or "E:/Reports/gate.json"}


def fake_gate_state_builder(package_dir="", export_root="", latest_maya_log_path="", latest_unreal_log_path="", report_path=None):
    selected = package_dir or "E:/Exports/SM_Crate"
    package = {
        "package_dir": selected,
        "asset_name": "SM_Crate",
        "target_path": "/Game/Props/SM_Crate",
        "asset_count": 1,
        "mesh_status": "ready",
        "texture_count": 2,
        "texture_status": "ready",
        "material_count": 1,
        "material_status": "ready",
        "profile_name": "Props_Opaque_PainterUE_ARM",
        "profile_status": "ready",
        "profile_count": 1,
        "gate_status": "pass",
        "can_accept": True,
        "warning_count": 0,
        "error_count": 0,
        "warnings": [],
        "errors": [],
        "next_action": "Import.",
        "report_path": "E:/Reports/gate.json",
    }
    return {
        "status": "ready",
        "export_root": export_root,
        "history": {"package_count": 1, "latest_package_dir": selected, "packages": [package]},
        "selected_package_dir": selected,
        "selected_package": package,
        "sections": [],
        "can_import": True,
        "next_action": "Import.",
    }


if __name__ == "__main__":
    unittest.main()
