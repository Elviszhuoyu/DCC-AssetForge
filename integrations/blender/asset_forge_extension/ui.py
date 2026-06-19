# -*- coding: utf-8 -*-
"""Blender UI workbench for Asset Forge static prop publishing."""

from __future__ import absolute_import

import json
import os
import time
import traceback

import bpy  # type: ignore

from asset_forge.blender.provider_asset_forge import BlenderAssetForgeProvider
from . import bridge


DEFAULT_TARGET_PATH = "/Game/Props/Blender"
DEFAULT_MATERIAL_PROFILE = "Props_Opaque_PainterUE_ARM"


class ASSETFORGE_PG_settings(bpy.types.PropertyGroup):
    export_root: bpy.props.StringProperty(  # type: ignore
        name="导出根目录",
        subtype="DIR_PATH",
        default="",
    )
    target_path: bpy.props.StringProperty(  # type: ignore
        name="UE 目标路径",
        default=DEFAULT_TARGET_PATH,
    )
    material_profile: bpy.props.StringProperty(  # type: ignore
        name="材质规则",
        default=DEFAULT_MATERIAL_PROFILE,
    )
    last_status: bpy.props.StringProperty(  # type: ignore
        name="状态",
        default="等待选择资产根节点",
    )
    last_asset_name: bpy.props.StringProperty(  # type: ignore
        name="资产",
        default="",
    )
    last_summary: bpy.props.StringProperty(  # type: ignore
        name="概览",
        default="未扫描",
    )
    last_report_path: bpy.props.StringProperty(  # type: ignore
        name="报告",
        default="",
    )


class ASSETFORGE_OT_refresh_status(bpy.types.Operator):
    bl_idname = "asset_forge.refresh_status"
    bl_label = "刷新状态"
    bl_description = "刷新 Asset Forge bridge、当前选择和根节点状态"

    def execute(self, context):
        settings = context.scene.asset_forge_settings
        settings.last_status = _bridge_line() + " | " + _root_line(context)
        return {"FINISHED"}


class ASSETFORGE_OT_start_bridge(bpy.types.Operator):
    bl_idname = "asset_forge.start_bridge"
    bl_label = "启动 Bridge"
    bl_description = "启动或复用本机 Asset Forge Blender MCP bridge"

    def execute(self, context):
        settings = context.scene.asset_forge_settings
        payload = bridge.start_bridge(repo_root=_repo_root(), log_path=_default_log_path())
        settings.last_status = "Bridge 已运行 {0}:{1}".format(payload.get("host", "127.0.0.1"), payload.get("port", ""))
        return {"FINISHED"}


class ASSETFORGE_OT_stop_bridge(bpy.types.Operator):
    bl_idname = "asset_forge.stop_bridge"
    bl_label = "停止 Bridge"
    bl_description = "停止当前 Blender 进程内的 Asset Forge MCP bridge"

    def execute(self, context):
        bridge.stop_bridge()
        context.scene.asset_forge_settings.last_status = "Bridge 已停止"
        return {"FINISHED"}


class ASSETFORGE_OT_scan_selection(bpy.types.Operator):
    bl_idname = "asset_forge.scan_selection"
    bl_label = "1 扫描资产"
    bl_description = "扫描当前选择；若只激活了子物体，会自动提升到最上层父组"

    def execute(self, context):
        return _run_provider_action(context, "scan")


class ASSETFORGE_OT_preflight_selection(bpy.types.Operator):
    bl_idname = "asset_forge.preflight_selection"
    bl_label = "2 风险检查"
    bl_description = "按 Asset Forge 共享规则检查当前 Blender 静态资产"

    def execute(self, context):
        return _run_provider_action(context, "preflight")


class ASSETFORGE_OT_export_package(bpy.types.Operator):
    bl_idname = "asset_forge.export_package"
    bl_label = "3 导出给 UE Gate"
    bl_description = "导出 FBX、材质占位贴图和 Asset Forge manifest，供 UE Gate 接收"

    def execute(self, context):
        return _run_provider_action(context, "export")


class ASSETFORGE_OT_open_last_report(bpy.types.Operator):
    bl_idname = "asset_forge.open_last_report"
    bl_label = "打开报告"
    bl_description = "在系统文件管理器里打开最近一次 Asset Forge 报告"

    def execute(self, context):
        path = context.scene.asset_forge_settings.last_report_path
        if not path or not os.path.exists(path):
            self.report({"WARNING"}, "没有可打开的报告")
            return {"CANCELLED"}
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            self.report({"INFO"}, path)
        return {"FINISHED"}


class ASSETFORGE_PT_main_panel(bpy.types.Panel):
    bl_idname = "ASSETFORGE_PT_main_panel"
    bl_label = "Asset Forge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Asset Forge"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.asset_forge_settings

        header = layout.box()
        row = header.row(align=True)
        row.label(text="发布工作台", icon="PLUGIN")
        row.operator("asset_forge.refresh_status", text="", icon="FILE_REFRESH")
        header.label(text=_bridge_line(), icon=_bridge_icon())
        header.label(text=_root_line(context), icon="OUTLINER_COLLECTION")

        setup = layout.box()
        setup.label(text="发布目标", icon="EXPORT")
        setup.prop(settings, "target_path")
        setup.prop(settings, "material_profile")
        setup.prop(settings, "export_root")

        actions = layout.box()
        actions.label(text="操作流", icon="CHECKMARK")
        row = actions.row(align=True)
        row.operator("asset_forge.scan_selection", text="扫描", icon="VIEWZOOM")
        row.operator("asset_forge.preflight_selection", text="检查", icon="CHECKMARK")
        actions.operator("asset_forge.export_package", text="导出 Package 给 UE Gate", icon="EXPORT")

        status = layout.box()
        status.label(text="状态", icon=_status_icon(settings.last_status))
        status.label(text=_clip(settings.last_status or "等待操作", 70))
        status.label(text=_clip(settings.last_summary or "未扫描", 70))
        if settings.last_asset_name:
            status.label(text="资产: {0}".format(_clip(settings.last_asset_name, 56)))
        if settings.last_report_path:
            row = status.row(align=True)
            row.label(text=_clip(os.path.basename(settings.last_report_path), 42), icon="TEXT")
            row.operator("asset_forge.open_last_report", text="", icon="FILEBROWSER")

        bridge_box = layout.box()
        bridge_box.label(text="MCP Bridge", icon="NETWORK_DRIVE")
        row = bridge_box.row(align=True)
        row.operator("asset_forge.start_bridge", text="启动", icon="PLAY")
        row.operator("asset_forge.stop_bridge", text="停止", icon="PAUSE")


CLASSES = (
    ASSETFORGE_PG_settings,
    ASSETFORGE_OT_refresh_status,
    ASSETFORGE_OT_start_bridge,
    ASSETFORGE_OT_stop_bridge,
    ASSETFORGE_OT_scan_selection,
    ASSETFORGE_OT_preflight_selection,
    ASSETFORGE_OT_export_package,
    ASSETFORGE_OT_open_last_report,
    ASSETFORGE_PT_main_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.asset_forge_settings = bpy.props.PointerProperty(type=ASSETFORGE_PG_settings)


def unregister():
    if hasattr(bpy.types.Scene, "asset_forge_settings"):
        del bpy.types.Scene.asset_forge_settings
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass


def _run_provider_action(context, action):
    settings = context.scene.asset_forge_settings
    try:
        params = _params(context)
        if not params.get("selection"):
            raise RuntimeError("没有可发布根节点：请选择资产根组，或激活任意子物体后重试。")
        provider = BlenderAssetForgeProvider(bpy_module=bpy)
        if action == "scan":
            result = provider.scan_static_prop(params)
        elif action == "preflight":
            result = provider.preflight_static_prop(params)
        elif action == "export":
            if not params.get("export_root"):
                params["export_root"] = _default_export_root()
                settings.export_root = params["export_root"]
            result = provider.export_static_prop_package(params)
        else:
            raise RuntimeError("Unknown Asset Forge action: {0}".format(action))
        report_path = _write_ui_report(action, result)
        _apply_result_to_settings(settings, action, result, report_path)
        return {"FINISHED"}
    except Exception as exc:
        settings.last_status = "错误: {0}".format(exc)
        settings.last_summary = "操作未完成，已写入调试报告"
        settings.last_report_path = _write_ui_report(action, {"status": "error", "message": str(exc), "traceback": traceback.format_exc()})
        return {"CANCELLED"}


def _params(context):
    settings = context.scene.asset_forge_settings
    roots = _effective_root_names(context)
    return {
        "selection": roots,
        "target_path": settings.target_path or DEFAULT_TARGET_PATH,
        "material_profile": settings.material_profile or DEFAULT_MATERIAL_PROFILE,
        "export_root": bpy.path.abspath(settings.export_root) if settings.export_root else "",
    }


def _effective_root_names(context):
    objects = list(getattr(context, "selected_objects", []) or [])
    if not objects:
        active = getattr(context, "active_object", None)
        if active is not None:
            objects = [active]
    roots = []
    seen = set()
    for obj in objects:
        root = _top_parent(obj)
        name = getattr(root, "name", "")
        if name and name not in seen:
            roots.append(name)
            seen.add(name)
    return roots


def _top_parent(obj):
    current = obj
    visited = set()
    while getattr(current, "parent", None) is not None and id(current) not in visited:
        visited.add(id(current))
        current = current.parent
    return current


def _apply_result_to_settings(settings, action, result, report_path):
    scan = result.get("scan", {}) if isinstance(result, dict) else {}
    validation = result.get("validation", {}) if isinstance(result, dict) else {}
    summary = validation.get("summary", {}) if isinstance(validation, dict) else {}
    asset_name = scan.get("asset_name") or result.get("asset_name") or ""
    settings.last_asset_name = asset_name
    settings.last_report_path = report_path
    if action == "scan":
        settings.last_status = "扫描完成"
        settings.last_summary = "{0} | Mesh {1} | 材质槽 {2}".format(asset_name or "未命名", scan.get("mesh_count", 0), scan.get("material_slots", 0))
    elif action == "preflight":
        settings.last_status = "风险检查 {0}".format(result.get("status", ""))
        settings.last_summary = "可导出 {0} | 警告 {1} | 阻断 {2}".format(result.get("can_export", False), summary.get("warnings", 0), summary.get("errors", 0))
    else:
        settings.last_status = "导出 {0} | FBX {1}".format(result.get("status", ""), result.get("fbx_export_status", ""))
        settings.last_summary = "Package: {0}".format(_clip(result.get("package_dir", ""), 80))


def _bridge_line():
    active_bridge = bridge.current_bridge()
    if not active_bridge:
        return "Bridge 未运行"
    return "Bridge 运行中 127.0.0.1:{0}".format(active_bridge.port)


def _bridge_icon():
    return "LINKED" if bridge.current_bridge() else "UNLINKED"


def _root_line(context):
    roots = _effective_root_names(context)
    if roots:
        return "发布根节点: {0}".format(", ".join(roots[:4]))
    return "发布根节点: 未选择"


def _status_icon(text):
    text = text or ""
    if "错误" in text or "失败" in text:
        return "ERROR"
    if "完成" in text or "导出" in text:
        return "CHECKMARK"
    return "INFO"


def _clip(text, limit):
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _write_ui_report(action, payload):
    root = _repo_root()
    report_dir = os.path.join(root, "AssetForgeReports", "blender_ui")
    if not os.path.isdir(report_dir):
        os.makedirs(report_dir)
    path = os.path.join(report_dir, "{0}_{1}.json".format(action, time.strftime("%Y%m%d_%H%M%S")))
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return path


def _repo_root():
    return os.environ.get("ASSET_FORGE_REPO_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _default_export_root():
    return os.path.join(_repo_root(), "AssetForgeReports", "blender_ui_exports")


def _default_log_path():
    return os.path.join(_repo_root(), "AssetForgeReports", "logs", "latest_blender.log")