# -*- coding: utf-8 -*-
"""Maya cmds 发布工作台：Static Prop MVP 的轻量可验收入口。"""

from __future__ import absolute_import, unicode_literals

import base64
import errno
import io
import json
import os
import sys
from collections import Counter
from datetime import datetime
from hashlib import sha256

from asset_forge.maya import material_binding_dialog, workbench_feedback, workbench_frame, workbench_locator, web_workbench
from asset_forge.maya.workbench_skin import WorkbenchSkin, maya_pixel_scale
from asset_forge.maya.cmds_bridge import get_cmds, get_mel
from asset_forge.maya.workbench_diagnostics import TEXTURE_USAGE_LABELS, describe
from asset_forge.maya.material_scanner import valid_texture_count
from asset_forge.maya.operation_logger import MayaOperationLogger, latest_log_path, read_latest_log_tail
from asset_forge.maya.package_opener import open_directory
from asset_forge.maya.pipeline import ExportValidationError, MayaStaticPropPipeline
from asset_forge.maya.project_settings import SETTING_VALUE_LABELS, format_project_settings_summary
from asset_forge.maya.project_settings import (
    NORMAL_FORMAT_LABELS, apply_rule_settings, load_project_settings, normalize_normal_format,
    normalize_project_settings, save_project_settings,
)
from asset_forge.shared.constants import ASSET_TYPE_STATIC_PROP
from asset_forge.shared.constants import TARGET_PLATFORM_HIGH_END_MOBILE, TARGET_PLATFORM_MOBILE, TARGET_PLATFORM_PC
from asset_forge.shared.material_profile_schema import get_project_material_profiles
from asset_forge.shared.python_compat import to_text
from asset_forge.shared.unreal_path import sanitize_unreal_package_path


WORKSPACE_NAME = "assetForgePublishWorkspace"
_LEGACY_WORKSPACE_SCRIPT = "from asset_forge.maya import ui; ui.restore_workspace()"
_WORKSPACE_INSTANCE = None
WINDOW_NAME = "assetForgePhase1Window"
BUILD_LABEL = "DCC AssetForge v0.2 - Maya 发布工作台"
FIELD_HINTS = {
    "模型前缀": "按团队规范调整模型名称的开头。",
    "贴图前缀": "设置导出贴图名的开头，适用于场景和外部贴图。",
    "三角面预算": "设置当前平台的单资产三角面上限。",
    "材质槽预算": "设置当前平台的单资产材质槽上限。",
    "目标平台": "切换后调入此平台的检查预算。",
    "材质匹配规则": "决定哪些贴图必需，以及如何匹配贴图。",
    "源法线坐标格式": "根据源贴图选择格式，保证凹凸方向正确。",
    "UE 目标路径": "设置资产在 UE 内容浏览器里的目录，例如 /Game/Props。",
    "导出根目录": "打包通过后，将文件写入这个文件夹。",
    "贴图目录": "指定外部贴图目录。留空时使用场景节点连接的贴图。",
    "贴图名筛选词（可选）": "同一目录混放多套资产时，输入可区分贴图集的名称片段。",
    "包体/文件夹名": "只修改导出包体名。留空时自动取当前资产名。",
    "包体迭代模式": "决定是否覆盖同名包体，或生成新版本。",
    "Nanite 策略建议": "设置建议 UE 使用的 Nanite 策略。",
    "Mesh LODGroup 建议": "可填写团队定义的网格 LOD 组名。",
    "Mesh LOD 导入策略建议": "设置 UE 如何处理 FBX 中的已有 LOD。",
    "Virtual Texture 策略建议": "按材质管线要求选择虚拟纹理策略。",
    "Texture Streaming 策略建议": "按项目规定选择贴图流送策略。",
    "Texture Group 建议": "可填写团队定义的纹理分组名。",
}
ACTION_HINTS = {
    "加载预设": "读取磁盘上团队共享的项目规范。",
    "保存预设": "将当前规则、预算和发布目标存为可共享的 JSON。",
    "应用当前预设": "整理当前字段并应用到工作台。",
    "手动绑定材质槽贴图": "手动选择每个材质槽对应的外部贴图集。",
    "跟随场景贴图": "取消外部目录覆盖并使用 Maya 场景连接。",
    "扫描贴图目录": "贴图文件有变化时，重新读取磁盘。",
    "修复贴图前缀": "先预览，再确认要重命名的贴图。",
    "修复资产名前缀": "先预览，再确认要重命名的模型。",
    "应用 Transform": "查看对象后确认冻结变换。",
}
INITIAL_NEXT_ACTION = "下一步 | 选中资产根节点 -> 扫描资产"
EMPTY_SELECTION_GUIDANCE = (
    "没有选中资产。\n"
    "下一步：在 Maya 里选择一个资产根节点或共同父组后重试；"
    "如果场景唯一可导出资产，DCC AssetForge 会在扫描时自动兜底；"
    "如果有多个候选资产，它不会猜测。"
)
TEXTURE_FILTER_LABEL = "贴图名筛选词（可选）"
TEXTURE_FILTER_HINT = "留空则自动匹配；目录混放多套资产时填名称片段"
PRESET_GUIDANCE = (
    "修改本页规范、预算与发布目标后，点「保存预设」可导出为标准 UTF-8 JSON（*.assetforge.json），"
    "支持用 VS Code / 记事本直接编辑并与团队共享。"
)
FOLLOW_PROJECT_DEFAULT = SETTING_VALUE_LABELS["project_default"]

PREFLIGHT_REPAIR_REPORT_HINT = "检查阶段不写报告；导出被阻断时会写调试报告。"
STATUS_ACCENTS = {"ok": "#22C55E", "warning": "#F59E0B", "error": "#EF4444", "info": "#38BDF8"}


def _directory_key(path):
    return os.path.normcase(os.path.abspath(path)) if path else ""


def asset_forge_repo_root():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
    return repo_root


def _workspace_restore_script(repo_root):
    # Maya serializes this Python callback inside a MEL string. Keep checkout paths
    # (including quotes, non-ASCII and backslashes) out of both language literals.
    launcher = os.path.join(repo_root, "scripts", "maya_launch_asset_forge.py")
    path_data = base64.b64encode(launcher.encode("utf-8")).decode("ascii")
    return ("__import__('runpy').run_path(__import__('base64').b64decode('{0}').decode('utf-8'))"
            "['restore_saved_workspace']()").format(path_data)


def asset_forge_icon_path():
    path = os.path.join(asset_forge_repo_root(), "Plugins", "AssetForge", "Resources", "Workbench", "brand", "af_shelf.png")
    return path.replace("\\", "/") if os.path.isfile(path) else ""


class AssetForgeMayaWindow(object):
    """Maya 端发布工作台。保持 cmds 兼容，把发布决策放在主屏。"""

    def __init__(self, cmds_module=None, pipeline=None, logger=None, log_root=None):
        self.cmds = cmds_module or get_cmds()
        self.pipeline = pipeline or MayaStaticPropPipeline()
        self.last_scan = None
        self.last_validation = None
        self.locator_selection = []
        self.locating = False
        self.active_issue = None
        self.issue_rows = []
        self.issue_buttons = []
        self.issue_details = []
        self.last_texture_scan = {}
        self.scene_texture_preview = ((), 0, ())
        self.texture_preview = None
        self.last_package_dir = ""
        self.export_receipt = {}
        self.review_gate = None
        self.last_selection = []
        self.pinned_roots = []
        self.pinned_ids = []
        self.selection_note = {}
        self.material_texture_set_overrides = {}
        self.material_binding_context = None
        self.checked_inputs = None
        self.project_settings_path = ""
        self.folder_notice = ""
        self.option_labels = {}
        self.settings_before_scene_preset = None
        self.controls = {}
        self.cards = {}
        self.disclosures = {}
        self.settings_sections = {}
        self.requested_visibility = {}
        self.skin = None
        self.web = None
        self.chrome = None
        self.workspace_name = WORKSPACE_NAME
        self.floating_geometry = None
        self.issue_revision = 0
        self.check_notice = {}
        self.action_button = {}
        self.action_serial = 0
        self.feedback_closed = False
        self.workspace_populated = False
        self.toast = None
        self.toast_enabled = True
        self.review_status = ("idle", "待检查")
        self.review_message = "待检查"
        self.recent_logs = []
        self._launcher_module = None
        self.logger = logger or MayaOperationLogger(root=log_root)
        self.latest_log_path = latest_log_path(self.logger.root)

    def show(self):
        if self.cmds is None:
            raise RuntimeError("maya.cmds is not available")
        if hasattr(self.cmds, "workspaceControl"):
            global _WORKSPACE_INSTANCE
            workspace = self.cmds.workspaceControl
            restore_script = _workspace_restore_script(asset_forge_repo_root())
            close_script = "from asset_forge.maya import ui; ui.close_workspace()"
            migration = None
            if workspace(WORKSPACE_NAME, exists=True):
                migration = _saved_workspace_migration(self.cmds)
                # Edit the native saved control in place. Deleting a restored shell and
                # recreating its name can leave Maya's saved definition on the old callback.
                workspace(WORKSPACE_NAME, edit=True, uiScript=restore_script, closeCommand=close_script)
                if _WORKSPACE_INSTANCE is not None or not _workspace_has_content(self.cmds):
                    if _WORKSPACE_INSTANCE is None:
                        _WORKSPACE_INSTANCE = self
                    workspace(WORKSPACE_NAME, edit=True, restore=True)
                    _schedule_workspace_restore(_WORKSPACE_INSTANCE, migration)
                    return WORKSPACE_NAME
                # Replacing a live panel from another loaded module also releases its script jobs.
                self.cmds.deleteUI(WORKSPACE_NAME)
            if self.cmds.window(WINDOW_NAME, exists=True):
                self.cmds.deleteUI(WINDOW_NAME)
            _WORKSPACE_INSTANCE = self
            workspace(WORKSPACE_NAME, label="资产工作台", initialWidth=370,
                      initialHeight=620, floating=True, actLikeMayaUIElement=True,
                      minimumWidth=265, retain=False, loadImmediately=True,
                      closeCommand=close_script, uiScript=restore_script)
            # Maya may reuse a saved callback when a control is recreated under the same name.
            workspace(WORKSPACE_NAME, edit=True, uiScript=restore_script, closeCommand=close_script)
            if not workspace(WORKSPACE_NAME, query=True, floating=True):
                workspace(WORKSPACE_NAME, edit=True, floating=True)
            if migration:
                _schedule_workspace_restore(self, migration)
            return WORKSPACE_NAME
        if self.cmds.window(WINDOW_NAME, exists=True):
            self.cmds.deleteUI(WINDOW_NAME)
        self.cmds.window(WINDOW_NAME, title=BUILD_LABEL, widthHeight=(340, 610), sizeable=True)
        self._populate(WINDOW_NAME)
        self.cmds.showWindow(WINDOW_NAME)
        return WINDOW_NAME

    def _populate(self, parent):
        self.cmds.setParent(parent)
        if hasattr(self.cmds, "workspaceControl"):
            directory = os.path.join(asset_forge_repo_root(), "Plugins", "AssetForge", "Resources", "Workbench")
            self.skin = WorkbenchSkin(directory, maya_pixel_scale(self.cmds))
            self.skin.apply_typeface(parent)
            self.skin.apply_tooltips(parent)
        area = self.cmds.formLayout() if self.skin else None
        if area:
            self.chrome = workbench_frame.create(self)
            detail = self.cmds.formLayout(height=35, manage=False)
            self.controls["detail_header"] = detail
            back = self.cmds.button(label="←", annotation="返回工作台", height=27, width=29,
                                    command=lambda *_: self.web.main())
            title = self.cmds.text(label="发布设置", align="left", height=28)
            close = self.cmds.button(label="×", annotation="关闭工作台", height=27, width=28, command=self._close)
            self.controls.update(detail_back=back, detail_title=title, detail_close=close)
            self.cmds.formLayout(detail, edit=True, attachForm=[(back, "left", 7), (back, "top", 4),
                                 (close, "right", 7), (close, "top", 4), (title, "top", 3)],
                                 attachControl=[(title, "left", 4, back), (title, "right", 4, close)])
            self.skin.box(detail, "header")
            self.skin.button(back, None, "navigation").setAccessibleName("返回工作台")
            self.skin.button(close, None, "navigation").setAccessibleName("关闭工作台")
            self.skin.text(title, "text", 13, 600)
            self.chrome.bind_drag(title)
            self.cmds.setParent(area)
            self.controls["workbench_area"] = area
        self.controls["main_scroll"] = self.cmds.scrollLayout(childResizable=True, minChildWidth=1,
                                                               verticalScrollBarThickness=12)
        if area:
            self.cmds.formLayout(area, edit=True, attachForm=[
                (detail, side, 0) for side in ("left", "right", "top")] + [
                (self.controls["main_scroll"], side, 0) for side in ("left", "right", "top", "bottom")])
        canvas = self.cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAttach=("both", 5))
        if self.skin:
            self.skin.box(self.controls["main_scroll"], "canvas")
            self.skin.box(canvas, "canvas")
        self._build_header()
        self._card("inspect", "资产检查", True)
        self.controls["current_asset"] = self.cmds.text(label="选择要检查的资产", height=24, align="left", font="boldLabelFont")
        if self.skin:
            self.skin.text(self.controls["current_asset"], "text", 13, 600)
        self.controls["select_review_asset"] = self.cmds.button(label="选中对象", command=self._select_review_asset, manage=False)
        self.controls["switch_review_asset_note"] = self.cmds.text(label="", align="left", wordWrap=True, manage=False)
        self.controls["switch_review_asset"] = self.cmds.button(label="切换并检查", command=self._switch_and_check, manage=False)
        self._action_button("规则与前缀设置", self._open_rules, "preset", "设置当前模型前缀、目标平台、材质规则和预算")
        self.controls["check_asset"] = self._action_button("检查资产", self._validate, "inspect", "按当前项目预设检查所选资产", 32)
        self.controls["check_notice"] = self.cmds.text(label="", align="left", wordWrap=True, manage=False)
        self.controls["issue_caption"] = self._rule_line("issue_caption", "检查结果", False)
        self.controls["review_rows"] = self.cmds.columnLayout(adjustableColumn=True, rowSpacing=4, manage=False)
        self.cmds.setParent("..")
        self.controls["passed_header"] = self.cmds.button(label="", command=self._toggle_passes, manage=False)
        self.controls["passed_list"] = self.cmds.text(label="", align="left", wordWrap=True, manage=False)
        self._end_card()

        self._card("publish", "发布与导出", True)
        self.controls["export_action"] = self._action_button("检查并导出 Package", self._export, "publish-on-accent",
                                                           "重新检查整个资产，并导出通过的 Package", 32, "publish")
        self._section("发布设置", collapse=True, key="action_section")
        self._build_rule_settings()
        self._build_publish_setup()
        self._build_texture_panel()
        self._build_asset_panel()
        self._build_project_preset_panel()
        self._build_advanced_settings()
        self._end_section()
        if self.skin:
            receipt = self.cmds.columnLayout(adjustableColumn=True, rowSpacing=2, manage=False)
            self.controls["export_receipt_bar"] = receipt
            hint = self.cmds.text(label="", align="left", wordWrap=True)
            self.controls["export_receipt_hint"] = hint
            self.skin.text(hint, "secondary", 11)
            self._action_button("打开目录", self._open_last_package, "folder",
                                "打开本次导出的 Package", 26)
            self.cmds.setParent("..")
        self._end_card()

        self._card("log", "技术日志", False)
        self._build_mcp_header_controls()
        self._build_preflight_panel()
        self._build_log_panel()
        self._end_card()
        if self.skin:
            self.skin.fill_dock(parent, self.controls["main_scroll"], canvas)
            index = os.path.join(directory, "web", "index.html")
            self.web = web_workbench.create(self, area, index)
            if self.web:
                lifetime = self.web
                self.web.start()
            else:
                lifetime = self.skin.widget(self.controls["check_asset"], self.skin.widgets.QPushButton)
            # Bootstrap can reload this module before Maya deletes the previous workspace.
            lifetime.destroyed.connect(self.chrome.close)
            lifetime.destroyed.connect(self._end_feedback)
            self.chrome.schedule()
        if hasattr(self.cmds, "file"):
            self._restore_scene_preset()
        self._log_operation("startup", "success", outputs={"window": parent})
        self._refresh_last_maya_log()
        if hasattr(self.cmds, "scriptJob"):
            if self.chrome:
                self.cmds.scriptJob(event=["quitApplication", self.chrome.shutdown], parent=parent)
            self.cmds.scriptJob(event=["SelectionChanged", self._selection_label], parent=parent)
            self.cmds.scriptJob(event=["SceneOpened", self._scene_opened], parent=parent)
            self.cmds.scriptJob(event=["NewSceneOpened", self._scene_opened], parent=parent)
            self._selection_label()
        self.workspace_populated = True

    def _switch_docking(self, *args):
        floating = self.cmds.workspaceControl(WORKSPACE_NAME, query=True, floating=True)
        if floating:
            dock = self.chrome.current_dock()
            top = dock.window() if dock is not None else None
            if self.chrome.exclusive_window(top):
                self.floating_geometry = top.saveGeometry()
            if self.chrome:
                self.chrome.release()
            # Maya chooses its native tab/grip while moving the control into its new tab group.
            workspace = self.cmds.workspaceControl
            workspace(WORKSPACE_NAME, edit=True, actLikeMayaUIElement=False)
            side = next((name for name in ("ChannelBoxLayerEditor", "AttributeEditor")
                         if workspace(name, exists=True) and workspace(name, query=True, visible=True)
                         and not workspace(name, query=True, floating=True)
                         and not workspace(name, query=True, collapse=True)), None)
            if side:
                workspace(WORKSPACE_NAME, edit=True, tabToControl=(side, -1))
                workspace(WORKSPACE_NAME, edit=True, r=True)
            else:
                workspace(WORKSPACE_NAME, edit=True, dockToMainWindow=("right", False))
        else:
            self.chrome.restore_dock_tab()
            self.cmds.workspaceControl(WORKSPACE_NAME, edit=True, floating=True)
            # Maya creates a new native frame when a tool is floated again.
            self.cmds.evalDeferred(self._restore_float_geometry)
        if self.chrome:
            self.chrome.schedule()
        self._web_changed()

    def _restore_float_geometry(self):
        if self.feedback_closed or _WORKSPACE_INSTANCE is not self:
            return
        if self.cmds.workspaceControl(WORKSPACE_NAME, exists=True) and self.cmds.workspaceControl(
                WORKSPACE_NAME, query=True, floating=True):
            dock = self.chrome.current_dock()
            top = dock.window() if dock is not None else None
            if self.floating_geometry is not None and self.chrome.exclusive_window(top):
                top.restoreGeometry(self.floating_geometry)
            if self.chrome:
                self.chrome.refresh()

    def _close(self, *args):
        self.action_serial += 1
        # Let WebChannel return before the native command destroys its sender.
        self.cmds.evalDeferred(lambda: self.cmds.workspaceControl(WORKSPACE_NAME, edit=True, close=True)
                               if _WORKSPACE_INSTANCE is self and not self.feedback_closed else None)

    def _end_feedback(self, *args):
        # A shelf reload creates a new module namespace before deleting the previous workspace.
        self.feedback_closed = True
        self.action_serial += 1
        self._dismiss_toast()

    def _dismiss_toast(self, *args):
        if self.toast is not None:
            self.toast.hide()
            self.toast.deleteLater()
            self.toast = None

    def _set_toast_enabled(self, enabled):
        self.toast_enabled = bool(enabled)
        self.cmds.optionVar(intValue=("assetForgeWorkbenchGuidanceToast", int(self.toast_enabled)))
        if not self.toast_enabled:
            self._dismiss_toast()

    def _notify_viewport(self, message):
        if not self.toast_enabled or not self.skin:
            return
        self._dismiss_toast()
        try:
            toast = workbench_feedback.viewport_toast(self, message)
        except (ImportError, RuntimeError):
            # Viewports can be destroyed while Maya switches layouts. The card keeps the result.
            return
        if toast is not None:
            self.toast = toast
            def forget(*args):
                if self.toast is toast:
                    self.toast = None
            toast.destroyed.connect(forget)

    def _check_notice(self, result=None):
        self.check_notice = result or {}
        control = self.controls.get("check_notice")
        if control:
            self.cmds.text(control, edit=True, manage=bool(result), label=result["text"] if result else "")
            if result and self.skin:
                ink = STATUS_ACCENTS[result["tone"]]
                widget = self.skin.widget(control, self.skin.widgets.QLabel)
                self.skin._style(widget, "QLabel {color:#F2F2F2;border-left:2px solid %s;padding:3px 6px;"
                                         "background:transparent;font-size:12px;}" % ink)
                widget.adjustSize()
        self._web_changed()

    def _action_buttons(self, key="", label="", busy=False):
        self.action_button = {"action": key, "label": label, "busy": busy} if key else {}
        for action, control, normal in (("inspect", "check_asset", "检查资产"), ("publish", "export_action", "检查并导出 Package"),
                                        ("rescan", "recheck_mesh", "复检当前网格")):
            if self.controls.get(control) and hasattr(self.cmds, "ls"):
                self.cmds.button(self.controls[control], edit=True, label=label if action == key else normal,
                                 enable=not busy and bool(self._review_selection()))
        self._web_changed()

    def _run_action(self, action, callback):
        if self.feedback_closed or self.action_button.get("busy"):
            return
        self.action_serial += 1
        serial = self.action_serial
        original_selection = list(self._review_selection() or []) if action == "publish" and not self.pinned_roots else None
        self._dismiss_toast()
        self._action_buttons(action, {"publish": "导出中…", "rescan": "复检中…"}.get(action, "检查中…"), True)

        def current():
            return not self.feedback_closed and serial == self.action_serial and (not self.skin or _WORKSPACE_INSTANCE is self)

        def execute():
            if not current():
                return
            try:
                if original_selection is None or list(self._review_selection() or []) == original_selection:
                    callback()
            finally:
                if current():
                    self._action_buttons()

        # Let both Maya and Chromium paint the action before running the synchronous host operation.
        if self.skin:
            self.skin.core.QTimer.singleShot(140, execute)
        else:
            execute()

    def _web_changed(self):
        if self.web:
            self.web.sync()

    def _tool_state(self):
        folder = self._texture_folder()
        scan = self._visible_texture_scan()
        texture_summary = _overview_texture_line(scan) if folder else _overview_texture_line({}, self.last_scan)
        scene_texture_count = 0 if folder else self._scene_texture_count()
        current = self.last_scan or {}
        inference_checked = (not folder and self.last_validation is not None
                             and "scene_inferred_texture_count" in current)
        texture_directory_label = folder or "自动（跟随场景贴图）"
        return {"platform": self._target_platform(), "materialProfile": self._material_profile(),
                # Show the editable value even while a user is correcting its syntax.
                "targetPath": self.cmds.textFieldGrp(self.controls["target_path"], query=True, text=True),
                "outputFolder": self._output_dir(), "lastPackage": self.last_package_dir,
                "exportedPackage": self.export_receipt.get("path", ""),
                "exportedDisplayPath": self.export_receipt.get("display", ""),
                "presetPath": self.project_settings_path, "presetName": os.path.basename(self.project_settings_path),
                "presetRules": self._preset_rules_summary(),
                "folderActions": {key: self._folder_state(key) for key in ("output", "textures", "preset")},
                "folderNotice": self.folder_notice,
                "textureFolder": folder, "textureSummary": texture_summary,
                "textureDirectoryLabel": texture_directory_label, "sceneTextureCount": scene_texture_count,
                "sceneInferredTextureCount": current["scene_inferred_texture_count"] if inference_checked else None,
                "logLines": self.recent_logs}

    def _native_window_mode(self, floating):
        cmds = self.cmds
        for name in ("banner_title", "banner_close"):
            cmds.control(self.controls[name], edit=True, manage=floating)
        cmds.button(self.controls["banner_dock"], edit=True, label="停靠工作台" if floating else "悬浮工作台")
        cmds.formLayout(self.controls["banner"], edit=True, height=52 if floating else 34,
                        attachForm=[(self.controls["summary"], "top", 28 if floating else 8)])
        self._web_changed()

    def _detail_controls(self, detail):
        cmds = self.cmds
        header, scroll = self.controls["detail_header"], self.controls["main_scroll"]
        cmds.layout(header, edit=True, manage=bool(detail))
        area = self.controls["workbench_area"]
        if detail:
            cmds.formLayout(area, edit=True, attachControl=[(scroll, "top", 0, header)])
            cmds.text(self.controls["detail_title"], edit=True, label={"settings": "发布设置", "rules": "规则与前缀设置", "textures": "贴图设置", "log": "技术日志"}[detail])
        else:
            cmds.formLayout(area, edit=True, attachForm=[(scroll, "top", 0)])
        cmds.layout(self.controls["banner"], edit=True, manage=not detail)
        for key, card in self.cards.items():
            visible = not detail or key == ("log" if detail == "log" else "publish")
            cmds.layout(card["shell"], edit=True, manage=visible)
            cmds.control(card["head"], edit=True, manage=not detail)
        cmds.control(self.controls["export_action"], edit=True, manage=not detail)
        cmds.control(self.settings_sections["action_section"]["head"], edit=True, manage=not detail)
        if detail in ("settings", "rules", "textures"):
            self._open_publish_settings()
            if detail == "rules":
                self._expand_sections("check_rules_section")
            elif detail == "textures":
                self._expand_sections("texture_section")
        elif detail == "log":
            self._toggle_card("log", True)
        scroll = self.skin.widget(self.controls["main_scroll"])
        area = scroll.findChild(self.skin.widgets.QScrollArea)
        if area is not None:
            area.verticalScrollBar().setValue(0)
            section = {"rules": "check_rules_section", "textures": "texture_section"}.get(detail)
            if section:
                target = self.skin.widget(self.settings_sections[section]["head"])
                self.skin.core.QTimer.singleShot(0, lambda: area.ensureWidgetVisible(target, 0, 0))

    def _build_header(self):
        if not hasattr(self.cmds, "formLayout"):
            self.cmds.text(label="AssetForge v0.2")
            self.controls["summary"] = self.cmds.text(label="待检查")
            return
        banner = self.cmds.formLayout(height=52)
        self.controls["banner"] = banner
        title = self.cmds.text(label="AssetForge v0.2", align="left", height=21)
        status = self.cmds.text(label="待检查", height=17)
        self.controls["summary"] = status
        dock = self.cmds.button(label="浮动 / 停靠", height=24, width=76, command=self._switch_docking)
        close = self.cmds.button(label="×", height=24, width=25, annotation="关闭工作台", command=self._close)
        self.controls.update(banner_title=title, banner_close=close, banner_dock=dock)
        self.cmds.formLayout(banner, edit=True, attachForm=[
            (title, "top", 3), (title, "left", 6), (status, "left", 6), (status, "top", 28),
            (dock, "top", 9), (close, "right", 5), (close, "top", 9)],
            attachControl=[(title, "right", 4, dock), (dock, "right", 4, close)])
        if self.skin:
            self.skin.box(banner, "header")
            self.skin.button(dock, None)
            self.skin.button(close, None)
            self.chrome.bind_drag(title)
            self.skin.brand(title)
            self.skin.pill(status, "待检查", "muted")
        self.cmds.setParent("..")

    def _action_button(self, label, command, icon, hint, height=28, role="action"):
        kwargs = {"label": label, "command": command, "annotation": hint, "height": height}
        if role == "tool":
            kwargs["width"] = 25
        button = self.cmds.button(**kwargs)
        if self.skin:
            self.skin.button(button, icon, role)
        return button

    def _card(self, key, title, expanded):
        shell = self.cmds.columnLayout(adjustableColumn=True, rowSpacing=0, columnAttach=("both", 1))
        if self.skin:
            self.skin.box(shell, "card")
        head = self.cmds.button(label=title, height=33, annotation=title, command=lambda *_: self._toggle_card(key))
        arrow = self.skin.card_title(head, title, key, expanded) if self.skin else None
        pad = self.skin.theme["cardPadding"] if self.skin else 10
        body = self.cmds.columnLayout(adjustableColumn=True, rowSpacing=5, columnAttach=("both", pad), manage=expanded)
        self.cards[key] = {"shell": shell, "body": body, "head": head, "open": expanded, "arrow": arrow}
        if self.skin:
            self.skin.box(body, "body")
            if key in ("inspect", "publish", "log"):
                self.skin.fields(body)

    def _end_card(self):
        if self.skin:
            spacer = self.cmds.text(label="", height=3)
            self.skin.text(spacer)
        elif hasattr(self.cmds, "separator"):
            self.cmds.separator(style="none", height=3)
        self.cmds.setParent("..")
        self.cmds.setParent("..")

    def _toggle_card(self, key, expanded=None):
        card = self.cards[key]
        expanded = not card["open"] if expanded is None else bool(expanded)
        card["open"] = expanded
        self.cmds.columnLayout(card["body"], edit=True, manage=expanded)
        if self.skin:
            card["arrow"].setPixmap(self.skin.pixmap("chevron-down" if expanded else "chevron-right", 12))

    def _open_publish_settings(self, *args):
        self._toggle_card("publish", True)
        self._expand_sections("action_section")

    def _open_rules(self, *args):
        if self.web:
            self.web.detail("rules")
        else:
            self._open_publish_settings()
            self._expand_sections("check_rules_section")

    def _open_textures(self):
        if self.web:
            self.web.detail("textures")
        else:
            self._open_publish_settings()
            self._expand_sections("texture_section")

    def _rule_line(self, key, text, visible=True):
        control = self.cmds.button(label=text, height=19, manage=visible,
                                   annotation="展开或收起" + text, command=lambda *_: self._toggle_group(key))
        arrow = self.skin.rule(control, text) if self.skin else None
        self.disclosures[key] = {"open": True, "arrow": arrow}
        return control

    def _toggle_group(self, key):
        group = self.disclosures[key]
        group["open"] = not group["open"]
        if self.skin:
            name = "chevron-down" if group["open"] else "chevron-right"
            group["arrow"].setPixmap(self.skin.pixmap(name, 10))
        self._manage("review_rows", self.requested_visibility.get("review_rows", False))

    def _two_actions(self, left, right):
        form = self.cmds.formLayout(height=29) if hasattr(self.cmds, "formLayout") else self.cmds.rowLayout(numberOfColumns=2)
        for key, label, callback, icon, hint in (left, right):
            self.controls[key] = self._action_button(label, callback, icon, hint)
        if hasattr(self.cmds, "formLayout"):
            a, b = self.controls[left[0]], self.controls[right[0]]
            self.cmds.formLayout(form, edit=True,
                                 attachForm=[(a, "left", 0), (a, "top", 0), (b, "right", 0), (b, "top", 0)],
                                 attachPosition=[(a, "right", 3, 50), (b, "left", 3, 50)])
        self.cmds.setParent("..")
        return form

    def _manage(self, key, visible):
        if not hasattr(self.cmds, "control"):
            return
        self.requested_visibility[key] = visible
        if key == "review_rows":
            self.cmds.control(self.controls["issue_caption"], edit=True, manage=visible)
            visible = visible and self.disclosures["issue_caption"]["open"]
        control = self.controls[key]
        if self.cmds.layout(control, exists=True):
            self.cmds.layout(control, edit=True, manage=visible)
        else:
            self.cmds.control(control, edit=True, manage=visible)

    def _set_export_receipt(self, path="", display=""):
        self.export_receipt = {"path": path, "display": display} if path else {}
        if "export_receipt_bar" in self.controls:
            if path:
                self.cmds.text(self.controls["export_receipt_hint"], edit=True, annotation=path,
                               label="已导出至 {0}\n请前往 UE「AssetForge 工作台 → 包体导入」选包".format(display))
            self._manage("export_receipt_bar", bool(path))
        self._web_changed()

    def _invalidate_review(self):
        self.checked_inputs = None
        self.action_serial += 1
        self._action_buttons()
        self._check_notice()
        self._dismiss_toast()
        self.review_gate = None
        self._set_export_receipt()
        self.last_validation = None
        self.locator_selection = []
        self.active_issue = None
        self._render_issues([])
        self._render_passes([])
        self._set_summary("待检查", "muted")

    def _reset_review(self, *args):
        self.scene_texture_preview = ((), 0, ())
        self.texture_preview = None
        self.last_scan = None
        self.last_selection = []
        self.pinned_roots = []
        self.pinned_ids = []
        self.selection_note = {}
        self.material_binding_context = None
        self.material_texture_set_overrides.clear()
        self._invalidate_review()
        self._set_panel("texture_summary", format_empty_texture_details())
        self._selection_label()

    def _viewport_selection(self):
        if hasattr(self.cmds, "ls"):
            return self.cmds.ls(selection=True, long=True) or []
        return self.pipeline.adapter.get_current_selection() or []

    @staticmethod
    def _display_selection(selected):
        name = "、".join(node.rsplit("|", 1)[-1].partition(".")[0] for node in selected[:2])
        return name + (" 等 {0} 项".format(len(selected)) if len(selected) > 2 else "")

    def _pin_selection(self, selection):
        self.pinned_roots = list(selection)
        self.pinned_ids = []
        if hasattr(self.cmds, "objExists"):
            self.pinned_ids = [(self.cmds.ls(node, uuid=True) or [""])[0] for node in selection]

    def _pinned_selection(self):
        if not self.pinned_ids:
            return list(self.pinned_roots)
        paths = []
        for node, identifier in zip(self.pinned_roots, self.pinned_ids):
            # A replacement node at the old path must never become the checked asset.
            matches = self.cmds.ls(identifier, long=True) if identifier else self.cmds.ls(node, long=True)
            if not matches or len(matches) != 1:
                return []
            paths.append(matches[0])
        return paths

    def _selection_label(self, *args):
        if self.locating:
            return
        selected = self._viewport_selection()
        if self.locator_selection and not self._inspecting_selection(selected):
            self.locator_selection = []
            workbench_locator.clear_markers()
        pinned = self._pinned_selection()
        self.selection_note = {}
        if self.pinned_roots:
            label = (self.last_scan or {}).get("asset_name") or self._display_selection(self.pinned_roots)
            if not pinned:
                self.selection_note = {"missing": True, "switchTo": self._display_selection(selected)}
            elif not selected:
                self.selection_note = {"canSelect": True}
            elif not all(any(node.partition(".")[0] == root or node.startswith(root + "|")
                             for root in pinned) for node in selected):
                self.selection_note = {"switchTo": self._display_selection(selected)}
        else:
            label = self._display_selection(selected) or "选择要检查的资产"
        for key in ("check_asset", "export_action"):
            if key in self.controls and hasattr(self.cmds, "button"):
                self.cmds.button(self.controls[key], edit=True, enable=bool(pinned or selected and not self.pinned_roots)
                                 and not self.action_button.get("busy"))
        control = self.controls.get("current_asset")
        if control:
            self.cmds.text(control, edit=True, label=label, annotation="\n".join(pinned or selected))
        if "select_review_asset" in self.controls:
            self._manage("select_review_asset", bool(self.selection_note.get("canSelect")))
            self._manage("switch_review_asset", bool(self.selection_note.get("switchTo")))
            self._set_label("switch_review_asset_note", "视口已选 " + self.selection_note.get("switchTo", ""))
            self._manage("switch_review_asset_note", bool(self.selection_note.get("switchTo")))
        self._web_changed()

    def _select_review_asset(self, *args, **kwargs):
        target = kwargs.get("target")
        roots = self._review_selection()
        if not roots:
            return
        self.cmds.selectMode(object=True)
        self.cmds.select([target] if target else roots, replace=True, noExpand=True)
        self._selection_label()

    def _focus_issue(self):
        row = self.active_issue
        if not row:
            return
        target = row.get("mesh") or row.get("object_path") or row["object"]
        self._select_review_asset(target=target if target and self.cmds.objExists(target) else None)
        panel = workbench_locator._model_panel(self.cmds)
        if panel:
            camera = self.cmds.modelEditor(panel, query=True, camera=True)
            if self.cmds.camera(camera, query=True, startupCamera=True):
                self.cmds.viewFit(camera, animate=False)

    def _open_uv_editor(self):
        row = self.active_issue or {}
        mesh = row.get("mesh")
        self._select_review_asset(target=mesh if mesh and self.cmds.objExists(mesh) else None)
        get_mel().eval("TextureViewWindow;")

    def _clear_history(self):
        roots = self._review_selection()
        if not roots:
            return
        targets = self.pipeline.scan_assets(roots).get("meshes", [])
        if not targets:
            return
        if self._should_confirm_prefix_fix() and self.cmds.confirmDialog(
                title="确认清理构造历史", message="清理已检查网格的构造历史。建模步骤将被移除，可使用 Maya 撤销。",
                button=["清理", "取消"], defaultButton="清理", cancelButton="取消", dismissString="取消") != "清理":
            return
        self.cmds.undoInfo(openChunk=True, chunkName="DCC AssetForge 清理构造历史")
        try:
            self.cmds.delete(targets, constructionHistory=True)
        finally:
            self.cmds.undoInfo(closeChunk=True)
        self._recheck_mesh()

    def _diagnostic_action(self, action):
        row = self.active_issue
        if not row or self.action_button.get("busy") or not self._review_selection():
            return
        operations = {"rename": self._rename_prefix, "rules": self._open_rules,
                      "focus": self._focus_issue, "freeze": self._apply_transform_fix,
                      "uv": self._open_uv_editor, "history": self._clear_history, "textures": self._open_textures,
                      "choose_textures": self._choose_texture_folder}
        if action not in {entry["id"] for entry in row["diagnostic"]["actions"]}:
            return
        try:
            operations[action]()
        except (RuntimeError, ValueError) as exc:
            self._show_error(exc, "diagnostic_action")

    def _passed_checks(self):
        validation = self.last_validation or {}
        return [describe(row, self.last_scan or {}, validation) for row in validation.get("checks", [])
                if row.get("status") == "pass"]

    def _render_passes(self, passed):
        if "passed_header" not in self.controls:
            return
        self._manage("passed_header", self.last_validation is not None)
        self._manage("passed_list", False)
        self.cmds.button(self.controls["passed_header"], edit=True,
                         label="✓ 已通过 {0} 项检查".format(len(passed)))
        self._set_label("passed_list", "\n".join(item["title"] for item in passed))

    def _toggle_passes(self, *args):
        self._manage("passed_list", not self.requested_visibility.get("passed_list"))

    def _inspecting_selection(self, selected):
        if not selected:
            return False
        if self.locator_selection and list(selected) == self.locator_selection:
            return True
        if not self.active_issue or not self.active_issue["mesh"]:
            return False
        # Editing points in the inspected mesh must keep its issue rows and the original export roots.
        mesh = self.active_issue["mesh"]
        owner = mesh.rpartition("|")[0]
        return all(node.partition(".")[0] in (owner, mesh) for node in selected)

    def _asset_roots(self, selected):
        roots = []
        for node in selected:
            owner = node.partition(".")[0]
            if hasattr(self.cmds, "nodeType") and self.cmds.nodeType(owner) == "mesh":
                owner = (self.cmds.listRelatives(owner, parent=True, fullPath=True) or [owner])[0]
            if owner not in roots:
                roots.append(owner)
        return roots

    def _review_selection(self):
        if self.pinned_roots:
            return self._pinned_selection()
        selected = self.pipeline.adapter.get_current_selection()
        if self._inspecting_selection(selected or []):
            return list(self.last_selection)
        return self._asset_roots(selected or [])

    def _render_issues(self, rows):
        self.issue_revision += 1
        self._web_changed()
        workbench_locator.clear_markers()
        self.controls.pop("recheck_mesh", None)
        if "review_rows" not in self.controls:
            self.issue_rows = rows
            return
        parent = self.controls["review_rows"]
        scroll = self.controls["main_scroll"]
        offset = 0
        if rows and self.issue_rows and hasattr(self.cmds, "evalDeferred"):
            offset = self.cmds.scrollLayout(scroll, query=True, scrollAreaValue=True)[0]
        if hasattr(self.cmds, "layout"):
            for child in self.cmds.layout(parent, query=True, childArray=True) or []:
                self.cmds.deleteUI(parent + "|" + child.rsplit("|", 1)[-1])
        self.issue_buttons = []
        self.issue_details = []
        self.issue_rows = rows
        self._manage("review_rows", bool(rows))
        self.cmds.setParent(parent)
        for row in rows:
            obj = row["object"].rsplit("|", 1)[-1]
            label = ("阻断" if row["severity"] == "error" else "警告") + "   " + row["label"]
            if row["components"]:
                label += "  ·  {0} {1}".format(len(row["components"]), "面" if row["kind"] == "f" else "边")
            if obj:
                label += "\n" + obj
            path = row["object"]
            if path and not path.startswith("|"):
                matches = self.cmds.ls(path, long=True) or []
                if len(matches) == 1:
                    path = matches[0]
            row["object_path"] = path
            tooltip = "\n".join(filter(None, (path, row["message"])))
            self.issue_buttons.append(self._action_button(label, self._row_callback(row), "locate", tooltip, 44))
            if self.skin:
                self.skin.issue(self.issue_buttons[-1], row, obj)
            detail = self.cmds.columnLayout(adjustableColumn=True, rowSpacing=4, manage=False)
            self.issue_details.append(detail)
            diagnostic = row["diagnostic"]
            self.cmds.text(label=diagnostic["summary"], align="left", wordWrap=True)
            self.cmds.text(label=diagnostic["export_impact"], align="left", wordWrap=True)
            self.cmds.text(label=diagnostic["fix_guidance"], align="left", wordWrap=True)
            for action in diagnostic["actions"]:
                self.cmds.button(label=action["label"], command=lambda *_, key=action["id"]: self._diagnostic_action(key))
            if row["components"]:
                row["location_control"] = self.cmds.text(
                    label="受影响组件：{0} {1}".format(len(row["components"]), "面" if row["kind"] == "f" else "边"),
                    align="left", wordWrap=True)
                self._action_button(diagnostic["component_label"], lambda *_: self._locate_active("source"),
                                    "component", "选择报告中的原始面或边")
                self._action_button("扩选一圈", lambda *_: self._locate_active("ring"), "ring", "选中问题点和相邻一圈顶点")
                self._action_button("转为顶点", lambda *_: self._locate_active("vertices"), "vertices", "选择问题直接关联的顶点")
            row["recheck_control"] = self.cmds.button(label="复检当前网格", command=self._recheck_mesh)
            if row["candidates"]:
                menu = self._field(self.cmds.optionMenu, "请选择材质对应的贴图集")
                self.cmds.menuItem(label="请选择", parent=menu)
                for value in row["candidates"]:
                    self.cmds.menuItem(label=value, parent=menu)
                self.cmds.optionMenu(menu, edit=True, changeCommand=self._binding_callback(row))
            self.cmds.setParent("..")
        self.cmds.setParent("..")
        if offset:
            def restore_scroll():
                if self.cmds.scrollLayout(scroll, exists=True):
                    delta = offset - self.cmds.scrollLayout(scroll, query=True, scrollAreaValue=True)[0]
                    if delta:
                        self.cmds.scrollLayout(scroll, edit=True, scrollByPixel=("down" if delta > 0 else "up", abs(delta)))
            self.cmds.evalDeferred(restore_scroll)

    def _binding_callback(self, row):
        def bind(value):
            if value in row["candidates"]:
                self.material_texture_set_overrides[row["object"]] = value
                # Rechecking rebuilds the combo box. Let Maya finish dispatching its choice first.
                revision = self.issue_revision
                self.cmds.evalDeferred(lambda: self._validate_binding([row["object"]])
                                       if not self.feedback_closed and self.issue_revision == revision else None)
        return bind

    def _row_callback(self, row):
        def select(*args):
            self.active_issue = row
            if self.skin:
                for item, button in zip(self.issue_rows, self.issue_buttons):
                    self.skin.active(button, item is row)
            self._show_diagnostic(row)
        return select

    def _show_diagnostic(self, row):
        for item, detail in zip(self.issue_rows, self.issue_details):
            self.cmds.layout(detail, edit=True, manage=item is row)
        if row.get("recheck_control"):
            self.controls["recheck_mesh"] = row["recheck_control"]
        workbench_locator.clear_markers()
        if row["components"]:
            self._locate_active("source")
        self._web_changed()

    def _locate_active(self, mode="source"):
        row = self.active_issue
        if not row or not row["components"] or not self._review_selection():
            return
        self.locating = True
        try:
            result = workbench_locator.locate(self.cmds, row, mode)
            self.locator_selection = result["selection"]
            row["location_feedback"] = result["message"]
        except (RuntimeError, ValueError, IndexError) as exc:
            row["location_feedback"] = "定位失败，请重新检查。 " + to_text(exc)
        finally:
            self.locating = False
        if row.get("location_control"):
            self.cmds.text(row["location_control"], edit=True, label=row["location_feedback"])
        self._selection_label()

    def _recheck_mesh(self, *args):
        self._run_action("rescan", lambda: self._check_asset(recheck=True))

    def _build_project_preset_panel(self):
        self._section("项目预设", collapse=True, key="project_preset_section")
        self.cmds.text(label=PRESET_GUIDANCE, align="left", wordWrap=True)
        self.controls["settings_path"] = self.cmds.text(label="当前预设：未加载 / 未保存", align="left", wordWrap=True)
        self._native_folder_button("preset")
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

    def _build_mcp_header_controls(self):
        self.cmds.rowLayout(numberOfColumns=3, adjustableColumn=1, columnWidth3=(92, 42, 42))
        self.controls["mcp_status"] = self.cmds.text(label="MCP：未检查", align="left")
        self._style_status_control(self.controls["mcp_status"], "muted", compact=True)
        self.cmds.button(label="启动", command=self._start_mcp_bridge, width=42)
        self.cmds.button(label="状态", command=self._show_mcp_status, width=42)
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
            self._set_mcp_status({"status": "error", "message": to_text(exc)})
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
            self._set_mcp_status({"status": "error", "message": to_text(exc)})
            self._show_error(exc, "mcp_bridge_show_status_from_ui")

    def _load_launcher_module(self):
        if self._launcher_module is not None:
            return self._launcher_module
        path = os.path.join(asset_forge_repo_root(), "scripts", "maya_launch_asset_forge.py")
        module_name = "asset_forge_maya_ui_launcher"
        try:
            from importlib import util
        except ImportError:
            import imp
            module = imp.load_source(module_name, path)
        else:
            spec = util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise RuntimeError("无法加载 Maya launcher: {0}".format(path))
            module = util.module_from_spec(spec)
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

    def _style_status_control(self, control, state="muted", compact=False):
        if self.skin:
            if compact:
                label = self.cmds.text(control, query=True, label=True)
                tone = {"ok": "success", "warning": "warning", "error": "danger", "info": "info"}.get(state, "secondary")
                self.skin.pill(control, label, tone)
            else:
                self.skin.text(control, "secondary")
            return
        try:
            import maya.OpenMayaUI as omui
            try:
                from shiboken6 import wrapInstance
                from PySide6 import QtWidgets
            except ImportError:
                from shiboken2 import wrapInstance
                from PySide2 import QtWidgets
            pointer = omui.MQtUtil.findControl(control)
            if pointer:
                widget = wrapInstance(int(pointer), QtWidgets.QWidget)
                accent = STATUS_ACCENTS.get(state, "#303030")
                widget.setStyleSheet("QLabel {background:#1F1F1F;color:#F2F2F2;border:none;"
                                     "border-left:2px solid " + accent + ";padding:2px 6px;}")
        except (ImportError, RuntimeError):
            return

    def _build_publish_setup(self):
        if hasattr(self.cmds, "optionVar"):
            key = "assetForgeWorkbenchGuidanceToast"
            self.toast_enabled = not self.cmds.optionVar(exists=key) or bool(self.cmds.optionVar(query=key))
        self._section("发布目标", collapse=False)
        self.controls["target_path"] = self._field(self.cmds.textFieldGrp, label="UE 目标路径", text="/Game/Props", adjustableColumn=2)
        self.controls["target_engine_version"] = self._field(
            self.cmds.textFieldGrp, label="目标 UE 版本", text="", adjustableColumn=2, annotation="例如 5.6 或 5.8。留空时在 UE 中确认。"
        )
        self.controls["output_dir"] = self._field(
            self.cmds.textFieldButtonGrp, label="导出根目录",
            text=os.path.expanduser("~/AssetForge/Exports"),
            buttonLabel="选择",
            buttonCommand=self._choose_output_dir,
            adjustableColumn=2,
        )
        self._native_folder_button("output")
        self._end_section()

    def _build_rule_settings(self):
        self._section("规范与预算", collapse=True, key="check_rules_section")
        self.controls["name_prefix"] = self._field(self.cmds.textFieldGrp, label="模型前缀", text="SM_", adjustableColumn=2,
                                                   changeCommand=self._review_inputs_edited)
        self.controls["texture_prefix"] = self._field(self.cmds.textFieldGrp, label="贴图前缀", text="T_", adjustableColumn=2)
        static_rules = self.pipeline.rules.get(ASSET_TYPE_STATIC_PROP, {})
        for key, label, rule, fallback in (
            ("triangle_budget", "三角面预算", "max_triangles", 50000),
            ("material_slot_budget", "材质槽预算", "max_material_slots", 5),
        ):
            self.controls[key] = self._field(self.cmds.intFieldGrp, label=label,
                                             value1=static_rules.get(rule, {}).get(TARGET_PLATFORM_PC, fallback),
                                             adjustableColumn=2, changeCommand=self._review_inputs_edited)
        self.controls["normal_format"] = self._field(self.cmds.optionMenu, label="源法线坐标格式",
                                                       changeCommand=self._review_inputs_edited)
        for label in NORMAL_FORMAT_LABELS.values():
            self.cmds.menuItem(label=label)
        self.controls["platform"] = self._field(self.cmds.optionMenu, label="目标平台", changeCommand=self._change_rule_platform)
        self.cmds.menuItem(label=TARGET_PLATFORM_PC)
        self.cmds.menuItem(label=TARGET_PLATFORM_HIGH_END_MOBILE)
        self.cmds.menuItem(label=TARGET_PLATFORM_MOBILE)
        self.cmds.optionMenu(self.controls["platform"], edit=True, value=TARGET_PLATFORM_PC)

        self.controls["material_profile"] = self._field(self.cmds.optionMenu, label="材质匹配规则",
                                                        changeCommand=self._texture_matching_edited)
        for profile in get_project_material_profiles()["profiles"]:
            self.cmds.menuItem(label=profile["name"])
        self.cmds.optionMenu(self.controls["material_profile"], edit=True, value="Props_Opaque_PainterUE_ARM")
        self._end_section()

    def _change_rule_platform(self, platform, *args):
        rules = self.pipeline.rules.get(ASSET_TYPE_STATIC_PROP, {})
        for key, rule in (("triangle_budget", "max_triangles"), ("material_slot_budget", "max_material_slots")):
            if key in self.controls:
                self.cmds.intFieldGrp(self.controls[key], edit=True, value1=rules.get(rule, {}).get(platform, 0))
        self._review_inputs_edited()

    def _build_asset_panel(self):
        self._section("资产设置", collapse=True, key="asset_section")
        self.controls["asset_hint"] = self.cmds.text(label="资产概览：未扫描", align="left", wordWrap=True)
        self.controls["asset_name_override"] = self._field(self.cmds.textFieldGrp, label="包体/文件夹名", text="", adjustableColumn=2)
        self.controls["package_version_mode"] = self._option_menu("包体迭代模式", ["overwrite", "auto_increment"], "overwrite")
        self._button_row([("修复资产名前缀", self._rename_prefix, 180), ("应用 Transform", self._apply_transform_fix, 160)])
        self._section("资产详情", collapse=True, key="asset_detail_section")
        self.controls["asset_identity"] = self.cmds.scrollField(editable=False, wordWrap=True, height=96, text=format_asset_identity({}))
        self._end_section()
        self._end_section()

    def _build_texture_panel(self):
        self._section("贴图匹配", collapse=True, key="texture_section")
        self.controls["texture_folder"] = self._field(
            self.cmds.textFieldButtonGrp, label="贴图目录",
            text="",
            buttonLabel="选择",
            buttonCommand=self._choose_texture_folder,
            changeCommand=self._texture_matching_edited,
            adjustableColumn=2,
        )
        self._native_folder_button("textures")
        self.controls["texture_set_token"] = self._field(
            self.cmds.textFieldGrp, label=TEXTURE_FILTER_LABEL, text="", adjustableColumn=2,
            changeCommand=self._texture_matching_edited,
        )
        if self.skin:
            field = self.skin.widget(self.controls["texture_set_token"])
            editor = field.findChild(self.skin.widgets.QLineEdit) if field else None
            if editor is not None:
                editor.setPlaceholderText(TEXTURE_FILTER_HINT)
        self._button_row([("跟随场景贴图", self._follow_scene_textures, 150)])
        self._button_row([("扫描贴图目录", self._scan_texture_folder, 150), ("手动绑定材质槽贴图", self._resolve_material_texture_sets, 150), ("修复贴图前缀", self._rename_texture_prefix, 150)])
        self._section("贴图详情", collapse=True, key="texture_detail_section")
        self.controls["texture_summary"] = self.cmds.scrollField(editable=False, wordWrap=True, height=132, text=format_empty_texture_details())
        self._end_section()
        self._end_section()

    def _build_preflight_panel(self):
        self._section("检查详情", collapse=True, key="preflight_section")
        self.controls["preflight_hint"] = self.cmds.text(label="检查：未执行", align="left", wordWrap=True)
        self.controls["preflight"] = self.cmds.scrollField(editable=False, wordWrap=True, height=138,
                                                         text=format_empty_preflight_details())
        if self.skin:
            self.skin.reader(self.controls["preflight"])
        self._end_section()

    def _build_advanced_settings(self):
        self.cmds.text(label="高级设置 / 导入建议（写入 Package，UE Gate 可复核）", align="left", wordWrap=True)
        self._section("基础导入", collapse=True)
        self.cmds.text(label="Maya 只生成 Package 和导入建议；UE Gate 会先检查，放行后再导入。", align="left", wordWrap=True)
        self._end_section()

        self._section("网格构建", collapse=True)
        self.cmds.text(label="保持 Mesh / 独立 Mesh 关系清晰；Combine Meshes、法线、LOD、Nanite 会在 UE Gate 导入前确认。", align="left", wordWrap=True)
        self.controls["nanite_policy"] = self._option_menu("Nanite 策略建议", ["project_default", "enable", "disable", "report_only"], "project_default")
        self.controls["static_mesh_lod_group"] = self._field(self.cmds.textFieldGrp, label="Mesh LODGroup 建议", text=FOLLOW_PROJECT_DEFAULT, adjustableColumn=2)
        self.controls["static_mesh_lod_import_policy"] = self._option_menu("Mesh LOD 导入策略建议", ["import_existing", "project_default", "ignore_lods", "report_only"], "import_existing")
        self._end_section()

        self._section("材质贴图", collapse=True)
        self.cmds.text(label="这些值会写入 Package；UE Gate 导入前仍可复核和覆盖。", align="left", wordWrap=True)
        self.controls["virtual_texture_policy"] = self._option_menu("Virtual Texture 策略建议", ["project_default", "auto", "force_on", "force_off"], "project_default")
        self.controls["texture_streaming_policy"] = self._option_menu("Texture Streaming 策略建议", ["project_default", "streaming", "never_stream"], "project_default")
        self.controls["texture_group"] = self._field(self.cmds.textFieldGrp, label="Texture Group 建议", text=FOLLOW_PROJECT_DEFAULT, adjustableColumn=2)
        self._end_section()

    def _build_log_panel(self):
        self._two_actions(("log_scan", "只扫描", self._scan, None, "只扫描当前选择"),
                          ("log_debug", "导出调试信息", self._export_debug_bundle, None, "保存当前工作台调试信息"))
        self.controls["result_block"] = self.cmds.columnLayout(adjustableColumn=True, rowSpacing=2, manage=False)
        caption = self.cmds.text(label="操作结果", align="left", height=20)
        result_field = self.cmds.scrollField(editable=False, wordWrap=True, height=24 if self.skin else 72)
        self.controls["results"] = result_field
        if self.skin:
            self.skin.text(caption, "secondary", 11, 600)
            self.skin.reader(result_field, fit_height=lambda height: self.cmds.scrollField(result_field, edit=True, height=height))
        self.cmds.setParent("..")
        self._section("Maya 操作日志", collapse=False, key="log_section")
        self.controls["last_maya_log"] = self.cmds.scrollField(editable=False, wordWrap=True, height=165)
        if self.skin:
            self.skin.reader(self.controls["last_maya_log"])
        self._end_section()
        self._two_actions(("log_folder", "打开导出目录", self._open_last_package, None, "打开最近的导出目录"),
                          ("log_analyze", "AI 分析", self._analyze, None, "分析当前资产检查结果"))

    def _section(self, label, collapse=False, key=None):
        if self.skin:
            self.cmds.columnLayout(adjustableColumn=True, rowSpacing=2)
            head = self.cmds.button(label=label, height=23, annotation="展开或收起" + label)
            arrow = self.skin.rule(head, label)
            body = self.cmds.columnLayout(adjustableColumn=True, rowSpacing=5, columnAttach=("both", 0), manage=not collapse)
            name = key or head
            self.settings_sections[name] = {"head": head, "body": body, "arrow": arrow, "open": not collapse}
            self.cmds.button(head, edit=True, command=lambda *_: self._toggle_setting(name))
            self._toggle_setting(name, not collapse)
            if key:
                self.controls[key] = body
            return
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

    def _toggle_setting(self, name, expanded=None):
        section = self.settings_sections[name]
        expanded = not section["open"] if expanded is None else bool(expanded)
        section["open"] = expanded
        self.cmds.columnLayout(section["body"], edit=True, manage=expanded)
        section["arrow"].setPixmap(self.skin.pixmap("chevron-down" if expanded else "chevron-right", 10))

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
        if self.skin:
            # Full-width actions remain legible when several long labels share a narrow dock.
            for item in buttons:
                self.cmds.button(label=item[0], command=item[1], height=25, annotation=ACTION_HINTS.get(item[0], item[0]))
            return
        self.cmds.rowLayout(numberOfColumns=len(buttons), adjustableColumn=len(buttons))
        for item in buttons:
            label, command = item[0], item[1]
            kwargs = {"label": label, "command": command, "annotation": ACTION_HINTS.get(label, label)}
            if len(item) > 2:
                kwargs["width"] = min(item[2], 97)
            self.cmds.button(**kwargs)
        self.cmds.setParent("..")

    def _field(self, command, label, **kwargs):
        kwargs.setdefault("annotation", FIELD_HINTS.get(label, "设置" + label))
        if self.skin:
            # Maya's group controls reserve a wide fixed label column. Put labels above their fields.
            caption = self.cmds.text(label=label, align="left", height=16)
            self.skin.text(caption, "secondary", 11)
            if "adjustableColumn" in kwargs:
                kwargs["columnWidth"] = (1, 1)
            label = ""
        return command(label=label, **kwargs)

    def _option_menu(self, label, values, default):
        control = self._field(self.cmds.optionMenu, label)
        self.option_labels[control] = {value: SETTING_VALUE_LABELS.get(value, value) for value in values}
        for value in values:
            visible = self.option_labels[control][value]
            self.cmds.menuItem(label=visible, annotation=FIELD_HINTS.get(label, "选择" + visible))
        self._set_option_value(control, default)
        return control

    def _option_value(self, control, visible_value):
        return next((value for value, label in self.option_labels.get(control, {}).items() if label == visible_value),
                    visible_value)

    def _set_option_value(self, control, value):
        self.cmds.optionMenu(control, edit=True, value=self.option_labels.get(control, {}).get(value, value))

    def _target_platform(self):
        return self.cmds.optionMenu(self.controls["platform"], query=True, value=True)

    def _target_engine_version(self):
        if "target_engine_version" in self.controls:
            return self.cmds.textFieldGrp(self.controls["target_engine_version"], query=True, text=True)
        return (getattr(self, "applied_project_settings", {}) or {}).get("target_engine_version", "")

    def _target_path(self):
        value = self.cmds.textFieldGrp(self.controls["target_path"], query=True, text=True)
        try:
            return sanitize_unreal_package_path(value)
        except ValueError as exc:
            raise RuntimeError(to_text(exc))

    def _name_prefix(self):
        return self.cmds.textFieldGrp(self.controls["name_prefix"], query=True, text=True).strip() or "SM_"

    def _asset_name_override(self):
        return self.cmds.textFieldGrp(self.controls["asset_name_override"], query=True, text=True).strip()

    def _package_version_mode(self):
        return self._option_value(self.controls["package_version_mode"], self.cmds.optionMenu(self.controls["package_version_mode"], query=True, value=True)) if "package_version_mode" in self.controls else "overwrite"

    def _texture_prefix(self):
        return self.cmds.textFieldGrp(self.controls["texture_prefix"], query=True, text=True).strip() or "T_"

    def _triangle_budget(self):
        return int(self.cmds.intFieldGrp(self.controls["triangle_budget"], query=True, value1=True) or 0)

    def _material_slot_budget(self):
        control = self.controls.get("material_slot_budget")
        if control:
            return int(self.cmds.intFieldGrp(control, query=True, value1=True) or 0)
        return 0

    def _normal_format(self):
        control = self.controls.get("normal_format")
        return normalize_normal_format(self.cmds.optionMenu(control, query=True, value=True) if control else None)

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
        return self._option_value(self.controls["virtual_texture_policy"], self.cmds.optionMenu(self.controls["virtual_texture_policy"], query=True, value=True)) if "virtual_texture_policy" in self.controls else "project_default"

    def _texture_streaming_policy(self):
        return self._option_value(self.controls["texture_streaming_policy"], self.cmds.optionMenu(self.controls["texture_streaming_policy"], query=True, value=True)) if "texture_streaming_policy" in self.controls else "project_default"

    def _texture_group(self):
        return self._group_value("texture_group")

    def _static_mesh_lod_group(self):
        return self._group_value("static_mesh_lod_group")

    def _group_value(self, name):
        control = self.controls.get(name)
        value = self.cmds.textFieldGrp(control, query=True, text=True).strip() if control else ""
        return "project_default" if not value or value == FOLLOW_PROJECT_DEFAULT else value

    def _nanite_policy(self):
        return self._option_value(self.controls["nanite_policy"], self.cmds.optionMenu(self.controls["nanite_policy"], query=True, value=True)) if "nanite_policy" in self.controls else "project_default"

    def _static_mesh_lod_import_policy(self):
        return self._option_value(self.controls["static_mesh_lod_import_policy"], self.cmds.optionMenu(self.controls["static_mesh_lod_import_policy"], query=True, value=True)) if "static_mesh_lod_import_policy" in self.controls else "import_existing"

    def _texture_import_policy(self):
        return {
            "virtual_texture_policy": self._virtual_texture_policy() or "project_default",
            "texture_streaming_policy": self._texture_streaming_policy() or "project_default",
            "texture_group": self._texture_group() or "project_default",
            "normal_format": self._normal_format(),
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
        return apply_rule_settings(self.pipeline.rules, self._target_platform(), self._name_prefix(),
                                   self._triangle_budget(), self._material_slot_budget())

    def _choose_output_dir(self, *args):
        paths = self.cmds.fileDialog2(fileMode=3, caption="选择 DCC AssetForge 导出根目录") or []
        if paths:
            self.cmds.textFieldButtonGrp(self.controls["output_dir"], edit=True, text=paths[0])

    def _scene_texture_state(self):
        roots = tuple(self._review_selection())
        if not roots:
            return 0, ()
        if roots != self.scene_texture_preview[0]:
            adapter = self.pipeline.adapter
            read_textures = getattr(adapter, "scene_textures", None)
            textures = read_textures(roots) if read_textures else []
            directories = tuple(dict.fromkeys(
                os.path.dirname(os.path.realpath(item["path"])) for item in textures
                if item.get("path") and os.path.isfile(item["path"])
            ))
            count = valid_texture_count(textures)
            if read_textures is None:
                count_textures = getattr(adapter, "count_scene_textures", None)
                count = count_textures(roots) if count_textures else 0
            self.scene_texture_preview = (roots, count, directories)
        current = self.last_scan or {}
        count, directories = self.scene_texture_preview[1:]
        if tuple(current.get("asset_roots") or self.last_selection) == roots:
            count = current.get("scene_texture_count", count)
        return count, directories

    def _scene_texture_count(self):
        return self._scene_texture_state()[0]

    def _folder_target(self, kind):
        if kind == "output":
            return self._output_dir(), "打开导出根目录，查找已打包资产。"
        if kind == "preset":
            path = os.path.dirname(os.path.abspath(self.project_settings_path)) if self.project_settings_path else ""
            return path, "打开当前项目预设所在的文件夹。"
        override = self._texture_folder()
        if override:
            return override, "打开当前外部贴图目录。"
        _, directories = self._scene_texture_state()
        if not directories:
            return "", "当前资产还没有可定位的场景贴图文件。"
        if len(directories) == 1:
            return directories[0], "打开场景贴图所在的文件夹。"
        try:
            common = os.path.commonpath(directories)
        except ValueError:
            common = ""
        if common and os.path.dirname(common) != common:
            return common, "场景贴图分散在多个文件夹，打开它们的公共父目录。"
        return directories[0], "场景贴图分散在多个位置，打开首个有效目录。"

    def _folder_state(self, kind):
        path, hint = self._folder_target(kind)
        return {"available": bool(path and os.path.isdir(path)), "hint": hint, "path": path}

    def _open_folder(self, kind):
        path, hint = self._folder_target(kind)
        try:
            open_directory(path)
        except (OSError, RuntimeError):
            self.folder_notice = "暂时无法打开文件夹。请检查路径是否存在并可以访问。 " + hint
        else:
            self.folder_notice = ""
        if self.folder_notice:
            self._set_results(self.folder_notice)
        self._web_changed()

    def _native_folder_button(self, kind):
        callback = lambda *_: self._open_folder(kind)
        hint = {"output": "打开导出根目录", "textures": "打开贴图所在的文件夹",
                "preset": "打开项目预设所在的文件夹"}[kind]
        if self.skin:
            button = self.cmds.button(label="", height=25, width=28, command=callback, annotation=hint)
            widget = self.skin.button(button, "folder", "tool")
            if widget is not None:
                widget.setAccessibleName(hint)
        else:
            self.cmds.button(label=hint, command=callback, annotation=hint)

    def _choose_texture_folder(self, *args):
        paths = self.cmds.fileDialog2(fileMode=3, caption="选择 Painter / Designer 贴图目录") or []
        if paths:
            previous = _directory_key(self._texture_folder())
            self.cmds.textFieldButtonGrp(self.controls["texture_folder"], edit=True, text=paths[0])
            if _directory_key(self._texture_folder()) != previous:
                self._texture_matching_edited()
            self._web_changed()

    def _follow_scene_textures(self, *args):
        self.cmds.textFieldButtonGrp(self.controls["texture_folder"], edit=True, text="")
        self.scene_texture_preview = ((), 0, ())
        self._texture_matching_edited()

    def _texture_matching_inputs(self):
        return (_directory_key(self._texture_folder()), self._texture_set_token(), self._material_profile())

    def _texture_matching_edited(self, *args):
        self.folder_notice = ""
        self.texture_preview = None
        self._review_inputs_edited()
        if self._texture_folder():
            self._scan_texture_folder()
        else:
            self._set_panel("texture_summary", self._format_texture_folder_scan({}))
        self._web_changed()

    def _visible_texture_scan(self):
        folder = _directory_key(self._texture_folder())
        if not folder:
            return {}
        scan = self.texture_preview if self.texture_preview is not None else (self.last_scan or {}).get("texture_folder_scan")
        return scan if scan and folder == _directory_key(scan.get("texture_folder", "")) else {}

    def _preflight_options(self):
        return {"target_platform": self._target_platform(), "material_profile": self._material_profile(),
                "texture_folder": self._texture_folder(), "texture_set_token": self._texture_set_token(),
                "target_path": self._target_path(), "rules": self._active_rules(),
                "texture_import_policy": self._texture_import_policy(), "static_mesh_import_policy": self._static_mesh_import_policy()}

    @staticmethod
    def _comparable_inputs(options):
        folder = options["texture_folder"]
        return dict(options, texture_folder=os.path.normcase(os.path.abspath(folder)) if folder else "")

    def _review_inputs_edited(self, *args):
        if self.checked_inputs is None:
            return
        try:
            current = self._comparable_inputs(self._preflight_options())
        except (RuntimeError, ValueError):
            # A partially edited input already invalidates prior clearance.
            current = None
        if self.checked_inputs == current:
            return
        self._invalidate_review()
        self._set_panel("preflight", "检查设置已更改，请重新检查资产。")
        self._set_next_action("下一步：点击“检查资产”。")

    def _texture_binding_inputs(self, selection, options):
        scene = self.cmds.file(query=True, sceneName=True) if hasattr(self.cmds, "file") else ""
        return (scene, tuple(sorted(selection)), _directory_key(options["texture_folder"]),
                options["texture_set_token"], options["material_profile"])

    def _run_preflight(self, selection=None):
        self.review_gate = None
        self._set_export_receipt()
        selection = self._review_selection() if selection is None else selection
        if not selection:
            raise RuntimeError(format_empty_selection_guidance())
        changed = bool(self.last_selection and list(selection) != list(self.last_selection))
        options = self._preflight_options()
        self.checked_inputs = self._comparable_inputs(options)
        context = self._texture_binding_inputs(selection, options)
        if context != self.material_binding_context:
            self.material_texture_set_overrides.clear()
            self.material_binding_context = context
        preflight = self.pipeline.preflight_assets(
            selection, asset_name_override="", source_name_suffix="",
            material_texture_set_overrides=self.material_texture_set_overrides, **options)
        self.last_scan = preflight["scan"]
        self.scene_texture_preview = ((), 0, ())
        self.last_validation = preflight["validation"]
        self.last_texture_scan = preflight.get("texture_folder_scan", {})
        self.texture_preview = None
        self.last_selection = list(selection)
        preflight["selection_changed"] = changed
        return preflight

    def _scan(self, *args):
        self._invalidate_review()
        try:
            self.last_scan = self.pipeline.scan_selection()
            self.last_texture_scan = self.last_scan.get("texture_folder_scan", {})
            self.last_selection = list(self.last_scan.get("asset_roots", []))
            self._set_label("current_asset", self.last_scan.get("asset_name", ""))
            self._set_next_action("下一步：点击“检查”，确认是否可以导出。")
            self._refresh_status_cards(self.last_scan, self.last_validation, self.last_texture_scan)
            self._set_panel("asset_identity", format_asset_identity(self.last_scan))
            self._set_panel("preflight", "下一步：点击“检查”查看阻断项、注意项和可修复项。")
            self._focus_asset_panel()
            self._set_results("模型扫描完成。")
            self._log_operation("scan_model", "success", outputs={"asset_name": self.last_scan.get("asset_name", ""), "mesh_count": self.last_scan.get("mesh_count", 0)})
        except Exception as exc:
            self._show_error(exc, "scan_model")

    def _validate(self, *args):
        selection = None if self.pinned_roots else self._review_selection()
        self._run_action("inspect", lambda: self._check_asset(selection=selection))

    def _switch_and_check(self, *args):
        selection = self._viewport_selection()
        if not selection:
            return
        selection = self._asset_roots(selection)
        self._run_action("switch", lambda: self._check_asset(selection=selection))

    def _validate_binding(self, materials):
        selection = self._review_selection()
        self._run_action("inspect", lambda: self._check_asset(materials, selection=selection))

    def _check_asset(self, materials=(), selection=None, recheck=False):
        if not (self._review_selection() if selection is None else selection):
            return "待检查"
        try:
            preflight = self._run_preflight(selection)
            self._pin_selection(self.last_selection)
            self._selection_label()
            text = format_preflight_summary(preflight["scan"], preflight["validation"], preflight.get("texture_folder_scan", {}))
            if preflight.get("selection_changed"):
                text = "检测到当前 Maya 选择已变化，已自动重新扫描。\n\n" + text
            self._apply_preflight_to_ui(preflight["scan"], preflight["validation"], preflight.get("texture_folder_scan", {}), text)
            self._set_results("检查完成。")
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
            result = self.check_notice
            name = preflight["scan"].get("asset_name", "")
            confirmed = {row.get("material_name") for row in preflight["scan"].get("material_texture_sets", [])
                         if row.get("status") == "bound" and row.get("binding_source") == "manual_override"
                         and row.get("texture_set") == self.material_texture_set_overrides.get(row.get("material_name"))}
            resolved = materials and all(material in confirmed for material in materials)
            summary = ("材质歧义已解除 · " if resolved else "") + result["finding"]
            completed = "复检完成：" if recheck else ""
            self._notify_viewport("{0} {1}{2} {3} → {4}".format(result["icon"], completed, name, summary, result["next"]))
            return "检查完成"
        except Exception as exc:
            self._action_error(exc, "preflight")
            return "检查失败"

    def _action_error(self, exc, operation):
        self.review_gate = None
        self._set_export_receipt()
        self._show_error(exc, operation)
        self._notify_viewport(self.check_notice["text"] + " → 下一步：查看技术日志")

    def _resolve_material_texture_sets(self, *args):
        try:
            selection = self._review_selection()
            if not selection or not self._texture_folder():
                self._set_results("请选择一个资产和外部贴图目录，再绑定贴图。")
                return
            options = self._preflight_options()
            context = self._texture_binding_inputs(selection, options)
            overrides = self.material_texture_set_overrides if context == self.material_binding_context else {}
            preview = self.pipeline.match_texture_source(
                self.pipeline.scan_assets(selection), options["texture_folder"], options["material_profile"],
                options["texture_set_token"], overrides,
            )
            folder_scan = preview["texture_folder_scan"]
            available = sorted(folder_scan.get("selected_texture_sets", []))
            if not available:
                self._set_panel("texture_summary", self._format_texture_folder_scan(folder_scan))
                self._set_results("请在贴图详情查看匹配结果，确认候选贴图集后再绑定。")
                return
            rows = preview.get("material_texture_sets", [])
            choices = [(row["material_name"], row.get("candidates") or available) for row in rows if row.get("material_name")]
            if not choices:
                self._set_results("当前资产没有可绑定的材质槽。")
                return
            selected = self._material_set_dialog(choices, overrides)
            if selected is not None:
                self.material_binding_context = context
                self.material_texture_set_overrides = selected
                ambiguous = [row.get("material_name") for row in rows if len(row.get("candidates") or []) > 1
                             and row.get("material_name") in selected]
                self._validate_binding(ambiguous)
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_error(exc, "resolve_material_texture_sets")

    def _material_set_dialog(self, choices, overrides):
        return material_binding_dialog.choose(self.skin, choices, overrides)

    def _scan_texture_folder(self, *args):
        folder = self._texture_folder()
        if not folder:
            return
        try:
            selection = list(self._review_selection())
            selection_changed = bool(self.last_selection and selection != self.last_selection)
            context = self.last_scan if selection and not selection_changed else None
            if selection and context is None:
                context = self.pipeline.scan_assets(selection)
            token = self._texture_set_token()
            preview = self.pipeline.match_texture_source(context or {}, folder, self._material_profile(), token)
            folder_scan = preview["texture_folder_scan"]
            # A refresh that discovers changed textures invalidates checkout of the old inputs.
            recorded = (self.last_scan or {}).get("texture_folder_scan", {})
            keys = ("textures", "requires_texture_set_selection", "material_texture_sets", "directory_status")
            if self.checked_inputs is not None and (selection_changed or any(recorded.get(key) != folder_scan.get(key) for key in keys)):
                self._invalidate_review()
                self._set_panel("preflight", "贴图匹配结果已更改，请重新检查资产。")
            self.texture_preview = folder_scan
            self.last_texture_scan = folder_scan
            texture_summary = self._format_texture_folder_scan(folder_scan)
            if selection_changed:
                texture_summary = "检测到当前 Maya 选择已变化，已按新选择匹配贴图。\n\n" + texture_summary
            self._set_panel("texture_summary", texture_summary)
            self._focus_texture_panel()
            self._set_results("贴图目录扫描完成。")
            self._log_operation(
                "scan_texture_folder", "success", inputs={"texture_folder": folder, "texture_set_token": token},
                outputs={"matched_count": folder_scan["matched_count"], "selected_texture_sets": folder_scan["selected_texture_sets"]},
                warnings=folder_scan.get("issues", []),
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self.texture_preview = {}
            self.last_texture_scan = {}
            self._set_panel("texture_summary", "无法核对贴图目录。请检查目录路径和访问权限，再重新扫描。")
            self._show_error(exc, "scan_texture_folder")
        self._web_changed()

    def _export(self, *args):
        selection = None if self.pinned_roots else self._review_selection()
        self._run_action("publish", lambda: self._export_package(selection))

    def _export_blocked_notice(self, scan):
        self._notify_viewport("✕ {0} 导出被阻断 → 下一步：处理检查卡片中的问题".format(scan.get("asset_name", "")))
        return "导出被阻断"

    def _export_package(self, selection=None):
        try:
            preflight = self._run_preflight(selection)
            self._pin_selection(self.last_selection)
            self._selection_label()
            selection = list(self.last_selection)
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
                self._apply_preflight_to_ui(preflight["scan"], preflight["validation"], preflight.get("texture_folder_scan", {}), preflight_text, status="导出前检查未通过")
                self._set_results(format_export_blocked_result(preflight["scan"], preflight["validation"], debug_report_path))
                self._log_operation(
                    "export_preflight_blocked",
                    "error",
                    outputs=_blocked_export_log_outputs(preflight["scan"], preflight["validation"], debug_report_path),
                    errors=_blocking_messages(preflight["validation"]),
                    report_path=debug_report_path,
                )
                return self._export_blocked_notice(preflight["scan"])

            self._log_operation("export_start", "started", inputs={"selection_count": len(selection), "target_path": self._target_path(), "texture_set_token": self._texture_set_token()})
            output_dir = self._output_dir()
            result = self.pipeline.export_assets(
                selection,
                output_dir,
                self._target_platform(),
                self._target_path(),
                material_profile=self._material_profile(),
                texture_folder=self._texture_folder(),
                texture_set_token=self._texture_set_token(),
                asset_name_override="",
                rules=self._active_rules(),
                texture_import_policy=self._texture_import_policy(),
                static_mesh_import_policy=self._static_mesh_import_policy(),
                source_name_suffix="",
                package_name_override=self._asset_name_override(),
                package_version_mode=self._package_version_mode(),
                project_preset=self._settings_from_ui(),
                material_texture_set_overrides=self.material_texture_set_overrides,
            )
            self.last_scan = result["scan"]
            self.last_validation = result["validation"]
            self.last_texture_scan = self.last_scan.get("texture_folder_scan", {})
            self.last_package_dir = result.get("package_dir", "")
            self._apply_preflight_to_ui(result["scan"], result["validation"], self.last_texture_scan, format_preflight_summary(result["scan"], result["validation"], self.last_texture_scan), status="导出完成")
            self._set_next_action("下一步：前往 UE「AssetForge 工作台 → 包体导入」，选择该 Package。")
            self._set_results(format_export_result_summary(result))
            self._log_operation("export_success", "success", outputs=_export_log_outputs(result), report_path=result.get("export_report_path", ""))
            if self.last_package_dir:
                root_parent = os.path.dirname(os.path.abspath(os.path.normpath(output_dir)))
                try:
                    display = os.path.relpath(self.last_package_dir, root_parent)
                except ValueError:  # A package provider may return a path on a different drive.
                    display = self.last_package_dir
                self._set_export_receipt(self.last_package_dir, display.replace("\\", "/"))
            self._notify_viewport("✓ {0} Package 已导出 → 下一步：前往 UE『AssetForge 工作台 → 包体导入』选包".format(self.last_scan.get("asset_name", "")))
            return "导出完成"
        except ExportValidationError as exc:
            self.last_scan = exc.scan
            self.last_validation = exc.validation
            self.last_texture_scan = (exc.scan or {}).get("texture_folder_scan", {})
            self._apply_preflight_to_ui(exc.scan, exc.validation, self.last_texture_scan, format_blocking_validation_summary(exc.validation, exc.scan, exc.debug_report_path), status="导出被阻断")
            self._set_results(format_export_blocked_result(exc.scan, exc.validation, exc.debug_report_path))
            self._log_operation("export_failed", "error", outputs=_blocked_export_log_outputs(exc.scan, exc.validation, exc.debug_report_path), errors=[to_text(exc)], report_path=exc.debug_report_path)
            self.cmds.warning(to_text(exc))
            return self._export_blocked_notice(exc.scan)
        except Exception as exc:
            self._action_error(exc, "export_failed")
            return "导出失败"

    def _rename_prefix(self, *args):
        undo_open = False
        pinned = bool(self.pinned_roots)
        repaired = False
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
                    if not pinned:
                        self._set_summary("状态：已取消资产名前缀修复")
                    self._set_results("未修改 Maya 场景。")
                    self._log_operation("fix_asset_name_prefix", "cancelled", inputs={"mesh_prefix": self._name_prefix()}, outputs={"asset_name": scan.get("asset_name", "")})
                    return
            if hasattr(self.cmds, "undoInfo"):
                self.cmds.undoInfo(openChunk=True, chunkName="DCC AssetForge 修复资产名前缀")
                undo_open = True
            if pinned:
                self._select_review_asset()
            if hasattr(self.pipeline, "rename_asset_root_with_prefix"):
                renamed = self.pipeline.rename_asset_root_with_prefix(self._name_prefix())
            else:
                renamed = self.pipeline.rename_selection_with_prefix(self._name_prefix())
            if pinned:
                self._select_review_asset()
            else:
                if renamed and hasattr(self.cmds, "select"):
                    self.cmds.select(renamed, replace=True)
                if hasattr(self.pipeline, "rename_mesh_transforms_with_prefix"):
                    renamed = list(renamed or []) + list(self.pipeline.rename_mesh_transforms_with_prefix(self._name_prefix()) or [])
            if not pinned:
                self.last_scan = self.pipeline.scan_selection()
                self._invalidate_review()
                self._set_summary("状态：资产名前缀修复完成")
                self._refresh_status_cards(self.last_scan, self.last_validation, self.last_texture_scan)
                self._set_panel("asset_identity", format_asset_identity(self.last_scan))
                self._set_panel("preflight", "已修复资产名，请重新点击“检查”。")
            repaired = True
            self._set_results("已处理资产名前缀: {0}".format(", ".join([item.split("|")[-1] for item in renamed])))
            self._log_operation("fix_asset_name_prefix", "success", inputs={"mesh_prefix": self._name_prefix()}, outputs={"renamed": renamed})
        except Exception as exc:
            self._show_error(exc, "fix_asset_name_prefix")
        finally:
            if undo_open:
                self.cmds.undoInfo(closeChunk=True)

        if pinned and repaired:
            self._recheck_mesh()

    def _apply_transform_fix(self, *args):
        undo_open = False
        pinned = bool(self.pinned_roots)
        repaired = False
        try:
            scan = self.pipeline.scan_assets(self._pinned_selection()) if pinned else self.last_scan or self.pipeline.scan_selection()
            targets = _transform_fix_targets(scan)
            if not targets:
                raise RuntimeError("没有可应用 Transform 的 Maya transform 节点。")
            if self._should_confirm_prefix_fix():
                answer = self.cmds.confirmDialog(
                    title="确认应用 Transform",
                    message=_format_transform_fix_preview(scan, targets),
                    button=["执行", "取消"],
                    defaultButton="执行",
                    cancelButton="取消",
                    dismissString="取消",
                )
                if answer != "执行":
                    if not pinned:
                        self._set_summary("状态：已取消 Transform 修复")
                    self._set_results("未修改 Maya 场景。")
                    self._log_operation("apply_transform_fix", "cancelled", outputs={"targets": targets})
                    return
            if not hasattr(self.cmds, "makeIdentity"):
                raise RuntimeError("当前 Maya cmds 环境不支持 makeIdentity，无法应用 Transform。")
            if hasattr(self.cmds, "undoInfo"):
                self.cmds.undoInfo(openChunk=True, chunkName="DCC AssetForge 应用 Transform")
                undo_open = True
            self.cmds.makeIdentity(targets, apply=True, translate=True, rotate=True, scale=True, normal=False)
            if hasattr(self.cmds, "select"):
                self.cmds.select(targets, replace=True)
            if not pinned:
                self.last_scan = self.pipeline.scan_selection()
                self._invalidate_review()
                self._set_summary("状态：Transform 已应用")
                self._refresh_status_cards(self.last_scan, self.last_validation, self.last_texture_scan)
                self._set_panel("asset_identity", format_asset_identity(self.last_scan))
                self._set_panel("preflight", "已应用 Transform，请重新点击“检查”。")
            repaired = True
            self._set_results("已应用 Transform: {0}".format(", ".join([item.split("|")[-1] for item in targets])))
            self._log_operation("apply_transform_fix", "success", outputs={"targets": targets})
        except Exception as exc:
            self._show_error(exc, "apply_transform_fix")
        finally:
            if undo_open:
                self.cmds.undoInfo(closeChunk=True)

        if pinned and repaired:
            self._recheck_mesh()

    def _rename_texture_prefix(self, *args):
        try:
            if self._texture_folder():
                self._scan_texture_folder()
                active_scan = self._visible_texture_scan()
                if not active_scan:
                    return
            else:
                active_scan = self.last_scan or self.pipeline.scan_selection()
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
            if result.get("renamed_count"):
                self._texture_matching_edited()
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
                "\n".join(json.dumps(entry, ensure_ascii=False, sort_keys=True)
                          for entry in read_latest_log_tail(self.logger.root, 18)),
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
                "material_slot_budget": self._material_slot_budget(),
                "normal_format": self._normal_format(),
                "mesh_prefix": self._name_prefix(),
                "package_name_override": self._asset_name_override(),
                "asset_name_override": "",
                "package_version_mode": self._package_version_mode(),
                "texture_prefix": self._texture_prefix(),
                "texture_set_token": self._texture_set_token(),
                "ue_target_path": self._target_path(),
                "target_engine_version": self._target_engine_version(),
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
        selection = self._review_selection()
        if not selection:
            raise RuntimeError("没有选中资产")
        if self.last_scan is None:
            return False
        if self.last_selection and list(selection) == list(self.last_selection):
            return False
        self.last_scan = self.pipeline.scan_selection()
        self._invalidate_review()
        self.last_texture_scan = self.last_scan.get("texture_folder_scan", {})
        self.last_selection = list(selection)
        return True

    def _should_confirm_prefix_fix(self):
        if getattr(self, "skip_confirmations", False):
            return False
        return hasattr(self.cmds, "confirmDialog")

    def _apply_project_settings(self, settings):
        previous_texture_inputs = self._texture_matching_inputs()
        active = normalize_project_settings(settings)
        self.applied_project_settings = dict(active)
        self.cmds.textFieldButtonGrp(self.controls["output_dir"], edit=True, text=active["export_root"])
        self.cmds.textFieldButtonGrp(self.controls["texture_folder"], edit=True, text=active["texture_root"])
        self.cmds.textFieldGrp(self.controls["name_prefix"], edit=True, text=active["mesh_prefix"])
        self.cmds.textFieldGrp(self.controls["asset_name_override"], edit=True, text=active["package_name_override"])
        if "package_version_mode" in self.controls:
            self._set_option_value(self.controls["package_version_mode"], active["package_version_mode"])
        self.cmds.textFieldGrp(self.controls["texture_prefix"], edit=True, text=active["texture_prefix"])
        self.cmds.textFieldGrp(self.controls["texture_set_token"], edit=True, text=active["texture_set_token"])
        self.cmds.textFieldGrp(self.controls["target_path"], edit=True, text=active["ue_target_path"])
        if "target_engine_version" in self.controls:
            self.cmds.textFieldGrp(self.controls["target_engine_version"], edit=True, text=active["target_engine_version"])
        self.cmds.intFieldGrp(self.controls["triangle_budget"], edit=True, value1=active["triangle_budget"])
        if "material_slot_budget" in self.controls:
            self.cmds.intFieldGrp(self.controls["material_slot_budget"], edit=True, value1=active["material_slot_budget"])
        if "normal_format" in self.controls:
            self.cmds.optionMenu(self.controls["normal_format"], edit=True, value=NORMAL_FORMAT_LABELS[active["normal_format"]])
        self.cmds.optionMenu(self.controls["platform"], edit=True, value=active["target_platform"])
        self.cmds.optionMenu(self.controls["material_profile"], edit=True, value=active["material_profile"])
        if "virtual_texture_policy" in self.controls:
            self._set_option_value(self.controls["virtual_texture_policy"], active["virtual_texture_policy"])
        if "texture_streaming_policy" in self.controls:
            self._set_option_value(self.controls["texture_streaming_policy"], active["texture_streaming_policy"])
        if "texture_group" in self.controls:
            self.cmds.textFieldGrp(self.controls["texture_group"], edit=True, text=SETTING_VALUE_LABELS.get(active["texture_group"], active["texture_group"]))
        if "nanite_policy" in self.controls:
            self._set_option_value(self.controls["nanite_policy"], active["nanite_policy"])
        if "static_mesh_lod_group" in self.controls:
            self.cmds.textFieldGrp(self.controls["static_mesh_lod_group"], edit=True, text=SETTING_VALUE_LABELS.get(active["static_mesh_lod_group"], active["static_mesh_lod_group"]))
        if "static_mesh_lod_import_policy" in self.controls:
            self._set_option_value(self.controls["static_mesh_lod_import_policy"], active["static_mesh_lod_import_policy"])
        self._set_preset_summary(active)
        if self._texture_matching_inputs() != previous_texture_inputs:
            self._texture_matching_edited()
        else:
            self._review_inputs_edited()
        return active

    def _unicode_safe_field_value(self, settings_key, ui_value):
        if "?" not in (ui_value or ""):
            return ui_value
        applied = getattr(self, "applied_project_settings", {}) or {}
        expected = applied.get(settings_key, "")
        if expected and any(ord(char) > 127 for char in expected):
            return expected
        return ui_value

    def _scene_opened(self, *args):
        self._restore_scene_preset()
        self._reset_review()

    def _restore_scene_preset(self):
        # Shelf launches rebuild the workspace. Resolve the preset from the saved scene every time.
        if self.settings_before_scene_preset is not None:
            previous, previous_path = self.settings_before_scene_preset
            self._apply_project_settings(previous)
            self.project_settings_path = previous_path
            self._set_settings_path(previous_path or "未加载", "当前")
            self.settings_before_scene_preset = None
        scene = self.cmds.file(query=True, sceneName=True)
        if not scene:
            return
        path = os.path.splitext(scene)[0] + ".assetforge.json"
        if not os.path.isfile(path):
            return
        previous = None
        try:
            settings = load_project_settings(path)
            previous = self._settings_from_ui()
            self._apply_project_settings(settings)
        except (ValueError, TypeError, IOError, RuntimeError) as exc:
            if previous is not None:
                self._apply_project_settings(previous)
            self.cmds.warning("无法加载场景预设 {0}：{1}".format(path, exc))
            return
        self.settings_before_scene_preset = previous, self.project_settings_path
        self.project_settings_path = path
        self._set_settings_path(path, "随场景加载")

    def _load_project_settings(self, *args):
        try:
            paths = self.cmds.fileDialog2(fileMode=1, caption="加载 DCC AssetForge 项目预设 JSON", fileFilter="项目预设 (*.json)") or []
            if not paths:
                return
            settings = load_project_settings(paths[0])
            self._apply_project_settings(settings)
            self.project_settings_path = paths[0]
            self._set_settings_path(paths[0], "已加载")
            if self.last_scan is None:
                self._set_summary("状态：已加载项目预设")
            self._set_preset_summary(settings)
            self._set_results("{0}\n\n预设文件：{1}".format(_format_project_settings(settings), paths[0]))
            self._log_operation("load_project_settings", "success", inputs={"path": paths[0]}, outputs=settings)
        except Exception as exc:
            self._show_error(exc, "load_project_settings")

    def _save_project_settings(self, *args):
        try:
            paths = self.cmds.fileDialog2(fileMode=0, caption="保存 DCC AssetForge 项目预设 JSON", fileFilter="项目预设 (*.assetforge.json)") or []
            if not paths:
                return
            settings = self._settings_from_ui()
            destination = paths[0].strip()
            if not destination.lower().endswith(".assetforge.json"):
                stem, suffix = os.path.splitext(destination)
                destination = (stem if suffix.lower() in (".json", ".*") else destination) + ".assetforge.json"
            path = save_project_settings(destination, settings)
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
            if self.last_scan is None:
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
            if not self._texture_folder():
                scene = self.last_scan or {}
                if self.last_validation is not None and "scene_inferred_texture_count" in scene:
                    return "场景节点已连 {0} 张\n同目录自动补齐 {1} 张\n如需更换来源，可选择外部贴图目录后复检。".format(
                        scene.get("scene_texture_count", 0), scene["scene_inferred_texture_count"])
                count = self._scene_texture_count()
                if count:
                    return "场景材质已连接 {0} 张可用贴图。检查资产后可核对同目录补齐数量。".format(count)
            return "尚未核对贴图。检查资产可读取场景贴图，也可以选择外部贴图目录。"
        status = {"valid": "可用", "incomplete": "贴图不完整", "empty": "目录为空", "unrecognized": "未识别到贴图"}
        usage_label = lambda use: TEXTURE_USAGE_LABELS.get("packed_arm" if use == "orm" else use, "预设指定贴图")
        totals = Counter(map(usage_label, scan.get("matched_usages", [])))
        usages = "、".join("{0} ×{1}".format(label, count) if count > 1 else label
                          for label, count in totals.items())
        lines = [
            "状态：{0}".format(status.get(scan.get("directory_status"), "待核对")),
            "当前选择：{0}".format(", ".join(scan.get("selected_texture_set_short_names", [])) or "未选择"),
            "已选贴图集：{0}".format(", ".join(scan.get("selected_texture_sets", [])) or "无"),
            "将导出贴图数量：{0}".format(scan.get("matched_count", 0)),
            "将导出用途：{0}".format(usages or "无"),
            "",
            "候选贴图集：",
        ]
        sets = scan.get("texture_sets", [])
        if not sets:
            lines.append("- 未找到候选贴图集")
        for item in sets:
            short = item.get("short_name", "") or item.get("set_name", "").split("_")[-1]
            missing = "、".join(map(usage_label, item.get("missing_usages", []))) or "无"
            usages = "、".join(map(usage_label, item.get("usages", []))) or "无"
            marker = "（当前）" if item.get("set_name", "") in scan.get("selected_texture_sets", []) else ""
            lines.append("- {0} / {1}{2}：完整度 {3}；用途 {4}；缺失 {5}".format(short, item.get("set_name", ""), marker, item.get("completeness", 0), usages, missing))
        lines.extend(["", "问题："])
        if scan.get("issues"):
            for issue in scan.get("issues", []):
                message = issue.get("message", "") if isinstance(issue, dict) else issue
                if isinstance(issue, dict) and issue.get("usage"):
                    message = message.replace("：" + issue["usage"], "：" + usage_label(issue["usage"]))
                    message = message.replace(" " + issue["usage"] + " ", " " + usage_label(issue["usage"]) + " ")
                lines.append("- {0}".format(message))
        else:
            lines.append("- 无阻断问题")
        lines.extend(["", "下一步建议："])
        if scan.get("auto_selected_texture_sets"):
            lines.append("- 未填写贴图名筛选词，系统已自动选择当前最优贴图集；如不正确，请填写 能区分所需贴图集的名称片段后重新扫描。")
        elif scan.get("selected_texture_set_short_names"):
            lines.append("- 已按当前筛选词选择贴图集。确认数量和用途后继续检查。")
        elif scan.get("rename_suggestions"):
            lines.append("- 如需规范命名，先确认贴图集，再点击“一键添加贴图前缀”。")
        elif scan.get("directory_status") == "valid":
            lines.append("- 可以继续检查或导出。")
        else:
            lines.append("- 请核对目录和缺失的贴图用途，再重新扫描。")
        return "\n".join(lines)

    def _apply_preflight_to_ui(self, scan, validation, texture_scan, preflight_text, status=""):
        self.review_gate = bool((validation or {}).get("can_export"))
        rows = workbench_locator.issue_rows(scan, validation)
        self._set_next_action(format_next_action_summary(scan or {}, validation or {}, texture_scan or {}))
        self._refresh_status_cards(scan or {}, validation or {}, texture_scan or {})
        self._set_panel("asset_identity", format_asset_identity(scan or {}))
        self._set_panel("texture_summary", self._format_texture_folder_scan(texture_scan or {}))
        self._set_panel("preflight", preflight_text)
        self.active_issue = None
        self._render_issues(rows)
        if len(rows) == 1:
            self.active_issue = rows[0]
            self._show_diagnostic(rows[0])
        self._set_label("current_asset", scan.get("asset_name", ""))
        self._render_passes(self._passed_checks())
        if "review_rows" not in self.controls:
            self._focus_preflight_panel()
        result = workbench_feedback.check_result(validation, rows)
        self._set_summary(result["text"], result["tone"], badge=result["badge"])
        self._check_notice(result)

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

    def _set_summary(self, text, state=None, badge=None):
        if badge is None and self.last_validation and self.last_validation.get("checks"):
            result = workbench_feedback.check_result(self.last_validation, self.issue_rows)
            text, state, badge = result["text"], result["tone"], result["badge"]
        if self.skin:
            tone = {"ok": "success", "error": "danger", "warning": "warning", "info": "info"}.get(state, "muted")
            status = {"success": "pass", "danger": "error", "warning": "warning", "info": "info"}.get(tone, "idle")
            if badge:
                short = badge
            elif text.startswith(("检查完成", "导出前检查未通过", "导出被阻断")):
                errors = sum(row["severity"] == "error" for row in self.issue_rows)
                warnings = len(self.issue_rows) - errors
                if errors and warnings:
                    short = "{0} 阻断 · {1} 警告".format(errors, warnings)
                elif errors:
                    short = "{0} 项阻断".format(errors)
                elif warnings:
                    short = "{0} 个警告".format(warnings)
                else:
                    short = "已阻断" if status == "error" else "已通过"
            else:
                short = text.replace("状态：", "").split("  ")[0]
                if len(short) > 6:
                    short = {"pass": "已完成", "error": "操作失败", "warning": "请检查"}.get(status, "查看详情")
            self.review_status = (status, short)
            self.review_message = text
            self._web_changed()
            self.skin.pill(self.controls["summary"], short, tone)
            self.cmds.text(self.controls["summary"], edit=True, annotation=text)
            return
        self.review_message = text
        self.review_status = ({"ok": "pass", "error": "error", "warning": "warning", "info": "info"}.get(state, "idle"), badge or text)
        polished = _polish_status_text(text)
        self._set_label("summary", polished, state or _summary_state(polished))

    def _set_next_action(self, text, state="info"):
        if "next_action" in self.controls:
            self._set_label("next_action", _polish_next_action_text(text), state)

    def _set_label(self, name, text, state=None):
        if name in self.controls:
            if name == "current_asset":
                self._web_changed()
            kwargs = {"edit": True, "label": text}
            self.cmds.text(self.controls[name], **kwargs)
            if state:
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
        self._set_label("preflight_hint", format_issue_card(validation))

    def _focus_asset_panel(self, *args):
        self._expand_sections("asset_section", "asset_detail_section")

    def _focus_texture_panel(self, *args):
        self._expand_sections("texture_section", "texture_detail_section")

    def _focus_preflight_panel(self, *args):
        self._expand_sections("preflight_section")

    def _focus_export_panel(self, *args):
        self._expand_sections("action_section", "preflight_section")

    def _expand_sections(self, *names):
        if not hasattr(self.cmds, "frameLayout"):
            return
        for name in names:
            if name in self.settings_sections:
                self._toggle_setting(name, True)
                continue
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

    def _preset_rules_summary(self):
        required = {"name_prefix", "texture_prefix", "triangle_budget", "material_slot_budget"}
        if not required.issubset(self.controls):
            return ""
        return "模型 {0} · 贴图 {1} · {2:,} 三角面 · {3} 材质槽".format(
            self._name_prefix(), self._texture_prefix(), self._triangle_budget(), self._material_slot_budget(),
        )

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
        self.cmds.scrollField(self.controls["results"], edit=True, text=text)
        if "result_block" in self.controls:
            self._manage("result_block", bool(text and text.strip()))

    def _show_error(self, exc, operation="ui_error"):
        message = to_text(exc)
        label = {"preflight": "检查失败", "export_failed": "导出失败"}.get(operation, "操作失败")
        lines = message.splitlines()
        summary = "{0} · {1}".format(label, lines[0] if lines else "查看技术日志")
        self._set_summary(summary, "error", badge=label)
        self._check_notice({"tone": "error", "text": "✕ " + summary})
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
            "material_slot_budget": self._material_slot_budget,
            "normal_format": self._normal_format,
            "mesh_prefix": self._name_prefix,
            "texture_prefix": self._texture_prefix,
            "texture_set_token": self._texture_set_token,
            "asset_name_override": self._asset_name_override,
            "package_name_override": self._asset_name_override,
            "package_version_mode": self._package_version_mode,
            "ue_target_path": self._target_path,
            "target_engine_version": self._target_engine_version,
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
        self.recent_logs = ["{0}  {1} · {2}".format(to_text(entry.get("timestamp") or "")[11:16],
                            _operation_label(entry["operation"]), _log_status_label(entry.get("status", "")))
                            for entry in reversed(entries[-3:]) if isinstance(entry, dict) and entry.get("operation")]
        if not entries:
            return "日志路径：{0}\n暂无 Maya 操作日志。".format(self.latest_log_path)
        formatted = [_format_log_entry(entry) for entry in reversed(entries)]
        formatted.append("日志路径：{0}".format(self.latest_log_path))
        return "\n\n".join(formatted)


def close_workspace():
    global _WORKSPACE_INSTANCE
    workbench_locator.clear_markers()
    if _WORKSPACE_INSTANCE and _WORKSPACE_INSTANCE.chrome:
        _WORKSPACE_INSTANCE.chrome.close()
    _WORKSPACE_INSTANCE = None


def _workspace_has_content(cmds):
    return any(WORKSPACE_NAME in path.split("|")[:-1] for path in cmds.lsUI(controlLayouts=True, long=True) or ())


def _autosave_enabled(cmds):
    return cmds.optionVar(exists="workspacesAutoSave") and cmds.optionVar(query="workspacesAutoSave")


def _workspace_scripts(value):
    if isinstance(value, dict):
        if value.get("objectName") == WORKSPACE_NAME:
            yield value.get("uiScript")
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return
    for child in children:
        for script in _workspace_scripts(child):
            yield script


def _saved_workspace_migration(cmds):
    """Recognize the old startup callback in the one layout this Maya process is using."""
    if not _autosave_enabled(cmds):
        return None
    try:
        layout = cmds.workspaceLayoutManager(query=True, current=True)
        if not layout or any(separator in layout for separator in ("/", "\\", ":")):
            return None
        filename = layout.replace(" ", "_") + ".json"
        path = os.path.join(cmds.internalVar(userPrefDir=True), "workspaces", filename)
        with io.open(path, "rb") as stream:
            raw = stream.read()
    except (IOError, OSError, RuntimeError, TypeError):
        return None
    for encoding in ("utf-8-sig", "gb18030", "mbcs"):
        try:
            scripts = list(_workspace_scripts(json.loads(raw.decode(encoding))))
            break
        except (LookupError, ValueError):
            continue
    else:
        return None
    old = 'python("{0}");'.format(_LEGACY_WORKSPACE_SCRIPT)
    if scripts in ([_LEGACY_WORKSPACE_SCRIPT], [old]):
        return layout, path, raw
    return None


def _schedule_workspace_restore(window, migration):
    cmds = window.cmds
    if not migration:
        cmds.evalDeferred(restore_workspace, lowestPriority=True)
        return

    def restore_and_save():
        restore_workspace()
        if _WORKSPACE_INSTANCE is not window or not window.workspace_populated or not _autosave_enabled(cmds):
            return
        layout, path, raw = migration
        try:
            if cmds.workspaceLayoutManager(query=True, current=True) != layout:
                return
            with io.open(path, "rb") as stream:
                if stream.read() != raw:
                    return
            # The backup only covers the exact pre-migration layout seen by this action.
            suffix = sha256(raw).hexdigest()[:16]
            backup = path + ".assetforge-before-restore-" + suffix + ".bak"
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                descriptor = os.open(backup, flags, 0o600)
            except OSError as exc:
                if exc.errno != errno.EEXIST:
                    raise
                with io.open(backup, "rb") as stream:
                    if stream.read() != raw:
                        return
            else:
                with io.open(descriptor, "wb") as stream:
                    stream.write(raw)
            cmds.workspaceLayoutManager(save=True)
        except (IOError, OSError, RuntimeError):
            cmds.warning("DCC AssetForge 已更新工作台回调，Maya 正常保存工作区后将在重启时生效。")

    cmds.evalDeferred(restore_and_save, lowestPriority=True)


def defer_workspace_restore():
    # Maya runs uiScript when recreating the workspace control, before its host layouts settle.
    cmds = get_cmds()
    cmds.evalDeferred(restore_workspace, lowestPriority=True)


def restore_workspace():
    global _WORKSPACE_INSTANCE
    cmds = get_cmds()
    if not cmds.workspaceControl(WORKSPACE_NAME, exists=True):
        return
    window = _WORKSPACE_INSTANCE
    if window is not None and window.workspace_populated:
        scroll = window.controls.get("main_scroll")
        if scroll and cmds.scrollLayout(scroll, exists=True):
            return
        window = None
    if window is None:
        window = _WORKSPACE_INSTANCE = AssetForgeMayaWindow(cmds_module=cmds)
    window._populate(WORKSPACE_NAME)


def show():
    """Show the DCC AssetForge Maya window."""
    return AssetForgeMayaWindow().show()


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
            "尚未核对贴图。",
            "检查资产可读取材质节点连接的贴图；选择外部贴图目录后将自动扫描。",
        ]
    )


def format_empty_preflight_details():
    return "\n".join(
        [
            "尚未执行检查。",
            "下一步：先扫描资产，再点击“只检查”。",
            "这里会列出阻断项、注意项和可点击的修复建议。",
        ]
    )


def format_issue_locator(scan, validation, texture_scan=None, preferred=""):
    scan = scan or {}
    validation = validation or {}
    texture_scan = texture_scan or {}
    warnings, errors = _checks_by_status(validation) if validation else ([], [])
    lines = [
        "定位：{0}".format(_locator_title(preferred, scan, validation, texture_scan)),
        "资产：{0}    贴图：{1} 张    阻断/注意：{2}/{3}".format(
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
        lines.append("注意项：")
        for item in warnings[:6]:
            lines.extend(_format_locator_check(item, "注意"))
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
        lines.append("结果：检查通过，可以导出 Package。")
        lines.append("下一步：导出后在 UE Gate 选择该 Package，点击“检查并导入”。")
    elif scan:
        lines.append("结果：资产已扫描，尚未执行检查。")
        lines.append("下一步：点击“只检查”。")
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
        return "检查详情"
    if preferred == "export":
        return "导出前状态"
    if validation:
        warnings, errors = _checks_by_status(validation)
        if errors or warnings:
            return "检查详情"
    if texture_scan:
        return "贴图详情"
    if scan:
        return "资产详情"
    return "等待扫描"


def _format_locator_check(item, severity_label):
    location = _check_location_hint(item)
    target = item.get("object") or item.get("asset") or item.get("node") or item.get("material") or item.get("id", "")
    if item.get("affected_meshes"):
        target = u", ".join(item["affected_meshes"])
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
    if check_id in ("ambiguous_material_texture_set", "invalid_material_texture_set"):
        return "贴图匹配 -> 手动绑定材质槽贴图"
    if check_id in ("unmatched_material", "material_texture_binding"):
        return "材质贴图绑定 -> 贴图详情 / 检查详情"
    if check_id == "zero_area_triangles":
        return "在 Maya 面选择模式定位到报告中的网格及面号（shape.f[编号]）"
    if check_id == "texture_set_selection":
        return "贴图名筛选词 -> 贴图详情"
    if check_id == "name_prefix":
        return "资产概览 -> 资产详情"
    if label:
        return label
    return "检查详情"


def _overview_status_line(scan, validation):
    scan = scan or {}
    validation = validation or {}
    if validation.get("can_export"):
        return "通过 | 检查完成，可以导出 Package"
    warnings, errors = _checks_by_status(validation) if validation else ([], [])
    if errors:
        return "阻断 | 先处理风险项，再重新检查"
    if warnings:
        return "注意 | 复核注意项后再导出"
    if scan:
        return "已扫描 | 下一步执行检查"
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
        return "未检查"
    warnings, errors = _checks_by_status(validation)
    if errors:
        return "阻断 {0} / 注意 {1}".format(len(errors), len(warnings))
    if warnings:
        return "注意 {0}".format(len(warnings))
    return "通过" if validation.get("can_export") else "待确认"


def _overview_export_line(scan, validation, texture_scan=None):
    scan = scan or {}
    validation = validation or {}
    if not scan:
        return "等待扫描"
    if not validation:
        return "等待检查"
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
        return "风险 | 未检查 · 扫描后检查"
    warnings, errors = _checks_by_status(validation)
    if errors:
        prefix = "阻断"
    elif warnings:
        prefix = "注意"
    elif validation.get("can_export"):
        prefix = "通过"
    else:
        prefix = "待确认"
    return "风险 | {0} · 阻断 {1} · 注意 {2}".format(prefix, len(errors), len(warnings))


def format_export_card(scan, validation, texture_scan=None):
    scan = scan or {}
    validation = validation or {}
    texture_scan = texture_scan or {}
    if not scan:
        return "发布 | 等待扫描 · 资产和检查"
    if not validation:
        return "发布 | 待检查 · 先检查"
    if validation.get("can_export"):
        texture_count = texture_scan.get("matched_count", len(scan.get("textures", [])))
        return "发布 | 可导出 · 贴图 {0} 张".format(texture_count)
    return "发布 | 阻断 · 先处理风险项"


def format_scan_stage(scan):
    scan = scan or {}
    if not scan:
        return "01 扫描 · 待开始"
    return "01 扫描 · 已识别 {0}".format(scan.get("asset_name", "未命名"))


def format_check_stage(scan, validation):
    scan = scan or {}
    validation = validation or {}
    if not scan:
        return "02 检查 · 等待扫描"
    if not validation:
        return "02 检查 · 可执行"
    warnings, errors = _checks_by_status(validation)
    if errors:
        return "02 检查 · 阻断 {0} / 注意 {1}".format(len(errors), len(warnings))
    if warnings:
        return "02 检查 · 注意 {0} / 可复核".format(len(warnings))
    return "02 检查 · 通过"


def format_export_stage(scan, validation):
    scan = scan or {}
    validation = validation or {}
    if not scan:
        return "03 导出 Package · 等待扫描"
    if not validation:
        return "03 导出 Package · 等待检查"
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
    if "警告" in text or "注意" in text or "待确认" in text:
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
            lines.append("命名说明：当前选择没有共同父节点，DCC AssetForge 只用第一个选择对象命名；下一步请选择共同父组，或在项目设置里填写资产名覆盖。")
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
    lines.extend(["", "注意项："])
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
        "DCC AssetForge 将修改当前 Maya 场景中的命名。",
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
        return "下一步：确认导出根目录和 UE 目标路径后，点击“检查并导出 Package”。"
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
                    "field_label": "贴图名筛选词",
                    "target_label": "贴图名筛选词输入框",
                    "field": "texture_set_token",
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
    transform_check = _first_check(validation, "frozen_transform")
    if transform_check or scan.get("frozen_transform") is False or scan.get("illegal_scale"):
        actions.append(
            {
                "id": "apply_transform_fix",
                "source_check": "frozen_transform",
                "kind": "maya_ui_callback",
                "label": "应用 Transform",
                "problem": (transform_check or {}).get("message", "Transform 未归零或存在非法缩放"),
                "button_label": "应用 Transform",
                "target_label": "应用 Transform 按钮",
                "ui_callback": "_apply_transform_fix",
                "target_count": len(_transform_fix_targets(scan)),
                "next_action": "点击“应用 Transform”后重新扫描和检查。",
                "next_step": "点击“应用 Transform”后重新扫描和检查。",
                "can_run_from_ui_flow": True,
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
                "field_label": "贴图名筛选词",
                "target_label": "贴图名筛选词输入框",
                "field": "texture_set_token",
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
        return "下一步：如使用外部贴图目录，请先点击“扫描贴图目录”；否则继续检查。"
    if scan.get("issues"):
        return "下一步：检查贴图集问题；如存在多套贴图，请输入能区分所需贴图集的名称片段后重新扫描。"
    if scan.get("rename_suggestions"):
        return "下一步：如需要统一贴图命名，确认贴图集后再点击“一键添加贴图前缀”。"
    return "下一步：贴图集已匹配，继续检查或导出。"


def _checks_by_status(validation):
    checks = list((validation or {}).get("checks", []))
    warnings = [item for item in checks if item.get("status") == "warning"]
    errors = [item for item in checks if item.get("status") == "error"]
    return warnings, errors


def _blocking_checks(validation):
    return [item for item in validation.get("checks", []) if item.get("status") == "error"]


def _first_check(validation, check_id):
    for item in (validation or {}).get("checks", []) or []:
        if item.get("id") == check_id:
            return item
    return None


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
            fixes.append("在“贴图名筛选词”中输入能区分所需贴图集的名称片段。")
    if texture_scan.get("rename_suggestions"):
        fixes.append("点击“一键添加贴图前缀”前，先确认当前贴图集选择。")
    return fixes


def _next_action_for_check(item, scan=None):
    check_id = item.get("id", "")
    if check_id == "name_prefix":
        scan = scan or {}
        return "点击“一键修复资产名前缀”或手动把导出资产名改成 {0}。".format(_expected_prefixed_name(scan.get("asset_name", ""), item))
    if check_id in ("ambiguous_material_texture_set", "invalid_material_texture_set"):
        return "在贴图匹配中点击“手动绑定材质槽贴图”，选中候选后应用并重新检查。"
    if check_id == "mesh_exists":
        return "确认选择的是包含 Mesh 的模型或组。"
    if check_id == "uv0":
        return "为模型补齐基础 UV0。"
    if check_id == "frozen_transform":
        return "冻结 Transform 后重新扫描。"
    if check_id == "texture_set_selection":
        return "在“贴图名筛选词”中选择正确候选贴图集后重新扫描。"
    return "修复该检查项后重新检查。"


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


def _transform_fix_targets(scan):
    result = []
    for item in list((scan or {}).get("asset_roots", []) or []) + list((scan or {}).get("transforms", []) or []):
        if item and item not in result:
            result.append(item)
    return result


def _format_transform_fix_preview(scan, targets):
    lines = [
        "DCC AssetForge 将在一个 Maya Undo Chunk 中执行 makeIdentity。",
        "范围：当前资产根节点和 Mesh Transform。",
        "资产：{0}".format((scan or {}).get("asset_name", "未命名")),
        "节点数：{0}".format(len(targets or [])),
        "",
    ]
    for item in list(targets or [])[:8]:
        lines.append("- {0}".format(item.split("|")[-1]))
    if len(targets or []) > 8:
        lines.append("- ...")
    return "\n".join(lines)


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
        return to_text(data)
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
        details.append("注意={0}".format(outputs.get("warning_count")))
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
    header = "{0}   {1} | {2}".format(to_text(data.get("timestamp") or "").replace("T", " "),
                                     _operation_label(data.get("operation", "")), _log_status_label(data.get("status", "")))
    return "\n".join([header] + details)


def _operation_label(operation):
    labels = {
        "startup": "打开工作台",
        "scan_model": "扫描资产",
        "preflight": "检查",
        "scan_texture_folder": "扫描贴图目录",
        "export_start": "开始导出",
        "export_success": "导出成功",
        "export_preflight_blocked": "导出前检查未通过",
        "export_failed": "导出失败",
        "fix_asset_name_prefix": "修复资产名前缀",
        "apply_transform_fix": "应用 Transform",
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
        return "待导入检查"
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
        "状态：可导出={0} | UE Gate={1} | 注意/阻断={2}/{3}".format(
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
        "状态：可导出={0} | UE Gate={1} | 注意/阻断={2}/{3}".format(
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
        "operator_action": "UE Gate: 选择该 Package -> 检查并导入",
        "next_step": "在 UE Gate 里选择该 Package，确认检查结果后导入",
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
        return "录制前看这里：资产 {0} 已可导出；打开导出报告 {1}；下一步在 UE Gate 选择该 Package，检查并导入。".format(
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
    return to_text(value or "")
