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

        self.assertEqual(descriptor["FriendlyName"], "Asset Forge")
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

            self.assertTrue(module.BOOTSTRAP_REPORT["repo_root"].endswith("DCC_Asset_Forge"))
            self.assertIn("Content/Python", module.BOOTSTRAP_REPORT["plugin_python_dir"])
            self.assertIn("added_python_paths", module.BOOTSTRAP_REPORT)
            self.assertIn("import_package", module.BOOTSTRAP_REPORT["actions"])
            self.assertGreater(module.BOOTSTRAP_REPORT["action_count"], 0)
            self.assertEqual(module.BOOTSTRAP_REPORT["widget_asset_path"], "/AssetForge/Editor/EUW_AssetForgeGate")
            self.assertEqual(module.BOOTSTRAP_REPORT["widget_launch_status"], "missing_asset")
            self.assertEqual(module.BOOTSTRAP_REPORT["material_content_mount"], "/AssetForge")
            self.assertEqual(module.BOOTSTRAP_REPORT["material_asset_count"], 34)
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
        self.assertIn("[放行]", source)
        self.assertIn("[阻断]", source)
        self.assertIn("RiskSummary", source)
        self.assertIn("风险：警告 %d / 阻断 %d", source)
        self.assertIn("ListPrimaryLabel", source)
        self.assertIn("ListSecondaryLabel", source)
        self.assertIn("独立 Mesh %d / FBX %d / 贴图 %d / 材质 %d", source)
        self.assertIn("preview_gate_for_package_dir", source)
        self.assertIn("import_approved_package_dir", source)
        self.assertIn("GetNextActionText", source)
        self.assertIn("GetApprovalIntentText", source)
        self.assertIn("GetApprovalStageText", source)
        self.assertIn("GetFlowSummaryText", source)
        self.assertIn("导入控制", source)
        self.assertIn("状态：未选择包体；导入动作禁用。", source)
        self.assertIn("状态：已选择包体；可先检查，导入等待报告放行。", source)
        self.assertIn("状态：报告已放行；可以导入当前包体。", source)
        self.assertIn("状态：报告未放行；请修复阻断项后重新检查。", source)
        self.assertIn("主操作会先生成检查报告；报告放行后才正式写入 UE。仅检查可用于复核，不会创建资产。", source)
        self.assertIn("PrimaryActionButton", source)
        self.assertIn("HandlePrimaryImportClicked", source)
        self.assertIn("检查并导入选中包体", source)
        self.assertIn("仅检查", source)
        self.assertIn("不写入验证", source)
        self.assertIn("仅导入已放行", source)
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
        self.assertIn("检查报告：", source)
        self.assertIn("报告放行：可以导入", source)
        self.assertIn("报告阻断：需要修复", source)
        self.assertIn("报告放行：%s", source)
        self.assertIn("报告阻断：%s", source)
        self.assertIn("报告未放行；修复阻断项后重新检查", source)
        self.assertIn("HasSelectedPackage", source)
        self.assertIn("检查并导入选中包体", source)
        self.assertIn("仅导入已放行", source)
        self.assertIn("未扫描到 AF 包体：请确认 Maya 导出已完成", source)
        self.assertIn("不会自动导入“最近导出包”", source)
        self.assertIn("当前包体还没有报告；先执行检查", source)
        self.assertIn("Content", source)
        self.assertIn("asset_forge_install.json", source)
        self.assertIn("ExecPythonCommandEx", source)
        self.assertNotIn("真实导入将接入", source)
        self.assertNotIn("最近包体 - HK416D_Round2", source)
        self.assertNotIn("最近包体 - SM_B", source)
        self.assertNotIn("<WORKSPACE_ROOT>/DCC_Asset_Forge", source)

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
            return "<LEGACY_WORK_DRIVE>/UE_Pj/UE5/MyProject/Plugins"

        @classmethod
        def engine_plugins_dir(cls):
            return "<LEGACY_WORK_DRIVE>/UE_5.6/Engine/Plugins"

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
            return "<LEGACY_WORK_DRIVE>/UE_5.6/Engine/Plugins"


if __name__ == "__main__":
    unittest.main()
