from __future__ import absolute_import

import json
import os
import shutil
import tempfile
import unittest

from asset_forge.unreal.editor_menu import (
    MENU_COMMAND,
    choose_package_directory,
    dry_run_gate_for_package_dir,
    import_approved_package_dir,
    latest_maya_package_dir,
    preview_gate_for_package_dir,
    register_asset_forge_menus,
    run_accept_flow_for_package_dir,
    run_accept_flow_from_directory_dialog,
    _confirm_import_package,
)


class UnrealEditorMenuTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_registers_main_menu_and_toolbar_entries(self):
        fake_unreal = FakeUnreal()

        report = register_asset_forge_menus(fake_unreal)

        self.assertEqual(report["status"], "success")
        self.assertIn("LevelEditor.MainMenu.Tools", report["registered"])
        self.assertIn("LevelEditor.LevelEditorToolBar.User", report["registered"])
        main_entry = fake_unreal.ToolMenus.menus.menus["LevelEditor.MainMenu.Tools"].entries[0]
        toolbar_entry = fake_unreal.ToolMenus.menus.menus["LevelEditor.LevelEditorToolBar.User"].entries[0]
        self.assertEqual(main_entry.command, MENU_COMMAND)
        self.assertEqual(toolbar_entry.command, MENU_COMMAND)
        self.assertEqual(toolbar_entry.type, "toolbar")
        self.assertTrue(fake_unreal.ToolMenus.menus.refreshed)

    def test_toolbar_registration_falls_back_to_root_toolbar_menu(self):
        fake_unreal = FakeUnreal()
        fake_unreal.ToolMenus.menus.fail_menu_names.add("LevelEditor.LevelEditorToolBar.User")

        report = register_asset_forge_menus(fake_unreal)

        self.assertEqual(report["status"], "success")
        self.assertIn("LevelEditor.MainMenu.Tools", report["registered"])
        self.assertIn("LevelEditor.LevelEditorToolBar", report["registered"])
        self.assertNotIn("LevelEditor.LevelEditorToolBar.User", report["registered"])
        toolbar_entry = fake_unreal.ToolMenus.menus.menus["LevelEditor.LevelEditorToolBar"].entries[0]
        self.assertEqual(toolbar_entry.command, MENU_COMMAND)
        self.assertEqual(toolbar_entry.type, "toolbar")

    def test_choose_package_directory_normalizes_dialog_result(self):
        fake_unreal = FakeUnreal()
        fake_unreal.DesktopPlatform.result = (True, "E:\\Package\\SM_Crate")

        path = choose_package_directory("E:\\Package", fake_unreal)

        self.assertEqual(path, "E:/Package/SM_Crate")

    def test_latest_maya_package_dir_reads_newest_export_success(self):
        log_path = os.path.join(self.temp_dir, "latest_maya.log")
        with open(log_path, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"operation": "export_success", "outputs": {"package_dir": "E:/Package/SM_old"}}) + "\n")
            stream.write(json.dumps({"operation": "export_success", "outputs": {"package_dir": "E:/Package/SM_new"}}) + "\n")

        self.assertEqual(latest_maya_package_dir(log_path), "E:/Package/SM_new")

    def test_directory_dialog_uses_latest_maya_package_as_default(self):
        fake_unreal = FakeUnreal()
        fake_unreal.DesktopPlatform.result = ""

        report = run_accept_flow_from_directory_dialog("E:/Package/SM_latest", fake_unreal)

        self.assertEqual(report["status"], "error")
        self.assertIn("E:/Package/SM_latest", fake_unreal.DesktopPlatform.calls[0])
        self.assertTrue(fake_unreal.EditorDialog.messages)

    def test_choose_package_directory_falls_back_to_valid_latest_package_without_desktop_dialog(self):
        package_dir = os.path.join(self.temp_dir, "SM_Crate")
        os.makedirs(package_dir)
        with open(os.path.join(package_dir, "SM_Crate_manifest.json"), "w", encoding="utf-8") as stream:
            stream.write("{}\n")
        fake_unreal = FakeUnreal()
        fake_unreal.DesktopPlatform = None

        path = choose_package_directory(package_dir, fake_unreal)

        self.assertEqual(path, package_dir.replace("\\", "/"))

    def test_import_confirmation_reports_target_and_existing_asset_count(self):
        package_dir = os.path.join(self.temp_dir, "SM_Crate")
        os.makedirs(package_dir)
        with open(os.path.join(package_dir, "SM_Crate_manifest.json"), "w", encoding="utf-8") as stream:
            json.dump({"asset_name": "SM_Crate", "target_path": "/Game/Props/Crate"}, stream)
        project_path = os.path.join(self.temp_dir, "AssetForgeBuildProxy.uproject")
        with open(project_path, "w", encoding="utf-8") as stream:
            json.dump({"EngineAssociation": "5.5"}, stream)
        fake_unreal = FakeUnreal()
        fake_unreal.Paths.project_file_path = project_path
        fake_unreal.SystemLibrary.engine_version = "5.5.4-AssetForgeTest"
        fake_unreal.EditorAssetLibrary.assets = ["/Game/Props/Crate/SM_Crate", "/Game/Props/Crate/Materials/MI_Crate"]

        self.assertTrue(_confirm_import_package(package_dir, fake_unreal))

        title, message, msg_type = fake_unreal.EditorDialog.messages[-1]
        self.assertEqual(title, "DCC AssetForge Import")
        self.assertEqual(msg_type, fake_unreal.AppMsgType.YES_NO)
        self.assertIn("资产：SM_Crate", message)
        self.assertIn("/Game/Props/Crate", message)
        self.assertIn("目标路径现有资产：2", message)
        self.assertIn("覆盖策略：", message)
        self.assertIn("UE 运行版本：5.5.4-AssetForgeTest", message)
        self.assertIn("工程版本标记：5.5", message)
        self.assertIn("package_acceptance_flow_report.json", message)
        self.assertIn("不会重建 /AssetForge", message)

    def test_import_confirmation_can_cancel(self):
        package_dir = os.path.join(self.temp_dir, "SM_Crate")
        os.makedirs(package_dir)
        with open(os.path.join(package_dir, "SM_Crate_manifest.json"), "w", encoding="utf-8") as stream:
            json.dump({"target_path": "/Game/Props/Crate"}, stream)
        fake_unreal = FakeUnreal()
        fake_unreal.EditorDialog.return_value = fake_unreal.AppReturnType.NO

        self.assertFalse(_confirm_import_package(package_dir, fake_unreal))

    def test_import_confirmation_treats_closed_dialog_as_cancel(self):
        package_dir = os.path.join(self.temp_dir, "SM_Crate")
        os.makedirs(package_dir)
        with open(os.path.join(package_dir, "SM_Crate_manifest.json"), "w", encoding="utf-8") as stream:
            json.dump({"target_path": "/Game/Props/Crate"}, stream)
        fake_unreal = FakeUnreal()
        fake_unreal.EditorDialog.return_value = None

        self.assertFalse(_confirm_import_package(package_dir, fake_unreal))

    def test_import_confirmation_blocks_when_dialog_unavailable(self):
        package_dir = os.path.join(self.temp_dir, "SM_Crate")
        os.makedirs(package_dir)
        with open(os.path.join(package_dir, "SM_Crate_manifest.json"), "w", encoding="utf-8") as stream:
            json.dump({"target_path": "/Game/Props/Crate"}, stream)
        fake_unreal = FakeUnreal()
        fake_unreal.EditorDialog = None

        self.assertFalse(_confirm_import_package(package_dir, fake_unreal))

    def test_direct_import_entry_requires_explicit_confirmation(self):
        fake_unreal = FakeUnreal()

        report = run_accept_flow_for_package_dir("E:/Package/SM_Crate", unreal_module=fake_unreal)

        self.assertEqual(report["status"], "cancelled")

    def test_menu_import_does_not_bootstrap_plugin_assets_by_default(self):
        from asset_forge.unreal import acceptance_runner

        package_dir = os.path.join(self.temp_dir, "SM_Crate")
        os.makedirs(package_dir)
        captured = {}
        original = acceptance_runner.run_asset_forge_package_acceptance

        def fake_run(package_dir_arg, **kwargs):
            captured["package_dir"] = package_dir_arg
            captured.update(kwargs)
            return {"status": "success", "report_path": "E:/Report.json", "warnings": [], "errors": []}

        acceptance_runner.run_asset_forge_package_acceptance = fake_run
        try:
            report = run_accept_flow_for_package_dir(
                package_dir,
                unreal_module=FakeUnreal(),
                confirmed=True,
                import_options={"combine_meshes": True},
            )
        finally:
            acceptance_runner.run_asset_forge_package_acceptance = original

        self.assertEqual(report["status"], "success")
        self.assertFalse(captured["auto_bootstrap_material_assets"])
        self.assertTrue(captured["run_import"])
        self.assertEqual(captured["import_options"], {"combine_meshes": True})

    def test_preview_gate_runs_read_only_acceptance(self):
        from asset_forge.unreal import acceptance_runner

        package_dir = os.path.join(self.temp_dir, "SM_Crate")
        os.makedirs(package_dir)
        captured = {}
        original = acceptance_runner.run_asset_forge_package_acceptance

        def fake_run(package_dir_arg, **kwargs):
            captured["package_dir"] = package_dir_arg
            captured.update(kwargs)
            return {"status": "pass", "report_path": "E:/Preview.json", "warnings": [], "errors": []}

        acceptance_runner.run_asset_forge_package_acceptance = fake_run
        try:
            fake_unreal = FakeUnreal()
            report = preview_gate_for_package_dir(
                package_dir,
                unreal_module=fake_unreal,
                import_options={"build_nanite": False, "import_mesh_lods": True},
            )
        finally:
            acceptance_runner.run_asset_forge_package_acceptance = original

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["ui_action"], "gate_check")
        self.assertEqual(captured["package_dir"], package_dir)
        self.assertEqual(captured["command_args"], ["ue_gate", "--check", package_dir])
        self.assertFalse(captured["run_import"])
        self.assertFalse(captured["require_import"])
        self.assertFalse(captured["auto_bootstrap_material_assets"])
        self.assertEqual(captured["import_options"], {"build_nanite": False, "import_mesh_lods": True})
        self.assertIn("检查报告完成：pass", fake_unreal.EditorDialog.messages[-1][1])

    def test_dry_run_gate_uses_distinct_ui_action(self):
        from asset_forge.unreal import acceptance_runner

        package_dir = os.path.join(self.temp_dir, "SM_Crate")
        os.makedirs(package_dir)
        captured = {}
        original = acceptance_runner.run_asset_forge_package_acceptance

        def fake_run(package_dir_arg, **kwargs):
            captured["package_dir"] = package_dir_arg
            captured.update(kwargs)
            return {"status": "pass", "report_path": "E:/DryRun.json", "warnings": [], "errors": []}

        acceptance_runner.run_asset_forge_package_acceptance = fake_run
        try:
            fake_unreal = FakeUnreal()
            report = dry_run_gate_for_package_dir(package_dir, unreal_module=fake_unreal)
        finally:
            acceptance_runner.run_asset_forge_package_acceptance = original

        self.assertEqual(report["ui_action"], "dry_run_gate")
        self.assertEqual(captured["command_args"], ["ue_gate", "--dry-run", package_dir])
        self.assertFalse(captured["run_import"])
        self.assertFalse(captured["require_import"])
        self.assertIn("导入计划检查完成：pass", fake_unreal.EditorDialog.messages[-1][1])
        self.assertNotIn("模拟导入", fake_unreal.EditorDialog.messages[-1][1])

    def test_import_approved_package_requires_user_confirmation(self):
        from asset_forge.unreal import acceptance_runner

        package_dir = os.path.join(self.temp_dir, "SM_Crate")
        os.makedirs(package_dir)
        with open(os.path.join(package_dir, "SM_Crate_manifest.json"), "w", encoding="utf-8") as stream:
            json.dump({"asset_name": "SM_Crate", "target_path": "/Game/Props/Crate"}, stream)
        fake_unreal = FakeUnreal()
        fake_unreal.EditorDialog.return_value = fake_unreal.AppReturnType.NO
        calls = []
        original = acceptance_runner.run_asset_forge_package_acceptance
        acceptance_runner.run_asset_forge_package_acceptance = lambda *args, **kwargs: calls.append((args, kwargs)) or {"status": "success"}
        try:
            report = import_approved_package_dir(package_dir, unreal_module=fake_unreal)
        finally:
            acceptance_runner.run_asset_forge_package_acceptance = original

        self.assertEqual(report["status"], "cancelled")
        self.assertEqual(calls, [])


class FakeToolMenusClass(object):
    menus = None

    @classmethod
    def get(cls):
        cls.menus = cls.menus or FakeToolMenus()
        return cls.menus


class FakeToolMenus(object):
    def __init__(self):
        self.menus = {}
        self.refreshed = False
        self.fail_menu_names = set()

    def find_menu(self, name):
        if name in self.fail_menu_names:
            return None
        return self.menus.get(name)

    def extend_menu(self, name):
        if name in self.fail_menu_names:
            return None
        self.menus.setdefault(name, FakeMenu(name))
        return self.menus[name]

    def refresh_all_widgets(self):
        self.refreshed = True


class FakeMenu(object):
    def __init__(self, name):
        self.name = name
        self.entries = []

    def add_menu_entry(self, section, entry):
        entry.section = section
        self.entries.append(entry)


class FakeEntry(object):
    def __init__(self, name="", type=None, **kwargs):
        self.name = name
        self.type = type
        self.command = ""

    def set_label(self, label):
        self.label = label

    def set_tool_tip(self, tool_tip):
        self.tool_tip = tool_tip

    def set_string_command(self, command_type, custom_type, command):
        self.command_type = command_type
        self.command = command


class FakeDesktopPlatform(object):
    result = ""
    calls = []

    @classmethod
    def open_directory_dialog(cls, *args):
        cls.calls.append(args)
        return cls.result


class FakeUnreal(object):
    ToolMenus = FakeToolMenusClass
    ToolMenuEntry = FakeEntry
    DesktopPlatform = FakeDesktopPlatform
    EditorDialog = None
    Paths = None
    SystemLibrary = None

    class MultiBlockType(object):
        MENU_ENTRY = "menu"
        TOOL_BAR_BUTTON = "toolbar"

    class ToolMenuStringCommandType(object):
        PYTHON = "python"

    class AppMsgType(object):
        OK = "ok"
        YES_NO = "yes_no"

    class AppReturnType(object):
        YES = "yes"
        NO = "no"

    def __init__(self):
        self.ToolMenus.menus = FakeToolMenus()
        self.DesktopPlatform.result = ""
        self.DesktopPlatform.calls = []
        self.EditorDialog = FakeEditorDialog()
        self.EditorAssetLibrary = FakeEditorAssetLibrary()
        self.Paths = FakePaths()
        self.SystemLibrary = FakeSystemLibrary()


class FakeEditorDialog(object):
    def __init__(self):
        self.messages = []
        self.return_value = "yes"

    def show_message(self, title, message, msg_type=None):
        self.messages.append((title, message, msg_type))
        return self.return_value


class FakeEditorAssetLibrary(object):
    def __init__(self):
        self.assets = []

    def list_assets(self, path, recursive=True, include_folder=False):
        return [asset for asset in self.assets if asset.startswith(path)]


class FakePaths(object):
    def __init__(self):
        self.project_file_path = ""

    def get_project_file_path(self):
        return self.project_file_path


class FakeSystemLibrary(object):
    def __init__(self):
        self.engine_version = "Unknown"

    def get_engine_version(self):
        return self.engine_version


if __name__ == "__main__":
    unittest.main()
