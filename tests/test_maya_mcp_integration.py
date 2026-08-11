from __future__ import absolute_import

import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import types
import unittest

from asset_forge.maya import mcp_actions
from integrations.maya_mcp.client import MayaBridgeClient
from integrations.maya_mcp.protocol import encode_message, make_request, normalize_bridge_response
from integrations.maya_mcp.server import handle_message
from integrations.maya_mcp.server import SERVER_INFO
from integrations.maya_mcp.tools import tool_definitions
from integrations.maya_mcp_runtime import __version__ as runtime_version
from integrations.maya.scripts import asset_forge_maya_bridge


class MayaMcpIntegrationTest(unittest.TestCase):
    def test_maya_mcp_versions_are_aligned_for_multi_instance_release(self):
        self.assertEqual(SERVER_INFO["version"], "0.2.0")
        self.assertEqual(asset_forge_maya_bridge.BRIDGE_VERSION, "0.2.0")
        self.assertEqual(runtime_version, "0.2.0")

    def test_tool_definitions_expose_static_prop_p0_actions(self):
        names = [item["name"] for item in tool_definitions()]

        self.assertIn("maya_instances", names)
        self.assertIn("maya_status", names)
        self.assertIn("maya_load_asset_forge", names)
        self.assertIn("maya_install_asset_forge_ui_shelf", names)
        self.assertIn("maya_install_mcp_bridge_shelf", names)
        self.assertIn("maya_open_scene", names)
        self.assertIn("maya_import_fbx", names)
        self.assertIn("maya_scan_static_prop", names)
        self.assertIn("maya_preflight_static_prop", names)
        self.assertIn("maya_export_static_prop_package", names)
        self.assertIn("maya_run_static_prop_ui_flow", names)
        self.assertIn("maya_get_latest_log", names)

    def test_tool_definitions_add_target_selectors_to_bridge_tools(self):
        tools = dict((item["name"], item) for item in tool_definitions())
        status_properties = tools["maya_status"]["inputSchema"]["properties"]

        self.assertIn("maya_instance", status_properties)
        self.assertIn("maya_pid", status_properties)
        self.assertIn("maya_port", status_properties)
        self.assertNotIn("maya_instance", tools["maya_instances"]["inputSchema"]["properties"])

    def test_protocol_request_contains_action_params_and_optional_token(self):
        request = make_request("maya_import_fbx", {"repo_root": "E:/Repo", "fbx_path": "E:/Asset.fbx"}, token="local-token")

        self.assertEqual(request["action"], "maya_import_fbx")
        self.assertEqual(request["params"]["repo_root"], "E:/Repo")
        self.assertEqual(request["params"]["fbx_path"], "E:/Asset.fbx")
        self.assertEqual(request["token"], "local-token")

    def test_protocol_accepts_static_prop_ui_flow_action(self):
        request = make_request("maya_run_static_prop_ui_flow", {"selection": ["|Crate"]}, token="local-token")

        self.assertEqual(request["action"], "maya_run_static_prop_ui_flow")
        self.assertEqual(request["params"]["selection"], ["|Crate"])

    def test_tool_schema_exposes_preset_and_package_version_fields(self):
        tools = dict((item["name"], item) for item in tool_definitions())
        schema = tools["maya_run_static_prop_ui_flow"]["inputSchema"]["properties"]

        self.assertIn("project_preset", schema)
        self.assertIn("preset_name", schema)
        self.assertIn("package_name_override", schema)
        self.assertIn("package_version_mode", schema)
        self.assertIn("package_version_padding", schema)

    def test_protocol_preserves_legacy_string_bridge_errors(self):
        with self.assertRaises(RuntimeError) as caught:
            normalize_bridge_response({"ok": False, "error": "legacy bridge error"})

        self.assertIn("legacy bridge error", str(caught.exception))

    def test_mcp_initialize_and_tools_list(self):
        init = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        tools = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

        self.assertEqual(init["result"]["serverInfo"]["name"], "maya-mcp")
        self.assertTrue(tools["result"]["tools"])

    def test_mcp_tools_call_wraps_bridge_result_as_text_content(self):
        client = FakeClient({"status": "pass", "can_accept": True})
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "maya_status", "arguments": {}},
            },
            client=client,
        )

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "pass")
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(client.calls[0][0], "maya_status")

    def test_mcp_tools_call_passes_import_fbx_arguments(self):
        client = FakeClient({"status": "success", "selected": ["|SM_Test"], "mesh_count": 1, "materials": []})
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "maya_import_fbx", "arguments": {"fbx_path": "E:/Asset.fbx", "rename_root": "SM_Test"}},
            },
            client=client,
        )

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["selected"], ["|SM_Test"])
        self.assertEqual(client.calls[0][0], "maya_import_fbx")
        self.assertEqual(client.calls[0][1]["rename_root"], "SM_Test")

    def test_maya_instances_returns_selection_summary(self):
        import integrations.maya_mcp.tools as tools_module

        old_load_instances = tools_module.load_instances
        try:
            tools_module.load_instances = lambda include_stale=False: [
                {
                    "instance_id": "maya-a",
                    "pid": 101,
                    "port": 8765,
                    "scene_name": "A.ma",
                    "display_name": "A.ma | pid 101 | port 8765",
                }
            ]
            response = handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "maya_instances", "arguments": {}},
                }
            )
        finally:
            tools_module.load_instances = old_load_instances

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["selection_summary"][0]["display_name"], "A.ma | pid 101 | port 8765")
        self.assertEqual(payload["selection_summary"][0]["maya_instance"], "maya-a")

    def test_maya_status_exposes_readonly_portfolio_capture_preflight_state(self):
        cmds = FakeReadonlyStatusCmds()
        window = FakeStaticPropUiWindow()
        window.last_scan = {"asset_name": "SM_Crate"}
        window.last_validation = {"status": "pass", "can_export": True, "checks": []}
        window.last_texture_scan = {"directory_status": "valid", "matched_count": 3}
        old_get_cmds = mcp_actions.get_cmds
        old_loaded = mcp_actions._is_asset_forge_loaded
        old_window = mcp_actions._STATIC_PROP_UI_WINDOW
        try:
            mcp_actions.get_cmds = lambda: cmds
            mcp_actions._is_asset_forge_loaded = lambda: True
            mcp_actions._STATIC_PROP_UI_WINDOW = window
            result = mcp_actions.maya_status({"repo_root": "E:/Repo"})
        finally:
            mcp_actions.get_cmds = old_get_cmds
            mcp_actions._is_asset_forge_loaded = old_loaded
            mcp_actions._STATIC_PROP_UI_WINDOW = old_window

        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["portfolio_capture_ready"])
        self.assertEqual(result["portfolio_capture_ready_reasons"], [])
        self.assertEqual(result["selected_nodes"], ["|SM_Crate"])
        self.assertEqual(result["current_ui_state"]["validation_status"], "pass")
        self.assertEqual(result["current_ui_state"]["texture_matched_count"], 3)
        card = result["portfolio_preflight_card"]
        self.assertEqual(card["can_record"], True)
        self.assertEqual(card["status_label"], "可录制")
        self.assertEqual(card["selected_count"], 1)
        self.assertEqual(card["has_selection"], True)
        self.assertEqual(card["has_scan"], True)
        self.assertIsInstance(card["has_latest_log"], bool)
        self.assertEqual(card["asset_name"], "SM_Crate")
        self.assertEqual(card["next_step"], "可以录制：展示扫描和预检结果，再进入导出或 UE 导入验证。")
        self.assertEqual(card["tips"], [])
        self.assertEqual(
            result["readonly_preflight_actions"],
            ["maya_status", "maya_get_latest_log", "maya_scan_static_prop", "maya_preflight_static_prop"],
        )
        self.assertEqual(result["readonly_preflight_steps"][0]["action"], "maya_status")
        self.assertEqual(result["readonly_preflight_steps"][0]["label"], "读取 Maya 桥接状态")
        self.assertIn("只读", result["readonly_preflight_steps"][0]["safety"])
        self.assertEqual(cmds.mutations, [])

    def test_viewport_screenshot_returns_concrete_playblast_frame_path(self):
        cmds = FakeViewportScreenshotCmds()
        old_get_cmds = mcp_actions.get_cmds
        try:
            mcp_actions.get_cmds = lambda: cmds
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = os.path.join(temp_dir, "maya_viewport.png")
                result = mcp_actions.maya_viewport_screenshot(
                    {"output_path": output_path, "width": 800, "height": 450}
                )

                self.assertEqual(result["status"], "success")
                self.assertEqual(result["output_path"], cmds.actual_path.replace("\\", "/"))
                self.assertEqual(result["playblast_template_path"], cmds.template_path.replace("\\", "/"))
                self.assertTrue(result["alpha_flattened"])
                self.assertTrue(os.path.exists(cmds.actual_path))
                self.assertEqual(cmds.playblast_kwargs["widthHeight"], (800, 450))
                from PIL import Image
                with Image.open(cmds.actual_path) as image:
                    self.assertEqual(image.mode, "RGB")
        finally:
            mcp_actions.get_cmds = old_get_cmds

    def test_maya_status_localizes_not_ready_reasons_without_asset_forge_or_scan(self):
        cmds = FakeReadonlyStatusCmds(selected=[])
        old_get_cmds = mcp_actions.get_cmds
        old_loaded = mcp_actions._is_asset_forge_loaded
        old_window = mcp_actions._STATIC_PROP_UI_WINDOW
        try:
            mcp_actions.get_cmds = lambda: cmds
            mcp_actions._is_asset_forge_loaded = lambda: False
            mcp_actions._STATIC_PROP_UI_WINDOW = None
            result = mcp_actions.maya_status({"repo_root": "E:/Repo"})
        finally:
            mcp_actions.get_cmds = old_get_cmds
            mcp_actions._is_asset_forge_loaded = old_loaded
            mcp_actions._STATIC_PROP_UI_WINDOW = old_window

        self.assertFalse(result["portfolio_capture_ready"])
        self.assertEqual(
            result["portfolio_capture_ready_reasons"],
            [
                "DCC AssetForge 尚未在当前 Maya 会话中加载。",
                "当前没有选择 Maya 节点，DCC AssetForge UI 中也没有可用的扫描结果。",
            ],
        )
        self.assertEqual(result["portfolio_preflight_card"]["can_record"], False)
        self.assertEqual(result["portfolio_preflight_card"]["status_label"], "待补齐")
        self.assertEqual(result["portfolio_preflight_card"]["selected_count"], 0)
        self.assertFalse(result["portfolio_preflight_card"]["has_scan"])
        self.assertEqual(result["portfolio_preflight_card"]["next_step"], "先加载 DCC AssetForge Maya 工具，再刷新状态。")
        self.assertEqual(result["readonly_preflight_steps"][2]["action"], "maya_scan_static_prop")
        self.assertEqual(result["readonly_preflight_steps"][2]["label"], "扫描当前静态道具")
        self.assertEqual(cmds.mutations, [])

    def test_maya_status_allows_existing_scan_without_current_selection(self):
        cmds = FakeReadonlyStatusCmds(selected=[])
        window = FakeStaticPropUiWindow()
        window.last_scan = {"asset_name": "SM_Crate"}
        old_get_cmds = mcp_actions.get_cmds
        old_loaded = mcp_actions._is_asset_forge_loaded
        old_window = mcp_actions._STATIC_PROP_UI_WINDOW
        try:
            mcp_actions.get_cmds = lambda: cmds
            mcp_actions._is_asset_forge_loaded = lambda: True
            mcp_actions._STATIC_PROP_UI_WINDOW = window
            result = mcp_actions.maya_status({"repo_root": "E:/Repo"})
        finally:
            mcp_actions.get_cmds = old_get_cmds
            mcp_actions._is_asset_forge_loaded = old_loaded
            mcp_actions._STATIC_PROP_UI_WINDOW = old_window

        self.assertTrue(result["portfolio_capture_ready"])
        self.assertEqual(result["selected_nodes"], [])
        self.assertTrue(result["current_ui_state"]["has_scan"])
        self.assertEqual(result["portfolio_capture_ready_reasons"], [])
        self.assertEqual(result["portfolio_preflight_card"]["can_record"], True)
        self.assertEqual(result["portfolio_preflight_card"]["status_label"], "可录制")
        self.assertEqual(result["portfolio_preflight_card"]["selected_count"], 0)
        self.assertFalse(result["portfolio_preflight_card"]["has_selection"])
        self.assertTrue(result["portfolio_preflight_card"]["has_scan"])
        self.assertEqual(result["portfolio_preflight_card"]["asset_name"], "SM_Crate")
        self.assertEqual(result["portfolio_preflight_card"]["next_step"], "可以录制：先展示已有扫描结果，再执行预检生成验收证据。")
        self.assertEqual(result["readonly_preflight_steps"][3]["action"], "maya_preflight_static_prop")
        self.assertEqual(result["readonly_preflight_steps"][3]["label"], "执行静态道具预检")
        self.assertIn("不写入资源", result["readonly_preflight_steps"][3]["safety"])
        self.assertEqual(cmds.mutations, [])

    def test_maya_run_python_ignores_request_level_enable_flag(self):
        old_value = os.environ.pop("ASSET_FORGE_MAYA_MCP_ALLOW_PYTHON", None)
        try:
            result = mcp_actions.maya_run_python({"code": "print('unsafe')", "allow_dev_python": True})
        finally:
            if old_value is not None:
                os.environ["ASSET_FORGE_MAYA_MCP_ALLOW_PYTHON"] = old_value

        self.assertEqual(result["status"], "error")
        self.assertFalse(result["can_accept"])
        self.assertIn("ASSET_FORGE_MAYA_MCP_ALLOW_PYTHON", result["next_action"])

    def test_maya_load_asset_forge_accepts_window_name_from_open_ui_bootstrap(self):
        old_loader = mcp_actions._load_python_file
        old_logger = mcp_actions._logger

        class FakeLauncher(object):
            def bootstrap(self, **kwargs):
                return "assetForgePhase1Window"

        try:
            mcp_actions._load_python_file = lambda *args, **kwargs: FakeLauncher()
            mcp_actions._logger = lambda _root=None: FakeMcpLogger()
            result = mcp_actions.maya_load_asset_forge({"repo_root": "E:/Repo", "open_ui": True})
        finally:
            mcp_actions._load_python_file = old_loader
            mcp_actions._logger = old_logger

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["opened_ui"])
        self.assertEqual(result["opened_window"], "assetForgePhase1Window")

    def test_maya_install_asset_forge_ui_shelf_uses_launcher_entry(self):
        old_loader = mcp_actions._load_python_file
        old_logger = mcp_actions._logger
        calls = []

        class FakeLauncher(object):
            def install_ui_shelf_button(self, **kwargs):
                calls.append(kwargs)
                return {
                    "status": "success",
                    "button": "assetForgeMayaWorkbenchButton",
                    "repo_root": kwargs["repo_root"],
                    "icon": kwargs["repo_root"] + "/Plugins/AssetForge/Resources/IconMayaShelf.png",
                }

        try:
            mcp_actions._load_python_file = lambda *args, **kwargs: FakeLauncher()
            mcp_actions._logger = lambda _root=None: FakeMcpLogger()
            result = mcp_actions.maya_install_asset_forge_ui_shelf({"repo_root": "E:/Repo", "shelf_name": "AssetForge"})
        finally:
            mcp_actions._load_python_file = old_loader
            mcp_actions._logger = old_logger

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["button"], "assetForgeMayaWorkbenchButton")
        self.assertIn("IconMayaShelf.png", result["icon"])
        self.assertEqual(calls[0]["repo_root"], "E:/Repo")
        self.assertEqual(calls[0]["shelf_name"], "AssetForge")

    def test_maya_install_mcp_bridge_shelf_uses_launcher_entry(self):
        old_loader = mcp_actions._load_python_file
        old_logger = mcp_actions._logger
        calls = []

        class FakeLauncher(object):
            def install_bridge_shelf_button(self, **kwargs):
                calls.append(kwargs)
                return {
                    "status": "success",
                    "button": "assetForgeMcpBridgeButton",
                    "repo_root": kwargs["repo_root"],
                    "icon": kwargs["repo_root"] + "/Plugins/AssetForge/Resources/IconMayaMcpShelf.png",
                }

        try:
            mcp_actions._load_python_file = lambda *args, **kwargs: FakeLauncher()
            mcp_actions._logger = lambda _root=None: FakeMcpLogger()
            result = mcp_actions.maya_install_mcp_bridge_shelf({"repo_root": "E:/Repo"})
        finally:
            mcp_actions._load_python_file = old_loader
            mcp_actions._logger = old_logger

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["button"], "assetForgeMcpBridgeButton")
        self.assertIn("IconMayaMcpShelf.png", result["icon"])
        self.assertEqual(calls[0]["repo_root"], "E:/Repo")

    def test_ui_state_detects_existing_maya_window_without_cached_object(self):
        old_get_cmds = mcp_actions.get_cmds
        old_window = mcp_actions._STATIC_PROP_UI_WINDOW

        class FakeWindowCmds(object):
            def window(self, name, exists=False):
                return bool(exists and name == "assetForgePhase1Window")

        try:
            mcp_actions.get_cmds = lambda: FakeWindowCmds()
            mcp_actions._STATIC_PROP_UI_WINDOW = None
            state = mcp_actions._current_static_prop_ui_state()
        finally:
            mcp_actions.get_cmds = old_get_cmds
            mcp_actions._STATIC_PROP_UI_WINDOW = old_window

        self.assertTrue(state["ui_loaded"])
        self.assertEqual(state["window"], "assetForgePhase1Window")
        self.assertFalse(state["has_scan"])

    def test_maya_import_fbx_success_returns_stable_selection_summary(self):
        with tempfile.NamedTemporaryFile(suffix=".fbx", delete=False) as stream:
            fbx_path = stream.name
        cmds = FakeImportCmds()
        scan = {"mesh_count": 2, "materials": [{"name": "M_Test"}], "asset_roots": ["|SM_AF_MCP_B_banji"]}
        try:
            with patched_mcp_action(cmds, scan):
                result = mcp_actions.maya_import_fbx({"fbx_path": fbx_path, "rename_root": "SM_AF_MCP_B_banji"})
        finally:
            os.remove(fbx_path)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["can_accept"])
        self.assertEqual(result["selected"], ["|SM_AF_MCP_B_banji"])
        self.assertEqual(result["mesh_count"], 2)
        self.assertEqual(result["materials"], [{"name": "M_Test"}])
        self.assertEqual(cmds.selected, ["|SM_AF_MCP_B_banji"])
        self.assertTrue(cmds.plugin_loaded)

    def test_maya_import_fbx_missing_file_returns_clear_error(self):
        cmds = FakeImportCmds()
        with patched_mcp_action(cmds, {"mesh_count": 1, "materials": []}):
            result = mcp_actions.maya_import_fbx({"fbx_path": "E:/missing/Nope.fbx"})

        self.assertEqual(result["status"], "error")
        self.assertFalse(result["can_accept"])
        self.assertIn("找不到 FBX 文件", result["errors"][0]["message"])

    def test_maya_import_fbx_empty_import_returns_clear_error(self):
        with tempfile.NamedTemporaryFile(suffix=".fbx", delete=False) as stream:
            fbx_path = stream.name
        cmds = FakeImportCmds(import_nodes=[])
        try:
            with patched_mcp_action(cmds, {"mesh_count": 1, "materials": []}):
                result = mcp_actions.maya_import_fbx({"fbx_path": fbx_path})
        finally:
            os.remove(fbx_path)

        self.assertEqual(result["status"], "error")
        self.assertIn("没有产生可用根节点", result["errors"][0]["message"])

    def test_maya_import_fbx_no_mesh_returns_clear_error(self):
        with tempfile.NamedTemporaryFile(suffix=".fbx", delete=False) as stream:
            fbx_path = stream.name
        cmds = FakeImportCmds()
        try:
            with patched_mcp_action(cmds, {"mesh_count": 0, "materials": []}):
                result = mcp_actions.maya_import_fbx({"fbx_path": fbx_path, "rename_root": "SM_Empty"})
        finally:
            os.remove(fbx_path)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["selected"], ["|SM_Empty"])
        self.assertIn("没有 mesh", result["errors"][0]["message"])

    def test_maya_import_fbx_groups_multiple_roots_before_scan(self):
        with tempfile.NamedTemporaryFile(suffix=".fbx", delete=False) as stream:
            fbx_path = stream.name
        cmds = FakeImportCmds(import_nodes=["|RootA", "|RootA|RootAShape", "|RootB", "|RootB|RootBShape"])
        cmds.node_types.update(
            {
                "|RootA": "transform",
                "|RootA|RootAShape": "mesh",
                "|RootB": "transform",
                "|RootB|RootBShape": "mesh",
                "|SM_Grouped": "transform",
            }
        )
        try:
            with patched_mcp_action(cmds, {"mesh_count": 2, "materials": [{"name": "M_Grouped"}]}):
                result = mcp_actions.maya_import_fbx({"fbx_path": fbx_path, "rename_root": "SM_Grouped", "group_imported": True})
        finally:
            os.remove(fbx_path)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected"], ["|SM_Grouped"])
        self.assertEqual(cmds.grouped_nodes, ["|RootA", "|RootB"])
        self.assertEqual(result["mesh_count"], 2)

    def test_static_prop_ui_flow_runs_window_callbacks_and_captures_export(self):
        cmds = FakeUiFlowCmds()
        window = FakeStaticPropUiWindow()
        old_get_cmds = mcp_actions.get_cmds
        old_get_window = mcp_actions._get_or_create_static_prop_ui_window
        old_logger = mcp_actions._logger
        try:
            mcp_actions.get_cmds = lambda: cmds
            mcp_actions._get_or_create_static_prop_ui_window = lambda: (window, True)
            mcp_actions._logger = lambda _root=None: FakeMcpLogger()
            result = mcp_actions.maya_run_static_prop_ui_flow(
                {
                    "selection": ["|Crate"],
                    "export_root": "D:/Exports",
                    "texture_dir": "D:/Textures",
                    "target_path": "/Game/Props/HK416D",
                    "texture_set_token": "a1,d1",
                    "virtual_texture_policy": "force_off",
                    "texture_streaming_policy": "streaming",
                    "texture_group": "project_default",
                    "nanite_policy": "disable",
                    "static_mesh_lod_group": "SmallProp",
                    "static_mesh_lod_import_policy": "report_only",
                }
            )
        finally:
            mcp_actions.get_cmds = old_get_cmds
            mcp_actions._get_or_create_static_prop_ui_window = old_get_window
            mcp_actions._logger = old_logger

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["ui_flow"])
        self.assertEqual(result["evidence_kind"], "maya_ui_callback_flow")
        self.assertEqual(result["asset_name"], "SM_Crate")
        self.assertEqual(result["renamed"], ["|SM_Crate", "|SM_Crate|SM_Crate_part"])
        self.assertEqual(result["package_dir"], "D:/Exports/SM_Crate")
        self.assertEqual(result["manifest_path"], "D:/Exports/SM_Crate/SM_Crate_manifest.json")
        self.assertEqual(result["fbx_path"], "D:/Exports/SM_Crate/SM_Crate.fbx")
        self.assertEqual(result["export_report_path"], "D:/Exports/SM_Crate/SM_Crate_export_report.json")
        self.assertEqual(
            [step["callback"] for step in result["steps"] if step["callback"]],
            ["_scan", "_rename_prefix", "_validate", "_scan_texture_folder", "_validate", "_export"],
        )
        for step in result["steps"]:
            self.assertIn("status", step)
            self.assertIn("warnings", step)
            self.assertIn("errors", step)
            self.assertIn("next_action", step)
        texture_step = [step for step in result["steps"] if step["callback"] == "_scan_texture_folder"][0]
        self.assertEqual(texture_step["texture_matched_count"], 3)
        self.assertEqual(cmds.selected, ["|Crate"])
        self.assertEqual(window.applied_settings["ue_target_path"], "/Game/Props/HK416D")
        self.assertEqual(window.applied_settings["mesh_prefix"], "SM_")
        self.assertEqual(window.applied_settings["texture_prefix"], "T_")
        self.assertEqual(window.applied_settings["material_profile"], "Props_Opaque_PainterUE_ARM")
        self.assertEqual(window.applied_settings["texture_set_token"], "a1,d1")
        self.assertEqual(window.applied_settings["virtual_texture_policy"], "force_off")
        self.assertEqual(window.applied_settings["texture_streaming_policy"], "streaming")
        self.assertEqual(window.applied_settings["texture_group"], "project_default")
        self.assertEqual(window.applied_settings["nanite_policy"], "disable")
        self.assertEqual(window.applied_settings["static_mesh_lod_group"], "SmallProp")
        self.assertEqual(window.applied_settings["static_mesh_lod_import_policy"], "report_only")
        self.assertEqual(window.pipeline.export_kwargs["texture_import_policy"]["virtual_texture_policy"], "force_off")
        self.assertEqual(window.pipeline.export_kwargs["static_mesh_import_policy"]["lod_group"], "SmallProp")
        self.assertEqual(window.pipeline.export_calls, 1)

    def test_backend_export_action_is_not_frontend_acceptance_evidence(self):
        cmds = FakeUiFlowCmds()
        cmds.select(["|SM_Crate"], replace=True)
        old_get_cmds = mcp_actions.get_cmds
        old_pipeline = mcp_actions.MayaStaticPropPipeline
        old_logger = mcp_actions._logger

        class FakeBackendExportPipeline(object):
            rules = {}

            def export_assets(self, selection, output_dir, target_platform, target_path, *args, **kwargs):
                package_dir = output_dir.replace("\\", "/") + "/SM_Crate"
                return {
                    "scan": {"asset_name": "SM_Crate"},
                    "validation": {"status": "pass", "can_export": True, "checks": []},
                    "package_dir": package_dir,
                    "manifest_path": package_dir + "/SM_Crate_manifest.json",
                    "fbx_path": package_dir + "/SM_Crate.fbx",
                    "export_report_path": package_dir + "/SM_Crate_export_report.json",
                }

        try:
            mcp_actions.get_cmds = lambda: cmds
            mcp_actions.MayaStaticPropPipeline = FakeBackendExportPipeline
            mcp_actions._logger = lambda _root=None: FakeMcpLogger()
            result = mcp_actions.maya_export_static_prop_package({"export_root": "D:/Exports"})
        finally:
            mcp_actions.get_cmds = old_get_cmds
            mcp_actions.MayaStaticPropPipeline = old_pipeline
            mcp_actions._logger = old_logger

        self.assertEqual(result["status"], "success")
        self.assertFalse(result["ui_flow"])
        self.assertEqual(result["evidence_kind"], "backend_action")
        self.assertIn("不等同于 Maya 前端验收", result["next_action"])

    def test_mcp_settings_accept_hidden_static_mesh_policy_overrides(self):
        settings = mcp_actions._settings(
            {
                "build_reversed_index_buffer": "enabled",
                "generate_lightmap_uvs": "disabled",
                "collision_complexity": "use_complex_as_simple",
            }
        )
        policy = mcp_actions._static_mesh_import_policy(settings)

        self.assertEqual(policy["build_reversed_index_buffer"], "enabled")
        self.assertEqual(policy["generate_lightmap_uvs"], "disabled")
        self.assertEqual(policy["collision_complexity"], "use_complex_as_simple")

    def test_ui_flow_settings_aliases_non_ascii_texture_root_for_maya_ui(self):
        temp_dir = tempfile.mkdtemp()
        old_repo_root = mcp_actions._repo_root
        try:
            mcp_actions._repo_root = lambda: temp_dir
            texture_root = os.path.join(temp_dir, "测试贴图")
            os.makedirs(texture_root)

            settings = mcp_actions._ui_flow_settings({"texture_dir": texture_root})

            if os.name == "nt":
                self.assertNotEqual(settings["texture_root"], texture_root.replace("\\", "/"))
                settings["texture_root"].encode("ascii")
                self.assertTrue(os.path.isdir(settings["texture_root"]))
            else:
                self.assertEqual(settings["texture_root"], texture_root.replace("\\", "/"))
        finally:
            mcp_actions._repo_root = old_repo_root
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_static_prop_ui_flow_prefix_fix_also_covers_internal_mesh_transforms(self):
        self.assertTrue(
            mcp_actions._scan_needs_prefix_fix(
                {"asset_name": "SM_B", "transforms": ["|SM_B|zuti|B_a", "|SM_B|zuti|SM_B_b"]},
                "SM_",
            )
        )
        self.assertFalse(
            mcp_actions._scan_needs_prefix_fix(
                {"asset_name": "SM_B", "transforms": ["|SM_B|zuti|SM_B_a", "|SM_B|zuti|SM_B_b"]},
                "SM_",
            )
        )

    def test_ui_step_evidence_exposes_structured_repair_actions(self):
        window = FakeStaticPropUiWindow()
        window.last_scan = {"asset_name": "Crate", "asset_roots": ["|Crate"], "mesh_count": 1}
        window.last_validation = {
            "status": "error",
            "can_export": False,
            "checks": [{"id": "name_prefix", "status": "error", "limit": "SM_", "message": "missing prefix"}],
        }
        window.last_texture_scan = {"rename_suggestions": [{"suggested_name": "T_Crate_BaseColor.png"}]}

        step = mcp_actions._ui_step_evidence(window, "preflight", "_validate", "success")

        actions = dict((item["id"], item) for item in step["repair_actions"])
        self.assertEqual(actions["fix_asset_name_prefix"]["ui_callback"], "_rename_prefix")
        self.assertEqual(actions["fix_asset_name_prefix"]["expected_asset_name"], "SM_Crate")
        self.assertEqual(actions["fix_texture_prefix"]["ui_callback"], "_rename_texture_prefix")
        self.assertIn("next_action", actions["fix_asset_name_prefix"])

    def test_bridge_client_talks_newline_json_to_local_socket(self):
        server = OneShotSocketServer({"id": "1", "ok": True, "result": {"status": "pass"}, "error": None})
        server.start()
        try:
            client = MayaBridgeClient(host="127.0.0.1", port=server.port, token="", timeout=5)
            result = client.call("maya_status", {})
        finally:
            server.stop()

        self.assertEqual(result["status"], "pass")
        self.assertEqual(server.received["action"], "maya_status")
        self.assertEqual(result["mcp_target"]["host"], "127.0.0.1")
        self.assertEqual(result["mcp_target"]["port"], server.port)

    def test_bridge_client_adds_resolved_instance_target_summary(self):
        server = OneShotSocketServer({"id": "1", "ok": True, "result": {"status": "pass"}, "error": None})
        server.start()
        try:
            client = MayaBridgeClient.from_instance(
                {
                    "instance_id": "maya-test",
                    "pid": 123,
                    "host": "127.0.0.1",
                    "port": server.port,
                    "scene_path": "E:/Scene.ma",
                }
            )
            result = client.call("maya_status", {})
        finally:
            server.stop()

        self.assertEqual(result["mcp_target"]["instance_id"], "maya-test")
        self.assertEqual(result["mcp_target"]["pid"], 123)
        self.assertEqual(result["mcp_target"]["scene_path"], "E:/Scene.ma")

    def test_bridge_handler_rejects_bad_token(self):
        server = asset_forge_maya_bridge.AssetForgeMayaBridgeServer(("127.0.0.1", 0), asset_forge_maya_bridge.AssetForgeMayaBridgeHandler, token="secret", repo_root="E:/Repo")
        thread = threading.Thread(target=server.handle_request)
        thread.daemon = True
        thread.start()
        try:
            with socket.create_connection(server.server_address, 5) as sock:
                sock.sendall(encode_message({"id": "bad", "action": "maya_status", "params": {}, "token": "wrong"}))
                raw = _read_line(sock)
        finally:
            server.server_close()
            thread.join(2)

        response = json.loads(raw.decode("utf-8"))
        self.assertFalse(response["ok"])
        self.assertIn("token", response["error"]["message"])

    def test_bridge_ping_does_not_enter_maya_main_thread(self):
        server = asset_forge_maya_bridge.AssetForgeMayaBridgeServer(("127.0.0.1", 0), asset_forge_maya_bridge.AssetForgeMayaBridgeHandler, token="", repo_root="E:/Repo")
        thread = threading.Thread(target=server.handle_request)
        thread.daemon = True
        thread.start()
        old_execute = asset_forge_maya_bridge._execute_in_maya_main_thread
        try:
            asset_forge_maya_bridge._execute_in_maya_main_thread = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("bridge_ping should stay on the socket thread"))
            with socket.create_connection(server.server_address, 5) as sock:
                sock.sendall(encode_message({"id": "ping", "action": "bridge_ping", "params": {}}))
                raw = _read_line(sock)
        finally:
            asset_forge_maya_bridge._execute_in_maya_main_thread = old_execute
            server.server_close()
            thread.join(2)

        response = json.loads(raw.decode("utf-8"))
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["status"], "running")
        self.assertEqual(response["result"]["repo_root"], "E:/Repo")

    def test_bridge_socket_health_uses_ping_response(self):
        server = asset_forge_maya_bridge.AssetForgeMayaBridgeServer(("127.0.0.1", 0), asset_forge_maya_bridge.AssetForgeMayaBridgeHandler, token="", repo_root="E:/Repo")
        thread = threading.Thread(target=server.handle_request)
        thread.daemon = True
        thread.start()
        try:
            healthy = asset_forge_maya_bridge._bridge_socket_healthy(server, timeout=1.0)
        finally:
            server.server_close()
            thread.join(2)

        self.assertTrue(healthy)

    def test_bridge_socket_health_rejects_unresponsive_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)

        class UnresponsiveServer(object):
            server_address = sock.getsockname()
            repo_root = "E:/Repo"
            instance_id = ""

        try:
            healthy = asset_forge_maya_bridge._bridge_socket_healthy(UnresponsiveServer(), timeout=0.05)
        finally:
            sock.close()

        self.assertFalse(healthy)

    def test_install_bridge_shelf_button_creates_one_click_launcher(self):
        fake_cmds = FakeMayaCmds()
        fake_mel = types.ModuleType("maya.mel")
        fake_mel.eval = lambda _expr: "ShelfTopLevel"
        with tempfile.TemporaryDirectory() as repo_root:
            icon_dir = os.path.join(repo_root, "Plugins", "AssetForge", "Resources")
            os.makedirs(icon_dir)
            with open(os.path.join(icon_dir, "IconMayaMcpShelf.png"), "wb") as stream:
                stream.write(b"asset-forge-test-icon")
            old_modules = _install_fake_maya_modules(fake_cmds, fake_mel)
            try:
                result = asset_forge_maya_bridge.install_bridge_shelf_button(repo_root=repo_root)
            finally:
                _restore_modules(old_modules)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["button"], asset_forge_maya_bridge.BRIDGE_SHELF_BUTTON)
        self.assertIn("start_bridge", fake_cmds.buttons[asset_forge_maya_bridge.BRIDGE_SHELF_BUTTON]["command"])
        self.assertIn("maya_launch_asset_forge.py", fake_cmds.buttons[asset_forge_maya_bridge.BRIDGE_SHELF_BUTTON]["command"])
        self.assertEqual(fake_cmds.buttons[asset_forge_maya_bridge.BRIDGE_SHELF_BUTTON]["label"], "Maya MCP")
        self.assertEqual(fake_cmds.buttons[asset_forge_maya_bridge.BRIDGE_SHELF_BUTTON]["annotation"], "Start Maya MCP bridge for Codex")
        self.assertIn("IconMayaMcpShelf.png", fake_cmds.buttons[asset_forge_maya_bridge.BRIDGE_SHELF_BUTTON]["image"])
        self.assertEqual(fake_cmds.buttons[asset_forge_maya_bridge.BRIDGE_SHELF_BUTTON]["imageOverlayLabel"], "")
        self.assertIn("IconMayaMcpShelf.png", result["icon"])
        self.assertEqual(
            fake_cmds.buttons[asset_forge_maya_bridge.BRIDGE_SHELF_BUTTON]["image"],
            fake_cmds.buttons[asset_forge_maya_bridge.BRIDGE_SHELF_BUTTON]["image1"],
        )

    def test_start_bridge_allocates_free_port_and_registers_instance(self):
        fake_cmds = FakeMayaCmds()
        fake_mel = types.ModuleType("maya.mel")
        fake_mel.eval = lambda _expr: "ShelfTopLevel"
        old_modules = _install_fake_maya_modules(fake_cmds, fake_mel)
        old_show = asset_forge_maya_bridge._safe_show_status_window
        old_log = asset_forge_maya_bridge._log_bridge_event
        old_default_port = asset_forge_maya_bridge.DEFAULT_PORT
        old_registry = os.environ.get("MAYA_MCP_REGISTRY_PATH")
        from integrations.maya_mcp_runtime.ports import allocate_port

        busy_port = allocate_port("127.0.0.1", 8765, 8799)
        busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        busy.bind(("127.0.0.1", busy_port))
        busy.listen(1)
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["MAYA_MCP_REGISTRY_PATH"] = os.path.join(temp_dir, "instances.json")
            try:
                asset_forge_maya_bridge.DEFAULT_PORT = busy_port
                asset_forge_maya_bridge._safe_show_status_window = lambda _status: None
                asset_forge_maya_bridge._log_bridge_event = lambda *args, **kwargs: {}
                status = asset_forge_maya_bridge.start_bridge(repo_root="E:/Repo")
                from integrations.maya_mcp_runtime.registry import load_instances

                instances = load_instances(path=os.environ["MAYA_MCP_REGISTRY_PATH"])
            finally:
                asset_forge_maya_bridge.stop_bridge()
                busy.close()
                asset_forge_maya_bridge._safe_show_status_window = old_show
                asset_forge_maya_bridge._log_bridge_event = old_log
                asset_forge_maya_bridge.DEFAULT_PORT = old_default_port
                if old_registry is None:
                    os.environ.pop("MAYA_MCP_REGISTRY_PATH", None)
                else:
                    os.environ["MAYA_MCP_REGISTRY_PATH"] = old_registry
                _restore_modules(old_modules)

        self.assertEqual(status["status"], "running")
        self.assertNotEqual(status["port"], busy_port)
        self.assertTrue(status["instance_id"])
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]["instance_id"], status["instance_id"])

    def test_bridge_stop_notifies_registered_status_listener(self):
        calls = []
        listener = asset_forge_maya_bridge.register_status_listener(lambda status: calls.append(status.get("status")))
        old_show = asset_forge_maya_bridge._safe_show_status_window
        try:
            asset_forge_maya_bridge._safe_show_status_window = lambda _status: None
            status = asset_forge_maya_bridge.stop_bridge()
        finally:
            asset_forge_maya_bridge.unregister_status_listener(listener)
            asset_forge_maya_bridge._safe_show_status_window = old_show

        self.assertEqual(status["status"], "stopped")
        self.assertEqual(calls[-1], "stopped")

    def test_bridge_start_command_points_to_launcher(self):
        command = asset_forge_maya_bridge._bridge_start_command(r"E:\Repo")

        self.assertIn("maya_launch_asset_forge.py", command)
        self.assertIn("start_bridge", command)
        self.assertIn("ASSET_FORGE_REPO_ROOT", command)

    def test_bridge_metrics_track_live_request_state(self):
        asset_forge_maya_bridge._reset_metrics("E:/Repo")

        asset_forge_maya_bridge._mark_request_start("maya_import_fbx", "req-1", "127.0.0.1")
        busy = asset_forge_maya_bridge._metrics_snapshot()

        self.assertEqual(busy["active_requests"], 1)
        self.assertEqual(busy["request_count"], 1)
        self.assertEqual(busy["current_action"], "maya_import_fbx")
        self.assertEqual(asset_forge_maya_bridge._health_from_metrics(busy), "busy")

        asset_forge_maya_bridge._mark_request_finish("maya_import_fbx", "req-1", "success", "")
        idle = asset_forge_maya_bridge._metrics_snapshot()

        self.assertEqual(idle["active_requests"], 0)
        self.assertEqual(idle["last_action"], "maya_import_fbx")
        self.assertEqual(idle["last_status"], "success")
        self.assertEqual(asset_forge_maya_bridge._health_from_metrics(idle), "healthy")

    def test_bridge_status_text_exposes_live_monitor_fields(self):
        asset_forge_maya_bridge._reset_metrics("E:/Repo")
        asset_forge_maya_bridge._mark_request_start("maya_preflight_static_prop", "req-2", "127.0.0.1")
        status = asset_forge_maya_bridge._metrics_snapshot()
        status.update({"status": "running", "health": "busy", "repo_root": "E:/Repo"})

        text = asset_forge_maya_bridge._format_status_text(status)

        self.assertIn("Live Activity:", text)
        self.assertIn("Active Requests: 1", text)
        self.assertIn("Total Requests: 1", text)
        self.assertIn("Current Action: maya_preflight_static_prop", text)
        asset_forge_maya_bridge._mark_request_finish("maya_preflight_static_prop", "req-2", "success", "")

    def test_bridge_status_window_refreshes_existing_controls(self):
        fake_cmds = FakeMayaCmds()
        fake_mel = types.ModuleType("maya.mel")
        fake_mel.eval = lambda _expr: "ShelfTopLevel"
        old_modules = _install_fake_maya_modules(fake_cmds, fake_mel)
        old_controls = dict(asset_forge_maya_bridge._WINDOW_CONTROLS)
        old_job = asset_forge_maya_bridge._MONITOR_JOB
        try:
            asset_forge_maya_bridge._WINDOW_CONTROLS.clear()
            asset_forge_maya_bridge._MONITOR_JOB = None
            asset_forge_maya_bridge._show_status_window({"status": "running", "health": "healthy", "repo_root": "E:/Repo"})
            state_control = asset_forge_maya_bridge._WINDOW_CONTROLS["state"]
            details_control = asset_forge_maya_bridge._WINDOW_CONTROLS["details"]
            asset_forge_maya_bridge._refresh_status_window_controls(
                {"status": "running", "health": "busy", "repo_root": "E:/Repo", "current_action": "maya_import_fbx", "active_requests": 1}
            )
            state = fake_cmds.text_values[state_control]
            details = fake_cmds.scroll_values[details_control]
        finally:
            asset_forge_maya_bridge._WINDOW_CONTROLS.clear()
            asset_forge_maya_bridge._WINDOW_CONTROLS.update(old_controls)
            asset_forge_maya_bridge._MONITOR_JOB = old_job
            _restore_modules(old_modules)

        self.assertIn("busy", state)
        self.assertIn("maya_import_fbx", details)

    def test_bridge_status_window_has_save_log_button(self):
        fake_cmds = FakeMayaCmds()
        fake_mel = types.ModuleType("maya.mel")
        fake_mel.eval = lambda _expr: "ShelfTopLevel"
        old_modules = _install_fake_maya_modules(fake_cmds, fake_mel)
        old_controls = dict(asset_forge_maya_bridge._WINDOW_CONTROLS)
        old_job = asset_forge_maya_bridge._MONITOR_JOB
        try:
            asset_forge_maya_bridge._WINDOW_CONTROLS.clear()
            asset_forge_maya_bridge._MONITOR_JOB = None
            asset_forge_maya_bridge._show_status_window({"status": "running", "health": "healthy", "repo_root": "E:/Repo"})
        finally:
            asset_forge_maya_bridge._WINDOW_CONTROLS.clear()
            asset_forge_maya_bridge._WINDOW_CONTROLS.update(old_controls)
            asset_forge_maya_bridge._MONITOR_JOB = old_job
            _restore_modules(old_modules)

        labels = [button.get("label") for button in fake_cmds.buttons.values()]
        self.assertIn("Maya MCP Bridge", fake_cmds.text_values.values())
        self.assertIn("Save Log", labels)
        self.assertIn("Stop Bridge", labels)
        self.assertLess(fake_cmds.call_order.index("button:Refresh"), fake_cmds.call_order.index("scrollField"))
        self.assertLess(fake_cmds.call_order.index("button:Stop Bridge"), fake_cmds.call_order.index("scrollField"))

    def test_save_status_log_writes_snapshot_event(self):
        calls = []
        old_logger = asset_forge_maya_bridge._log_bridge_event
        old_server = asset_forge_maya_bridge._SERVER
        try:
            asset_forge_maya_bridge._SERVER = None
            asset_forge_maya_bridge._log_bridge_event = lambda *args, **kwargs: calls.append((args, kwargs)) or {"path": "E:/Repo/latest_maya.log"}
            result = asset_forge_maya_bridge._save_status_log("E:/Repo")
        finally:
            asset_forge_maya_bridge._SERVER = old_server
            asset_forge_maya_bridge._log_bridge_event = old_logger

        self.assertEqual(result["status"], "success")
        self.assertEqual(calls[0][0][0], "mcp_bridge_status_snapshot")
        self.assertIn("status_text", calls[0][1]["outputs"])


class FakeClient(object):
    def __init__(self, result):
        self.result = result
        self.calls = []

    def call(self, action, params=None):
        self.calls.append((action, params or {}))
        return self.result


class FakeMcpLogger(object):
    def log(self, *args, **kwargs):
        return {}


class FakeMcpPipeline(object):
    scan = {}

    def scan_assets(self, selection):
        result = dict(self.scan)
        result.setdefault("asset_roots", list(selection or []))
        return result


class FakeUiFlowCmds(object):
    def __init__(self):
        self.selected = []

    def select(self, nodes=None, replace=True, clear=False):
        self.selected = [] if clear else list(nodes or [])

    def ls(self, *args, **kwargs):
        if kwargs.get("selection"):
            return list(self.selected)
        return []


class FakeReadonlyStatusCmds(object):
    def __init__(self, selected=None):
        self.selected = ["|SM_Crate"] if selected is None else list(selected)
        self.mutations = []

    def about(self, version=False):
        return "2025" if version else ""

    def file(self, *args, **kwargs):
        if kwargs.get("query") and kwargs.get("sceneName"):
            return "E:/Shots/portfolio_scene.ma"
        self.mutations.append(("file", args, kwargs))
        raise AssertionError("maya_status must not mutate the scene.")

    def ls(self, *args, **kwargs):
        if kwargs.get("selection"):
            return list(self.selected)
        return []

    def select(self, *args, **kwargs):
        self.mutations.append(("select", args, kwargs))
        raise AssertionError("maya_status must not change selection.")

    def playblast(self, *args, **kwargs):
        self.mutations.append(("playblast", args, kwargs))
        raise AssertionError("maya_status must not capture viewport output.")


class FakeViewportScreenshotCmds(object):
    def __init__(self):
        self.actual_path = ""
        self.template_path = ""
        self.playblast_kwargs = {}

    def currentTime(self, query=True):
        return 0

    def playblast(self, *args, **kwargs):
        self.playblast_kwargs = dict(kwargs)
        requested = kwargs["filename"]
        self.actual_path = requested + ".0000.png"
        self.template_path = requested + ".####.png"
        from PIL import Image
        image = Image.new("RGBA", (4, 4), (255, 255, 255, 0))
        image.putpixel((1, 1), (200, 180, 150, 255))
        image.save(self.actual_path, "PNG")
        return self.template_path


class FakeStaticPropUiWindow(object):
    def __init__(self):
        self.controls = {"window": "AssetForgeMayaWindow"}
        self.applied_settings = {}
        self.callbacks = []
        self.last_scan = None
        self.last_validation = None
        self.last_texture_scan = {}
        self.pipeline = FakeStaticPropUiPipeline(self)

    def _apply_project_settings(self, settings):
        self.applied_settings = dict(settings)

    def _scan(self):
        self.callbacks.append("_scan")
        self.last_scan = self.pipeline.scan()
        self.last_validation = None

    def _rename_prefix(self):
        self.callbacks.append("_rename_prefix")
        renamed = self.pipeline.rename_asset_root_with_prefix(self.applied_settings.get("mesh_prefix", "SM_"))
        renamed = list(renamed or []) + list(self.pipeline.rename_mesh_transforms_with_prefix(self.applied_settings.get("mesh_prefix", "SM_")))
        self.last_scan = self.pipeline.scan()
        self.last_validation = None
        return renamed

    def _validate(self):
        self.callbacks.append("_validate")
        self.last_scan = self.pipeline.scan()
        prefix = self.applied_settings.get("mesh_prefix", "SM_")
        can_export = self.last_scan["asset_name"].startswith(prefix)
        self.last_validation = {
            "status": "pass" if can_export else "error",
            "can_export": can_export,
            "checks": [] if can_export else [{"id": "name_prefix", "status": "error", "message": "missing prefix"}],
        }

    def _scan_texture_folder(self):
        self.callbacks.append("_scan_texture_folder")
        self.last_texture_scan = {"directory_status": "valid", "matched_count": 3}
        self.last_scan = dict(self.last_scan or self.pipeline.scan(), texture_folder_scan=self.last_texture_scan)

    def _export(self):
        self.callbacks.append("_export")
        result = self.pipeline.export_assets(
            ["|SM_Crate"],
            self.applied_settings.get("export_root", "D:/Exports"),
            self.applied_settings.get("target_platform", "high_end_mobile"),
            self.applied_settings.get("ue_target_path", "/Game/Props"),
            material_profile=self.applied_settings.get("material_profile", "Props_Opaque_PainterUE_ARM"),
            texture_folder=self.applied_settings.get("texture_root", ""),
            texture_set_token=self.applied_settings.get("texture_set_token", ""),
            texture_import_policy={
                "virtual_texture_policy": self.applied_settings.get("virtual_texture_policy", "project_default"),
                "texture_streaming_policy": self.applied_settings.get("texture_streaming_policy", "project_default"),
                "texture_group": self.applied_settings.get("texture_group", "project_default"),
            },
            static_mesh_import_policy={
                "nanite_policy": self.applied_settings.get("nanite_policy", "project_default"),
                "lod_group": self.applied_settings.get("static_mesh_lod_group", "project_default"),
                "import_lod_policy": self.applied_settings.get("static_mesh_lod_import_policy", "import_existing"),
            },
        )
        self.last_scan = result["scan"]
        self.last_validation = result["validation"]
        self.last_texture_scan = self.last_scan.get("texture_folder_scan", {})


class FakeStaticPropUiPipeline(object):
    def __init__(self, window):
        self.window = window
        self.asset_name = "Crate"
        self.export_calls = 0
        self.export_kwargs = {}

    def scan(self):
        scan = {
            "asset_name": self.asset_name,
            "asset_roots": ["|{0}".format(self.asset_name)],
            "mesh_count": 1,
            "textures": [],
        }
        if self.window.last_texture_scan:
            scan["texture_folder_scan"] = self.window.last_texture_scan
        return scan

    def rename_asset_root_with_prefix(self, prefix):
        if not self.asset_name.startswith(prefix):
            self.asset_name = prefix + self.asset_name
        return ["|{0}".format(self.asset_name)]

    def rename_mesh_transforms_with_prefix(self, prefix):
        return ["|{0}|{0}_part".format(self.asset_name)]

    def export_assets(self, selection, output_dir, *args, **kwargs):
        self.export_calls += 1
        self.export_kwargs = dict(kwargs)
        package_dir = "{0}/{1}".format(output_dir.replace("\\", "/"), self.asset_name)
        scan = self.scan()
        validation = {"status": "pass", "can_export": True, "checks": []}
        return {
            "scan": scan,
            "validation": validation,
            "package_dir": package_dir,
            "manifest_path": package_dir + "/" + self.asset_name + "_manifest.json",
            "fbx_path": package_dir + "/" + self.asset_name + ".fbx",
            "export_report_path": package_dir + "/" + self.asset_name + "_export_report.json",
        }


class patched_mcp_action(object):
    def __init__(self, cmds, scan):
        self.cmds = cmds
        self.scan = scan
        self.old_get_cmds = None
        self.old_pipeline = None
        self.old_logger = None

    def __enter__(self):
        self.old_get_cmds = mcp_actions.get_cmds
        self.old_pipeline = mcp_actions.MayaStaticPropPipeline
        self.old_logger = mcp_actions._logger
        FakeMcpPipeline.scan = dict(self.scan)
        mcp_actions.get_cmds = lambda: self.cmds
        mcp_actions.MayaStaticPropPipeline = FakeMcpPipeline
        mcp_actions._logger = lambda _root=None: FakeMcpLogger()
        return self

    def __exit__(self, exc_type, exc, tb):
        mcp_actions.get_cmds = self.old_get_cmds
        mcp_actions.MayaStaticPropPipeline = self.old_pipeline
        mcp_actions._logger = self.old_logger


class FakeImportCmds(object):
    def __init__(self, import_nodes=None):
        self.import_nodes = list(import_nodes) if import_nodes is not None else ["|AFMCP:B_banji", "|AFMCP:B_banji|B_banjiShape"]
        self.selected = []
        self.plugin_loaded = False
        self.new_scene = False
        self.grouped_nodes = []
        self.node_types = {
            "|AFMCP:B_banji": "transform",
            "|AFMCP:B_banji|B_banjiShape": "mesh",
            "|SM_AF_MCP_B_banji": "transform",
            "|SM_Empty": "transform",
        }

    def pluginInfo(self, name, query=False, loaded=False):
        return self.plugin_loaded

    def loadPlugin(self, name, quiet=True):
        self.plugin_loaded = True

    def file(self, path=None, **kwargs):
        if kwargs.get("new"):
            self.new_scene = True
            return None
        if kwargs.get("i"):
            return list(self.import_nodes)
        return ""

    def ls(self, *args, **kwargs):
        if kwargs.get("assemblies"):
            return []
        if kwargs.get("selection"):
            return list(self.selected)
        if args:
            nodes = args[0]
            return list(nodes if isinstance(nodes, list) else [nodes])
        return []

    def nodeType(self, node):
        return self.node_types.get(node, "")

    def listRelatives(self, node, parent=False, fullPath=False, **kwargs):
        if parent and "|" in node.strip("|"):
            return ["|" + node.strip("|").rsplit("|", 1)[0]]
        return []

    def rename(self, node, name):
        path = "|" + name
        self.node_types[path] = self.node_types.get(node, "transform")
        return path

    def group(self, nodes, name="", world=True):
        path = "|" + name
        self.grouped_nodes = list(nodes or [])
        self.node_types[path] = "transform"
        return path

    def select(self, nodes, replace=True):
        self.selected = list(nodes or [])


class OneShotSocketServer(object):
    def __init__(self, response):
        self.response = response
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(1)
        self.port = self.socket.getsockname()[1]
        self.received = {}
        self.thread = threading.Thread(target=self._serve)
        self.thread.daemon = True

    def start(self):
        self.thread.start()

    def stop(self):
        self.socket.close()
        self.thread.join(2)

    def _serve(self):
        conn, _addr = self.socket.accept()
        with conn:
            raw = _read_line(conn)
            self.received = json.loads(raw.decode("utf-8"))
            conn.sendall(encode_message(self.response))


def _read_line(sock):
    chunks = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    return b"".join(chunks).split(b"\n", 1)[0]


class FakeMayaCmds(types.ModuleType):
    def __init__(self):
        types.ModuleType.__init__(self, "maya.cmds")
        self.shelves = set(["ShelfTopLevel"])
        self.buttons = {}
        self.deleted = []
        self.windows = set()
        self.text_values = {}
        self.scroll_values = {}
        self.script_jobs = []
        self.call_order = []
        self._text_count = 0
        self._scroll_count = 0

    def shelfLayout(self, name=None, exists=False, parent=None):
        if exists:
            return name in self.shelves
        self.shelves.add(name)
        return name

    def shelfButton(self, name=None, exists=False, **kwargs):
        if exists:
            return name in self.buttons
        self.buttons[name] = dict(kwargs)
        return name

    def deleteUI(self, name):
        self.deleted.append(name)
        self.buttons.pop(name, None)
        self.windows.discard(name)

    def window(self, name=None, exists=False, **kwargs):
        if exists:
            return name in self.windows
        self.windows.add(name)
        return name

    def columnLayout(self, **kwargs):
        return "columnLayout1"

    def rowLayout(self, **kwargs):
        return "rowLayout1"

    def text(self, name=None, edit=False, label=None, **kwargs):
        if edit:
            self.text_values[name] = label
            return name
        self._text_count += 1
        control = name or "text{0}".format(self._text_count)
        self.text_values[control] = label
        return control

    def scrollField(self, name=None, edit=False, text=None, **kwargs):
        if edit:
            self.scroll_values[name] = text
            return name
        self._scroll_count += 1
        self.call_order.append("scrollField")
        control = name or "scroll{0}".format(self._scroll_count)
        self.scroll_values[control] = text
        return control

    def button(self, **kwargs):
        name = "button{0}".format(len(self.buttons) + 1)
        self.buttons[name] = dict(kwargs)
        self.call_order.append("button:{0}".format(kwargs.get("label", "")))
        return name

    def setParent(self, name):
        return name

    def showWindow(self, name):
        self.windows.add(name)
        return name

    def scriptJob(self, **kwargs):
        self.script_jobs.append(dict(kwargs))
        return len(self.script_jobs)


def _install_fake_maya_modules(fake_cmds, fake_mel):
    old = {name: sys.modules.get(name) for name in ["maya", "maya.cmds", "maya.mel"]}
    maya = types.ModuleType("maya")
    maya.cmds = fake_cmds
    maya.mel = fake_mel
    sys.modules["maya"] = maya
    sys.modules["maya.cmds"] = fake_cmds
    sys.modules["maya.mel"] = fake_mel
    return old


def _restore_modules(old):
    for name, module in old.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


if __name__ == "__main__":
    unittest.main()
