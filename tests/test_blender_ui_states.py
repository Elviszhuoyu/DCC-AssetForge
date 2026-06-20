from __future__ import absolute_import

import importlib
import sys
import types
import unittest


class BlenderUiStateTest(unittest.TestCase):
    def setUp(self):
        self.old_bpy = sys.modules.get("bpy")
        bpy = types.ModuleType("bpy")
        bpy.types = types.SimpleNamespace(PropertyGroup=object, Operator=object, Panel=object)
        bpy.props = types.SimpleNamespace(
            EnumProperty=lambda **_kwargs: None,
            StringProperty=lambda **_kwargs: None,
            IntProperty=lambda **_kwargs: None,
            PointerProperty=lambda **_kwargs: None,
        )
        bpy.utils = types.SimpleNamespace(register_class=lambda _cls: None, unregister_class=lambda _cls: None)
        bpy.path = types.SimpleNamespace(abspath=lambda value: value)
        sys.modules["bpy"] = bpy
        self.addCleanup(self._restore_bpy)

    def _restore_bpy(self):
        if self.old_bpy is None:
            sys.modules.pop("bpy", None)
        else:
            sys.modules["bpy"] = self.old_bpy

    def test_warning_state_does_not_use_error_icon(self):
        ui = importlib.import_module("integrations.blender.asset_forge_extension.ui")

        self.assertEqual(ui._status_icon("warning"), "QUESTION")
        self.assertNotEqual(ui._status_icon("warning"), "ERROR")
        self.assertEqual(ui._line_state("状态：可导出 | 分数：56 | 通过/警告/阻断：8/4/0"), "warning")

    def test_texture_detail_separates_node_folder_and_placeholder_sources(self):
        ui = importlib.import_module("integrations.blender.asset_forge_extension.ui")
        scan = {
            "materials": [
                {
                    "name": "B_a1",
                    "base_color": [0.5, 0.5, 0.5, 1.0],
                    "textures": [
                        {"usage": "base_color", "source_type": "blender_image_node"},
                        {"usage": "normal", "source_type": "texture_folder"},
                        {"usage": "packed_arm", "source_type": "blender_placeholder"},
                    ],
                }
            ]
        }

        text = ui._format_texture_detail(scan)

        self.assertIn("贴图来源：Blender节点 1 / 占位 1 / 贴图目录 1", text)
        self.assertIn("base_color[节点]", text)
        self.assertIn("normal[目录]", text)
        self.assertIn("packed_arm[占位]", text)
        self.assertNotIn("已发现节点贴图", text)

    def test_restart_bridge_operator_is_registered_and_visible(self):
        ui = importlib.import_module("integrations.blender.asset_forge_extension.ui")

        self.assertIn(ui.ASSETFORGE_OT_restart_bridge, ui.CLASSES)
        self.assertEqual(ui.ASSETFORGE_OT_restart_bridge.bl_idname, "asset_forge.restart_bridge")

    def test_params_include_publish_rule_fields(self):
        ui = importlib.import_module("integrations.blender.asset_forge_extension.ui")
        settings = types.SimpleNamespace(
            target_platform="high_end_mobile",
            target_path="/Game/Props/Blender",
            material_profile="Props_Opaque_PainterUE_ARM",
            mesh_prefix="AF_",
            triangle_budget=123,
            texture_root="",
            texture_set_token="",
            export_root="",
            virtual_texture_policy="project_default",
            texture_streaming_policy="project_default",
            texture_group="project_default",
            nanite_policy="project_default",
            static_mesh_lod_group="project_default",
            static_mesh_lod_import_policy="import_existing",
        )
        root = types.SimpleNamespace(name="B", parent=None)
        context = types.SimpleNamespace(scene=types.SimpleNamespace(asset_forge_settings=settings), selected_objects=[root], active_object=root)

        params = ui._params(context)

        self.assertEqual(params["selection"], ["B"])
        self.assertEqual(params["mesh_prefix"], "AF_")
        self.assertEqual(params["triangle_budget"], 123)

    def test_bridge_state_warns_when_bridge_version_is_missing_or_old(self):
        ui = importlib.import_module("integrations.blender.asset_forge_extension.ui")

        self.assertEqual(ui._version_tuple("0.2.0"), (0, 2, 0))
        self.assertLess(ui._version_tuple("0.1.9"), ui._version_tuple(ui.MIN_BRIDGE_VERSION))

        class OldModule(object):
            BRIDGE_VERSION = "0.1.0"

        class NewModule(object):
            BRIDGE_VERSION = "0.2.0"

        self.assertEqual(ui._bridge_version(object()), "")
        self.assertLess(ui._version_tuple(ui._bridge_version(OldModule)), ui._version_tuple(ui.MIN_BRIDGE_VERSION))
        self.assertEqual(ui._version_tuple(ui._bridge_version(NewModule)), ui._version_tuple(ui.MIN_BRIDGE_VERSION))

    def test_independent_bridge_ui_exposes_chinese_restart_and_refresh_modules(self):
        bridge_ui = importlib.import_module("integrations.blender_mcp_bridge.ui")

        self.assertEqual(bridge_ui.BRIDGE_VERSION, "0.2.0")
        self.assertIn(bridge_ui.BLENDERMCP_OT_restart_bridge, bridge_ui.CLASSES)
        self.assertIn(bridge_ui.BLENDERMCP_OT_refresh_asset_forge_modules, bridge_ui.CLASSES)
        self.assertEqual(bridge_ui.BLENDERMCP_OT_restart_bridge.bl_idname, "blender_mcp.restart_bridge")
        self.assertEqual(bridge_ui.BLENDERMCP_OT_refresh_asset_forge_modules.bl_label, "刷新 Asset Forge 模块")
        self.assertIn("健康：离线", bridge_ui._status_line())

    def test_independent_bridge_ui_refresh_modules_uses_whitelisted_action(self):
        bridge_ui = importlib.import_module("integrations.blender_mcp_bridge.ui")
        calls = []

        class FakeActiveBridge(object):
            def handle_request(self, request):
                calls.append(request)
                return {
                    "ok": True,
                    "result": {
                        "refreshed_modules": ["asset_forge.blender.provider_asset_forge"],
                    },
                }

        class FakeSettings(object):
            last_action = ""
            log_text = "Bridge 日志为空。"

        context = types.SimpleNamespace(scene=types.SimpleNamespace(blender_mcp_settings=FakeSettings()))
        old_current_bridge = bridge_ui.bridge.current_bridge
        bridge_ui.bridge.current_bridge = lambda: FakeActiveBridge()
        try:
            result = bridge_ui.BLENDERMCP_OT_refresh_asset_forge_modules().execute(context)
        finally:
            bridge_ui.bridge.current_bridge = old_current_bridge

        self.assertEqual(result, {"FINISHED"})
        self.assertEqual(calls[0]["action"], "blender_refresh_asset_forge_modules")
        self.assertIn("asset_forge.blender.provider_asset_forge", context.scene.blender_mcp_settings.log_text)


if __name__ == "__main__":
    unittest.main()
