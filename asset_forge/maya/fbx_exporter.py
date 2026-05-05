"""Maya FBX exporter for Static Prop assets."""

from __future__ import absolute_import

import os

from asset_forge.maya.cmds_bridge import get_cmds, get_mel


DEFAULT_FBX_EXPORT_PRESET = {
    "animation": False,
    "skins": False,
    "shapes": False,
    "smoothing_groups": True,
    "tangents_and_binormals": True,
    "triangulate": False,
    "units": "cm",
}


class MayaFbxExporter(object):
    """Export selected Maya assets through the FBX plugin."""

    def __init__(self, cmds_module=None, mel_module=None):
        self.cmds = cmds_module or get_cmds()
        self.mel = mel_module or get_mel()

    def is_available(self):
        return self.cmds is not None and self.mel is not None

    def export_asset(self, asset_root, output_path, preset=None):
        if not self.is_available():
            raise RuntimeError("当前环境不可用 maya.cmds 或 maya.mel")

        self._ensure_fbx_plugin()
        self._ensure_parent_dir(output_path)
        self.cmds.select(asset_root, replace=True)
        self._apply_preset(preset or DEFAULT_FBX_EXPORT_PRESET)
        self.mel.eval('FBXExport -f "{0}" -s'.format(self._maya_path(output_path)))
        return output_path

    def export_selected(self, output_path, preset=None):
        if not self.is_available():
            raise RuntimeError("当前环境不可用 maya.cmds 或 maya.mel")

        selection = self.cmds.ls(selection=True, long=True) or []
        if not selection:
            raise RuntimeError("没有选中可导出的资产")

        self._ensure_fbx_plugin()
        self._ensure_parent_dir(output_path)
        self._apply_preset(preset or DEFAULT_FBX_EXPORT_PRESET)
        self.mel.eval('FBXExport -f "{0}" -s'.format(self._maya_path(output_path)))
        return output_path

    def _ensure_fbx_plugin(self):
        if self.cmds.pluginInfo("fbxmaya", query=True, loaded=True):
            return
        self.cmds.loadPlugin("fbxmaya")

    def _apply_preset(self, preset):
        self.mel.eval("FBXResetExport")
        self.mel.eval("FBXExportInAscii -v false")
        self.mel.eval("FBXExportAnimationOnly -v false")
        self.mel.eval("FBXExportBakeComplexAnimation -v {0}".format(self._bool(preset.get("animation", False))))
        self.mel.eval("FBXExportSkins -v {0}".format(self._bool(preset.get("skins", False))))
        self.mel.eval("FBXExportShapes -v {0}".format(self._bool(preset.get("shapes", False))))
        self.mel.eval("FBXExportSmoothingGroups -v {0}".format(self._bool(preset.get("smoothing_groups", True))))
        self.mel.eval("FBXExportTangents -v {0}".format(self._bool(preset.get("tangents_and_binormals", True))))
        self.mel.eval("FBXExportTriangulate -v {0}".format(self._bool(preset.get("triangulate", False))))
        self.mel.eval("FBXExportConvertUnitString {0}".format(preset.get("units", "cm")))

    def _bool(self, value):
        return "true" if value else "false"

    def _ensure_parent_dir(self, path):
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.exists(parent):
            os.makedirs(parent)

    def _maya_path(self, path):
        return os.path.abspath(path).replace("\\", "/")
