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


if __name__ == "__main__":
    unittest.main()
