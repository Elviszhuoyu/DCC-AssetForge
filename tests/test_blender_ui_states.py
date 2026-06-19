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


if __name__ == "__main__":
    unittest.main()
