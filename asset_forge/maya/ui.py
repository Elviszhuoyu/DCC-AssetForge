# -*- coding: utf-8 -*-
"""Maya cmds 发布工作台：Static Prop MVP 的轻量可验收入口。"""

from __future__ import absolute_import

import io
import importlib.util
import json
import os
import sys
from datetime import datetime

from asset_forge.maya.cmds_bridge import get_cmds
from asset_forge.maya.operation_logger import MayaOperationLogger, latest_log_path, read_latest_log_tail
from asset_forge.maya.package_opener import open_directory
from asset_forge.maya.pipeline import ExportValidationError, MayaStaticPropPipeline
from asset_forge.maya.project_settings import format_project_settings_summary
from asset_forge.maya.project_settings import load_project_settings, normalize_project_settings, save_project_settings
from asset_forge.shared.constants import ASSET_TYPE_STATIC_PROP
from asset_forge.shared.constants import TARGET_PLATFORM_HIGH_END_MOBILE, TARGET_PLATFORM_MOBILE, TARGET_PLATFORM_PC
from asset_forge.shared.material_profile_schema import get_project_material_profiles
from asset_forge.shared.unreal_path import sanitize_unreal_package_path


WINDOW_NAME = "assetForgePhase1Window"
BUILD_LABEL = "Asset Forge v0.1.8 - Maya 发布工作台 / Build 2026-06-03-R10"
INITIAL_NEXT_ACTION = "下一步 | 选中资产根节点 -> 扫描资产"
EMPTY_SELECTION_GUIDANCE = (
    "没有选中资产。\n"
    "下一步：在 Maya 里选择一个资产根节点或共同父组后重试；"
    "如果场景唯一可导出资产，Asset Forge 会在扫描时自动兜底；"
    "如果有多个候选资产，它不会猜测。"
)
PREFLIGHT_REPAIR_REPORT_HINT = "预检阶段不写报告；导出被阻断时会写调试报告。"
STATUS_COLORS = {
    "ok": (0.09, 0.17, 0.14),
    "warning": (0.18, 0.15, 0.10),
    "error": (0.20, 0.11, 0.11),
    "info": (0.09, 0.15, 0.18),
    "waiting": (0.14, 0.15, 0.16),
    "panel": (0.11, 0.12, 0.13),
    "muted": (0.18, 0.19, 0.20),
}
STATUS_ACCENTS = {
    "ok": "#6ff2ba",
    "warning": "#e6b85c",
    "error": "#ff726d",
    "info": "#6bd7f5",
    "waiting": "#8a969c",
    "panel": "#768187",
    "muted": "#595c60",
}


def asset_forge_repo_root():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
    return repo_root


def asset_forge_icon_path(filename="IconMayaHeader.png"):
    repo_root = asset_forge_repo_root()
    candidates = [
        os.path.join(repo_root, "Plugins", "AssetForge", "Resources", filename),
        os.path.join(repo_root, "Plugins", "AssetForge", "Resources", "IconMayaHeader.png"),
        os.path.join(repo_root, "Plugins", "AssetForge", "Resources", "IconToolbar.png"),
        os.path.join(repo_root, "Plugins", "AssetForge", "Resources", "Icon128.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path.replace("\\", "/")
    return ""


class AssetForgeMayaWindow(object):
    """Maya 端发布工作台。保持 cmds 兼容，把发布决策放在主屏。"""

    def __init__(self, cmds_module=None, pipeline=None, logger=None, log_root=None):
        self.cmds = cmds_module or get_cmds()
        self.pipeline = pipeline or MayaStaticPropPipeline()
        self.last_scan = None
        self.last_validation = None
        self.last_texture_scan = {}
        self.last_package_dir = ""
        self.last_selection = []
        self.project_settings_path = ""
        self.controls = {}
        self._button_controls = set()
        self._launcher_module = None
        self.logger = logger or MayaOperationLogger(root=log_root)
        self.latest_log_path = latest_log_path(self.logger.root)

    def show(self):
        if self.cmds is None:
            raise RuntimeError("maya.cmds is not available")

        if self.cmds.window(WINDOW_NAME, exists=True):
            self.cmds.deleteUI(WINDOW_NAME)

        self.cmds.window(WINDOW_NAME, title=BUILD_LABEL, widthHeight=(980, 780))
        if hasattr(self.cmds, "scrollLayout"):
            self.controls["main_scroll"] = self.cmds.scrollLayout(childResizable=True, verticalScrollBarThickness=16)
        self.cmds.columnLayout(adjustableColumn=True, rowSpacing=7)
        self._build_header()
        self._build_project_preset_panel()
        self._build_primary_actions()
        self._build_publish_setup()
        self._build_asset_panel()
        self._build_texture_panel()
        self._build_preflight_panel()
        self._build_advanced_settings()
        self._build_log_panel()

        self.cmds.showWindow(WINDOW_NAME)
        self._log_operation("startup", "success", outputs={"window": WINDOW_NAME})
        self._refresh_last_maya_log()
        return WINDOW_NAME

    def _build_header(self):
        self.cmds.rowLayout(numberOfColumns=3, adjustableColumn=2, columnWidth3=(56, 540, 250), columnAttach3=("left", "left", "right"))
        icon_path = asset_forge_icon_path("IconMayaHeader.png")
        if icon_path and hasattr(self.cmds, "image"):
            self.controls["brand_badge"] = self.cmds.image(image=icon_path, width=48, height=48)
        else:
            self.controls["brand_badge"] = self.cmds.text(label="Asset Forge", align="center", width=48, height=28)
            self._style_status_control(self.controls["brand_badge"], "panel", compact=True)
        self.cmds.columnLayout(adjustableColumn=True, rowSpacing=2)
        self.cmds.text(label="Asset Forge Maya 发布工作台", align="left")
        self.cmds.text(label="v0.1.8 / Build 2026-06-03-R10", align="left")
        self.cmds.text(label="Maya 导出 Package -> UE Gate 入审报告 / 预演导入计划 / 正式导入", align="left")
        self.cmds.text(label="Maya 负责导出包和建议；UE Gate 负责生成入审报告、预演导入计划和正式导入。", align="left")
        self.cmds.setParent("..")
        self._build_mcp_header_controls()
        self.cmds.setParent("..")
        self._section("发布状态", collapse=False, key="overview_section")
        self.controls["summary"] = self._status_text("未扫描 | 等待选择资产", "panel", height=30)
        self.controls["next_action"] = self._status_text(INITIAL_NEXT_ACTION, "info", height=30)
        self.controls["overview_panel"] = self._status_text(format_overview_panel({}, {}, {}), "panel", height=30)
        self._build_status_card_row()
        self._build_issue_locator()
        self._end_section()

    def _build_project_preset_panel(self):
        self._section("项目预设", collapse=False, key="project_preset_section")
        self.controls["settings_path"] = self.cmds.text(label="当前预设：未加载 / 未保存", align="left")
        self.controls["settings_summary"] = self.cmds.scrollField(
            editable=False,
            wordWrap=True,
            height=112,
            text=format_project_settings_summary(normalize_project_settings({}), max_rows=8),
        )
        self._button_row(
            [
                ("加载预设", self._load_project_settings),
                ("保存预设", self._save_project_settings),
                ("应用当前预设", self._apply_current_settings),
            ]
        )
        self._end_section()

    def _build_status_card_row(self):
        self.cmds.rowLayout(numberOfColumns=4, adjustableColumn=4)
        self.controls["asset_card"] = self._status_button("asset_card", format_asset_card({}), self._focus_asset_panel, "waiting", height=30, width=230)
        self.controls["texture_card"] = self._status_button("texture_card", format_texture_card({}), self._focus_texture_panel, "waiting", height=30, width=230)
        self.controls["issue_card"] = self._status_button("issue_card", format_issue_card({}), self._focus_preflight_panel, "waiting", height=30, width=230)
        self.controls["export_card"] = self._status_button("export_card", format_export_card({}, {}), self._focus_export_panel, "waiting", height=30, width=230)
        self.cmds.setParent("..")

    def _build_issue_locator(self):
        self._section("问题定位", collapse=False, key="issue_locator_section")
        self.controls["issue_locator"] = self.cmds.scrollField(editable=False, wordWrap=True, height=126, text=format_issue_locator({}, {}, {}))
        self._end_section()

    def _build_mcp_header_controls(self):
        self.cmds.rowLayout(numberOfColumns=3, adjustableColumn=1, columnWidth3=(150, 50, 50))
        self.controls["mcp_status"] = self.cmds.text(label="MCP：未检查", align="left")
        self._style_status_control(self.controls["mcp_status"], "muted", compact=True)
        self.cmds.button(label="启动", command=self._start_mcp_bridge, width=54)
        self.cmds.button(label="状态", command=self._show_mcp_status, width=54)
        self.cmds.setParent("..")

    def _start_mcp_bridge(self, *args):
        try:
            launcher = self._load_launcher_module()
            status = launcher.start_bridge(repo_root=asset_forge_repo_root())
            bridge_module = launcher.current_bridge_module(asset_forge_repo_root())
            self._register_mcp_status_listener(bridge_module)
            self._set_mcp_status(status)
            self._log_operation("mcp_bridge_start_from_ui", "success", outputs=status)
        except Exception as exc:
            self._set_mcp_status({"status": "error", "message": str(exc)})
            self._show_error(exc, "mcp_bridge_start_from_ui")

    def _show_mcp_status(self, *args):
        try:
            launcher = self._load_launcher_module()
            bridge_module = launcher.current_bridge_module(asset_forge_repo_root())
            self._register_mcp_status_listener(bridge_module)
            status = bridge_module.show_bridge_status_window()
            self._set_mcp_status(status)
            self._log_operation("mcp_bridge_show_status_from_ui", "success", outputs=status)
        except Exception as exc:
            self._set_mcp_status({"status": "error", "message": str(exc)})
            self._show_error(exc, "mcp_bridge_show_status_from_ui")

    def _load_launcher_module(self):
        if self._launcher_module is not None:
            return self._launcher_module
        path = os.path.join(asset_forge_repo_root(), "scripts", "maya_launch_asset_forge.py")
        module_name = "asset_forge_maya_ui_launcher"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载 Maya launcher: {0}".format(path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        self._launcher_module = module
        return module

    def _register_mcp_status_listener(self, bridge_module):
        register = getattr(bridge_module, "register_status_listener", None)
        if not callable(register):
            return
        if getattr(self, "_mcp_status_listener_registered", False):
            return
        register(self._set_mcp_status)
        self._mcp_status_listener_registered = True

    def _set_mcp_status(self, status):
        if "mcp_status" not in self.controls:
            return
        status = status or {}
        state = status.get("status", "unknown")
        port = status.get("port", "")
        if state == "running":
            text = "MCP：{0} 运行中".format(port) if port else "MCP：运行中"
        elif state == "success":
            text = "MCP：入口已刷新"
        elif state == "stopped":
            text = "MCP：未运行"
        elif state == "error":
            text = "MCP：启动失败"
        else:
            text = "MCP：{0}".format(state)
        self.cmds.text(self.controls["mcp_status"], edit=True, label=text)
        self._style_status_control(self.controls["mcp_status"], _mcp_status_state(state), compact=True)

    def _status_text(self, label, state="muted", height=None, width=None):
        kwargs = {
            "label": label,
            "align": "left",
            "enableBackground": True,
            "backgroundColor": STATUS_COLORS.get(state, STATUS_COLORS["muted"]),
        }
        if height:
            kwargs["height"] = height
        if width:
            kwargs["width"] = width
        control = self.cmds.text(**kwargs)
        self._style_status_control(control, state)
        return control

    def _status_button(self, name, label, command, state="muted", height=None, width=None):
        kwargs = {
            "label": label,
            "align": "left",
            "command": command,
            "enableBackground": True,
            "backgroundColor": STATUS_COLORS.get(state, STATUS_COLORS["muted"]),
        }
        if height:
            kwargs["height"] = height
        if width:
            kwargs["width"] = width
        control = self.cmds.button(**kwargs)
        self._button_controls.add(name)
        self._style_status_button(control, state)
        return control

    def _style_status_control(self, control, state="muted", compact=False):
        try:
            import maya.OpenMayaUI as omui  # type: ignore
            try:
                from shiboken6 import wrapInstance  # type: ignore
                from PySide6 import QtWidgets  # type: ignore
            except Exception:
                from shiboken2 import wrapInstance  # type: ignore
                from PySide2 import QtWidgets  # type: ignore
            ptr = omui.MQtUtil.findControl(control)
            if not ptr:
                return
            widget = wrapInstance(int(ptr), QtWidgets.QWidget)
            rgb = _qt_rgb(STATUS_COLORS.get(state, STATUS_COLORS["muted"]))
            accent = STATUS_ACCENTS.get(state, STATUS_ACCENTS["muted"])
            text_color = _status_text_color(state)
            padding = "2px 7px" if compact else "5px 9px"
            radius = "6px" if compact else "8px"
            weight = "600" if state in ("ok", "warning", "error", "info") else "500"
            widget.setStyleSheet(
                "QLabel {{"
                "background-color: rgb({0});"
                "color: {1};"
                "border: 1px solid #3b4245;"
                "border-left: 3px solid {2};"
                "border-radius: {3};"
                "padding: {4};"
                "font-weight: {5};"
                "}}".format(rgb, text_color, accent, radius, padding, weight)
            )
        except Exception:
            return

    def _style_status_button(self, control, state="muted"):
        try:
            import maya.OpenMayaUI as omui  # type: ignore
            try:
                from shiboken6 import wrapInstance  # type: ignore
                from PySide6 import QtWidgets  # type: ignore
            except Exception:
                from shiboken2 import wrapInstance  # type: ignore
                from PySide2 import QtWidgets  # type: ignore
            ptr = omui.MQtUtil.findControl(control)
            if not ptr:
                return
            widget = wrapInstance(int(ptr), QtWidgets.QWidget)
            rgb = _qt_rgb(STATUS_COLORS.get(state, STATUS_COLORS["muted"]))
            accent = STATUS_ACCENTS.get(state, STATUS_ACCENTS["muted"])
            text_color = _status_text_color(state)
            widget.setStyleSheet(
                "QPushButton {{"
                "background-color: rgb({0});"
                "color: {1};"
                "border: 1px solid #3b4245;"
                "border-left: 3px solid {2};"
                "border-radius: 6px;"
                "padding: 5px 9px;"
                "font-weight: 600;"
                "text-align: left;"
                "}}"
                "QPushButton:hover {{border-color: {2};}}".format(rgb, text_color, accent)
            )
        except Exception:
            return

    def _build_primary_actions(self):
        self._section("发布动作", collapse=False, key="action_section")
        self._button_row(
            [
                ("1 扫描资产", self._scan, 160),
                ("2 检查风险", self._validate, 160),
                ("3 导出 Package 给 UE Gate", self._export, 240),
            ]
        )
        self._end_section()

    def _build_publish_setup(self):
        self._section("1 发布目标", collapse=False)
        self.controls["platform"] = self.cmds.optionMenu(label="目标平台")
        self.cmds.menuItem(label=TARGET_PLATFORM_PC)
        self.cmds.menuItem(label=TARGET_PLATFORM_HIGH_END_MOBILE)
        self.cmds.menuItem(label=TARGET_PLATFORM_MOBILE)
        self.cmds.optionMenu(self.controls["platform"], edit=True, value=TARGET_PLATFORM_HIGH_END_MOBILE)

        self.controls["material_profile"] = self.cmds.optionMenu(label="材质匹配规则")
        for profile in get_project_material_profiles()["profiles"]:
            self.cmds.menuItem(label=profile["name"])
        self.cmds.optionMenu(self.controls["material_profile"], edit=True, value="Props_Opaque_PainterUE_ARM")

        self.controls["target_path"] = self.cmds.textFieldGrp(label="UE 目标路径", text="/Game/Props", adjustableColumn=2)
        self.controls["output_dir"] = self.cmds.textFieldButtonGrp(
            label="导出根目录",
            text=os.path.expanduser("~/AssetForge/Exports"),
            buttonLabel="选择",
            buttonCommand=self._choose_output_dir,
            adjustableColumn=2,
        )
        self._end_section()

    def _build_asset_panel(self):
        self._section("2 资产概览", collapse=False, key="asset_section")
        self.controls["asset_hint"] = self.cmds.text(label="资产概览：未扫描", align="left")
        self.controls["name_prefix"] = self.cmds.textFieldGrp(label="模型前缀", text="SM_", adjustableColumn=2)
        self.controls["asset_name_override"] = self.cmds.textFieldGrp(label="包体/文件夹名", text="", adjustableColumn=2)
        self.controls["package_version_mode"] = self._option_menu("包体迭代模式", ["overwrite", "auto_increment"], "overwrite")
        self.controls["triangle_budget"] = self.cmds.intFieldGrp(label="三角面预算", value1=50000, adjustableColumn=2)
        self._button_row([("修复资产名前缀", self._rename_prefix, 180)])
        self._section("资产详情", collapse=True, key="asset_detail_section")
        self.controls["asset_identity"] = self.cmds.scrollField(editable=False, wordWrap=True, height=112, text=format_asset_identity({}))
        self._end_section()
        self._end_section()

    def _build_texture_panel(self):
        self._section("3 贴图匹配", collapse=False, key="texture_section")
        self.controls["texture_hint"] = self.cmds.text(label="贴图匹配：未扫描", align="left")
        self.controls["texture_folder"] = self.cmds.textFieldButtonGrp(
            label="贴图目录",
            text="",
            buttonLabel="选择",
            buttonCommand=self._choose_texture_folder,
            adjustableColumn=2,
        )
        self.controls["texture_set_token"] = self.cmds.textFieldGrp(label="贴图集关键词", text="", adjustableColumn=2)
        self.controls["texture_prefix"] = self.cmds.textFieldGrp(label="贴图前缀", text="T_", adjustableColumn=2)
        self._button_row([("扫描贴图目录", self._scan_texture_folder, 150), ("修复贴图前缀", self._rename_texture_prefix, 180)])
        self._section("贴图详情", collapse=True, key="texture_detail_section")
        self.controls["texture_summary"] = self.cmds.scrollField(editable=False, wordWrap=True, height=168, text=format_empty_texture_details())
        self._end_section()
        self._end_section()

    def _build_preflight_panel(self):
        self._section("4 风险检查", collapse=False, key="preflight_section")
        self.controls["preflight_hint"] = self.cmds.text(label="风险检查：未预检", align="left")
        self._section("检查详情", collapse=True, key="preflight_detail_section")
        self.controls["preflight"] = self.cmds.scrollField(editable=False, wordWrap=True, height=186, text=format_empty_preflight_details())
        self._end_section()
        self._end_section()

    def _build_advanced_settings(self):
        self.cmds.text(label="高级设置 / 导入策略（写入 Package，UE Gate 可复核）", align="left")
        self._section("基础导入", collapse=True)
        self.cmds.text(label="Maya 只生成 Package 和导入建议；UE Gate 按“生成入审报告 -> 预演导入计划 -> 正式导入”执行。", align="left")
        self._end_section()

        self._section("网格构建", collapse=True)
        self.cmds.text(label="保持 Mesh / 独立 Mesh 关系清晰；Combine Meshes、法线、LOD、Nanite 会在 UE Gate 预演导入计划中确认。", align="left")
        self.controls["nanite_policy"] = self._option_menu("Nanite 策略建议", ["project_default", "enable", "disable", "report_only"], "project_default")
        self.controls["static_mesh_lod_group"] = self.cmds.textFieldGrp(label="Mesh LODGroup 建议", text="project_default", adjustableColumn=2)
        self.controls["static_mesh_lod_import_policy"] = self._option_menu("Mesh LOD 导入策略建议", ["import_existing", "project_default", "ignore_lods", "report_only"], "import_existing")
        self._end_section()

        self._section("材质贴图", collapse=True)
        self.cmds.text(label="这些值会写入 Package；UE Gate 导入前仍可复核和覆盖。", align="left")
        self.controls["virtual_texture_policy"] = self._option_menu("Virtual Texture 策略建议", ["project_default", "auto", "force_on", "force_off"], "project_default")
        self.controls["texture_streaming_policy"] = self._option_menu("Texture Streaming 策略建议", ["project_default", "streaming", "never_stream"], "project_default")
        self.controls["texture_group"] = self.cmds.textFieldGrp(label="Texture Group 建议", text="project_default", adjustableColumn=2)
        self._end_section()

    def _build_log_panel(self):
        self._section("结果 / 日志", collapse=True)
        self._button_row([("打开导出目录", self._open_last_package), ("AI 分析", self._analyze), ("导出调试信息", self._export_debug_bundle)])
        self.controls["results"] = self.cmds.scrollField(editable=False, wordWrap=True, height=64)
        self.cmds.text(label="Maya 操作日志", align="left")
        self.controls["last_maya_log"] = self.cmds.scrollField(editable=False, wordWrap=True, height=76)
        self._end_section()

    def _section(self, label, collapse=False, key=None):
        if hasattr(self.cmds, "frameLayout"):
            try:
                frame = self.cmds.frameLayout(label=label, collapsable=True, collapse=bool(collapse), marginWidth=6, marginHeight=4)
                if key:
                    self.controls[key] = frame
                self.cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
                return
            except Exception:
                pass
        if key:
            self.controls[key] = label
        self.cmds.text(label=label, align="left")

    def _end_section(self):
        if hasattr(self.cmds, "frameLayout"):
            try:
                self.cmds.setParent("..")
                self.cmds.setParent("..")
            except Exception:
                pass

    def _separator(self):
        if hasattr(self.cmds, "separator"):
            try:
                self.cmds.separator(height=8, style="in")
            except Exception:
                pass

    def _button_row(self, buttons):
        self.cmds.rowLayout(numberOfColumns=len(buttons), adjustableColumn=len(buttons))
        for item in buttons:
            label, command = item[0], item[1]
            kwargs = {"label": label, "command": command}
            if len(item) > 2:
                kwargs["width"] = item[2]
            self.cmds.button(**kwargs)
        self.cmds.setParent("..")

    def _option_menu(self, label, values, default):
        control = self.cmds.optionMenu(label=label)
        for value in values:
            self.cmds.menuItem(label=value)
        self.cmds.optionMenu(control, edit=True, value=default)
        return control

    def _target_platform(self):
        return self.cmds.optionMenu(self.controls["platform"], query=True, value=True)

    def _target_path(self):
        value = self.cmds.textFieldGrp(self.controls["target_path"], query=True, text=True)
        try:
            return sanitize_unreal_package_path(value)
        except ValueError as exc:
            raise RuntimeError(str(exc))

    def _name_prefix(self):
        return self.cmds.textFieldGrp(self.controls["name_prefix"], query=True, text=True).strip() or "SM_"

    def _asset_name_override(self):
        return self.cmds.textFieldGrp(self.controls["asset_name_override"], query=True, text=True).strip()

    def _package_version_mode(self):
        return self.cmds.optionMenu(self.controls["package_version_mode"], query=True, value=True) if "package_version_mode" in self.controls else "overwrite"

    def _texture_prefix(self):
        return self.cmds.textFieldGrp(self.controls["texture_prefix"], query=True, text=True).strip() or "T_"

    def _triangle_budget(self):
        return int(self.cmds.intFieldGrp(self.controls["triangle_budget"], query=True, value1=True) or 0)

    def _material_profile(self):
        return self.cmds.optionMenu(self.controls["material_profile"], query=True, value=True)

    def _output_dir(self):
        value = self.cmds.textFieldButtonGrp(self.controls["output_dir"], query=True, text=True).strip()
        return self._unicode_safe_field_value("export_root", value)

    def _texture_folder(self):
        value = self.cmds.textFieldButtonGrp(self.controls["texture_folder"], query=True, text=True).strip()
        return self._unicode_safe_field_value("texture_root", value)

    def _texture_set_token(self):
        return self.cmds.textFieldGrp(self.controls["texture_set_token"], query=True, text=True).strip()

    def _virtual_texture_policy(self):
        return self.cmds.optionMenu(self.controls["virtual_texture_policy"], query=True, value=True) if "virtual_texture_policy" in self.controls else "project_default"

    def _texture_streaming_policy(self):
        return self.cmds.optionMenu(self.controls["texture_streaming_policy"], query=True, value=True) if "texture_streaming_policy" in self.controls else "project_default"

    def _texture_group(self):
        return self.cmds.textFieldGrp(self.controls["texture_group"], query=True, text=True).strip() if "texture_group" in self.controls else "project_default"

    def _static_mesh_lod_group(self):
        return self.cmds.textFieldGrp(self.controls["static_mesh_lod_group"], query=True, text=True).strip() if "static_mesh_lod_group" in self.controls else "project_default"

    def _nanite_policy(self):
        return self.cmds.optionMenu(self.controls["nanite_policy"], query=True, value=True) if "nanite_policy" in self.controls else "project_default"

    def _static_mesh_lod_import_policy(self):
        return self.cmds.optionMenu(self.controls["static_mesh_lod_import_policy"], query=True, value=True) if "static_mesh_lod_import_policy" in self.controls else "import_existing"

    def _texture_import_policy(self):
        return {
            "virtual_texture_policy": self._virtual_texture_policy() or "project_default",
            "texture_streaming_policy": self._texture_streaming_policy() or "project_default",
            "texture_group": self._texture_group() or "project_default",
        }

    def _static_mesh_import_policy(self):
        applied = getattr(self, "applied_project_settings", {}) or {}
        return {
            "nanite_policy": self._nanite_policy() or "project_default",
            "lod_group": self._static_mesh_lod_group() or "project_default",
            "import_lod_policy": self._static_mesh_lod_import_policy() or "import_existing",
            "build_reversed_index_buffer": applied.get("build_reversed_index_buffer", "report_only"),
            "generate_lightmap_uvs": applied.get("generate_lightmap_uvs", "report_only"),
            "collision_complexity": applied.get("collision_complexity", "report_only"),
        }

    def _active_rules(self):
        rules = _copy_rules(self.pipeline.rules)
        static_rules = rules.setdefault(ASSET_TYPE_STATIC_PROP, {})
        budgets = dict(static_rules.get("max_triangles", {}))
        budget = self._triangle_budget()
        if budget > 0:
            budgets[self._target_platform()] = budget
        static_rules["max_triangles"] = budgets
        static_rules["name_prefix"] = self._name_prefix()
        return rules

    def _choose_output_dir(self, *args):
        paths = self.cmds.fileDialog2(fileMode=3, caption="选择 Asset Forge 导出根目录") or []
        if paths:
            self.cmds.textFieldButtonGrp(self.controls["output_dir"], edit=True, text=paths[0])

    def _choose_texture_folder(self, *args):
        paths = self.cmds.fileDialog2(fileMode=3, caption="选择 Painter / Designer 贴图目录") or []
        if paths:
            self.cmds.textFieldButtonGrp(self.controls["texture_folder"], edit=True, text=paths[0])

    def _run_preflight(self):
        selection = self.pipeline.adapter.get_current_selection()
        if not selection:
            raise RuntimeError(format_empty_selection_guidance())
        changed = bool(self.last_selection and list(selection) != list(self.last_selection))
        preflight = self.pipeline.preflight_assets(
            selection,
            target_platform=self._target_platform(),
            material_profile=self._material_profile(),
            texture_folder=self._texture_folder(),
            texture_set_token=self._texture_set_token(),
            target_path=self._target_path(),
            asset_name_override=self._asset_name_override(),
            rules=self._active_rules(),
            texture_import_policy=self._texture_import_policy(),
            static_mesh_import_policy=self._static_mesh_import_policy(),
            source_name_suffix="Maya",
        )
        self.last_scan = preflight["scan"]
        self.last_validation = preflight["validation"]
        self.last_texture_scan = preflight.get("texture_folder_scan", {})
        self.last_selection = list(selection)
        preflight["selection_changed"] = changed
        return preflight

    def _scan(self, *args):
        try:
            self.last_scan = self.pipeline.scan_selection()
            self.last_validation = None
            self.last_texture_scan = self.last_scan.get("texture_folder_scan", {})
            self.last_selection = list(self.last_scan.get("asset_roots", []))
            self._set_summary("状态：模型扫描完成")
            self._set_next_action("下一步：点击“检查”，确认是否可以导出。")
            self._refresh_status_cards(self.last_scan, self.last_validation, self.last_texture_scan)
            self._set_panel("asset_identity", format_asset_identity(self.last_scan))
            self._set_panel("preflight", "下一步：点击“检查”查看阻断项、警告和可修复项。")
            self._focus_asset_panel()
            self._set_results("模型扫描完成。")
            self._log_operation("scan_model", "success", outputs={"asset_name": self.last_scan.get("asset_name", ""), "mesh_count": self.last_scan.get("mesh_count", 0)})
        except Exception as exc:
            self._show_error(exc, "scan_model")

    def _validate(self, *args):
        try:
            preflight = self._run_preflight()
            text = format_preflight_summary(preflight["scan"], preflight["validation"], preflight.get("texture_folder_scan", {}))
            if preflight.get("selection_changed"):
                text = "检测到当前 Maya 选择已变化，已自动重新扫描。\n\n" + text
            self._apply_preflight_to_ui(preflight["scan"], preflight["validation"], preflight.get("texture_folder_scan", {}), text)
            self._set_results("预检完成。")
            repair_actions = repair_actions_for_state(preflight["scan"], preflight["validation"], preflight.get("texture_folder_scan", {}))
            self._log_operation(
                "preflight",
                "success",
                outputs={
                    "status": preflight["validation"].get("status"),
                    "can_export": preflight["validation"].get("can_export"),
                    "repair_action_count": len(repair_actions),
                    "repair_actions": repair_actions,
                },
            )
        except Exception as exc:
            self._show_error(exc, "preflight")

    def _scan_texture_folder(self, *args):
        try:
            selection_changed = self._scan_if_selection_changed()
            if self.last_scan is None:
                self.last_scan = self.pipeline.scan_selection()
                self.last_selection = list(self.last_scan.get("asset_roots", []))
            folder = self._texture_folder()
            if not folder:
                raise RuntimeError("请先指定贴图目录")
            folder_scan = self.pipeline.scan_texture_folder(folder, self.last_scan.get("asset_name", ""), self._material_profile(), self._texture_set_token())
            self.last_texture_scan = folder_scan
            self.last_scan = dict(self.last_scan, texture_folder_scan=folder_scan, textures=list(folder_scan.get("textures", [])))
            self._set_summary("状态：贴图目录扫描完成，匹配 {0} 张".format(folder_scan.get("matched_count", 0)))
            self._set_next_action(_next_action_for_texture_scan(folder_scan))
            self._refresh_status_cards(self.last_scan, self.last_validation, self.last_texture_scan)
            self._set_panel("asset_identity", format_asset_identity(self.last_scan))
            texture_summary = self._format_texture_folder_scan(folder_scan)
            if selection_changed:
                texture_summary = "检测到当前 Maya 选择已变化，扫描贴图前已自动重新扫描资产。\n\n" + texture_summary
            self._set_panel("texture_summary", texture_summary)
            self._focus_texture_panel()
            self._set_results("贴图目录扫描完成。")
            self._log_operation(
                "scan_texture_folder",
                "success",
                inputs={"texture_folder": folder, "texture_set_token": self._texture_set_token()},
                outputs={
                    "matched_count": folder_scan.get("matched_count", 0),
                    "selected_texture_sets": folder_scan.get("selected_texture_sets", []),
                    "status": folder_scan.get("directory_status", ""),
                    "repair_actions": repair_actions_for_state(self.last_scan, self.last_validation or {}, folder_scan),
                },
                warnings=folder_scan.get("issues", []),
            )
        except Exception as exc:
            self._show_error(exc, "scan_texture_folder")

    def _export(self, *args):
        try:
            selection = self.pipeline.adapter.get_current_selection()
            if not selection:
                raise RuntimeError(format_empty_selection_guidance())
            preflight = self._run_preflight()
            preflight_text = format_preflight_summary(preflight["scan"], preflight["validation"], preflight.get("texture_folder_scan", {}))
            if preflight.get("selection_changed"):
                preflight_text = "检测到当前 Maya 选择已变化，导出前已自动重新扫描。\n\n" + preflight_text
            if not preflight["validation"].get("can_export", False):
                debug_report_path = ""
                if hasattr(self.pipeline, "_write_blocked_export_report"):
                    debug_report_path = self.pipeline._write_blocked_export_report(
                        self._output_dir(),
                        preflight["scan"],
                        preflight["validation"],
                        self._target_platform(),
                        self._target_path(),
                    )
                self._apply_preflight_to_ui(preflight["scan"], preflight["validation"], preflight.get("texture_folder_scan", {}), preflight_text, status="导出前预检未通过")
                self._set_results(format_export_blocked_result(preflight["scan"], preflight["validation"], debug_report_path))
                self._log_operation(
                    "export_preflight_blocked",
                    "error",
                    outputs=_blocked_export_log_outputs(preflight["scan"], preflight["validation"], debug_report_path),
                    errors=_blocking_messages(preflight["validation"]),
                    report_path=debug_report_path,
                )
                return

            self._log_operation("export_start", "started", inputs={"selection_count": len(selection), "target_path": self._target_path(), "texture_set_token": self._texture_set_token()})
            result = self.pipeline.export_assets(
                selection,
                self._output_dir(),
                self._target_platform(),
                self._target_path(),
                material_profile=self._material_profile(),
                texture_folder=self._texture_folder(),
                texture_set_token=self._texture_set_token(),
                asset_name_override=self._asset_name_override(),
                rules=self._active_rules(),
                texture_import_policy=self._texture_import_policy(),
                static_mesh_import_policy=self._static_mesh_import_policy(),
                source_name_suffix="Maya",
                package_name_override=self._asset_name_override(),
                package_version_mode=self._package_version_mode(),
                project_preset=self._settings_from_ui(),
            )
            self.last_scan = result["scan"]
            self.last_validation = result["validation"]
            self.last_texture_scan = self.last_scan.get("texture_folder_scan", {})
            self.last_package_dir = result.get("package_dir", "")
            self._apply_preflight_to_ui(result["scan"], result["validation"], self.last_texture_scan, format_preflight_summary(result["scan"], result["validation"], self.last_texture_scan), status="导出完成")
            self._set_next_action("下一步：到 UE Gate 选择该 Package，生成入审报告并预演导入计划，再查看 UE 日志与导入报告。")
            self._set_results(format_export_result_summary(result))
            self._log_operation("export_success", "success", outputs=_export_log_outputs(result), report_path=result.get("export_report_path", ""))
        except ExportValidationError as exc:
            self.last_scan = exc.scan
            self.last_validation = exc.validation
            self.last_texture_scan = (exc.scan or {}).get("texture_folder_scan", {})
            self._apply_preflight_to_ui(exc.scan, exc.validation, self.last_texture_scan, format_blocking_validation_summary(exc.validation, exc.scan, exc.debug_report_path), status="导出被阻断")
            self._set_results(format_export_blocked_result(exc.scan, exc.validation, exc.debug_report_path))
            self._log_operation("export_failed", "error", outputs=_blocked_export_log_outputs(exc.scan, exc.validation, exc.debug_report_path), errors=[str(exc)], report_path=exc.debug_report_path)
            self.cmds.warning(str(exc))
        except Exception as exc:
            self._show_error(exc, "export_failed")

    def _rename_prefix(self, *args):
        undo_open = False
        try:
            scan = self.last_scan or self.pipeline.scan_selection()
            if self._should_confirm_prefix_fix():
                answer = self.cmds.confirmDialog(
                    title="确认修复资产名前缀",
                    message=_format_asset_prefix_preview(scan, self._name_prefix()),
                    button=["执行", "取消"],
                    defaultButton="执行",
                    cancelButton="取消",
                    dismissString="取消",
                )
                if answer != "执行":
                    self._set_summary("状态：已取消资产名前缀修复")
                    self._set_results("未修改 Maya 场景。")
                    self._log_operation("fix_asset_name_prefix", "cancelled", inputs={"mesh_prefix": self._name_prefix()}, outputs={"asset_name": scan.get("asset_name", "")})
                    return
            if hasattr(self.cmds, "undoInfo"):
                self.cmds.undoInfo(openChunk=True, chunkName="Asset Forge 修复资产名前缀")
                undo_open = True
            if hasattr(self.pipeline, "rename_asset_root_with_prefix"):
                renamed = self.pipeline.rename_asset_root_with_prefix(self._name_prefix())
            else:
                renamed = self.pipeline.rename_selection_with_prefix(self._name_prefix())
            if renamed and hasattr(self.cmds, "select"):
                self.cmds.select(renamed, replace=True)
            if hasattr(self.pipeline, "rename_mesh_transforms_with_prefix"):
                renamed = list(renamed or []) + list(self.pipeline.rename_mesh_transforms_with_prefix(self._name_prefix()) or [])
            self.last_scan = self.pipeline.scan_selection()
            self.last_validation = None
            self._set_summary("状态：资产名前缀修复完成")
            self._refresh_status_cards(self.last_scan, self.last_validation, self.last_texture_scan)
            self._set_panel("asset_identity", format_asset_identity(self.last_scan))
            self._set_panel("preflight", "已修复资产名，请重新点击“检查”。")
            self._set_results("已处理资产名前缀: {0}".format(", ".join([item.split("|")[-1] for item in renamed])))
            self._log_operation("fix_asset_name_prefix", "success", inputs={"mesh_prefix": self._name_prefix()}, outputs={"renamed": renamed})
        except Exception as exc:
            self._show_error(exc, "fix_asset_name_prefix")
        finally:
            if undo_open:
                self.cmds.undoInfo(closeChunk=True)

    def _rename_texture_prefix(self, *args):
        try:
            if self.last_scan is None:
                self.last_scan = self.pipeline.scan_selection()
            if self._texture_folder():
                folder_scan = self.pipeline.scan_texture_folder(
                    self._texture_folder(),
                    self.last_scan.get("asset_name", ""),
                    self._material_profile(),
                    self._texture_set_token(),
                )
                self.last_texture_scan = folder_scan
                self.last_scan = dict(self.last_scan, texture_folder_scan=folder_scan, textures=list(folder_scan.get("textures", [])))
            active_scan = self.last_texture_scan or self.last_scan
            preview = self.pipeline.plan_texture_prefix_renames(active_scan, self._texture_prefix(), require_selected_set=True)
            if preview.get("status") == "error":
                raise RuntimeError(preview.get("message", "贴图前缀重命名预览失败。"))
            if hasattr(self.cmds, "confirmDialog"):
                answer = self.cmds.confirmDialog(
                    title="确认添加贴图前缀",
                    message=_format_texture_prefix_preview(preview),
                    button=["执行", "取消"],
                    defaultButton="执行",
                    cancelButton="取消",
                    dismissString="取消",
                )
                if answer != "执行":
                    self._set_summary("状态：已取消贴图前缀重命名")
                    self._set_results(self._format_texture_prefix_result(preview))
                    self._log_operation("add_texture_prefix", "cancelled", inputs={"texture_set_token": self._texture_set_token()}, outputs=preview)
                    return
            else:
                self._set_summary("状态：贴图前缀预览完成，当前测试环境不执行磁盘重命名")
                self._set_results(self._format_texture_prefix_result(preview))
                self._log_operation("add_texture_prefix", "preview", inputs={"texture_prefix": self._texture_prefix(), "texture_set_token": self._texture_set_token()}, outputs=preview, warnings=[item for item in preview.get("actions", []) if item.get("status") == "skipped"])
                return
            result = self.pipeline.execute_texture_prefix_renames(active_scan, self._texture_prefix(), require_selected_set=True)
            self._set_summary("状态：贴图前缀处理完成，重命名 {0}，跳过 {1}".format(result.get("renamed_count", 0), result.get("skipped_count", 0)))
            self._refresh_status_cards(self.last_scan, self.last_validation, self.last_texture_scan)
            self._set_results(self._format_texture_prefix_result(result))
            self._log_operation("add_texture_prefix", "success", inputs={"texture_prefix": self._texture_prefix(), "texture_set_token": self._texture_set_token()}, outputs=result, warnings=[item for item in result.get("actions", []) if item.get("status") == "skipped"])
        except Exception as exc:
            self._show_error(exc, "add_texture_prefix")

    def _open_last_package(self, *args):
        try:
            opened_path = open_directory(self.last_package_dir)
            self._set_summary("状态：已打开导出目录")
            self._set_results("导出目录: {0}".format(opened_path))
            self._log_operation("open_package_dir", "success", outputs={"opened_path": opened_path})
        except Exception as exc:
            self._show_error(exc, "open_package_dir")

    def _analyze(self, *args):
        try:
            if self.last_scan is None:
                self.last_scan = self.pipeline.scan_selection()
            if self.last_validation is None:
                self.last_validation = self.pipeline.validate_scan(self.last_scan, self._target_platform())
            suggestion = self.pipeline.analyze(self.last_scan, self.last_validation)
            self._set_summary("状态：AI 建议已生成")
            self._set_results(suggestion)
            self._log_operation("ai_analyze", "success")
        except Exception as exc:
            self._show_error(exc, "ai_analyze")

    def _export_debug_bundle(self, *args):
        try:
            debug_dir = os.path.join(self.logger.root, "AssetForgeReports", "debug")
            if not os.path.isdir(debug_dir):
                os.makedirs(debug_dir)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_path = os.path.join(debug_dir, "maya_debug_{0}.txt".format(timestamp))
            lines = [
                BUILD_LABEL,
                "generated_at: {0}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                "latest_log: {0}".format(self.latest_log_path),
                "last_package_dir: {0}".format(self.last_package_dir or "未生成"),
                "selection: {0}".format(", ".join(self.last_selection) or "未扫描"),
                "",
                "[settings]",
                json.dumps(self._settings_snapshot(), ensure_ascii=False, indent=2, sort_keys=True),
                "",
                "[scan]",
                json.dumps(self.last_scan or {}, ensure_ascii=False, indent=2, sort_keys=True),
                "",
                "[validation]",
                json.dumps(self.last_validation or {}, ensure_ascii=False, indent=2, sort_keys=True),
                "",
                "[texture_scan]",
                json.dumps(self.last_texture_scan or {}, ensure_ascii=False, indent=2, sort_keys=True),
                "",
                "[maya_log_tail]",
                "\n".join(read_latest_log_tail(self.logger.root, 18)),
            ]
            with io.open(debug_path, "w", encoding="utf-8") as stream:
                stream.write("\n".join(lines))
            self._set_summary("状态：调试信息已导出", "ok")
            self._set_results("调试信息已导出：{0}".format(debug_path.replace("\\", "/")))
            self._log_operation("export_debug_bundle", "success", outputs={"debug_path": debug_path.replace("\\", "/")})
        except Exception as exc:
            self._show_error(exc, "export_debug_bundle")

    def _settings_from_ui(self):
        settings = dict(getattr(self, "applied_project_settings", {}) or {})
        settings.update(
            {
                "export_root": self._output_dir(),
                "texture_root": self._texture_folder(),
                "triangle_budget": self._triangle_budget(),
                "mesh_prefix": self._name_prefix(),
                "package_name_override": self._asset_name_override(),
                "asset_name_override": self._asset_name_override(),
                "package_version_mode": self._package_version_mode(),
                "texture_prefix": self._texture_prefix(),
                "texture_set_token": self._texture_set_token(),
                "ue_target_path": self._target_path(),
                "target_platform": self._target_platform(),
                "material_profile": self._material_profile(),
                "virtual_texture_policy": self._virtual_texture_policy(),
                "texture_streaming_policy": self._texture_streaming_policy(),
                "texture_group": self._texture_group(),
                "nanite_policy": self._nanite_policy(),
                "static_mesh_lod_group": self._static_mesh_lod_group(),
                "static_mesh_lod_import_policy": self._static_mesh_lod_import_policy(),
            }
        )
        return normalize_project_settings(settings)

    def _scan_if_selection_changed(self):
        selection = self.pipeline.adapter.get_current_selection()
        if not selection:
            raise RuntimeError("没有选中资产")
        if self.last_scan is None:
            return False
        if self.last_selection and list(selection) == list(self.last_selection):
            return False
        self.last_scan = self.pipeline.scan_selection()
        self.last_validation = None
        self.last_texture_scan = self.last_scan.get("texture_folder_scan", {})
        self.last_selection = list(selection)
        return True

    def _should_confirm_prefix_fix(self):
        if getattr(self, "skip_confirmations", False):
            return False
        return hasattr(self.cmds, "confirmDialog")

    def _apply_project_settings(self, settings):
        active = normalize_project_settings(settings)
        self.applied_project_settings = dict(active)
        self.cmds.textFieldButtonGrp(self.controls["output_dir"], edit=True, text=active["export_root"])
        self.cmds.textFieldButtonGrp(self.controls["texture_folder"], edit=True, text=active["texture_root"])
        self.cmds.textFieldGrp(self.controls["name_prefix"], edit=True, text=active["mesh_prefix"])
        self.cmds.textFieldGrp(self.controls["asset_name_override"], edit=True, text=active["package_name_override"])
        if "package_version_mode" in self.controls:
            self.cmds.optionMenu(self.controls["package_version_mode"], edit=True, value=active["package_version_mode"])
        self.cmds.textFieldGrp(self.controls["texture_prefix"], edit=True, text=active["texture_prefix"])
        self.cmds.textFieldGrp(self.controls["texture_set_token"], edit=True, text=active["texture_set_token"])
        self.cmds.textFieldGrp(self.controls["target_path"], edit=True, text=active["ue_target_path"])
        self.cmds.intFieldGrp(self.controls["triangle_budget"], edit=True, value1=active["triangle_budget"])
        self.cmds.optionMenu(self.controls["platform"], edit=True, value=active["target_platform"])
        self.cmds.optionMenu(self.controls["material_profile"], edit=True, value=active["material_profile"])
        if "virtual_texture_policy" in self.controls:
            self.cmds.optionMenu(self.controls["virtual_texture_policy"], edit=True, value=active["virtual_texture_policy"])
        if "texture_streaming_policy" in self.controls:
            self.cmds.optionMenu(self.controls["texture_streaming_policy"], edit=True, value=active["texture_streaming_policy"])
        if "texture_group" in self.controls:
            self.cmds.textFieldGrp(self.controls["texture_group"], edit=True, text=active["texture_group"])
        if "nanite_policy" in self.controls:
            self.cmds.optionMenu(self.controls["nanite_policy"], edit=True, value=active["nanite_policy"])
        if "static_mesh_lod_group" in self.controls:
            self.cmds.textFieldGrp(self.controls["static_mesh_lod_group"], edit=True, text=active["static_mesh_lod_group"])
        if "static_mesh_lod_import_policy" in self.controls:
            self.cmds.optionMenu(self.controls["static_mesh_lod_import_policy"], edit=True, value=active["static_mesh_lod_import_policy"])
        self._set_preset_summary(active)
        return active

    def _unicode_safe_field_value(self, settings_key, ui_value):
        if "?" not in (ui_value or ""):
            return ui_value
        applied = getattr(self, "applied_project_settings", {}) or {}
        expected = applied.get(settings_key, "")
        if expected and any(ord(char) > 127 for char in expected):
            return expected
        return ui_value

    def _load_project_settings(self, *args):
        try:
            paths = self.cmds.fileDialog2(fileMode=1, caption="加载 Asset Forge 项目预设 JSON") or []
            if not paths:
                return
            settings = load_project_settings(paths[0])
            self._apply_project_settings(settings)
            self.project_settings_path = paths[0]
            self._set_settings_path(paths[0], "已加载")
            self._set_summary("状态：已加载项目预设")
            self._set_preset_summary(settings)
            self._set_results("{0}\n\n预设文件：{1}".format(_format_project_settings(settings), paths[0]))
            self._log_operation("load_project_settings", "success", inputs={"path": paths[0]}, outputs=settings)
        except Exception as exc:
            self._show_error(exc, "load_project_settings")

    def _save_project_settings(self, *args):
        try:
            paths = self.cmds.fileDialog2(fileMode=0, caption="保存 Asset Forge 项目预设 JSON") or []
            if not paths:
                return
            settings = self._settings_from_ui()
            path = save_project_settings(paths[0], settings)
            self.project_settings_path = path
            saved_settings = load_project_settings(path)
            self._set_settings_path(path, "已保存")
            self._set_summary("状态：已保存项目预设")
            self._set_preset_summary(saved_settings)
            self._set_results("{0}\n\n保存路径: {1}".format(_format_project_settings(saved_settings), path))
            self._log_operation("save_project_settings", "success", inputs={"path": paths[0]}, outputs={"path": path})
        except Exception as exc:
            self._show_error(exc, "save_project_settings")

    def _apply_current_settings(self, *args):
        try:
            settings = self._apply_project_settings(self._settings_from_ui())
            self._set_summary("状态：项目预设已应用到当前 UI")
            if self.project_settings_path:
                self._set_settings_path(self.project_settings_path, "已应用")
            self._set_preset_summary(settings)
            self._set_results("{0}\n\n当前预设文件：{1}".format(_format_project_settings(settings), self.project_settings_path or "未加载 / 未保存"))
            self._log_operation("apply_project_settings", "success", outputs=settings)
        except Exception as exc:
            self._show_error(exc, "apply_project_settings")

    def _format_texture_folder_scan(self, scan):
        if not scan:
            return "状态：未扫描贴图目录\n下一步：指定贴图目录后点击“扫描贴图目录”。"
        lines = [
            "状态：{0}".format(scan.get("directory_status", "unknown")),
            "当前选择：{0}".format(", ".join(scan.get("selected_texture_set_short_names", [])) or "未选择"),
            "已选贴图集：{0}".format(", ".join(scan.get("selected_texture_sets", [])) or "无"),
            "将导出贴图数量：{0}".format(scan.get("matched_count", 0)),
            "将导出用途：{0}".format(", ".join(scan.get("matched_usages", [])) or "无"),
            "",
            "候选贴图集：",
        ]
        sets = scan.get("texture_sets", [])
        if not sets:
            lines.append("- 未找到候选贴图集")
        for item in sets:
            short = item.get("short_name", "") or item.get("set_name", "").split("_")[-1]
            missing = ", ".join(item.get("missing_usages", [])) or "无"
            usages = ", ".join(item.get("usages", [])) or "无"
            marker = "（当前）" if item.get("set_name", "") in scan.get("selected_texture_sets", []) else ""
            lines.append("- {0} / {1}{2}：完整度 {3}；用途 {4}；缺失 {5}".format(short, item.get("set_name", ""), marker, item.get("completeness", 0), usages, missing))
        lines.extend(["", "问题："])
        if scan.get("issues"):
            for issue in scan.get("issues", []):
                lines.append("- {0}".format(issue.get("message", issue) if isinstance(issue, dict) else issue))
        else:
            lines.append("- 无阻断问题")
        lines.extend(["", "下一步建议："])
        if scan.get("auto_selected_texture_sets"):
            lines.append("- 未填写贴图集关键词，系统已自动选择当前最优贴图集；如不正确，请填写 a1,d1 或完整名称片段后重新扫描。")
        elif scan.get("selected_texture_set_short_names"):
            lines.append("- 已按当前关键词选择贴图集；确认数量和用途后继续预检。")
        elif scan.get("rename_suggestions"):
            lines.append("- 如需规范命名，先确认贴图集，再点击“一键添加贴图前缀”。")
        else:
            lines.append("- 可以继续预检或导出。")
        return "\n".join(lines)

    def _apply_preflight_to_ui(self, scan, validation, texture_scan, preflight_text, status=""):
        state = "ok" if (validation or {}).get("can_export") else _issue_card_state(validation)
        self._set_summary("状态：{0}".format(status or ("可导出" if (validation or {}).get("can_export") else "不可导出")), state)
        self._set_next_action(format_next_action_summary(scan or {}, validation or {}, texture_scan or {}))
        self._refresh_status_cards(scan or {}, validation or {}, texture_scan or {})
        self._set_panel("asset_identity", format_asset_identity(scan or {}))
        self._set_panel("texture_summary", self._format_texture_folder_scan(texture_scan or {}))
        self._set_panel("preflight", preflight_text)
        self._focus_preflight_panel()

    def _format_texture_prefix_result(self, result):
        lines = [
            "贴图前缀：{0}".format(result.get("texture_prefix", "")),
            "计划/已重命名：{0}".format(result.get("renamed_count", result.get("planned_count", 0))),
            "跳过：{0}".format(result.get("skipped_count", 0)),
            "",
        ]
        for action in result.get("actions", []):
            lines.append("[{0}] {1}".format(action.get("status", ""), action.get("message", "")))
        return "\n".join(lines)

    def _set_summary(self, text, state=None):
        polished = _polish_status_text(text)
        self._set_label("summary", polished, state or _summary_state(polished))

    def _set_next_action(self, text, state="info"):
        if "next_action" in self.controls:
            self._set_label("next_action", _polish_next_action_text(text), state)

    def _set_label(self, name, text, state=None):
        if name in self.controls:
            kwargs = {"edit": True, "label": text}
            if state:
                kwargs.update({"enableBackground": True, "backgroundColor": STATUS_COLORS.get(state, STATUS_COLORS["muted"])})
            if name in self._button_controls and hasattr(self.cmds, "button"):
                self.cmds.button(self.controls[name], **kwargs)
            else:
                self.cmds.text(self.controls[name], **kwargs)
            if state:
                if name in self._button_controls:
                    self._style_status_button(self.controls[name], state)
                else:
                    self._style_status_control(self.controls[name], state)

    def _refresh_status_cards(self, scan=None, validation=None, texture_scan=None):
        scan = scan or {}
        validation = validation or {}
        texture_scan = texture_scan or {}
        self._set_label("overview_panel", format_overview_panel(scan, validation, texture_scan), _overview_panel_state(scan, validation, texture_scan))
        self._set_label("asset_card", format_asset_card(scan), _asset_card_state(scan))
        self._set_label("texture_card", format_texture_card(texture_scan, scan), _texture_card_state(texture_scan, scan))
        self._set_label("issue_card", format_issue_card(validation), _issue_card_state(validation))
        self._set_label("export_card", format_export_card(scan, validation, texture_scan), _export_card_state(scan, validation, texture_scan))
        self._set_label("asset_hint", format_asset_card(scan))
        self._set_label("texture_hint", format_texture_card(texture_scan, scan))
        self._set_label("preflight_hint", format_issue_card(validation))
        self._set_panel("issue_locator", format_issue_locator(scan, validation, texture_scan))

    def _focus_asset_panel(self, *args):
        self._expand_sections("asset_section", "asset_detail_section")
        self._set_panel("issue_locator", format_issue_locator(self.last_scan or {}, self.last_validation or {}, self.last_texture_scan or {}, preferred="asset"))

    def _focus_texture_panel(self, *args):
        self._expand_sections("texture_section", "texture_detail_section")
        self._set_panel("issue_locator", format_issue_locator(self.last_scan or {}, self.last_validation or {}, self.last_texture_scan or {}, preferred="texture"))

    def _focus_preflight_panel(self, *args):
        self._expand_sections("issue_locator_section", "preflight_section", "preflight_detail_section")
        self._set_panel("issue_locator", format_issue_locator(self.last_scan or {}, self.last_validation or {}, self.last_texture_scan or {}, preferred="risk"))

    def _focus_export_panel(self, *args):
        self._expand_sections("action_section", "preflight_section", "preflight_detail_section")
        self._set_panel("issue_locator", format_issue_locator(self.last_scan or {}, self.last_validation or {}, self.last_texture_scan or {}, preferred="export"))

    def _expand_sections(self, *names):
        if not hasattr(self.cmds, "frameLayout"):
            return
        for name in names:
            control = self.controls.get(name)
            if not control:
                continue
            try:
                self.cmds.frameLayout(control, edit=True, collapse=False)
            except Exception:
                pass

    def _set_settings_path(self, path, status):
        if "settings_path" in self.controls:
            self.cmds.text(self.controls["settings_path"], edit=True, label="当前预设：{0}（{1}）".format(path, status))

    def _set_preset_summary(self, settings):
        if "settings_summary" in self.controls:
            self.cmds.scrollField(
                self.controls["settings_summary"],
                edit=True,
                text=format_project_settings_summary(settings, max_rows=10),
            )

    def _set_panel(self, name, text):
        if name in self.controls:
            self.cmds.scrollField(self.controls[name], edit=True, text=text)

    def _set_results(self, text):
        self.cmds.scrollField(self.controls["results"], edit=True, text="{0}\n\n日志路径：{1}".format(text, self.latest_log_path))

    def _show_error(self, exc, operation="ui_error"):
        message = str(exc)
        self._set_summary("状态：错误", "error")
        self._set_results(message)
        self._log_operation(operation, "error", errors=[message])
        self.cmds.warning(message)

    def _log_operation(self, operation, status, inputs=None, outputs=None, errors=None, warnings=None, report_path=""):
        entry = self.logger.log(operation, status, inputs=self._operation_inputs(inputs), outputs=outputs, errors=errors, warnings=warnings, report_path=report_path)
        self.latest_log_path = entry.get("log_path", self.latest_log_path)
        self._refresh_last_maya_log()
        return entry

    def _operation_inputs(self, inputs=None):
        data = dict(inputs or {})
        data["settings"] = self._settings_snapshot()
        return data

    def _settings_snapshot(self):
        snapshot = {}
        readers = {
            "export_root": self._output_dir,
            "texture_root": self._texture_folder,
            "triangle_budget": self._triangle_budget,
            "mesh_prefix": self._name_prefix,
            "texture_prefix": self._texture_prefix,
            "texture_set_token": self._texture_set_token,
            "asset_name_override": self._asset_name_override,
            "package_name_override": self._asset_name_override,
            "package_version_mode": self._package_version_mode,
            "ue_target_path": self._target_path,
            "target_platform": self._target_platform,
            "material_profile": self._material_profile,
            "virtual_texture_policy": self._virtual_texture_policy,
            "texture_streaming_policy": self._texture_streaming_policy,
            "texture_group": self._texture_group,
            "nanite_policy": self._nanite_policy,
            "static_mesh_lod_group": self._static_mesh_lod_group,
            "static_mesh_lod_import_policy": self._static_mesh_lod_import_policy,
            "build_reversed_index_buffer": lambda: (getattr(self, "applied_project_settings", {}) or {}).get("build_reversed_index_buffer", "report_only"),
            "generate_lightmap_uvs": lambda: (getattr(self, "applied_project_settings", {}) or {}).get("generate_lightmap_uvs", "report_only"),
            "collision_complexity": lambda: (getattr(self, "applied_project_settings", {}) or {}).get("collision_complexity", "report_only"),
        }
        for key, reader in readers.items():
            try:
                snapshot[key] = reader()
            except Exception:
                snapshot[key] = ""
        return snapshot

    def _refresh_last_maya_log(self):
        if "last_maya_log" not in self.controls:
            return
        self.cmds.scrollField(self.controls["last_maya_log"], edit=True, text=self._format_last_maya_log())

    def _format_last_maya_log(self, tail_lines=30):
        entries = read_latest_log_tail(self.logger.root, tail_lines)
        if not entries:
            return "日志路径：{0}\n暂无 Maya 操作日志。".format(self.latest_log_path)
        formatted = ["日志路径：{0}".format(self.latest_log_path), ""]
        for entry in entries:
            formatted.append(_format_log_entry(entry))
        return "\n".join(formatted)


def show():
    """Show the Asset Forge Maya window."""
    return AssetForgeMayaWindow().show()


def _qt_rgb(color):
    return "{0}, {1}, {2}".format(
        int(max(0.0, min(1.0, color[0])) * 255),
        int(max(0.0, min(1.0, color[1])) * 255),
        int(max(0.0, min(1.0, color[2])) * 255),
    )


def _status_text_color(state):
    if state == "ok":
        return "#c8f8df"
    if state == "warning":
        return "#f4dda8"
    if state == "error":
        return "#ffcecb"
    if state == "info":
        return "#cbeeff"
    return "#e6eaec"


def format_overview_panel(scan, validation, texture_scan=None):
    scan = scan or {}
    validation = validation or {}
    texture_scan = texture_scan or {}
    return "{0}    {1}".format(
        _overview_status_line(scan, validation),
        "资产 {0}    贴图 {1}    风险 {2}    发布 {3}".format(
            _overview_asset_line(scan),
            _overview_texture_line(texture_scan, scan),
            _overview_risk_line(validation),
            _overview_export_line(scan, validation, texture_scan),
        ),
    )


def format_empty_texture_details():
    return "\n".join(
        [
            "尚未扫描贴图目录。",
            "下一步：选择 Painter / Designer 贴图目录后点击“扫描贴图目录”。",
            "如果不指定目录，导出时只会使用 Maya 场景里能识别到的贴图记录。",
        ]
    )


def format_empty_preflight_details():
    return "\n".join(
        [
            "尚未执行风险检查。",
            "下一步：先扫描资产，再点击“检查风险”。",
            "这里会列出阻断项、警告项和可点击的修复建议。",
        ]
    )


def format_issue_locator(scan, validation, texture_scan=None, preferred=""):
    scan = scan or {}
    validation = validation or {}
    texture_scan = texture_scan or {}
    warnings, errors = _checks_by_status(validation) if validation else ([], [])
    lines = [
        "定位：{0}".format(_locator_title(preferred, scan, validation, texture_scan)),
        "资产：{0}    贴图：{1} 张    阻断/警告：{2}/{3}".format(
            scan.get("asset_name", "未扫描") or "未扫描",
            texture_scan.get("matched_count", len(scan.get("textures", []) or [])),
            len(errors),
            len(warnings) + len(texture_scan.get("issues", []) or []),
        ),
        "",
    ]
    if errors:
        lines.append("阻断项：")
        for item in errors[:6]:
            lines.extend(_format_locator_check(item, "阻断"))
    elif warnings:
        lines.append("警告项：")
        for item in warnings[:6]:
            lines.extend(_format_locator_check(item, "警告"))
    elif texture_scan.get("issues"):
        lines.append("贴图问题：")
        for item in texture_scan.get("issues", [])[:6]:
            if isinstance(item, dict):
                lines.append("- {0}：{1}".format(item.get("id", "texture_issue"), item.get("message", "")))
                if item.get("next_action"):
                    lines.append("  下一步：{0}".format(item.get("next_action")))
            else:
                lines.append("- {0}".format(item))
    elif validation.get("can_export"):
        lines.append("结果：预检通过，可以导出 Package 给 UE Gate。")
        lines.append("下一步：导出后在 UE Gate 生成入审报告、预演导入计划，再正式导入。")
    elif scan:
        lines.append("结果：资产已扫描，尚未执行风险检查。")
        lines.append("下一步：点击“检查风险”。")
    else:
        lines.append("结果：尚未扫描资产。")
        lines.append("下一步：选择资产根节点后点击“扫描资产”。")
    return "\n".join(lines)


def _locator_title(preferred, scan, validation, texture_scan):
    if preferred == "asset":
        return "资产详情"
    if preferred == "texture":
        return "贴图详情"
    if preferred == "risk":
        return "风险检查详情"
    if preferred == "export":
        return "导出前状态"
    if validation:
        warnings, errors = _checks_by_status(validation)
        if errors or warnings:
            return "风险检查详情"
    if texture_scan:
        return "贴图详情"
    if scan:
        return "资产详情"
    return "等待扫描"


def _format_locator_check(item, severity_label):
    location = _check_location_hint(item)
    target = item.get("object") or item.get("asset") or item.get("node") or item.get("material") or item.get("id", "")
    lines = [
        "- [{0}] {1} | 对象：{2}".format(severity_label, item.get("id", "check"), target or "未指定"),
        "  位置：{0}".format(location),
        "  原因：{0}".format(_blocker_reason(item, {}) if severity_label == "阻断" else item.get("message", "")),
    ]
    next_action = item.get("next_action") or _next_action_for_check(item, {})
    if next_action:
        lines.append("  下一步：{0}".format(next_action))
    return lines


def _check_location_hint(item):
    check_id = item.get("id", "")
    label = item.get("label", "")
    if check_id in ("unmatched_material", "material_texture_binding"):
        return "材质贴图绑定 -> 贴图详情 / 检查详情"
    if check_id == "texture_set_selection":
        return "贴图集关键词 -> 贴图详情"
    if check_id == "name_prefix":
        return "资产概览 -> 资产详情"
    if label:
        return label
    return "检查详情"


def _overview_status_line(scan, validation):
    scan = scan or {}
    validation = validation or {}
    if validation.get("can_export"):
        return "通过 | 预检完成，可以导出 Package 给 UE Gate"
    warnings, errors = _checks_by_status(validation) if validation else ([], [])
    if errors:
        return "阻断 | 先处理风险项，再重新检查"
    if warnings:
        return "警告 | 复核警告项后再导出"
    if scan:
        return "已扫描 | 下一步执行风险检查"
    return "未扫描 | 选择资产根节点，然后扫描"


def _mcp_status_state(state):
    if state == "running":
        return "ok"
    if state == "error":
        return "error"
    if state == "success":
        return "info"
    return "muted"


def _overview_asset_line(scan):
    scan = scan or {}
    if not scan:
        return "未扫描"
    return "{0} / Mesh {1} / Tri {2}".format(
        scan.get("asset_name", "未命名"),
        scan.get("mesh_count", 0),
        _compact_int(scan.get("triangles", 0)),
    )


def _overview_texture_line(texture_scan, scan=None):
    texture_scan = texture_scan or {}
    scan = scan or {}
    if texture_scan:
        return "{0} 张 / 问题 {1}".format(texture_scan.get("matched_count", 0), len(texture_scan.get("issues", []) or []))
    scene_count = len(scan.get("textures", []) or [])
    return "场景 {0} 张".format(scene_count) if scene_count else "未扫描"


def _overview_risk_line(validation):
    validation = validation or {}
    if not validation:
        return "未预检"
    warnings, errors = _checks_by_status(validation)
    if errors:
        return "阻断 {0} / 警告 {1}".format(len(errors), len(warnings))
    if warnings:
        return "警告 {0}".format(len(warnings))
    return "通过" if validation.get("can_export") else "待确认"


def _overview_export_line(scan, validation, texture_scan=None):
    scan = scan or {}
    validation = validation or {}
    if not scan:
        return "等待扫描"
    if not validation:
        return "等待预检"
    return "可导出" if validation.get("can_export") else "已阻断"


def format_asset_card(scan):
    scan = scan or {}
    if not scan:
        return "资产 | 未扫描 · 选择后扫描"
    name = scan.get("asset_name", "") or "未命名"
    return "资产 | {0} · Mesh {1} · Tri {2}".format(
        name,
        scan.get("mesh_count", 0),
        _compact_int(scan.get("triangles", 0)),
    )


def format_texture_card(texture_scan, scan=None):
    texture_scan = texture_scan or {}
    scan = scan or {}
    if not texture_scan:
        count = len(scan.get("textures", []) or [])
        if count:
            return "贴图 | 场景 {0} 张 · 待确认".format(count)
        return "贴图 | 未扫描 · 选择目录"
    selected = ", ".join(texture_scan.get("selected_texture_set_short_names", [])) or "未选择"
    issues = len(texture_scan.get("issues", []) or [])
    prefix = "待确认" if issues else "就绪"
    return "贴图 | {0} · {1} 张 · 问题 {2}".format(prefix, texture_scan.get("matched_count", 0), issues)


def format_issue_card(validation):
    validation = validation or {}
    if not validation:
        return "风险 | 未预检 · 扫描后检查"
    warnings, errors = _checks_by_status(validation)
    if errors:
        prefix = "阻断"
    elif warnings:
        prefix = "警告"
    elif validation.get("can_export"):
        prefix = "通过"
    else:
        prefix = "待确认"
    return "风险 | {0} · 阻断 {1} · 警告 {2}".format(prefix, len(errors), len(warnings))


def format_export_card(scan, validation, texture_scan=None):
    scan = scan or {}
    validation = validation or {}
    texture_scan = texture_scan or {}
    if not scan:
        return "发布 | 等待扫描 · 资产和预检"
    if not validation:
        return "发布 | 待预检 · 先检查"
    if validation.get("can_export"):
        texture_count = texture_scan.get("matched_count", len(scan.get("textures", [])))
        return "发布 | 可导出 · 贴图 {0} 张".format(texture_count)
    return "发布 | 阻断 · 先处理风险项"


def format_scan_stage(scan):
    scan = scan or {}
    if not scan:
        return "01 扫描资产 · 待开始"
    return "01 扫描资产 · 已识别 {0}".format(scan.get("asset_name", "未命名"))


def format_check_stage(scan, validation):
    scan = scan or {}
    validation = validation or {}
    if not scan:
        return "02 检查风险 · 等待扫描"
    if not validation:
        return "02 检查风险 · 可执行"
    warnings, errors = _checks_by_status(validation)
    if errors:
        return "02 检查风险 · 阻断 {0} / 警告 {1}".format(len(errors), len(warnings))
    if warnings:
        return "02 检查风险 · 警告 {0} / 可复核".format(len(warnings))
    return "02 检查风险 · 通过"


def format_export_stage(scan, validation):
    scan = scan or {}
    validation = validation or {}
    if not scan:
        return "03 导出 Package · 等待扫描"
    if not validation:
        return "03 导出 Package · 等待预检"
    if validation.get("can_export"):
        return "03 导出 Package · 可导出"
    return "03 导出 Package · 阻断"


def _polish_status_text(text):
    text = (text or "").strip()
    if text.startswith("状态："):
        return "状态 | {0}".format(text[3:].strip())
    return text


def _polish_next_action_text(text):
    text = (text or "").strip()
    if text.startswith("下一步："):
        return "下一步 | {0}".format(text[4:].strip())
    return text


def _summary_state(text):
    text = text or ""
    if "错误" in text or "不可导出" in text or "阻断" in text:
        return "error"
    if "警告" in text or "待确认" in text:
        return "warning"
    if "可导出" in text or "完成" in text or "就绪" in text:
        return "ok"
    if "下一步" in text:
        return "info"
    return "muted"


def _asset_card_state(scan):
    return "ok" if scan else "waiting"


def _overview_panel_state(scan, validation, texture_scan=None):
    scan = scan or {}
    validation = validation or {}
    if validation.get("can_export"):
        return "ok"
    warnings, errors = _checks_by_status(validation) if validation else ([], [])
    if errors:
        return "error"
    if warnings:
        return "warning"
    if scan:
        return "info"
    return "panel"


def _texture_card_state(texture_scan, scan=None):
    texture_scan = texture_scan or {}
    scan = scan or {}
    if not texture_scan:
        return "warning" if scan.get("textures") else "waiting"
    if texture_scan.get("issues"):
        return "warning"
    if texture_scan.get("directory_status") in ("invalid", "missing", "error"):
        return "error"
    if texture_scan.get("rename_suggestions"):
        return "warning"
    return "ok"


def _issue_card_state(validation):
    validation = validation or {}
    if not validation:
        return "waiting"
    warnings, errors = _checks_by_status(validation)
    if errors or validation.get("status") == "error":
        return "error"
    if warnings or validation.get("status") == "warning":
        return "warning"
    return "ok" if validation.get("can_export") else "warning"


def _export_card_state(scan, validation, texture_scan=None):
    scan = scan or {}
    validation = validation or {}
    if not scan:
        return "waiting"
    if not validation:
        return "info"
    return "ok" if validation.get("can_export") else "error"


def format_asset_identity(scan):
    scan = scan or {}
    if not scan:
        return "\n".join(
            [
                "当前资产根节点：未扫描",
                "当前导出资产名：未扫描",
                "来源：未扫描",
                format_empty_selection_guidance(),
            ]
        )
    roots = scan.get("asset_roots", [])
    source_path = scan.get("asset_name_source_path", scan.get("asset_root", ""))
    lines = [
        "当前资产根节点：{0}".format(scan.get("asset_root", "") or "未识别"),
        "当前导出资产名：{0}".format(scan.get("asset_name", "")),
        "来源：{0}".format(_source_label(scan.get("asset_name_source", ""))),
        "资产名来源节点：{0}".format(source_path or "未识别"),
        "Mesh 数量：{0}".format(scan.get("mesh_count", 0)),
        "三角面：{0}".format(scan.get("triangles", 0)),
    ]
    if len(roots) > 1:
        lines.append("当前选择根节点：{0} 个，将作为一个资产包导出。".format(len(roots)))
        for root in roots[:4]:
            lines.append("- {0}".format(root))
        if len(roots) > 4:
            lines.append("- ... 另有 {0} 个".format(len(roots) - 4))
        if scan.get("asset_name_source") == "common_parent":
            lines.append("命名说明：多个选择共享同一父节点，资产名来自共同父节点。")
        elif scan.get("asset_name_source") == "first_selection":
            lines.append("命名说明：当前选择没有共同父节点，Asset Forge 只用第一个选择对象命名；下一步请选择共同父组，或在项目设置里填写资产名覆盖。")
    return "\n".join(lines)


def format_empty_selection_guidance():
    return EMPTY_SELECTION_GUIDANCE


def format_preflight_summary(scan, validation, texture_scan=None):
    scan = scan or {}
    validation = validation or {}
    texture_scan = texture_scan or {}
    can_export = bool(validation.get("can_export", False))
    errors = _blocking_checks(validation)
    warnings = [item for item in validation.get("checks", []) if item.get("status") == "warning"]
    lines = [
        "状态：{0}".format("可导出" if can_export else "不可导出"),
        "当前导出资产名：{0}".format(scan.get("asset_name", "")),
        "来源：{0}".format(_source_label(scan.get("asset_name_source", ""))),
        "Mesh 数量：{0}".format(scan.get("mesh_count", 0)),
        "三角面：{0}".format(scan.get("triangles", 0)),
        "贴图集选择：{0}".format(", ".join(texture_scan.get("selected_texture_set_short_names", [])) or "未选择"),
        "将导出贴图数：{0}".format(texture_scan.get("matched_count", len(scan.get("textures", [])))),
        "",
        "阻断项：",
    ]
    if not errors:
        lines.append("- 无")
    for item in errors:
        lines.append("- {0}：{1}".format(item.get("id", ""), _blocker_reason(item, scan)))
        lines.append("  下一步：{0}".format(item.get("next_action", _next_action_for_check(item, scan))))
        if item.get("id") == "name_prefix":
            expected_name = _expected_prefixed_name(scan.get("asset_name", ""), item)
            lines.append(
                "  当前导出资产名 {0} 来自{1}；它缺少 {2} 前缀，因此不能导出。".format(
                    scan.get("asset_name", ""),
                    _source_label(scan.get("asset_name_source", "")),
                    item.get("limit", "SM_").split()[0] if item.get("limit") else "SM_",
                )
            )
            lines.append("  下一步：点击“一键修复资产名前缀”或手动把导出资产名改成 {0}。".format(expected_name))
    lines.extend(["", "警告项："])
    if not warnings:
        lines.append("- 无")
    for item in warnings:
        lines.append("- {0}：{1}".format(item.get("id", ""), item.get("message", "")))
    lines.extend(["", "可自动修复项："])
    fixes = _auto_fix_items(errors, texture_scan)
    if not fixes:
        lines.append("- 无")
    else:
        for item in fixes:
            lines.append("- {0}".format(item))
    repair_actions = repair_actions_for_state(scan, validation, texture_scan)
    if repair_actions:
        lines.extend(["", "修复队列："])
        for action in repair_actions:
            lines.append("- {0}".format(_format_repair_action_line(action)))
            lines.append("  下一步：{0}".format(action.get("next_action", "")))
    return "\n".join(lines)


def format_blocking_validation_summary(validation, scan=None, debug_report_path=""):
    return "\n".join(
        [
            format_preflight_summary(scan or {}, validation or {}, (scan or {}).get("texture_folder_scan", {})),
            "",
            "调试报告：{0}".format(debug_report_path or "未写出"),
        ]
    )


def _format_asset_prefix_preview(scan, prefix):
    scan = scan or {}
    prefix = prefix or "SM_"
    asset_name = scan.get("asset_name", "")
    source_path = scan.get("asset_name_source_path") or scan.get("asset_root") or ""
    expected = asset_name if asset_name.startswith(prefix) else prefix + asset_name
    mesh_count = scan.get("mesh_count", 0)
    lines = [
        "Asset Forge 将修改当前 Maya 场景中的命名。",
        "",
        "当前资产名：{0}".format(asset_name or "未扫描"),
        "建议资产名：{0}".format(expected or prefix),
        "目标节点：{0}".format(source_path or "当前选择 / 共同父节点"),
        "Mesh 数量：{0}".format(mesh_count),
        "",
        "执行后会放入一个 Maya Undo Chunk，可用 Ctrl+Z 一次撤销。",
        "确认只在当前选中资产上执行。"
    ]
    return "\n".join(lines)


def format_next_action_summary(scan, validation, texture_scan=None):
    errors = _blocking_checks(validation or {})
    if errors:
        return "下一步：{0}".format(_next_action_for_check(errors[0], scan or {}))
    texture_action = _next_action_for_texture_scan(texture_scan or {})
    if texture_action and "未扫描" not in texture_action:
        return texture_action
    if (validation or {}).get("can_export"):
        return "下一步：确认导出根目录和 UE 目标路径后，点击“导出 Package 给 UE Gate”。"
    return "下一步：先点击“扫描”与“检查”，根据阻断项修复资产。"


def repair_actions_for_state(scan, validation, texture_scan=None):
    """Return a testable repair queue for the current Maya publish state."""
    scan = scan or {}
    validation = validation or {}
    texture_scan = texture_scan or {}
    actions = []
    for item in _blocking_checks(validation):
        check_id = item.get("id", "")
        if check_id == "name_prefix":
            actions.append(
                {
                    "id": "fix_asset_name_prefix",
                    "source_check": check_id,
                    "kind": "maya_ui_callback",
                    "label": "修复资产名前缀",
                    "problem": _blocker_reason(item, scan),
                    "button_label": "修复资产名前缀",
                    "target_label": "修复资产名前缀按钮",
                    "ui_callback": "_rename_prefix",
                    "expected_asset_name": _expected_prefixed_name(scan.get("asset_name", ""), item),
                    "next_action": _next_action_for_check(item, scan),
                    "next_step": _next_action_for_check(item, scan),
                    "can_run_from_ui_flow": True,
                }
            )
        elif check_id == "texture_set_selection":
            actions.append(
                {
                    "id": "select_texture_set",
                    "source_check": check_id,
                    "kind": "field_input",
                    "label": "选择贴图集标记",
                    "problem": _blocker_reason(item, scan),
                    "field_label": "贴图集关键词",
                    "target_label": "贴图集关键词输入框",
                    "field": "texture_set_token",
                    "example": "a1,d1",
                    "next_action": _next_action_for_check(item, scan),
                    "next_step": _next_action_for_check(item, scan),
                    "can_run_from_ui_flow": False,
                }
            )
        else:
            actions.append(
                {
                    "id": "fix_{0}".format(check_id or "blocking_check"),
                    "source_check": check_id,
                    "kind": "manual",
                    "label": item.get("label", check_id or "Blocking check"),
                    "problem": _blocker_reason(item, scan),
                    "next_action": item.get("next_action") or _next_action_for_check(item, scan),
                    "next_step": item.get("next_action") or _next_action_for_check(item, scan),
                    "can_run_from_ui_flow": False,
                }
            )
    if texture_scan.get("issues"):
        actions.append(
            {
                "id": "review_texture_set_issues",
                "source_check": "texture_folder_scan",
                "kind": "field_input",
                "label": "检查贴图集问题",
                "problem": _texture_scan_problem(texture_scan),
                "field_label": "贴图集关键词",
                "target_label": "贴图集关键词输入框",
                "field": "texture_set_token",
                "example": "a1,d1",
                "next_action": _next_action_for_texture_scan(texture_scan),
                "next_step": _next_action_for_texture_scan(texture_scan),
                "can_run_from_ui_flow": False,
            }
        )
    if texture_scan.get("rename_suggestions"):
        actions.append(
            {
                "id": "fix_texture_prefix",
                "source_check": "texture_prefix",
                "kind": "maya_ui_callback",
                "label": "修复贴图前缀",
                "problem": _texture_scan_problem(texture_scan) or "贴图命名缺少统一前缀",
                "button_label": "修复贴图前缀",
                "target_label": "修复贴图前缀按钮",
                "ui_callback": "_rename_texture_prefix",
                "planned_count": len(texture_scan.get("rename_suggestions", []) or []),
                "next_action": _next_action_for_texture_scan(texture_scan),
                "next_step": _next_action_for_texture_scan(texture_scan),
                "can_run_from_ui_flow": True,
            }
        )
    return actions


def _format_repair_action_line(action):
    target = _repair_action_target(action)
    problem = action.get("problem") or action.get("source_check", "")
    next_step = action.get("next_step") or action.get("next_action", "")
    report_path = action.get("report_path") or action.get("report_hint") or PREFLIGHT_REPAIR_REPORT_HINT
    return "{0}：问题={1}；入口={2}；下一步={3}；报告={4}".format(
        action.get("label", ""),
        problem,
        target,
        next_step,
        report_path,
    )


def _repair_action_target(action):
    if action.get("ui_callback"):
        return "点击“{0}”按钮".format(action.get("button_label", "按钮"))
    if action.get("field"):
        example = action.get("example", "")
        if example:
            return "在“{0}”中输入 {1}".format(action.get("field_label", "字段"), example)
        return "填写“{0}”".format(action.get("field_label", "字段"))
    return action.get("target_label") or action.get("kind", "")


def _texture_scan_problem(texture_scan):
    issues = list((texture_scan or {}).get("issues", []) or [])
    if issues:
        first_issue = issues[0]
        return first_issue.get("message") or first_issue.get("id") or "贴图集需要人工确认"
    if (texture_scan or {}).get("rename_suggestions"):
        return "贴图命名缺少统一前缀"
    return ""


def _next_action_for_texture_scan(scan):
    if not scan:
        return "下一步：如使用外部贴图目录，请先点击“扫描贴图目录”；否则继续预检。"
    if scan.get("issues"):
        return "下一步：检查贴图集问题；如存在多套贴图，请输入 a1,d1 这类关键词后重新扫描。"
    if scan.get("rename_suggestions"):
        return "下一步：如需要统一贴图命名，确认贴图集后再点击“一键添加贴图前缀”。"
    return "下一步：贴图集已匹配，继续预检或导出。"


def _checks_by_status(validation):
    checks = list((validation or {}).get("checks", []))
    warnings = [item for item in checks if item.get("status") == "warning"]
    errors = [item for item in checks if item.get("status") == "error"]
    return warnings, errors


def _blocking_checks(validation):
    return [item for item in validation.get("checks", []) if item.get("status") == "error"]


def _blocking_messages(validation):
    return [_blocker_reason(item, {}) for item in _blocking_checks(validation)]


def _blocker_reason(item, scan):
    if item.get("id") == "name_prefix":
        return "导出资产名缺少 SM_ 前缀"
    return item.get("message", "")


def _auto_fix_items(errors, texture_scan):
    fixes = []
    for item in errors:
        if item.get("id") == "name_prefix":
            fixes.append("点击“一键修复资产名前缀”，只处理当前资产根/共同父节点。")
        if item.get("id") == "texture_set_selection":
            fixes.append("在“贴图集关键词”中输入候选短名，例如 a1,d1。")
    if texture_scan.get("rename_suggestions"):
        fixes.append("点击“一键添加贴图前缀”前，先确认当前贴图集选择。")
    return fixes


def _next_action_for_check(item, scan=None):
    check_id = item.get("id", "")
    if check_id == "name_prefix":
        scan = scan or {}
        return "点击“一键修复资产名前缀”或手动把导出资产名改成 {0}。".format(_expected_prefixed_name(scan.get("asset_name", ""), item))
    if check_id == "mesh_exists":
        return "确认选择的是包含 Mesh 的模型或组。"
    if check_id == "uv0":
        return "为模型补齐基础 UV0。"
    if check_id == "frozen_transform":
        return "冻结 Transform 后重新扫描。"
    if check_id == "texture_set_selection":
        return "在“贴图集关键词”中选择正确候选贴图集后重新扫描。"
    return "修复该检查项后重新预检。"


def _source_label(source):
    labels = {
        "selected_root": "所选父组/共同父节点",
        "common_parent": "所选父组/共同父节点",
        "first_selection": "第一个选择对象",
    }
    return labels.get(source, source or "未知")


def _compact_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return value
    if abs(number) >= 1000:
        compact = "{0:.1f}k".format(number / 1000.0)
        return compact.replace(".0k", "k")
    return number


def _expected_prefixed_name(asset_name, item):
    prefix = item.get("limit", "SM_") or "SM_"
    prefix = prefix.split()[0]
    if asset_name and not asset_name.startswith(prefix):
        return prefix + asset_name
    return asset_name or prefix + "Asset"


def _format_project_settings(settings):
    return format_project_settings_summary(settings, max_rows=16)


def _format_texture_prefix_preview(result):
    lines = [
        "将添加贴图前缀：{0}".format(result.get("texture_prefix", "T_")),
        "计划重命名：{0}".format(result.get("planned_count", 0)),
        "将跳过：{0}".format(result.get("skipped_count", 0)),
        "",
    ]
    for action in result.get("actions", [])[:10]:
        lines.append(action.get("message", ""))
    return "\n".join(lines)


def read_log_tail(path, tail_lines=30):
    return [json.dumps(entry, ensure_ascii=False) + "\n" for entry in read_jsonl_tail(path, tail_lines)]


def _format_log_entry(data):
    if not isinstance(data, dict):
        return str(data)
    if data.get("raw"):
        return data.get("raw", "")
    details = []
    outputs = data.get("outputs") or {}
    if outputs.get("path"):
        details.append(outputs.get("path"))
    if outputs.get("matched_count") is not None:
        details.append("贴图匹配={0}".format(outputs.get("matched_count")))
    if outputs.get("asset_name"):
        details.append("资产={0}".format(outputs.get("asset_name")))
    if outputs.get("package_dir"):
        details.append("发布包={0}".format(outputs.get("package_dir")))
    if outputs.get("can_export") is not None:
        details.append("可导出={0}".format(_status_value_label(outputs.get("can_export"))))
    if outputs.get("can_import") is not None:
        details.append("UE Gate={0}".format(_status_value_label(outputs.get("can_import"))))
    if outputs.get("warning_count") is not None:
        details.append("警告={0}".format(outputs.get("warning_count")))
    if outputs.get("error_count") is not None:
        details.append("阻断={0}".format(outputs.get("error_count")))
    if outputs.get("repair_action_count") is not None:
        details.append("修复项={0}".format(outputs.get("repair_action_count")))
    elif outputs.get("repair_actions"):
        details.append("修复项={0}".format(len(outputs.get("repair_actions") or [])))
    if outputs.get("repair_actions"):
        first_action = (outputs.get("repair_actions") or [{}])[0]
        details.append("首个修复={0}".format(first_action.get("label") or first_action.get("id", "")))
        if first_action.get("problem"):
            details.append("问题={0}".format(first_action.get("problem")))
        details.append("修复入口={0}".format(_repair_action_target(first_action)))
        if first_action.get("next_step") or first_action.get("next_action"):
            details.append("修复下一步={0}".format(first_action.get("next_step") or first_action.get("next_action")))
    if outputs.get("next_step"):
        details.append("下一步={0}".format(outputs.get("next_step")))
    if outputs.get("portfolio_capture_hint"):
        details.append("录制提示={0}".format(outputs.get("portfolio_capture_hint")))
    report_path = data.get("report_path") or outputs.get("report_path")
    if not report_path and outputs.get("repair_actions"):
        first_action = ((outputs.get("repair_actions") or [{}])[0] or {})
        report_path = first_action.get("report_path") or first_action.get("report_hint") or PREFLIGHT_REPAIR_REPORT_HINT
    if report_path:
        details.append("报告={0}".format(report_path))
    if data.get("errors"):
        details.append("错误={0}".format(data.get("errors")[0]))
    suffix = " | " + " | ".join(details) if details else ""
    return "{0} | {1} | {2}{3}".format(data.get("timestamp", ""), _operation_label(data.get("operation", "")), _log_status_label(data.get("status", "")), suffix)


def _operation_label(operation):
    labels = {
        "startup": "打开工作台",
        "scan_model": "扫描资产",
        "preflight": "检查风险",
        "scan_texture_folder": "扫描贴图目录",
        "export_start": "开始导出",
        "export_success": "导出成功",
        "export_preflight_blocked": "导出前检查未通过",
        "export_failed": "导出失败",
        "fix_asset_name_prefix": "修复资产名前缀",
        "add_texture_prefix": "修复贴图前缀",
        "open_package_dir": "打开导出目录",
        "ai_analyze": "AI 分析",
        "load_project_settings": "加载项目设置",
        "save_project_settings": "保存项目设置",
        "apply_project_settings": "应用项目设置",
    }
    return labels.get(operation, operation or "未命名操作")


def _log_status_label(status):
    labels = {
        "success": "成功",
        "started": "开始",
        "error": "错误",
        "cancelled": "已取消",
        "preview": "预览",
    }
    return labels.get(status, status or "未知状态")


def _import_status_label(value):
    if value == "pending_ue_dry_run":
        return "待生成入审报告"
    return value


def _status_value_label(value):
    if isinstance(value, bool):
        return _bool_status(value)
    return _import_status_label(value)


def format_export_result_summary(result):
    outputs = _export_log_outputs(result)
    lines = [
        "导出完成 | Package 已生成，等待 UE Gate",
        "发布包：{0}".format(outputs.get("package_dir") or "未写出"),
        "包体名：{0} | 模式：{1}".format(outputs.get("package_name") or "未记录", outputs.get("package_version_mode") or "overwrite"),
        "清单：{0}".format(outputs.get("manifest_path") or "未写出"),
        "报告：{0}".format(outputs.get("report_path") or "未写出"),
        "状态：可导出={0} | UE Gate={1} | 警告/阻断={2}/{3}".format(
            _bool_status(outputs.get("can_export")),
            _import_status_label(outputs.get("can_import") or "pending_ue_dry_run"),
            outputs.get("warning_count", 0),
            outputs.get("error_count", 0),
        ),
        outputs.get("operator_action"),
        outputs.get("portfolio_capture_hint"),
        "下一步：{0}".format(outputs.get("next_step")),
    ]
    return "\n".join(lines)


def format_export_blocked_result(scan, validation, report_path=""):
    outputs = _blocked_export_log_outputs(scan, validation, report_path)
    lines = [
        "导出阻断 | Package 未生成",
        "发布包：未生成",
        "报告：{0}".format(outputs.get("report_path") or "未写出"),
        "状态：可导出={0} | UE Gate={1} | 警告/阻断={2}/{3}".format(
            _bool_status(outputs.get("can_export")),
            _bool_status(outputs.get("can_import")),
            outputs.get("warning_count", 0),
            outputs.get("error_count", 0),
        ),
        outputs.get("operator_action"),
        "第一阻断：{0}".format(outputs.get("first_blocker")),
        outputs.get("portfolio_capture_hint"),
        "下一步：{0}".format(outputs.get("next_step")),
    ]
    if outputs.get("repair_actions"):
        lines.append("修复队列：")
        for action in outputs.get("repair_actions", []):
            lines.append("- {0}".format(_format_repair_action_line(action)))
    return "\n".join(lines)


def _export_log_outputs(result):
    scan = result.get("scan", {}) if isinstance(result, dict) else {}
    validation = result.get("validation", {}) if isinstance(result, dict) else {}
    texture_scan = scan.get("texture_folder_scan", {}) if isinstance(scan, dict) else {}
    warnings, errors = _validation_issue_counts(validation)
    can_export = validation.get("can_export", False)
    return {
        "asset_name": scan.get("asset_name", ""),
        "mesh_count": scan.get("mesh_count", 0),
        "matched_count": texture_scan.get("matched_count", len(scan.get("textures", []))),
        "texture_set_token": texture_scan.get("texture_set_token", ""),
        "selected_texture_sets": texture_scan.get("selected_texture_sets", []),
        "texture_import_policy": result.get("manifest", {}).get("texture_import_policy", {}),
        "static_mesh_import_policy": result.get("manifest", {}).get("static_mesh_import_policy", {}),
        "status": validation.get("status", ""),
        "can_export": can_export,
        "can_import": _can_import_state(result, can_export),
        "warning_count": warnings,
        "error_count": errors,
        "manifest_path": result.get("manifest_path", ""),
        "package_dir": result.get("package_dir", ""),
        "package_name": ((result.get("manifest", {}) or {}).get("package_naming", {}) or {}).get("package_name", ""),
        "package_version_mode": ((result.get("manifest", {}) or {}).get("package_naming", {}) or {}).get("version_mode", ""),
        "package_naming": (result.get("manifest", {}) or {}).get("package_naming", {}),
        "report_path": result.get("export_report_path", ""),
        "operator_action": "UE Gate: 选择该 Package -> 生成入审报告 -> 预演导入计划 -> 正式导入",
        "next_step": "在 UE Gate 里选择该 Package，按清单生成入审报告、预演导入计划、正式导入",
        "portfolio_capture_hint": result.get("portfolio_capture_hint")
        or _portfolio_capture_hint(True, scan, validation, result.get("export_report_path", "")),
    }


def _blocked_export_log_outputs(scan, validation, report_path=""):
    warnings, errors = _validation_issue_counts(validation)
    first_blocker = (_blocking_messages(validation or {}) or ["处理 Preflight 阻断项后重新导出"])[0]
    repair_actions = repair_actions_for_state(scan or {}, validation or {}, (scan or {}).get("texture_folder_scan", {}))
    repair_actions = _repair_actions_with_report_path(repair_actions, report_path)
    return {
        "asset_name": (scan or {}).get("asset_name", ""),
        "can_export": False,
        "can_import": False,
        "warning_count": warnings,
        "error_count": errors,
        "repair_action_count": len(repair_actions),
        "repair_actions": repair_actions,
        "report_path": report_path,
        "debug_report_path": report_path,
        "first_blocker": first_blocker,
        "operator_action": "修复：先处理第一阻断项 -> 重新检查 -> 再导出",
        "next_step": "先修复第一阻断项：{0}；然后重新检查并重试导出".format(first_blocker),
        "portfolio_capture_hint": _portfolio_capture_hint(False, scan or {}, validation or {}, report_path, repair_actions),
    }


def _repair_actions_with_report_path(repair_actions, report_path):
    result = []
    normalized_report_path = (report_path or "").replace("\\", "/")
    for action in repair_actions or []:
        item = dict(action)
        if normalized_report_path:
            item["report_path"] = normalized_report_path
        else:
            item["report_hint"] = PREFLIGHT_REPAIR_REPORT_HINT
        result.append(item)
    return result


def _portfolio_capture_hint(can_export, scan, validation, report_path="", repair_actions=None):
    asset_name = (scan or {}).get("asset_name", "Asset")
    normalized_report_path = (report_path or "").replace("\\", "/")
    if can_export:
        return "录制前看这里：资产 {0} 已可导出；打开导出报告 {1}；下一步在 UE Gate 选择该 Package，生成入审报告、预演导入计划、正式导入。".format(
            asset_name,
            normalized_report_path or "待生成报告",
        )
    first_action = ((repair_actions or [{}])[0] or {}).get("label") or (_blocking_messages(validation or {}) or ["fix blocker"])[0]
    return "录制前看这里：资产 {0} 还不能导出；先展示第一个修复项“{1}”；打开阻断报告 {2}；下一步点对应入口后重新检查。".format(
        asset_name,
        first_action,
        normalized_report_path or "阻断调试报告",
    )


def _validation_issue_counts(validation):
    validation = validation or {}
    summary = validation.get("summary", {}) if isinstance(validation, dict) else {}
    warnings = summary.get("warnings", None)
    errors = summary.get("errors", None)
    checks = validation.get("checks", []) if isinstance(validation, dict) else []
    if not isinstance(warnings, int):
        warnings = len([item for item in checks if item.get("status") == "warning"])
    if not isinstance(errors, int):
        errors = len([item for item in checks if item.get("status") == "error"])
    return warnings, errors


def _can_import_state(result, can_export):
    explicit = result.get("can_import")
    if explicit is not None:
        return bool(explicit)
    summary = result.get("summary") or {}
    if isinstance(summary, dict) and summary.get("can_import") is not None:
        return bool(summary.get("can_import"))
    return "pending_ue_dry_run" if can_export else False


def _bool_status(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value or "")


def _copy_rules(rules):
    result = {}
    for key, value in (rules or {}).items():
        if isinstance(value, dict):
            result[key] = _copy_rules(value)
        elif isinstance(value, list):
            result[key] = [dict(item) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value
    return result
