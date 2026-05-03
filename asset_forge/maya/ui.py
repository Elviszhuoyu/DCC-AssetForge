"""Simple Maya cmds UI for Asset Forge Phase 1."""

from __future__ import absolute_import

import os

from asset_forge.maya.cmds_bridge import get_cmds
from asset_forge.maya.pipeline import MayaStaticPropPipeline
from asset_forge.shared.constants import (
    TARGET_PLATFORM_HIGH_END_MOBILE,
    TARGET_PLATFORM_MOBILE,
    TARGET_PLATFORM_PC,
)


WINDOW_NAME = "assetForgePhase1Window"


class AssetForgeMayaWindow(object):
    """Minimal Maya UI for the Static Prop MVP workflow."""

    def __init__(self, cmds_module=None, pipeline=None):
        self.cmds = cmds_module or get_cmds()
        self.pipeline = pipeline or MayaStaticPropPipeline()
        self.last_scan = None
        self.last_validation = None
        self.controls = {}

    def show(self):
        if self.cmds is None:
            raise RuntimeError("maya.cmds is not available")

        if self.cmds.window(WINDOW_NAME, exists=True):
            self.cmds.deleteUI(WINDOW_NAME)

        self.cmds.window(WINDOW_NAME, title="Asset Forge v0.1", widthHeight=(420, 520))
        self.cmds.columnLayout(adjustableColumn=True, rowSpacing=8)

        self.cmds.text(label="Asset Forge - Maya Static Prop MVP", align="left")
        self.controls["platform"] = self.cmds.optionMenu(label="目标平台")
        self.cmds.menuItem(label=TARGET_PLATFORM_PC)
        self.cmds.menuItem(label=TARGET_PLATFORM_HIGH_END_MOBILE)
        self.cmds.menuItem(label=TARGET_PLATFORM_MOBILE)
        self.cmds.optionMenu(self.controls["platform"], edit=True, value=TARGET_PLATFORM_HIGH_END_MOBILE)

        self.controls["target_path"] = self.cmds.textFieldGrp(
            label="UE 路径",
            text="/Game/Props",
            adjustableColumn=2,
        )
        self.controls["output_dir"] = self.cmds.textFieldButtonGrp(
            label="导出目录",
            text=os.path.expanduser("~/AssetForge/Exports"),
            buttonLabel="...",
            buttonCommand=self._choose_output_dir,
            adjustableColumn=2,
        )

        self.cmds.rowLayout(numberOfColumns=3, adjustableColumn=3)
        self.cmds.button(label="扫描", command=self._scan)
        self.cmds.button(label="检查", command=self._validate)
        self.cmds.button(label="导出", command=self._export)
        self.cmds.setParent("..")

        self.controls["summary"] = self.cmds.text(label="等待扫描", align="left")
        self.controls["results"] = self.cmds.scrollField(editable=False, wordWrap=True, height=300)
        self.cmds.button(label="AI 分析", command=self._analyze)

        self.cmds.showWindow(WINDOW_NAME)
        return WINDOW_NAME

    def _target_platform(self):
        return self.cmds.optionMenu(self.controls["platform"], query=True, value=True)

    def _target_path(self):
        return self.cmds.textFieldGrp(self.controls["target_path"], query=True, text=True)

    def _output_dir(self):
        return self.cmds.textFieldButtonGrp(self.controls["output_dir"], query=True, text=True)

    def _choose_output_dir(self, *args):
        paths = self.cmds.fileDialog2(fileMode=3, caption="选择 Asset Forge 导出目录") or []
        if paths:
            self.cmds.textFieldButtonGrp(self.controls["output_dir"], edit=True, text=paths[0])

    def _scan(self, *args):
        try:
            self.last_scan = self.pipeline.scan_selection()
            self.last_validation = None
            self._set_summary("扫描完成: {0}".format(self.last_scan.get("asset_name", "")))
            self._set_results(self._format_scan(self.last_scan))
        except Exception as exc:
            self._show_error(exc)

    def _validate(self, *args):
        try:
            if self.last_scan is None:
                self.last_scan = self.pipeline.scan_selection()
            self.last_validation = self.pipeline.validate_scan(self.last_scan, self._target_platform())
            self._set_summary(
                "检查完成: {0} / Score {1}".format(
                    self.last_validation.get("status"),
                    self.last_validation.get("score"),
                )
            )
            self._set_results(self._format_validation(self.last_validation))
        except Exception as exc:
            self._show_error(exc)

    def _export(self, *args):
        try:
            selection = self.pipeline.adapter.get_current_selection()
            if not selection:
                raise RuntimeError("No selected asset")
            result = self.pipeline.export_asset(
                selection[0],
                self._output_dir(),
                self._target_platform(),
                self._target_path(),
            )
            self.last_scan = result["scan"]
            self.last_validation = result["validation"]
            self._set_summary("导出完成: {0}".format(result["manifest_path"]))
            self._set_results(self._format_validation(result["validation"]))
        except Exception as exc:
            self._show_error(exc)

    def _analyze(self, *args):
        try:
            if self.last_scan is None:
                self.last_scan = self.pipeline.scan_selection()
            if self.last_validation is None:
                self.last_validation = self.pipeline.validate_scan(self.last_scan, self._target_platform())
            suggestion = self.pipeline.analyze(self.last_scan, self.last_validation)
            self._set_summary("AI 建议已生成")
            self._set_results(suggestion)
        except Exception as exc:
            self._show_error(exc)

    def _format_scan(self, scan):
        lines = [
            "Asset: {0}".format(scan.get("asset_name", "")),
            "Meshes: {0}".format(scan.get("mesh_count", 0)),
            "Triangles: {0}".format(scan.get("triangles", 0)),
            "Material Slots: {0}".format(scan.get("material_slots", 0)),
            "UV0: {0}".format(scan.get("has_uv0", False)),
            "Lightmap UV: {0}".format(scan.get("has_lightmap_uv", False)),
            "Frozen Transform: {0}".format(scan.get("frozen_transform", False)),
            "Hidden Objects: {0}".format(len(scan.get("hidden_objects", []))),
            "History Nodes: {0}".format(len(scan.get("history_nodes", []))),
        ]
        return "\n".join(lines)

    def _format_validation(self, validation):
        lines = [
            "Status: {0}".format(validation.get("status")),
            "Score: {0}".format(validation.get("score")),
            "Can Export: {0}".format(validation.get("can_export")),
            "",
        ]
        for item in validation.get("checks", []):
            lines.append("[{0}] {1}: {2}".format(item["status"], item["label"], item["message"]))
        return "\n".join(lines)

    def _set_summary(self, text):
        self.cmds.text(self.controls["summary"], edit=True, label=text)

    def _set_results(self, text):
        self.cmds.scrollField(self.controls["results"], edit=True, text=text)

    def _show_error(self, exc):
        message = str(exc)
        self._set_summary("错误: {0}".format(message))
        self._set_results(message)
        self.cmds.warning(message)


def show():
    """Show the Asset Forge Maya window."""
    return AssetForgeMayaWindow().show()
