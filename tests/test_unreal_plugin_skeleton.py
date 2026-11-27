from __future__ import absolute_import

import json
import os
import importlib.util
import shutil
import tempfile
import unittest

from asset_forge.unreal.material_package_schema import get_default_material_package_plan
from asset_forge.unreal.doctor import run_asset_forge_doctor
from asset_forge.unreal.plugin_content_bootstrap import UnrealPluginContentBootstrap
from asset_forge.unreal.plugin_mount_preflight import UnrealPluginMountPreflight


class UnrealPluginSkeletonTest(unittest.TestCase):
    def test_assetforge_plugin_descriptor_matches_material_mount(self):
        plugin_path = os.path.join("Plugins", "AssetForge", "AssetForge.uplugin")

        with open(plugin_path, "r", encoding="utf-8") as stream:
            descriptor = json.load(stream)
        plan = get_default_material_package_plan()

        self.assertEqual(descriptor["FriendlyName"], "DCC AssetForge")
        self.assertTrue(descriptor["CanContainContent"])
        self.assertEqual(
            descriptor.get("Modules", []),
            [{"Name": "AssetForgeEditor", "Type": "Editor", "LoadingPhase": "Default"}],
        )
        self.assertIn("PythonScriptPlugin", [item["Name"] for item in descriptor["Plugins"]])
        self.assertIn("EditorScriptingUtilities", [item["Name"] for item in descriptor["Plugins"]])
        self.assertEqual(plan["content_mount"], "/AssetForge")
        self.assertEqual(plan["disk_content_root"], "Plugins/AssetForge/Content")

    def test_doctor_confirms_plugin_cpp_module_policy(self):
        temp_dir = tempfile.mkdtemp()
        try:
            report = run_asset_forge_doctor(os.getcwd(), os.path.join(temp_dir, "doctor.json"))
            checks = dict((item["id"], item) for item in report["checks"])

            self.assertEqual(checks["plugin_cpp_modules"]["status"], "pass")
            self.assertIn("Editor C++", checks["plugin_cpp_modules"]["message"])
            self.assertEqual(checks["maya_bootstrap_launcher"]["status"], "pass")
            self.assertEqual(checks["ue_python_init"]["status"], "pass")
            self.assertEqual(checks["manifest_schema_smoke"]["status"], "pass")
            self.assertEqual(checks["maya_operation_log_writable"]["status"], "pass")
            self.assertEqual(checks["unreal_operation_log_writable"]["status"], "pass")
            self.assertIn("manual_validation_required", report)
            self.assertIn("pretest_summary", report)
        finally:
            shutil.rmtree(temp_dir)

    def test_plugin_content_directories_exist_for_default_material_package(self):
        expected_dirs = [
            os.path.join("Plugins", "AssetForge", "Content", "Materials"),
            os.path.join("Plugins", "AssetForge", "Content", "MaterialFunctions"),
            os.path.join("Plugins", "AssetForge", "Content", "ParameterCollections"),
            os.path.join("Plugins", "AssetForge", "Content", "Python"),
        ]

        for directory in expected_dirs:
            self.assertTrue(os.path.isdir(directory), directory)

    def test_plugin_python_bootstrap_exposes_editor_widget_actions(self):
        init_path = os.path.join("Plugins", "AssetForge", "Content", "Python", "init_unreal.py")
        temp_dir = tempfile.mkdtemp()
        old_log_root = os.environ.get("ASSET_FORGE_LOG_ROOT")

        try:
            os.environ["ASSET_FORGE_LOG_ROOT"] = temp_dir
            module = self._load_module(init_path)

            self.assertTrue(os.path.isdir(module.BOOTSTRAP_REPORT["repo_root"]))
            self.assertTrue(os.path.isdir(os.path.join(module.BOOTSTRAP_REPORT["repo_root"], "asset_forge")))
            self.assertIn("Content/Python", module.BOOTSTRAP_REPORT["plugin_python_dir"])
            self.assertIn("added_python_paths", module.BOOTSTRAP_REPORT)
            self.assertIn("import_package", module.BOOTSTRAP_REPORT["actions"])
            self.assertGreater(module.BOOTSTRAP_REPORT["action_count"], 0)
            self.assertEqual(module.BOOTSTRAP_REPORT["widget_asset_path"], "/AssetForge/Editor/EUW_AssetForgeGate")
            self.assertEqual(module.BOOTSTRAP_REPORT["widget_launch_status"], "missing_asset")
            self.assertEqual(module.BOOTSTRAP_REPORT["material_content_mount"], "/AssetForge")
            self.assertEqual(module.BOOTSTRAP_REPORT["material_asset_count"], 36)
            self.assertEqual(module.BOOTSTRAP_REPORT["menu_register_status"], "skipped")
            self.assertIn("C++ Slate UI", module.BOOTSTRAP_REPORT["tool_menu_command"])
            self.assertTrue(module.BOOTSTRAP_REPORT["unreal_log_path"].endswith("latest_unreal.log"))
            self.assertTrue(os.path.exists(module.BOOTSTRAP_REPORT["unreal_log_path"]))
        finally:
            if old_log_root is None:
                os.environ.pop("ASSET_FORGE_LOG_ROOT", None)
            else:
                os.environ["ASSET_FORGE_LOG_ROOT"] = old_log_root
            shutil.rmtree(temp_dir)

    def test_native_bootstrap_queries_tab_without_spawning_it_or_generating_a_legacy_asset(self):
        from unittest.mock import Mock, patch

        source = os.path.join("Plugins", "AssetForge", "Content", "Python", "init_unreal.py")
        # The descriptor may load before Python exposes the module's reflected class.
        ue = FakeUnreal(existing_assets=[])
        ue.SystemLibrary = Mock()
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"ASSET_FORGE_LOG_ROOT": root}), \
                patch("asset_forge.unreal.editor_widget_launcher.get_unreal", return_value=ue), \
                patch("asset_forge.unreal.editor_widget_asset.ensure_editor_widget_asset") as create:
            report = self._load_module(source).BOOTSTRAP_REPORT
        self.assertEqual(report["widget_launch_status"], "awaiting_native")
        self.assertEqual(report["widget_tab_id"], "AssetForge.GateWorkbench")
        self.assertEqual(report["widget_asset_path"], "")
        create.assert_not_called()
        ue.SystemLibrary.execute_console_command.assert_not_called()

    def test_bootstrap_reports_missing_plugin_assets_without_creating_project_content(self):
        report = UnrealPluginContentBootstrap(unreal_module=FakeUnreal(existing_assets=[])).validate()

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["content_mount"], "/AssetForge")
        self.assertIn("/AssetForge/Materials/M_AF_Props_Master", report["missing_assets"])
        self.assertIn("/AssetForge/MaterialInstances/MI_AF_Props_Default", report["missing_assets"])
        self.assertEqual(report["missing_compatibility_assets"], [])
        self.assertNotIn("/Game/AssetForge/Materials/M_AF_Props_Opaque", report["missing_assets"])

    def test_bootstrap_passes_when_planned_plugin_assets_exist(self):
        plan = get_default_material_package_plan()
        existing_assets = []
        existing_assets.extend(texture["path"] for texture in plan["placeholder_textures"])
        existing_assets.extend(material["path"] for material in plan["materials"])
        existing_assets.extend(material_instance["path"] for material_instance in plan["material_instances"])
        existing_assets.extend(function["path"] for function in plan["functions"])
        existing_assets.extend(collection["path"] for collection in plan["parameter_collections"])

        report = UnrealPluginContentBootstrap(unreal_module=FakeUnreal(existing_assets)).validate(plan)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["missing_assets"], [])

    def test_bootstrap_rescans_only_disk_present_registry_misses_in_one_call(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        existing = "/AssetForge/Textures/T_Existing"
        first = "/AssetForge/Materials/M_Disk"
        second = "/AssetForge/Materials/M_AlsoDisk"
        third = "/AssetForge/Textures/T_Disk"
        missing = "/AssetForge/MaterialInstances/MI_Missing"
        registered = {existing}
        registry = Mock()
        registry.scan_paths_synchronous.side_effect = lambda *_: registered.update((first, second, third))
        ue = SimpleNamespace(
            Paths=object(),
            EditorAssetLibrary=SimpleNamespace(does_asset_exist=lambda path: path in registered),
            AssetRegistryHelpers=SimpleNamespace(get_asset_registry=lambda: registry),
        )
        plan = {"content_mount": "/AssetForge", "materials": [{"path": path} for path in (existing, first, second, third, missing)]}
        bootstrap = UnrealPluginContentBootstrap(ue, "Unused/AssetForge.uplugin")
        disk_files = {"M_Disk.uasset", "M_AlsoDisk.uasset", "T_Disk.uasset"}
        is_file = patch("asset_forge.unreal.plugin_content_bootstrap.os.path.isfile",
                        side_effect=lambda path: os.path.basename(path) in disk_files)
        with patch("asset_forge.unreal.plugin_content_bootstrap.os.path.isdir", return_value=True), is_file:
            checks = bootstrap._asset_checks(plan, {"status": "pass"})
        registry.scan_paths_synchronous.assert_called_once_with(["/AssetForge/Materials", "/AssetForge/Textures"], True)
        registry.wait_for_completion.assert_not_called()
        self.assertEqual([row["status"] for row in checks], ["pass", "pass", "pass", "pass", "warning"])

    def test_bootstrap_batches_unknown_mounts_with_the_older_load_only_api(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        first = "/AssetForge/Materials/M_Disk"
        second = "/AssetForge/Materials/M_Missing"
        registered = set()
        registry = Mock()
        registry.scan_paths_synchronous.side_effect = lambda *_: registered.add(first + ".M_Disk")
        ue = SimpleNamespace(
            EditorAssetLibrary=SimpleNamespace(load_asset=lambda path: path if path in registered else None),
            AssetRegistryHelpers=SimpleNamespace(get_asset_registry=lambda: registry),
        )
        bootstrap = UnrealPluginContentBootstrap(ue, "Unused/AssetForge.uplugin")
        plan = {"materials": [{"path": first}, {"path": second, "required_for_import": False}]}
        checks = bootstrap._asset_checks(plan)
        registry.scan_paths_synchronous.assert_called_once_with(["/AssetForge/Materials"], True)
        registry.wait_for_completion.assert_not_called()
        self.assertEqual([row["status"] for row in checks], ["pass", "info"])

    def test_bootstrap_skips_asset_queries_when_plugin_is_not_mounted(self):
        fake_unreal = FakeUnrealWithExternalPlugin()
        fake_unreal.EditorAssetLibrary.query_count = 0

        report = UnrealPluginContentBootstrap(unreal_module=fake_unreal).validate()

        self.assertEqual(report["status"], "warning")
        self.assertIn("/AssetForge/Materials/M_AF_Props_Master", report["missing_assets"])
        self.assertIn("/AssetForge/MaterialInstances/MI_AF_Props_Default", report["missing_assets"])
        self.assertEqual(report["missing_compatibility_assets"], [])
        self.assertEqual(fake_unreal.EditorAssetLibrary.query_count, 0)
        self.assertIn("未安装或启用", [item for item in report["checks"] if item["id"] == "content_mount"][0]["message"])

    def test_bootstrap_prefers_installed_project_plugin_descriptor(self):
        fake_unreal = FakeUnrealWithInstalledPlugin()
        fake_unreal.EditorAssetLibrary.query_count = 0

        report = UnrealPluginContentBootstrap(unreal_module=fake_unreal).validate()

        self.assertEqual(report["status"], "warning")
        self.assertIn("UEProject/Plugins/AssetForge/AssetForge.uplugin", report["descriptor_path"])
        self.assertEqual([item for item in report["checks"] if item["id"] == "content_mount"][0]["status"], "pass")

    def test_bootstrap_passes_with_stock_marketplace_plugin_and_no_unused_folders(self):
        from pathlib import Path
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine_plugins = root / "EnginePlugins"
            plugin = engine_plugins / "Marketplace" / "AssetForge"
            for name in ("Materials", "MaterialInstances", "Textures", "Python"):
                (plugin / "Content" / name).mkdir(parents=True)
            descriptor = plugin / "AssetForge.uplugin"
            descriptor.write_text('{"CanContainContent": true}', encoding="utf-8")
            ue = SimpleNamespace(
                Paths=SimpleNamespace(
                    project_plugins_dir=lambda: str(root / "ProjectPlugins"),
                    engine_plugins_dir=lambda: str(engine_plugins),
                ),
                EditorAssetLibrary=SimpleNamespace(does_asset_exist=lambda path: True),
            )

            report = UnrealPluginContentBootstrap(ue).validate()

            self.assertEqual(report["descriptor_path"], descriptor.as_posix())
            self.assertEqual(report["status"], "pass")
            self.assertTrue(UnrealPluginMountPreflight(unreal_module=ue).check(report)["can_use_plugin_content"])

    def test_bootstrap_checks_registered_descriptor_and_mount_before_other_copies(self):
        from pathlib import Path
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_plugins = root / "ProjectPlugins"
            registered = root / "AdditionalPlugins" / "AssetForge" / "AssetForge.uplugin"
            project = project_plugins / "AssetForge" / "AssetForge.uplugin"
            for descriptor in (registered, project):
                (descriptor.parent / "Content").mkdir(parents=True)
                descriptor.write_text('{"CanContainContent": true}', encoding="utf-8")
            ue = SimpleNamespace(
                Paths=SimpleNamespace(project_plugins_dir=lambda: str(project_plugins)),
                PluginBlueprintLibrary=SimpleNamespace(
                    get_plugin_descriptor_file_path=lambda name: str(registered),
                    is_plugin_mounted=lambda name: True,
                ),
            )
            plan = {"content_mount": "/AssetForge"}
            bootstrap = UnrealPluginContentBootstrap(ue)

            report = bootstrap.validate(plan)
            self.assertEqual(report["descriptor_path"], registered.as_posix())
            self.assertEqual(report["status"], "pass")

            ue.PluginBlueprintLibrary.is_plugin_mounted = lambda name: False
            report = bootstrap.validate(plan)
            self.assertEqual(report["status"], "warning")
            self.assertFalse(UnrealPluginMountPreflight(content_bootstrap=bootstrap).check(report)["can_use_plugin_content"])

            # Losing the registered descriptor must not allow a stale local copy to validate.
            registered.unlink()
            ue.PluginBlueprintLibrary.is_plugin_mounted = lambda name: True
            report = bootstrap.validate(plan)
            self.assertEqual(report["descriptor_path"], registered.as_posix())
            self.assertEqual(report["status"], "error")
            self.assertFalse(UnrealPluginMountPreflight(content_bootstrap=bootstrap).check(report)["can_use_plugin_content"])

    def test_bootstrap_reports_a_missing_folder_when_the_plan_requires_it(self):
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory) / "AssetForge"
            (plugin / "Content").mkdir(parents=True)
            descriptor = plugin / "AssetForge.uplugin"
            descriptor.write_text('{"CanContainContent": true}', encoding="utf-8")
            plan = {"content_mount": "/AssetForge", "functions": [{"path": "/AssetForge/MaterialFunctions/MF_Test"}]}

            report = UnrealPluginContentBootstrap(FakeUnreal([]), str(descriptor)).validate(plan)

            self.assertEqual(report["status"], "error")
            missing = [check["path"] for check in report["checks"] if check["id"] == "plugin_directory" and check["status"] == "error"]
            self.assertEqual(missing, [(plugin / "Content" / "MaterialFunctions").as_posix()])

    def test_plugin_mount_preflight_focuses_on_content_root(self):
        fake_unreal = FakeUnrealWithInstalledPlugin()

        report = UnrealPluginMountPreflight(unreal_module=fake_unreal).check()

        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["can_use_plugin_content"])
        self.assertEqual(report["content_mount"], "/AssetForge")
        self.assertEqual(report["mount_check"]["status"], "pass")

    def test_plugin_mount_preflight_warns_when_not_installed(self):
        fake_unreal = FakeUnrealWithExternalPlugin()

        report = UnrealPluginMountPreflight(unreal_module=fake_unreal).check()

        self.assertEqual(report["status"], "warning")
        self.assertFalse(report["can_use_plugin_content"])
        self.assertEqual(report["mount_check"]["status"], "warning")

    def test_cpp_gate_workbench_scans_manifest_packages_instead_of_dummy_text(self):
        source_path = os.path.join("Plugins", "AssetForge", "Source", "AssetForgeEditor", "Private", "AssetForgeEditorModule.cpp")

        with open(source_path, "r", encoding="utf-8") as stream:
            source = stream.read()

        self.assertIn("FindManifestsRecursive", source)
        self.assertIn("*_manifest.json", source)
        self.assertIn("BuildPackageItemFromManifest", source)
        self.assertIn("DccPackageRootName", source)
        self.assertIn("dcc_packages", source)
        self.assertIn("AddPackageDirsFromLog", source)
        self.assertIn("latest_blender.log", source)
        self.assertIn("field_validation", source)
        self.assertIn("runtime_alias", source)
        self.assertIn("ASSET_FORGE_EXPORT_ROOT", source)
        self.assertIn("ASSET_FORGE_SOURCE_ROOT", source)
        self.assertIn("FilteredPackages", source)
        self.assertIn("HandleSearchChanged", source)
        self.assertIn("OnTextChanged", source)
        self.assertIn("StatePrefix", source)
        self.assertIn("[待检查]", source)
        self.assertIn("[可导入]", source)
        self.assertIn("[可导入 · 需复核]", source)
        self.assertIn("[已导入]", source)
        self.assertIn("[阻断]", source)
        self.assertIn("RiskSummary", source)
        self.assertIn("风险：警告 %d / 阻断 %d", source)
        self.assertIn("ListPrimaryLabel", source)
        self.assertIn("ListSecondaryLabel", source)
        self.assertIn("独立 Mesh %d / FBX %d / 贴图 %d / 材质 %d", source)
        self.assertIn("workbench_check_package", source)
        self.assertIn("workbench_prepare_package", source)
        self.assertIn("workbench_apply_package", source)
        self.assertIn("GetNextActionText", source)
        self.assertIn("HasSelectedPackage", source)
        self.assertIn("CanImportSelectedPackage", source)
        self.assertIn("GetFlowSummaryText", source)
        self.assertIn("包体摘要", source)
        self.assertIn("状态：未选择包体；导入动作禁用。", source)
        self.assertIn("状态：已选择包体；可先检查，导入等待报告放行。", source)
        self.assertIn("状态：报告已放行；可以导入当前包体。", source)
        self.assertIn("状态：报告未放行；请修复阻断项后重新检查。", source)
        self.assertIn("检查包体结构、风险和目标路径，生成检查报告；不创建 UE 资产。", source)
        self.assertIn("Gate.Import", source)
        self.assertIn("HandleImportClicked", source)
        self.assertIn("检查包体", source)
        self.assertIn("HandlePreviewClicked", source)
        self.assertIn("不写入验证", source)
        self.assertIn("确认导入", source)
        self.assertIn("GetReportStateText", source)
        self.assertIn("GetReportPermissionText", source)
        self.assertIn("GetReportRiskText", source)
        self.assertIn("导入许可", source)
        self.assertIn("风险计数", source)
        self.assertIn("AttachReportDecision", source)
        self.assertIn("JsonObjectField(Report, TEXT(\"summary\"))", source)
        self.assertIn("decision_label", source)
        self.assertIn("can_import", source)
        self.assertIn("warning_count", source)
        self.assertIn("error_count", source)
        self.assertIn("next_action", source)
        self.assertIn("报告待判定", source)
        self.assertIn("未选择包体；刷新扫描并在左侧选择一个 AF 包体。", source)
        self.assertIn("暂无报告；导入许可未生成，当前不应执行导入。", source)
        self.assertIn("报告已生成但未记录导入许可", source)
        self.assertIn("请先检查包体，报告放行后可确认导入。", source)
        self.assertIn("报告放行：可以导入", source)
        self.assertIn("报告阻断：需要修复", source)
        self.assertIn("报告放行：%s", source)
        self.assertIn("报告阻断：%s", source)
        self.assertIn("报告未放行；修复阻断项后重新检查", source)
        self.assertIn(".IsEnabled(this,&SAssetForgeGatePanel::HasSelectedPackage)", source)
        self.assertIn(".IsEnabled(this,&SAssetForgeGatePanel::CanImportSelectedPackage)", source)
        self.assertIn("SelectedPackage->ReportErrorCount <= 0", source)
        self.assertIn("未扫描到 AF 包体：请确认 Maya 导出已完成", source)
        self.assertIn("const FString PackageDir = SelectedPackage->PackageDir;", source)
        self.assertIn("当前包体还没有报告；先执行检查", source)
        self.assertIn("Content", source)
        self.assertIn("asset_forge_install.json", source)
        self.assertIn("ExecPythonCommandEx", source)
        self.assertNotIn("真实导入将接入", source)
        self.assertNotIn("最近包体 - HK416D_Round2", source)
        self.assertNotIn("最近包体 - SM_B", source)
        self.assertNotIn("X:/Private/DCCAssetForge", source)

    def _load_module(self, path):
        spec = importlib.util.spec_from_file_location("asset_forge_test_init_unreal", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class FakeUnreal(object):
    class EditorAssetLibrary(object):
        existing_assets = set()

        @classmethod
        def does_asset_exist(cls, asset_path):
            return asset_path in cls.existing_assets

    def __init__(self, existing_assets):
        self.EditorAssetLibrary.existing_assets = set(existing_assets)


class FakeUnrealWithExternalPlugin(object):
    class Paths(object):
        @classmethod
        def project_plugins_dir(cls):
            return "Y:/Projects/MyProject/Plugins"

        @classmethod
        def engine_plugins_dir(cls):
            return "D:/AssetForgeFixtures/UE_5.6/Engine/Plugins"

    class EditorAssetLibrary(object):
        query_count = 0

        @classmethod
        def does_asset_exist(cls, asset_path):
            cls.query_count += 1
            return False


class FakeUnrealWithInstalledPlugin(FakeUnrealWithExternalPlugin):
    class Paths(object):
        @classmethod
        def project_plugins_dir(cls):
            return "tests/fixtures/UEProject/Plugins"

        @classmethod
        def engine_plugins_dir(cls):
            return "D:/AssetForgeFixtures/UE_5.6/Engine/Plugins"


if __name__ == "__main__":
    unittest.main()
