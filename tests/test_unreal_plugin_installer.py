from __future__ import absolute_import

import json
import os
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest

from asset_forge.unreal.plugin_installer import install_assetforge_plugin, plan_assetforge_plugin_install


class UnrealPluginInstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_plugin = os.path.join(self.temp_dir, "SourceAssetForge")
        os.makedirs(os.path.join(self.source_plugin, "Content", "Python"))
        os.makedirs(os.path.join(self.source_plugin, "Source", "AssetForge"))
        self._write_json(
            os.path.join(self.source_plugin, "AssetForge.uplugin"),
            {
                "FileVersion": 3,
                "FriendlyName": "DCC AssetForge",
                "CanContainContent": True,
                "Modules": [],
            },
        )
        with open(os.path.join(self.source_plugin, "Content", "Python", "init_unreal.py"), "w", encoding="utf-8") as stream:
            stream.write("BOOTSTRAP_REPORT = {}\n")
        with open(os.path.join(self.source_plugin, "Source", "AssetForge", "AssetForge.Build.cs"), "w", encoding="utf-8") as stream:
            stream.write("// should not be installed for Blueprint/Python projects\n")

        self.project_dir = os.path.join(self.temp_dir, "UEProject")
        os.makedirs(self.project_dir)
        self.project_file = os.path.join(self.project_dir, "UEProject.uproject")
        self._write_json(self.project_file, {"FileVersion": 3, "Plugins": []})

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_plan_resolves_project_plugin_target(self):
        plan = plan_assetforge_plugin_install(self.project_file, self.source_plugin)

        self.assertEqual(plan["status"], "ready")
        self.assertTrue(plan["can_install"])
        self.assertEqual(plan["content_mount"], "/AssetForge")
        self.assertTrue(plan["target_plugin_dir"].endswith("UEProject/Plugins/AssetForge"))
        self.assertTrue(plan["requires_editor_restart"])
        self.assertFalse(plan["requires_cpp_compile"])
        self.assertIn("Source", plan["skipped_directories"])
        self.assertEqual(plan["runtime_directories"], ["asset_forge", "config"])
        self.assertTrue(plan["runtime_target_root"].endswith("UEProject/Plugins/AssetForge/Content/Python"))
        self.assertEqual(plan["source_hash_algorithm"], "sha256")
        self.assertEqual(len(plan["source_hash"]), 64)
        self.assertGreater(plan["planned_copied_file_count"], 0)
        self.assertTrue(plan["planned_copied_files_sample"])
        self.assertEqual(plan["build_readiness"]["status"], "not_required")
        self.assertEqual(plan["blocked_by_running_editor"], "not_applicable")

    def test_install_copies_plugin_and_enables_uproject(self):
        report = install_assetforge_plugin(self.project_dir, self.source_plugin)

        target_descriptor = os.path.join(self.project_dir, "Plugins", "AssetForge", "AssetForge.uplugin")
        target_python = os.path.join(self.project_dir, "Plugins", "AssetForge", "Content", "Python", "init_unreal.py")
        target_runtime = os.path.join(self.project_dir, "Plugins", "AssetForge", "Content", "Python", "asset_forge", "unreal", "editor_menu.py")
        target_config = os.path.join(self.project_dir, "Plugins", "AssetForge", "Content", "Python", "config", "material_profiles.json")
        target_metadata = os.path.join(self.project_dir, "Plugins", "AssetForge", "Content", "Python", "config", "asset_forge_install.json")
        project_data = self._read_json(self.project_file)
        self.assertEqual(report["status"], "success")
        self.assertTrue(os.path.exists(target_descriptor))
        self.assertTrue(os.path.exists(target_python))
        self.assertTrue(os.path.exists(target_runtime))
        self.assertTrue(os.path.exists(target_config))
        self.assertTrue(os.path.exists(target_metadata))
        self.assertFalse(os.path.exists(os.path.join(self.project_dir, "Plugins", "AssetForge", "Source")))
        self.assertIn(target_descriptor.replace("\\", "/"), report["copied_files"])
        self.assertIn(target_runtime.replace("\\", "/"), report["runtime_files"])
        self.assertIn(target_metadata.replace("\\", "/"), report["runtime_files"])
        self.assertEqual(report["target_plugin_dir"], os.path.join(self.project_dir, "Plugins", "AssetForge").replace("\\", "/"))
        self.assertFalse(report["requires_cpp_compile"])
        self.assertEqual(len(report["source_hash"]), 64)
        self.assertGreater(report["planned_copied_file_count"], 0)
        self.assertGreater(report["copied_file_count"], 0)
        self.assertIn(target_descriptor.replace("\\", "/"), report["copied_files_sample"])
        self.assertEqual(report["install_smoke"]["build_readiness"]["status"], "not_required")
        self.assertEqual(report["release_boundary"]["status"], "ready_after_restart")
        self.assertTrue(report["release_boundary"]["can_claim_clean_install"])
        self.assertEqual(report["release_boundary"]["manual_validation_commands"], [])
        self.assertTrue(report["post_install_checks"])
        self.assertTrue(all(item["status"] == "pass" for item in report["post_install_checks"]))
        self.assertEqual(project_data["Plugins"][0], {"Name": "AssetForge", "Enabled": True})
        metadata = self._read_json(target_metadata)
        self.assertTrue(metadata["source_latest_maya_log"].endswith("AssetForgeReports/logs/latest_maya.log"))

    def test_install_reports_enabled_when_plugin_was_already_enabled(self):
        self._write_json(self.project_file, {"FileVersion": 3, "Plugins": [{"Name": "AssetForge", "Enabled": True}]})

        report = install_assetforge_plugin(self.project_dir, self.source_plugin)

        self.assertTrue(report["enabled_in_project"])

    def test_installed_real_plugin_bootstrap_uses_embedded_runtime(self):
        report = install_assetforge_plugin(self.project_dir)
        target_python = os.path.join(self.project_dir, "Plugins", "AssetForge", "Content", "Python", "init_unreal.py")
        embedded_root = os.path.dirname(target_python)
        old_log_root = os.environ.get("ASSET_FORGE_LOG_ROOT")
        old_sys_path = list(sys.path)
        removed_modules = dict(
            (name, module)
            for name, module in sys.modules.items()
            if name == "asset_forge" or name.startswith("asset_forge.")
        )
        repo_root = os.getcwd()

        try:
            os.environ["ASSET_FORGE_LOG_ROOT"] = self.temp_dir
            for name in removed_modules:
                sys.modules.pop(name, None)
            sys.path[:] = [
                path
                for path in sys.path
                if path not in ("", repo_root) and os.path.abspath(path or repo_root) != repo_root
            ]
            module = self._load_module(target_python)

            self.assertEqual(report["status"], "success")
            self.assertTrue(report["plan"]["requires_cpp_compile"])
            self.assertTrue(os.path.exists(os.path.join(self.project_dir, "Plugins", "AssetForge", "Source", "AssetForgeEditor", "AssetForgeEditor.Build.cs")))
            self.assertIn(embedded_root.replace("\\", "/"), module.BOOTSTRAP_REPORT["added_python_paths"])
            self.assertIn("C++ Slate UI", module.BOOTSTRAP_REPORT["tool_menu_command"])
            self.assertNotEqual(module.BOOTSTRAP_REPORT["menu_register_status"], "error")
        finally:
            sys.modules.pop("asset_forge_test_installed_init_unreal", None)
            for name in list(sys.modules):
                if name == "asset_forge" or name.startswith("asset_forge."):
                    sys.modules.pop(name, None)
            sys.modules.update(removed_modules)
            sys.path[:] = old_sys_path
            if old_log_root is None:
                os.environ.pop("ASSET_FORGE_LOG_ROOT", None)
            else:
                os.environ["ASSET_FORGE_LOG_ROOT"] = old_log_root

    def test_plan_accepts_editor_cpp_modules_and_copies_source(self):
        self._write_json(
            os.path.join(self.source_plugin, "AssetForge.uplugin"),
            {
                "FileVersion": 3,
                "FriendlyName": "DCC AssetForge",
                "CanContainContent": True,
                "Modules": [{"Name": "AssetForge", "Type": "Editor"}],
            },
        )

        os.makedirs(os.path.join(self.source_plugin, "Source", "AssetForge"), exist_ok=True)

        plan = plan_assetforge_plugin_install(self.project_file, self.source_plugin)
        report = install_assetforge_plugin(self.project_file, self.source_plugin)

        self.assertEqual(plan["status"], "ready")
        self.assertTrue(plan["can_install"])
        self.assertTrue(plan["requires_cpp_compile"])
        self.assertTrue(plan["can_build_after_editor_closed"])
        self.assertEqual(plan["blocked_by_running_editor"], "not_checked")
        self.assertEqual(plan["build_readiness"]["target_binary"].split("/")[-1], "UnrealEditor-AssetForgeEditor.dll")
        self.assertNotIn("Source", plan["skipped_directories"])
        self.assertTrue(any(check["id"] == "plugin_cpp_modules" for check in plan["checks"]))
        self.assertEqual(report["status"], "success")
        self.assertTrue(os.path.exists(os.path.join(self.project_dir, "Plugins", "AssetForge", "Source", "AssetForge", "AssetForge.Build.cs")))
        self.assertFalse(report["release_boundary"]["can_claim_clean_install"])
        self.assertIn("close UE Editor", report["release_boundary"]["next_actions"][0])
        manual_commands = report["release_boundary"]["manual_validation_commands"]
        self.assertEqual([item["step"] for item in manual_commands], ["close_ue_editor", "run_ubt", "claim_boundary_after_success"])
        self.assertIn("关闭 UE", manual_commands[0]["display_label"])
        self.assertIn("运行 UBT", manual_commands[1]["display_label"])
        self.assertIn("验证边界", manual_commands[2]["display_label"])
        self.assertIn("UEProjectEditor Win64 Development", manual_commands[1]["command_template"])
        self.assertIn(self.project_file.replace("\\", "/"), manual_commands[1]["command_template"])
        self.assertEqual(manual_commands[1]["target_plugin_dir"], os.path.join(self.project_dir, "Plugins", "AssetForge").replace("\\", "/"))
        self.assertIn("successful closed-editor UBT build", manual_commands[2]["action"])

    def test_plan_blocks_cpp_build_when_external_ue_mcp_bridge_has_known_blockers(self):
        self._write_json(
            os.path.join(self.source_plugin, "AssetForge.uplugin"),
            {
                "FileVersion": 3,
                "FriendlyName": "DCC AssetForge",
                "CanContainContent": True,
                "Modules": [{"Name": "AssetForge", "Type": "Editor"}],
            },
        )
        self._write_ue_mcp_bridge_blockers()

        plan = plan_assetforge_plugin_install(self.project_file, self.source_plugin)
        report = install_assetforge_plugin(self.project_file, self.source_plugin)

        readiness = plan["build_readiness"]
        self.assertEqual(readiness["status"], "blocked")
        self.assertEqual(readiness["blocked_by_plugin"], "UE_MCP_Bridge")
        self.assertIn("JsonSerializer", readiness["blocker_summary"])
        self.assertFalse(readiness["can_build_after_editor_closed"])
        self.assertIn("external_plugin_preflight", readiness)
        self.assertTrue(any(item["id"] == "ue_mcp_bridge_duplicate_json_serializer" and item["status"] == "error" for item in readiness["external_plugin_preflight"]))
        self.assertTrue(any(item["id"] == "ue_mcp_bridge_statetree_runtime_guard" and item["status"] == "error" for item in readiness["external_plugin_preflight"]))
        self.assertEqual(report["install_smoke"]["build_readiness"]["status"], "blocked")
        self.assertEqual(report["release_boundary"]["status"], "blocked")
        self.assertFalse(report["release_boundary"]["can_claim_clean_install"])
        self.assertIn("UE_MCP_Bridge", report["release_boundary"]["what_is_not_proven"][-1])
        self.assertIn("fix or disable UE_MCP_Bridge", report["release_boundary"]["next_actions"][0])

    def test_dry_run_does_not_write_project(self):
        report = install_assetforge_plugin(self.project_dir, self.source_plugin, dry_run=True)

        target_descriptor = os.path.join(self.project_dir, "Plugins", "AssetForge", "AssetForge.uplugin")
        self.assertEqual(report["status"], "skipped")
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["copied_files"], [])
        self.assertEqual(report["copied_file_count"], 0)
        self.assertGreater(report["planned_copied_file_count"], 0)
        self.assertTrue(report["planned_copied_files_sample"])
        self.assertEqual(report["install_smoke"]["source_hash"], report["source_hash"])
        self.assertEqual(report["release_boundary"]["status"], "dry_run")
        self.assertFalse(report["release_boundary"]["can_claim_clean_install"])
        self.assertIn("files were not copied", report["release_boundary"]["what_is_not_proven"][0])
        self.assertFalse(os.path.exists(target_descriptor))
        self.assertEqual(self._read_json(self.project_file)["Plugins"], [])

    def test_dry_run_cpp_plugin_reports_manual_validation_without_clean_claim(self):
        self._write_json(
            os.path.join(self.source_plugin, "AssetForge.uplugin"),
            {
                "FileVersion": 3,
                "FriendlyName": "DCC AssetForge",
                "CanContainContent": True,
                "Modules": [{"Name": "AssetForge", "Type": "Editor"}],
            },
        )

        report = install_assetforge_plugin(self.project_dir, self.source_plugin, dry_run=True)

        target_source = os.path.join(self.project_dir, "Plugins", "AssetForge", "Source")
        manual_commands = report["release_boundary"]["manual_validation_commands"]
        self.assertEqual(report["status"], "skipped")
        self.assertEqual(report["release_boundary"]["status"], "dry_run")
        self.assertTrue(report["requires_cpp_compile"])
        self.assertFalse(report["release_boundary"]["can_claim_clean_install"])
        self.assertEqual(report["copied_file_count"], 0)
        self.assertFalse(os.path.exists(target_source))
        self.assertIn("files were not copied", report["release_boundary"]["what_is_not_proven"][0])
        self.assertIn("native editor module", report["release_boundary"]["what_is_not_proven"][1])
        self.assertEqual(manual_commands[0]["step"], "close_ue_editor")
        self.assertEqual(manual_commands[1]["step"], "run_ubt")
        self.assertIn("关闭 UE", manual_commands[0]["display_label"])
        self.assertIn("运行 UBT", manual_commands[1]["display_label"])
        self.assertIn("验证边界", manual_commands[2]["display_label"])
        self.assertIn("UEProjectEditor Win64 Development", manual_commands[1]["command_template"])
        self.assertEqual(manual_commands[2]["dry_run"], True)

    def test_install_reads_uproject_with_utf8_bom(self):
        with open(self.project_file, "w", encoding="utf-8-sig") as stream:
            json.dump({"FileVersion": 3, "Plugins": []}, stream)

        report = install_assetforge_plugin(self.project_dir, self.source_plugin)

        self.assertEqual(report["status"], "success")
        self.assertEqual(self._read_json(self.project_file)["Plugins"][0], {"Name": "AssetForge", "Enabled": True})

    def test_install_script_help_prints_usage_without_running_install(self):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/unreal_plugin_install.py",
                "--help",
            ],
            cwd=os.getcwd(),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertIn("Usage:", result.stdout)
        self.assertIn("<uproject_or_project_dir>", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_install_script_writes_report_path(self):
        report_path = os.path.join(self.temp_dir, "plugin_install_report.json")
        result = subprocess.run(
            [
                sys.executable,
                "scripts/unreal_plugin_install.py",
                self.project_file,
                report_path,
                "--dry-run",
            ],
            cwd=os.getcwd(),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        stdout_report = json.loads(result.stdout)
        disk_report = self._read_json(report_path)
        self.assertEqual(stdout_report["status"], "skipped")
        self.assertIn("install_smoke", stdout_report)
        self.assertEqual(stdout_report["copied_file_count"], 0)
        self.assertGreater(stdout_report["planned_copied_file_count"], 0)
        self.assertEqual(disk_report["status"], "skipped")
        self.assertEqual(disk_report["install_smoke"]["source_hash"], stdout_report["install_smoke"]["source_hash"])

    def test_install_script_returns_nonzero_for_failed_report(self):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/unreal_plugin_install.py",
                os.path.join(self.temp_dir, "MissingProject"),
            ],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "failed")

    def _write_json(self, path, data):
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")

    def _read_json(self, path):
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)

    def _load_module(self, path):
        spec = importlib.util.spec_from_file_location("asset_forge_test_installed_init_unreal", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _write_ue_mcp_bridge_blockers(self):
        bridge_root = os.path.join(self.project_dir, "Plugins", "UE_MCP_Bridge", "Source", "UE_MCP_Bridge")
        os.makedirs(os.path.join(bridge_root, "Private", "Handlers"), exist_ok=True)
        os.makedirs(os.path.join(bridge_root, "Public"), exist_ok=True)
        with open(os.path.join(bridge_root, "Private", "JsonSerializer.cpp"), "w", encoding="utf-8") as stream:
            stream.write("// private json serializer\n")
        with open(os.path.join(bridge_root, "Public", "JsonSerializer.cpp"), "w", encoding="utf-8") as stream:
            stream.write("// duplicate json serializer\n")
        with open(os.path.join(bridge_root, "Private", "Handlers", "StateTreeHandlers.cpp"), "w", encoding="utf-8") as stream:
            stream.write("Node.GetExecutionRuntimeDataType();\n")
            stream.write("EditorNode.ExecutionRuntimeData.InitializeAs(ExecType);\n")

    def test_plan_blocks_statetree_macro_when_runtime_data_guard_is_still_56(self):
        self._write_json(
            os.path.join(self.source_plugin, "AssetForge.uplugin"),
            {
                "FileVersion": 3,
                "FriendlyName": "DCC AssetForge",
                "CanContainContent": True,
                "Modules": [{"Name": "AssetForge", "Type": "Editor"}],
            },
        )
        bridge_root = os.path.join(self.project_dir, "Plugins", "UE_MCP_Bridge", "Source", "UE_MCP_Bridge")
        os.makedirs(os.path.join(bridge_root, "Private", "Handlers"), exist_ok=True)
        with open(os.path.join(bridge_root, "Private", "Handlers", "StateTreeHandlers.cpp"), "w", encoding="utf-8") as stream:
            stream.write("#define UE_MCP_HAS_STATETREE_GENERAL_PROPERTY_BINDING (ENGINE_MAJOR_VERSION > 5 || (ENGINE_MAJOR_VERSION == 5 && ENGINE_MINOR_VERSION >= 7))\n")
            stream.write("#define UE_MCP_HAS_STATETREE_EXECUTION_RUNTIME_DATA (ENGINE_MAJOR_VERSION > 5 || (ENGINE_MAJOR_VERSION == 5 && ENGINE_MINOR_VERSION >= 6))\n")
            stream.write("#if UE_MCP_HAS_STATETREE_EXECUTION_RUNTIME_DATA\n")
            stream.write("Node.GetExecutionRuntimeDataType();\n")
            stream.write("EditorNode.ExecutionRuntimeData.InitializeAs(ExecType);\n")
            stream.write("#endif\n")

        plan = plan_assetforge_plugin_install(self.project_file, self.source_plugin)
        runtime_guard_checks = [
            item
            for item in plan["build_readiness"]["external_plugin_preflight"]
            if item["id"] == "ue_mcp_bridge_statetree_runtime_guard"
        ]

        self.assertEqual(plan["build_readiness"]["status"], "blocked")
        self.assertEqual(runtime_guard_checks[0]["status"], "error")


if __name__ == "__main__":
    unittest.main()
