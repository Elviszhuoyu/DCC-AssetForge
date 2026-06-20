# -*- coding: utf-8 -*-
"""Callable actions for a future Unreal Editor Utility Widget."""

from __future__ import absolute_import

import os

from asset_forge.unreal import pipeline as unreal_pipeline
from asset_forge.unreal.editor_widget_model import build_gate_panel_state, discover_package_history, preview_package_gate


ACTION_PLAN = (
    {
        "id": "refresh_packages",
        "label": "刷新包体",
        "description": "读取最近导出和导入记录，刷新导入门禁队列。",
        "callable": "refresh_package_history",
    },
    {
        "id": "scan_export_directory",
        "label": "扫描导出目录",
        "description": "扫描一个或多个导出根目录，列出可审批的 Asset Forge 包体。",
        "callable": "scan_export_directory",
    },
    {
        "id": "ensure_widget_asset",
        "label": "修复工作台",
        "description": "创建或修复 EUW_AssetForgeGate 导入门禁工作台。",
        "callable": "ensure_widget_asset",
    },
    {
        "id": "read_widget_tree",
        "label": "读取控件树",
        "description": "读取门禁工作台需要绑定的核心控件。",
        "callable": "read_widget_tree",
    },
    {
        "id": "select_manifest",
        "label": "选择 Manifest",
        "description": "选择一个 Asset Forge manifest 文件作为导入对象。",
        "callable": "",
    },
    {
        "id": "select_package",
        "label": "选择包体",
        "description": "选择一个 Asset Forge 导出包目录。",
        "callable": "",
    },
    {
        "id": "dry_run_manifest",
        "label": "Manifest 预演计划",
        "description": "校验一个 manifest 并解析导入计划，不执行正式导入。",
        "callable": "dry_run_selected_manifest",
    },
    {
        "id": "import_manifest",
        "label": "导入 Manifest",
        "description": "导入当前选择的 manifest。",
        "callable": "import_selected_manifest",
    },
    {
        "id": "dry_run_package",
        "label": "预演导入计划",
        "description": "为一个 Asset Forge 包体生成导入计划，不创建 UE 资产。",
        "callable": "dry_run_selected_package",
    },
    {
        "id": "preview_package_gate",
        "label": "生成入审报告",
        "description": "生成入审报告：核对资产、贴图、材质、风险和入审状态。",
        "callable": "preview_selected_package_gate",
    },
    {
        "id": "open_report",
        "label": "打开报告",
        "description": "打开当前包体已有的门禁或导入报告，不执行导入。",
        "callable": "open_report",
    },
    {
        "id": "preview_cleanup_generated_props",
        "label": "预览清理候选",
        "description": "列出 /Game/Props 下 Asset Forge 生成的历史测试目录，不执行删除。",
        "callable": "preview_generated_props_cleanup",
    },
    {
        "id": "cleanup_generated_props",
        "label": "清理历史导入",
        "description": "清理 /Game/Props 下 Asset Forge 生成的历史测试目录，保留 Materials、Textures 和当前规范资产。",
        "callable": "cleanup_generated_props",
    },
    {
        "id": "import_package",
        "label": "正式导入",
        "description": "导入当前门禁通过的 Asset Forge 包体。",
        "callable": "import_selected_package",
    },
    {
        "id": "dry_run_all",
        "label": "批量预检",
        "description": "预检导出目录下的所有 manifest。",
        "callable": "dry_run_all_exports",
    },
    {
        "id": "import_all",
        "label": "批量导入",
        "description": "导入导出目录下的所有 manifest。",
        "callable": "import_all_exports",
    },
)


class UnrealEditorWidgetActions(object):
    """Small facade that a future Editor Utility Widget can call directly."""

    def __init__(self, pipeline_module=None, package_gate_preview=None, package_import=None, report_opener=None):
        self.pipeline = pipeline_module or unreal_pipeline
        self.package_gate_preview = package_gate_preview or preview_package_gate
        self.package_import = package_import
        self.report_opener = report_opener

    def action_plan(self):
        return [dict(item) for item in ACTION_PLAN]

    def refresh_package_history(self, export_root="", latest_maya_log_path=None, latest_unreal_log_path=None, limit=20, latest_blender_log_path=None):
        return discover_package_history(export_root, latest_maya_log_path, latest_unreal_log_path, limit, latest_blender_log_path)

    def scan_export_directory(self, export_root, limit=20):
        return discover_package_history(export_root, "", "", limit, latest_blender_log_path="")

    def ensure_widget_asset(self, unreal_module=None):
        from asset_forge.unreal.editor_widget_asset import ensure_editor_widget_asset

        return ensure_editor_widget_asset(unreal_module)

    def read_widget_tree(self, unreal_module=None):
        from asset_forge.unreal.editor_widget_asset import read_editor_widget_core_tree

        return read_editor_widget_core_tree(unreal_module)

    def build_gate_panel_state(self, package_dir="", export_root="", latest_maya_log_path=None, latest_unreal_log_path=None, report_path=None):
        return build_gate_panel_state(package_dir, export_root, latest_maya_log_path, latest_unreal_log_path, report_path)

    def preview_selected_package_gate(self, package_dir, report_path=None):
        return self.package_gate_preview(package_dir, report_path)

    def open_report(self, report_path):
        report_path = _normalize_path(report_path)
        if not report_path or not os.path.isfile(report_path):
            return {
                "status": "missing",
                "can_open": False,
                "report_path": report_path,
                "message": "报告文件不存在，请先生成入审报告或预演导入计划。",
            }
        opener = self.report_opener or _open_report_path
        opener(report_path)
        return {
            "status": "opened",
            "can_open": True,
            "report_path": report_path,
            "message": "已打开报告。",
        }

    def dry_run_selected_manifest(self, manifest_path, log_path=None):
        return self.pipeline.dry_run_manifest(manifest_path, log_path)

    def import_selected_manifest(self, manifest_path, log_path=None):
        return self.pipeline.import_manifest(manifest_path, log_path)

    def dry_run_selected_package(self, package_dir, report_path=None):
        return self.pipeline.import_asset_forge_package(package_dir, dry_run=True, report_path=report_path)

    def import_selected_package(self, package_dir, report_path=None):
        if self.package_import is not None:
            return self.package_import(package_dir, report_path=report_path)

        from asset_forge.unreal.editor_menu import import_approved_package_dir

        return import_approved_package_dir(package_dir, report_path=report_path)

    def cleanup_generated_props(self, package_dir="", target_path="/Game/Props"):
        from asset_forge.unreal.editor_menu import cleanup_asset_forge_generated_props

        return cleanup_asset_forge_generated_props(package_dir, import_options={"cleanup_target_path": target_path})

    def preview_generated_props_cleanup(self, package_dir="", target_path="/Game/Props"):
        from asset_forge.unreal.editor_menu import preview_generated_props_cleanup

        return preview_generated_props_cleanup(package_dir, import_options={"cleanup_target_path": target_path})

    def import_latest_export(self, export_root, log_path=None, dry_run=False):
        if not dry_run:
            return {
                "status": "blocked",
                "can_import": False,
                "message": "UE Gate 不允许静默导入最新包；请先选择包体、生成入审报告、预演导入计划，再正式导入。",
                "next_action": "使用 scan_export_directory -> preview_selected_package_gate -> dry_run_selected_package -> import_selected_package。",
            }
        return self.pipeline.import_latest_manifest(export_root, log_path, True)

    def dry_run_all_exports(self, export_root, report_path=None):
        return self.pipeline.import_all_manifests(export_root, report_path, dry_run=True)

    def import_all_exports(self, export_root, report_path=None):
        return self.pipeline.import_all_manifests(export_root, report_path, dry_run=False)


def get_action_plan():
    return UnrealEditorWidgetActions().action_plan()


def refresh_package_history(export_root="", latest_maya_log_path=None, latest_unreal_log_path=None, limit=20, latest_blender_log_path=None):
    return UnrealEditorWidgetActions().refresh_package_history(export_root, latest_maya_log_path, latest_unreal_log_path, limit, latest_blender_log_path)


def scan_export_directory(export_root, limit=20):
    return UnrealEditorWidgetActions().scan_export_directory(export_root, limit)


def ensure_widget_asset(unreal_module=None):
    return UnrealEditorWidgetActions().ensure_widget_asset(unreal_module)


def read_widget_tree(unreal_module=None):
    return UnrealEditorWidgetActions().read_widget_tree(unreal_module)


def build_editor_widget_gate_panel_state(package_dir="", export_root="", latest_maya_log_path=None, latest_unreal_log_path=None, report_path=None):
    return UnrealEditorWidgetActions().build_gate_panel_state(package_dir, export_root, latest_maya_log_path, latest_unreal_log_path, report_path)


def preview_selected_package_gate(package_dir, report_path=None):
    return UnrealEditorWidgetActions().preview_selected_package_gate(package_dir, report_path)


def open_report(report_path):
    return UnrealEditorWidgetActions().open_report(report_path)


def dry_run_selected_manifest(manifest_path, log_path=None):
    return UnrealEditorWidgetActions().dry_run_selected_manifest(manifest_path, log_path)


def import_selected_manifest(manifest_path, log_path=None):
    return UnrealEditorWidgetActions().import_selected_manifest(manifest_path, log_path)


def dry_run_selected_package(package_dir, report_path=None):
    return UnrealEditorWidgetActions().dry_run_selected_package(package_dir, report_path)


def import_selected_package(package_dir, report_path=None):
    return UnrealEditorWidgetActions().import_selected_package(package_dir, report_path)


def cleanup_generated_props(package_dir="", target_path="/Game/Props"):
    return UnrealEditorWidgetActions().cleanup_generated_props(package_dir, target_path)


def preview_generated_props_cleanup(package_dir="", target_path="/Game/Props"):
    return UnrealEditorWidgetActions().preview_generated_props_cleanup(package_dir, target_path)


def import_latest_export(export_root, log_path=None, dry_run=False):
    return UnrealEditorWidgetActions().import_latest_export(export_root, log_path, dry_run)


def dry_run_all_exports(export_root, report_path=None):
    return UnrealEditorWidgetActions().dry_run_all_exports(export_root, report_path)


def import_all_exports(export_root, report_path=None):
    return UnrealEditorWidgetActions().import_all_exports(export_root, report_path)


def _normalize_path(path):
    return (str(path or "")).replace("\\", "/")


def _open_report_path(report_path):
    if hasattr(os, "startfile"):
        os.startfile(report_path)
        return
    raise RuntimeError("current platform does not expose os.startfile for report opening")
