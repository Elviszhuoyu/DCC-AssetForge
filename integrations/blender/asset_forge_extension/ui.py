# -*- coding: utf-8 -*-
"""Blender Asset Forge workbench UI."""

from __future__ import absolute_import

import importlib
import json
import os
import struct
import sys
import time
import traceback
import zlib

import bpy  # type: ignore

from asset_forge.blender.provider_asset_forge import BlenderAssetForgeProvider
from asset_forge.maya.project_settings import format_project_settings_summary
from asset_forge.maya.project_settings import load_project_settings, normalize_project_settings, save_project_settings
from asset_forge.shared.constants import TARGET_PLATFORM_HIGH_END_MOBILE, TARGET_PLATFORM_MOBILE, TARGET_PLATFORM_PC


DEFAULT_TARGET_PATH = "/Game/Props"
DEFAULT_MATERIAL_PROFILE = "Props_Opaque_PainterUE_ARM"
MIN_BRIDGE_VERSION = "0.2.0"
_PREVIEWS = None
_STATUS_ICON_COLORS = {
    "ok": (36, 190, 132, 255),
    "warning": (236, 180, 54, 255),
    "blocked": (232, 92, 92, 255),
    "error": (232, 72, 72, 255),
    "info": (72, 155, 240, 255),
    "waiting": (150, 158, 168, 255),
}


class ASSETFORGE_PG_settings(bpy.types.PropertyGroup):
    target_platform: bpy.props.EnumProperty(name="目标平台", items=[(TARGET_PLATFORM_PC, "pc", "PC"), (TARGET_PLATFORM_HIGH_END_MOBILE, "high_end_mobile", "高端移动"), (TARGET_PLATFORM_MOBILE, "mobile", "移动")], default=TARGET_PLATFORM_PC)  # type: ignore
    export_root: bpy.props.StringProperty(name="导出根目录", subtype="DIR_PATH", default="")  # type: ignore
    target_path: bpy.props.StringProperty(name="UE 目标路径", default=DEFAULT_TARGET_PATH)  # type: ignore
    material_profile: bpy.props.StringProperty(name="材质匹配规则", default=DEFAULT_MATERIAL_PROFILE)  # type: ignore
    asset_name_override: bpy.props.StringProperty(name="包体/文件夹名", default="")  # type: ignore
    package_version_mode: bpy.props.EnumProperty(name="包体迭代模式", items=[("overwrite", "覆盖当前版本", "重复导出写入同名 Package"), ("auto_increment", "自动递增版本", "导出为 SM_Name_Blender_v001 这类版本包")], default="overwrite")  # type: ignore
    project_preset_path: bpy.props.StringProperty(name="项目预设文件", subtype="FILE_PATH", default="")  # type: ignore
    project_preset_status: bpy.props.StringProperty(name="项目预设", default=format_project_settings_summary(normalize_project_settings({}), max_rows=8))  # type: ignore
    mesh_prefix: bpy.props.StringProperty(name="模型前缀", default="SM_")  # type: ignore
    triangle_budget: bpy.props.IntProperty(name="三角面预算", default=50000, min=0)  # type: ignore
    texture_root: bpy.props.StringProperty(name="贴图目录", subtype="DIR_PATH", default="")  # type: ignore
    texture_set_token: bpy.props.StringProperty(name="贴图集关键词", default="")  # type: ignore
    texture_prefix: bpy.props.StringProperty(name="贴图前缀", default="T_")  # type: ignore
    nanite_policy: bpy.props.EnumProperty(name="Nanite 策略建议", items=[("project_default", "project_default", "项目默认"), ("enable", "enable", "启用"), ("disable", "disable", "禁用"), ("report_only", "report_only", "只写报告")], default="project_default")  # type: ignore
    static_mesh_lod_group: bpy.props.StringProperty(name="Mesh LODGroup 建议", default="project_default")  # type: ignore
    static_mesh_lod_import_policy: bpy.props.EnumProperty(name="Mesh LOD 导入策略", items=[("import_existing", "import_existing", "导入已有 LOD"), ("project_default", "project_default", "项目默认"), ("ignore_lods", "ignore_lods", "忽略 LOD"), ("report_only", "report_only", "只写报告")], default="import_existing")  # type: ignore
    virtual_texture_policy: bpy.props.EnumProperty(name="Virtual Texture 策略", items=[("project_default", "project_default", "项目默认"), ("auto", "auto", "自动"), ("force_on", "force_on", "强制开启"), ("force_off", "force_off", "强制关闭")], default="project_default")  # type: ignore
    texture_streaming_policy: bpy.props.EnumProperty(name="Texture Streaming 策略", items=[("project_default", "project_default", "项目默认"), ("streaming", "streaming", "Streaming"), ("never_stream", "never_stream", "Never Stream")], default="project_default")  # type: ignore
    texture_group: bpy.props.StringProperty(name="Texture Group 建议", default="project_default")  # type: ignore
    last_status: bpy.props.StringProperty(name="状态", default="未扫描 | 等待选择资产")  # type: ignore
    next_action: bpy.props.StringProperty(name="下一步", default="下一步 | 选中资产根节点 -> 检查并导出 Package")  # type: ignore
    last_asset_name: bpy.props.StringProperty(name="资产", default="未扫描")  # type: ignore
    last_texture_status: bpy.props.StringProperty(name="贴图", default="未扫描")  # type: ignore
    last_issue_status: bpy.props.StringProperty(name="风险", default="未检查")  # type: ignore
    last_export_status: bpy.props.StringProperty(name="发布", default="等待扫描")  # type: ignore
    asset_detail: bpy.props.StringProperty(name="资产详情", default="当前资产根节点：未扫描\n当前导出资产名：未扫描\n来源：未扫描")  # type: ignore
    texture_detail: bpy.props.StringProperty(name="贴图详情", default="贴图匹配：未扫描\n贴图集关键词可留空：系统会按材质名和贴图目录自动推断；多套无法唯一判断时会在检查阶段阻断。")  # type: ignore
    preflight_detail: bpy.props.StringProperty(name="检查详情", default="检查：未执行")  # type: ignore
    result_detail: bpy.props.StringProperty(name="结果", default="等待操作")  # type: ignore
    last_report_path: bpy.props.StringProperty(name="报告", default="")  # type: ignore


class ASSETFORGE_OT_refresh_status(bpy.types.Operator):
    bl_idname = "asset_forge.refresh_status"
    bl_label = "刷新状态"
    bl_description = "刷新 Bridge、选择和工作台状态"

    def execute(self, context):
        settings = context.scene.asset_forge_settings
        settings.last_status = _summary_state_line(settings)
        settings.next_action = _next_action_for_selection(context)
        return {"FINISHED"}


class ASSETFORGE_OT_start_bridge(bpy.types.Operator):
    bl_idname = "asset_forge.start_bridge"
    bl_label = "启动 MCP"
    bl_description = "启动独立 Blender MCP Bridge"

    def execute(self, context):
        settings = context.scene.asset_forge_settings
        module, source = _bridge_module(try_enable=True)
        if module is None:
            settings.last_status = "MCP：独立 Blender MCP Bridge 未安装或未启用"
            return {"CANCELLED"}
        payload = module.start_bridge(repo_root=_repo_root(), log_path=_default_log_path())
        settings.last_status = "MCP：{0} 运行中 {1}:{2}".format(source, payload.get("host", "127.0.0.1"), payload.get("port", ""))
        settings.next_action = "下一步 | 选中资产根节点 -> 扫描资产"
        return {"FINISHED"}


class ASSETFORGE_OT_stop_bridge(bpy.types.Operator):
    bl_idname = "asset_forge.stop_bridge"
    bl_label = "停止 MCP"
    bl_description = "停止当前 Blender MCP Bridge"

    def execute(self, context):
        module, source = _bridge_module()
        if module is not None:
            module.stop_bridge()
            context.scene.asset_forge_settings.last_status = "MCP：{0} 已停止".format(source)
        return {"FINISHED"}


class ASSETFORGE_OT_restart_bridge(bpy.types.Operator):
    bl_idname = "asset_forge.restart_bridge"
    bl_label = "重启 MCP"
    bl_description = "安全停止当前 MCP Bridge，重新加载独立 bridge 模块后启动；不保存 .blend 或用户偏好"

    def execute(self, context):
        settings = context.scene.asset_forge_settings
        module, source = _bridge_module()
        if module is None:
            settings.last_status = "MCP：独立 Blender MCP Bridge 未安装或未启用"
            return {"CANCELLED"}
        try:
            stop = getattr(module, "stop_bridge", None)
            if callable(stop):
                stop()
            if source == "independent":
                module = importlib.reload(module)
            payload = module.start_bridge(repo_root=_repo_root(), log_path=_default_log_path())
        except Exception as exc:
            settings.last_status = "MCP：重启失败 {0}".format(exc)
            settings.next_action = "下一步 | 查看 Blender MCP 日志后重试。"
            return {"CANCELLED"}
        settings.last_status = "MCP：{0} 已重启 {1}:{2}".format(source, payload.get("host", "127.0.0.1"), payload.get("port", ""))
        settings.next_action = "下一步 | 重新扫描资产，确认贴图目录和风险状态。"
        return {"FINISHED"}


class ASSETFORGE_OT_scan_selection(bpy.types.Operator):
    bl_idname = "asset_forge.scan_selection"
    bl_label = "只扫描"
    bl_description = "扫描当前选择；若只激活子物体，会自动提升到最上层父组"

    def execute(self, context):
        return _run_provider_action(context, "scan")


class ASSETFORGE_OT_preflight_selection(bpy.types.Operator):
    bl_idname = "asset_forge.preflight_selection"
    bl_label = "只检查"
    bl_description = "运行 Static Prop 共享规则检查"

    def execute(self, context):
        return _run_provider_action(context, "preflight")


class ASSETFORGE_OT_export_package(bpy.types.Operator):
    bl_idname = "asset_forge.export_package"
    bl_label = "检查并导出 Package"
    bl_description = "先检查当前资产，再导出 FBX、材质/贴图占位与 manifest，交给 UE Gate 接收"

    def execute(self, context):
        return _run_provider_action(context, "export")


class ASSETFORGE_OT_apply_transform_fix(bpy.types.Operator):
    bl_idname = "asset_forge.apply_transform_fix"
    bl_label = "应用 Transform"
    bl_description = "应用当前资产 Mesh 的位移、旋转和缩放；支持 Blender Undo，不保存 .blend"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.asset_forge_settings
        targets = _transform_fix_mesh_objects(context)
        if not targets:
            self.report({"WARNING"}, "没有可应用 Transform 的 Mesh 对象")
            return {"CANCELLED"}
        original_selection = list(getattr(context, "selected_objects", []) or [])
        original_active = getattr(context, "active_object", None)
        try:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in targets:
                obj.select_set(True)
            context.view_layer.objects.active = targets[0]
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True, properties=True)
        except Exception as exc:
            settings.result_detail = "Transform 修复失败：{0}".format(exc)
            return {"CANCELLED"}
        finally:
            try:
                bpy.ops.object.select_all(action="DESELECT")
                for obj in original_selection:
                    obj.select_set(True)
                if original_active is not None:
                    context.view_layer.objects.active = original_active
            except Exception:
                pass
        settings.last_status = "已修复 | Transform"
        settings.last_issue_status = "风险 | 待复检"
        settings.preflight_detail = "已应用 Transform。\n下一步：点击“只检查”重新检查。"
        settings.result_detail = "已应用 Transform: {0}".format(", ".join([obj.name for obj in targets]))
        return {"FINISHED"}


class ASSETFORGE_OT_load_project_preset(bpy.types.Operator):
    bl_idname = "asset_forge.load_project_preset"
    bl_label = "加载预设"
    bl_description = "加载团队通用 Asset Forge 项目预设 JSON"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})  # type: ignore

    def execute(self, context):
        settings = load_project_settings(self.filepath)
        _apply_project_settings_to_blender(context.scene.asset_forge_settings, settings)
        context.scene.asset_forge_settings.project_preset_path = self.filepath
        context.scene.asset_forge_settings.project_preset_status = format_project_settings_summary(settings, max_rows=10)
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class ASSETFORGE_OT_save_project_preset(bpy.types.Operator):
    bl_idname = "asset_forge.save_project_preset"
    bl_label = "保存预设"
    bl_description = "保存当前 Blender 工作台参数为团队通用项目预设 JSON"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})  # type: ignore

    def execute(self, context):
        settings = _project_settings_from_blender(context.scene.asset_forge_settings)
        path = save_project_settings(self.filepath, settings)
        saved = load_project_settings(path)
        context.scene.asset_forge_settings.project_preset_path = path
        context.scene.asset_forge_settings.project_preset_status = format_project_settings_summary(saved, max_rows=10)
        return {"FINISHED"}

    def invoke(self, context, event):
        current = context.scene.asset_forge_settings.project_preset_path
        self.filepath = current or os.path.join(_default_export_root(), "asset_forge_project_preset.json")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class ASSETFORGE_OT_apply_project_preset(bpy.types.Operator):
    bl_idname = "asset_forge.apply_project_preset"
    bl_label = "应用当前预设"
    bl_description = "把当前 Blender 工作台参数归一化为当前项目预设；不读取或写入文件"

    def execute(self, context):
        settings = _project_settings_from_blender(context.scene.asset_forge_settings)
        _apply_project_settings_to_blender(context.scene.asset_forge_settings, settings)
        context.scene.asset_forge_settings.project_preset_status = format_project_settings_summary(settings, max_rows=10)
        context.scene.asset_forge_settings.next_action = "下一步 | 当前 UI 参数已应用为项目预设，可扫描资产。"
        return {"FINISHED"}


class ASSETFORGE_OT_open_last_report(bpy.types.Operator):
    bl_idname = "asset_forge.open_last_report"
    bl_label = "打开报告"
    bl_description = "打开最近一次 Asset Forge 报告"

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
        box = layout.box()
        row = box.row(align=True)
        title = row.row(align=True)
        icon_value = _logo_icon_value()
        if icon_value:
            title.label(text="Asset Forge Blender 发布工作台", icon_value=icon_value)
        else:
            title.label(text="Asset Forge Blender 发布工作台", icon="PLUGIN")
        active = _current_bridge()
        row.label(text="MCP: {0} 运行中".format(active.port) if active else "MCP: 未运行", icon="CHECKMARK" if active else "TIME")
        row.operator("asset_forge.refresh_status", text="", icon="FILE_REFRESH")
        _status_line(box, _bridge_line(), _bridge_state())
        _status_line(box, _root_line(context), "info")
        _status_line(box, settings.next_action, "info")


class ASSETFORGE_PT_project_preset_panel(bpy.types.Panel):
    bl_idname = "ASSETFORGE_PT_project_preset_panel"
    bl_label = "项目预设"
    bl_parent_id = "ASSETFORGE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        s = context.scene.asset_forge_settings
        layout = self.layout
        row = layout.row(align=True)
        row.operator("asset_forge.load_project_preset", text="加载预设", icon="FILE_FOLDER")
        row.operator("asset_forge.save_project_preset", text="保存预设", icon="FILE_TICK")
        layout.operator("asset_forge.apply_project_preset", text="应用当前预设", icon="CHECKMARK")
        if s.project_preset_path:
            layout.label(text=os.path.basename(s.project_preset_path), icon="TEXT")
        _draw_text_block(layout, s.project_preset_status)


class ASSETFORGE_PT_status_panel(bpy.types.Panel):
    bl_idname = "ASSETFORGE_PT_status_panel"
    bl_label = "发布状态"
    bl_parent_id = "ASSETFORGE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        s = context.scene.asset_forge_settings
        layout = self.layout
        row = layout.row(align=True)
        _status_card(row, s.last_asset_name, _asset_state(s))
        _status_card(row, s.last_texture_status, _texture_state(s))
        row = layout.row(align=True)
        _status_card(row, s.last_issue_status, _issue_state(s))
        _status_card(row, s.last_export_status, _export_state(s))


class ASSETFORGE_PT_actions_panel(bpy.types.Panel):
    bl_idname = "ASSETFORGE_PT_actions_panel"
    bl_label = "导出控制"
    bl_parent_id = "ASSETFORGE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        layout.operator("asset_forge.export_package", text="检查并导出 Package", icon="EXPORT")
        row = layout.row(align=True)
        row.operator("asset_forge.scan_selection", text="只扫描", icon="VIEWZOOM")
        row.operator("asset_forge.preflight_selection", text="只检查", icon="CHECKMARK")
        _draw_mcp_action_controls(layout)


class ASSETFORGE_PT_target_panel(bpy.types.Panel):
    bl_idname = "ASSETFORGE_PT_target_panel"
    bl_label = "1 发布目标"
    bl_parent_id = "ASSETFORGE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        s = context.scene.asset_forge_settings
        layout = self.layout
        layout.prop(s, "target_platform")
        layout.prop(s, "material_profile")
        layout.prop(s, "target_path")
        layout.prop(s, "export_root")


class ASSETFORGE_PT_asset_panel(bpy.types.Panel):
    bl_idname = "ASSETFORGE_PT_asset_panel"
    bl_label = "2 资产概览"
    bl_parent_id = "ASSETFORGE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        s = context.scene.asset_forge_settings
        layout = self.layout
        layout.prop(s, "mesh_prefix")
        layout.prop(s, "asset_name_override")
        layout.prop(s, "package_version_mode")
        layout.prop(s, "triangle_budget")
        layout.operator("asset_forge.apply_transform_fix", text="应用 Transform", icon="EMPTY_ARROWS")
        _draw_text_block(layout, s.asset_detail)


class ASSETFORGE_PT_texture_panel(bpy.types.Panel):
    bl_idname = "ASSETFORGE_PT_texture_panel"
    bl_label = "3 贴图 / 材质匹配"
    bl_parent_id = "ASSETFORGE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.asset_forge_settings
        layout = self.layout
        layout.prop(s, "texture_root")
        layout.prop(s, "texture_set_token")
        layout.prop(s, "texture_prefix")
        _draw_text_block(layout, s.texture_detail)


class ASSETFORGE_PT_preflight_panel(bpy.types.Panel):
    bl_idname = "ASSETFORGE_PT_preflight_panel"
    bl_label = "4 检查详情"
    bl_parent_id = "ASSETFORGE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.asset_forge_settings
        _draw_preflight_block(self.layout, s.preflight_detail)


class ASSETFORGE_PT_policy_panel(bpy.types.Panel):
    bl_idname = "ASSETFORGE_PT_policy_panel"
    bl_label = "导入策略（写入 Package，UE Gate 可复核）"
    bl_parent_id = "ASSETFORGE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.asset_forge_settings
        layout = self.layout
        layout.label(text="基础导入：Blender 写 Package，UE Gate 检查通过后导入。", icon="FILE_TICK")
        layout.label(text="网格构建", icon="MESH_DATA")
        layout.prop(s, "nanite_policy")
        layout.prop(s, "static_mesh_lod_group")
        layout.prop(s, "static_mesh_lod_import_policy")
        layout.label(text="材质贴图", icon="TEXTURE")
        layout.prop(s, "virtual_texture_policy")
        layout.prop(s, "texture_streaming_policy")
        layout.prop(s, "texture_group")


class ASSETFORGE_PT_result_panel(bpy.types.Panel):
    bl_idname = "ASSETFORGE_PT_result_panel"
    bl_label = "结果 / 日志"
    bl_parent_id = "ASSETFORGE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.asset_forge_settings
        row = self.layout.row(align=True)
        row.operator("asset_forge.open_last_report", text="打开报告", icon="FILEBROWSER")
        _draw_text_block(self.layout, s.result_detail)
        if s.last_report_path:
            self.layout.label(text=os.path.basename(s.last_report_path), icon="TEXT")


CLASSES = (
    ASSETFORGE_PG_settings,
    ASSETFORGE_OT_refresh_status,
    ASSETFORGE_OT_start_bridge,
    ASSETFORGE_OT_stop_bridge,
    ASSETFORGE_OT_restart_bridge,
    ASSETFORGE_OT_scan_selection,
    ASSETFORGE_OT_preflight_selection,
    ASSETFORGE_OT_export_package,
    ASSETFORGE_OT_apply_transform_fix,
    ASSETFORGE_OT_load_project_preset,
    ASSETFORGE_OT_save_project_preset,
    ASSETFORGE_OT_apply_project_preset,
    ASSETFORGE_OT_open_last_report,
    ASSETFORGE_PT_main_panel,
    ASSETFORGE_PT_project_preset_panel,
    ASSETFORGE_PT_status_panel,
    ASSETFORGE_PT_actions_panel,
    ASSETFORGE_PT_target_panel,
    ASSETFORGE_PT_asset_panel,
    ASSETFORGE_PT_texture_panel,
    ASSETFORGE_PT_preflight_panel,
    ASSETFORGE_PT_policy_panel,
    ASSETFORGE_PT_result_panel,
)


def register():
    _refresh_asset_forge_blender_modules()
    _register_previews()
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
    _unregister_previews()


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
        settings.last_status = "失败 | {0}".format(exc)
        settings.last_issue_status = "失败 | 工具异常"
        settings.preflight_detail = "异常：{0}\n{1}".format(exc, traceback.format_exc(limit=4))
        settings.result_detail = "操作失败，已写入调试报告。"
        settings.last_report_path = _write_ui_report(action, {"status": "error", "message": str(exc), "traceback": traceback.format_exc()})
        return {"CANCELLED"}


def _refresh_asset_forge_blender_modules():
    """Refresh cached provider modules after a safe add-on reload."""
    global BlenderAssetForgeProvider
    module_names = (
        "asset_forge.shared.package_naming",
        "asset_forge.maya.export_package",
        "asset_forge.shared.texture_folder_scanner",
        "asset_forge.shared.material_texture_set_mapping",
        "asset_forge.shared.material_texture_bindings",
        "asset_forge.blender.scanner",
        "asset_forge.blender.fbx_exporter",
        "asset_forge.blender.provider_asset_forge",
    )
    for name in module_names:
        module = sys.modules.get(name)
        if module is not None:
            importlib.reload(module)
    from asset_forge.blender.provider_asset_forge import BlenderAssetForgeProvider as refreshed_provider

    BlenderAssetForgeProvider = refreshed_provider


def _params(context):
    s = context.scene.asset_forge_settings
    return {
        "selection": _effective_root_names(context),
        "target_platform": s.target_platform,
        "target_path": s.target_path or DEFAULT_TARGET_PATH,
        "material_profile": s.material_profile or DEFAULT_MATERIAL_PROFILE,
        "package_name_override": s.asset_name_override,
        "asset_name_override": "",
        "source_name_suffix": "",
        "package_version_mode": getattr(s, "package_version_mode", "overwrite"),
        "mesh_prefix": s.mesh_prefix or "SM_",
        "triangle_budget": int(s.triangle_budget or 0),
        "texture_folder": bpy.path.abspath(s.texture_root) if s.texture_root else "",
        "texture_set_token": s.texture_set_token,
        "export_root": bpy.path.abspath(s.export_root) if s.export_root else "",
        "texture_import_policy": _texture_import_policy(s),
        "static_mesh_import_policy": _static_mesh_import_policy(s),
        "project_preset": _project_settings_from_blender(s),
    }


def _project_settings_from_blender(s):
    return normalize_project_settings(
        {
            "export_root": bpy.path.abspath(getattr(s, "export_root", "")) if getattr(s, "export_root", "") else "",
            "texture_root": bpy.path.abspath(getattr(s, "texture_root", "")) if getattr(s, "texture_root", "") else "",
            "triangle_budget": int(getattr(s, "triangle_budget", 0) or 0),
            "mesh_prefix": getattr(s, "mesh_prefix", "SM_") or "SM_",
            "package_name_override": getattr(s, "asset_name_override", ""),
            "asset_name_override": "",
            "package_version_mode": getattr(s, "package_version_mode", "overwrite"),
            "texture_prefix": getattr(s, "texture_prefix", "T_") or "T_",
            "texture_set_token": getattr(s, "texture_set_token", ""),
            "ue_target_path": getattr(s, "target_path", DEFAULT_TARGET_PATH) or DEFAULT_TARGET_PATH,
            "target_platform": getattr(s, "target_platform", TARGET_PLATFORM_PC),
            "material_profile": getattr(s, "material_profile", DEFAULT_MATERIAL_PROFILE) or DEFAULT_MATERIAL_PROFILE,
            "virtual_texture_policy": getattr(s, "virtual_texture_policy", "project_default") or "project_default",
            "texture_streaming_policy": getattr(s, "texture_streaming_policy", "project_default") or "project_default",
            "texture_group": getattr(s, "texture_group", "project_default") or "project_default",
            "nanite_policy": getattr(s, "nanite_policy", "project_default") or "project_default",
            "static_mesh_lod_group": getattr(s, "static_mesh_lod_group", "project_default") or "project_default",
            "static_mesh_lod_import_policy": getattr(s, "static_mesh_lod_import_policy", "import_existing") or "import_existing",
        }
    )


def _apply_project_settings_to_blender(s, settings):
    active = normalize_project_settings(settings)
    s.export_root = active["export_root"]
    s.texture_root = active["texture_root"]
    s.triangle_budget = active["triangle_budget"]
    s.mesh_prefix = active["mesh_prefix"]
    s.asset_name_override = active["package_name_override"]
    if hasattr(s, "package_version_mode"):
        s.package_version_mode = active["package_version_mode"]
    s.texture_prefix = active["texture_prefix"]
    s.texture_set_token = active["texture_set_token"]
    s.target_path = active["ue_target_path"]
    s.target_platform = active["target_platform"]
    s.material_profile = active["material_profile"]
    s.virtual_texture_policy = active["virtual_texture_policy"]
    s.texture_streaming_policy = active["texture_streaming_policy"]
    s.texture_group = active["texture_group"]
    s.nanite_policy = active["nanite_policy"]
    s.static_mesh_lod_group = active["static_mesh_lod_group"]
    s.static_mesh_lod_import_policy = active["static_mesh_lod_import_policy"]


def _texture_import_policy(s):
    return {"virtual_texture_policy": s.virtual_texture_policy or "project_default", "texture_streaming_policy": s.texture_streaming_policy or "project_default", "texture_group": s.texture_group or "project_default"}


def _static_mesh_import_policy(s):
    return {"nanite_policy": s.nanite_policy or "project_default", "lod_group": s.static_mesh_lod_group or "project_default", "import_lod_policy": s.static_mesh_lod_import_policy or "import_existing", "build_reversed_index_buffer": "report_only", "generate_lightmap_uvs": "report_only", "collision_complexity": "report_only"}


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


def _transform_fix_mesh_objects(context):
    objects = list(getattr(context, "selected_objects", []) or [])
    active = getattr(context, "active_object", None)
    if not objects and active is not None:
        objects = [active]
    roots = []
    for obj in objects:
        root = _top_parent(obj)
        if root not in roots:
            roots.append(root)
    meshes = []
    for root in roots:
        for obj in [root] + list(getattr(root, "children_recursive", []) or []):
            if getattr(obj, "type", "") == "MESH" and obj not in meshes:
                meshes.append(obj)
    return meshes


def _top_parent(obj):
    current = obj
    visited = set()
    while getattr(current, "parent", None) is not None and id(current) not in visited:
        visited.add(id(current))
        parent = current.parent
        if _is_organization_root(parent):
            return current
        current = current.parent
    return current


def _is_organization_root(obj):
    name = str(getattr(obj, "name", "") or "").lower()
    if name in ("collection", "scene", "root"):
        return True
    if name.startswith("group") and name[5:].isdigit():
        return True
    return False


def _apply_result_to_settings(s, action, result, report_path):
    scan = result.get("scan", {}) if isinstance(result, dict) else {}
    if not scan and isinstance(result, dict):
        scan = _scan_from_manifest(result.get("manifest", {}) or {})
    validation = result.get("validation", {}) if isinstance(result, dict) else {}
    summary = validation.get("summary", {}) if isinstance(validation, dict) else {}
    checks = validation.get("checks", []) if isinstance(validation, dict) else []
    errors = int(summary.get("errors", 0) or 0)
    warnings = int(summary.get("warnings", 0) or 0)
    asset_name = scan.get("asset_name") or result.get("asset_name") or "未命名"
    s.last_report_path = report_path
    s.last_asset_name = "资产 | {0}".format(asset_name)
    s.last_texture_status = "贴图 | {0} 材质 / {1} 贴图".format(len(scan.get("materials", []) or []), _texture_count_from_scan(scan))
    s.asset_detail = _format_asset_detail(scan)
    s.texture_detail = _format_texture_detail(scan)
    if action == "scan":
        s.last_status = "已扫描 | {0}".format(asset_name)
        s.last_issue_status = "风险 | 未检查"
        s.last_export_status = "发布 | 等待检查"
        s.preflight_detail = "检查：未执行\n下一步：点击“只检查”，或直接点击“检查并导出 Package”。"
        s.result_detail = "扫描完成。\n报告：{0}".format(report_path)
        s.next_action = "下一步 | 检查 -> 修复阻断项 -> 导出 Package"
        return
    s.preflight_detail = _format_preflight_detail(validation)
    if errors:
        s.last_issue_status = "阻断 | {0} 项 / 注意 {1}".format(errors, warnings)
        s.last_export_status = "发布 | 已阻断"
        s.next_action = _next_action_from_checks(checks)
    elif warnings:
        s.last_issue_status = "注意 | {0} 项".format(warnings)
        s.last_export_status = "发布 | 可导出" if result.get("can_export") else "发布 | 待确认"
        s.next_action = "下一步 | 可导出，但建议确认注意项后再进入 UE Gate。"
    else:
        s.last_issue_status = "通过 | 0 阻断"
        s.last_export_status = "发布 | 可导出"
        s.next_action = "下一步 | 检查并导出 Package。"
    if action == "preflight":
        s.last_status = "已检查 | 可导出 {0}".format(bool(result.get("can_export")))
        s.result_detail = "检查完成。\n报告：{0}".format(report_path)
    else:
        s.last_status = "导出 {0} | FBX {1}".format(result.get("status", ""), result.get("fbx_export_status", ""))
        if result.get("status") == "success" and result.get("can_continue_to_ue"):
            s.last_export_status = "发布 | 已导出"
            s.next_action = "下一步 | 在 UE Gate 选择该 Package，点击“检查并导入”。"
        s.result_detail = _format_export_result(result, report_path)


def _scan_from_manifest(manifest):
    if not isinstance(manifest, dict) or not manifest:
        return {}
    return {
        "asset_name": manifest.get("asset_name", ""),
        "materials": manifest.get("materials", []) or [],
        "textures": manifest.get("textures", []) or [],
        "material_slot_details": manifest.get("material_slots", []) or [],
        "material_texture_sets": manifest.get("material_texture_sets", []) or [],
        "material_texture_bindings": manifest.get("material_texture_bindings", []) or [],
        "texture_folder_scan": manifest.get("texture_folder_scan", {}) or {},
        "texture_selection_policy": manifest.get("texture_selection_policy", {}) or {},
        "package_naming": manifest.get("package_naming", {}) or {},
    }


def _format_asset_detail(scan):
    if not scan:
        return "当前资产根节点：未扫描\n当前导出资产名：未扫描\n来源：未扫描"
    lines = [
        "当前资产根节点：{0}".format(", ".join(scan.get("asset_roots", []) or [])),
        "当前导出资产名：{0}".format(scan.get("asset_name", "")),
        "包体/文件夹名：{0}".format((scan.get("package_naming", {}) or {}).get("package_name") or scan.get("package_name") or "导出时解析"),
        "源名称：{0} -> 自动规范：{1}".format(scan.get("source_asset_name", ""), scan.get("asset_name", "")),
        "Mesh：{0} | 顶点：{1} | 三角面：{2} | 面：{3}".format(scan.get("mesh_count", 0), scan.get("vertices", 0), scan.get("triangles", 0), scan.get("faces", 0)),
        "材质槽：{0} | UV0：{1} | Lightmap UV：{2} | 冻结变换：{3}".format(scan.get("material_slots", 0), _yes(scan.get("has_uv0")), _yes(scan.get("has_lightmap_uv")), _yes(scan.get("frozen_transform"))),
    ]
    if scan.get("meshes"):
        lines.append("Meshes：{0}".format(", ".join(scan.get("meshes", [])[:8])))
    return "\n".join(lines)


def _format_texture_detail(scan):
    materials = scan.get("materials", []) if isinstance(scan, dict) else []
    textures = _textures_from_scan(scan) if isinstance(scan, dict) else []
    lines = ["贴图匹配：{0} 材质 / {1} 贴图".format(len(materials), len(textures))]
    folder_scan = scan.get("texture_folder_scan", {}) if isinstance(scan, dict) else {}
    if folder_scan:
        lines.extend(_texture_folder_selection_lines(folder_scan))
    if not textures:
        lines.append("未发现 Image Texture 节点；导出时会生成 BaseColor/Normal/ARM 占位贴图，UE Gate 可追踪。")
    else:
        usages = sorted(set(item.get("usage", "") for item in textures if item.get("usage")))
        lines.append("贴图来源：{0}".format(_texture_source_summary(textures)))
        lines.append("贴图用途：{0}".format(", ".join(usages)))
    for material in materials[:8]:
        material_textures = list(material.get("textures", []) or [])
        usage_text = _material_texture_usage_summary(material_textures)
        lines.append("- {0} | {1} | BaseColor {2}".format(material.get("name", ""), usage_text, _compact_color(material.get("base_color", []))))
    return "\n".join(lines)


def _texture_folder_selection_lines(folder_scan):
    token = str(folder_scan.get("texture_set_token") or folder_scan.get("texture_set_filter") or "").strip()
    auto_token = str(folder_scan.get("auto_material_texture_set_token") or "").strip()
    selected = folder_scan.get("selected_texture_sets") or []
    if token:
        return ["贴图集关键词：{0}".format(token)]
    if auto_token:
        return ["贴图集关键词：留空，已按材质名自动识别 {0}".format(auto_token)]
    if folder_scan.get("requires_texture_set_selection"):
        names = ", ".join([item.get("set_name", "") for item in folder_scan.get("texture_sets", [])[:6]])
        return ["贴图集关键词：留空但存在多套候选，需填写关键词后再导出。候选：{0}".format(names)]
    if selected:
        names = ", ".join([item.get("set_name", "") for item in selected[:4]])
        return ["贴图集关键词：留空，已自动选择 {0}".format(names)]
    return ["贴图集关键词：留空，系统会按材质名/资产名自动推断。"]


def _texture_source_summary(textures):
    labels = {
        "blender_image_node": "Blender节点",
        "texture_folder": "贴图目录",
        "blender_placeholder": "占位",
    }
    counts = {}
    for texture in textures or []:
        source = texture.get("source_type", "") or "unknown"
        counts[source] = counts.get(source, 0) + 1
    return " / ".join(
        "{0} {1}".format(labels.get(source, source or "未知"), count)
        for source, count in sorted(counts.items())
    )


def _material_texture_usage_summary(textures):
    if not textures:
        return "占位待导出"
    source_labels = {
        "blender_image_node": "节点",
        "texture_folder": "目录",
        "blender_placeholder": "占位",
    }
    parts = []
    for texture in sorted(textures or [], key=lambda item: item.get("usage", "")):
        usage = texture.get("usage", "") or "unknown"
        source = source_labels.get(texture.get("source_type", ""), "来源")
        parts.append("{0}[{1}]".format(usage, source))
    return ", ".join(parts)


def _texture_count_from_scan(scan):
    return len(_textures_from_scan(scan))


def _textures_from_scan(scan):
    textures = list(scan.get("textures", []) or []) if isinstance(scan, dict) else []
    if textures:
        return textures
    result = []
    for material in scan.get("materials", []) or []:
        result.extend(list(material.get("textures", []) or []))
    return result


def _format_preflight_detail(validation):
    if not validation:
        return "检查：未执行"
    summary = validation.get("summary", {}) or {}
    lines = ["状态：{0} | 分数：{1} | 通过/注意/阻断：{2}/{3}/{4}".format("可导出" if validation.get("can_export") else "不可导出", validation.get("score", 0), summary.get("passes", 0), summary.get("warnings", 0), summary.get("errors", 0))]
    for item in validation.get("checks", []) or []:
        lines.append("{0} {1}：{2}".format(_check_marker(item.get("status")), item.get("label") or item.get("id"), item.get("message", "")))
    return "\n".join(lines)


def _format_export_result(result, report_path):
    naming = ((result.get("manifest", {}) or {}).get("package_naming", {}) or result.get("package_naming", {}) or {})
    return "导出状态：{0}\nFBX：{1}\nPackage：{2}\n包体名：{3} | 模式：{4}\n报告：{5}\n下一步：{6}".format(
        result.get("status", ""),
        result.get("fbx_export_status", ""),
        result.get("package_dir", ""),
        naming.get("package_name", "") or "未记录",
        naming.get("version_mode", "") or "overwrite",
        report_path,
        result.get("next_action", ""),
    )


def _next_action_from_checks(checks):
    for item in checks or []:
        if item.get("status") == "error":
            if item.get("id") == "frozen_transform":
                return "下一步 | 冻结/应用根节点 Transform 后重新检查。"
            return "下一步 | 修复阻断项“{0}”后重新检查。".format(item.get("label") or item.get("id"))
    return "下一步 | 确认注意项后导出 Package。"


def _bridge_module(try_enable=False):
    try:
        import blender_mcp_bridge.bridge as module  # type: ignore
        return module, "independent"
    except Exception:
        if try_enable:
            try:
                import addon_utils  # type: ignore
                addon_utils.enable("blender_mcp_bridge", default_set=False, persistent=False)
                import blender_mcp_bridge.bridge as module  # type: ignore
                return module, "independent"
            except Exception:
                pass
    try:
        from . import bridge as module
        return module, "legacy"
    except Exception:
        return None, "missing"


def _current_bridge():
    module, _source = _bridge_module()
    if module is None:
        return None
    current = getattr(module, "current_bridge", None)
    if callable(current):
        return current()
    return getattr(module, "_BRIDGE", None)


def _bridge_line():
    active = _current_bridge()
    module, source = _bridge_module()
    if not active:
        return "MCP：未运行 | 来源 {0}".format(source)
    version = _bridge_version(module)
    version_text = " | v{0}".format(version) if version else " | 旧缓存需重启"
    if version and _version_tuple(version) < _version_tuple(MIN_BRIDGE_VERSION):
        version_text += " 需重启"
    return "MCP：{0} 运行中 127.0.0.1:{1}{2}".format(source, active.port, version_text)


def _draw_mcp_header_controls(layout):
    state = _mcp_control_state()
    active = _current_bridge()
    status = layout.row(align=True)
    if active:
        status.label(text="MCP: {0} 运行中".format(active.port), icon="CHECKMARK")
    else:
        status.label(text="MCP: 未运行", icon="TIME")
    start = layout.row(align=True)
    start.enabled = state["can_start"]
    start.operator("asset_forge.start_bridge", text=state["start_label"], icon="PLAY")
    restart = layout.row(align=True)
    restart.enabled = state["can_restart"]
    restart.operator("asset_forge.restart_bridge", text=state["restart_label"], icon="FILE_REFRESH")
    layout.operator("asset_forge.refresh_status", text="状态", icon="INFO")


def _draw_mcp_action_controls(layout):
    state = _mcp_control_state()
    bridge_row = layout.row(align=True)
    start = bridge_row.row(align=True)
    start.enabled = state["can_start"]
    start.operator("asset_forge.start_bridge", text=state["start_label"], icon="PLAY")
    restart = bridge_row.row(align=True)
    restart.enabled = state["can_restart"]
    restart.operator("asset_forge.restart_bridge", text=state["restart_label"], icon="FILE_REFRESH")
    stop = bridge_row.row(align=True)
    stop.enabled = state["can_stop"]
    stop.operator("asset_forge.stop_bridge", text="停止 MCP", icon="PAUSE")


def _mcp_control_state(active=None, module=None):
    if active is None:
        active = _current_bridge()
    if module is None:
        module, _source = _bridge_module()
    running = bool(active)
    stale = running and _bridge_module_needs_restart(module)
    return {
        "can_start": not running,
        "can_restart": running,
        "can_stop": running,
        "start_label": "启动 MCP",
        "restart_label": "重启刷新" if stale else "重启 MCP",
        "state": "stale" if stale else "running" if running else "stopped",
    }


def _bridge_state():
    if not _current_bridge():
        return "warning"
    module, _source = _bridge_module()
    if _bridge_module_needs_restart(module):
        return "warning"
    return "ok"


def _bridge_module_needs_restart(module):
    version = _bridge_version(module)
    return (not version) or _version_tuple(version) < _version_tuple(MIN_BRIDGE_VERSION)


def _bridge_version(module):
    return str(getattr(module, "BRIDGE_VERSION", "") or "")


def _version_tuple(value):
    parts = []
    for item in str(value or "").split("."):
        try:
            parts.append(int(item))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _root_line(context):
    roots = _effective_root_names(context)
    return "发布根节点：{0}".format(", ".join(roots[:4]) if roots else "未选择")


def _next_action_for_selection(context):
    return "下一步 | 点击扫描资产" if _effective_root_names(context) else "下一步 | 选中资产根节点或任意子物体"


def _summary_state_line(s):
    return "{0} | {1} | {2}".format(s.last_asset_name, s.last_issue_status, s.last_export_status)


def _asset_state(s):
    return "waiting" if "未扫描" in s.last_asset_name else "ok"


def _texture_state(s):
    detail = s.texture_detail or ""
    if "未扫描" in s.last_texture_status:
        return "waiting"
    if "需填写关键词" in detail or "多套候选" in detail:
        return "warning"
    if "0 贴图" in s.last_texture_status:
        return "warning"
    return "ok"


def _issue_state(s):
    text = s.last_issue_status or ""
    if "失败" in text:
        return "error"
    if "阻断" in text:
        return "blocked"
    if "警告" in text or "注意" in text:
        return "warning"
    if "通过" in text:
        return "ok"
    return "waiting"


def _export_state(s):
    text = s.last_export_status or ""
    if "阻断" in text:
        return "blocked"
    if "可导出" in text or "success" in text:
        return "ok"
    return "waiting"


def _status_card(row, text, state):
    item = row.row(align=True)
    item.alert = state in ("error", "blocked")
    _status_label(item, "{0} {1}".format(_status_badge(state), _clip(text, 32)), state)


def _status_line(layout, text, state):
    row = layout.row(align=True)
    row.alert = state in ("error", "blocked")
    _status_label(row, "{0} {1}".format(_status_badge(state), _clip(text, 70)), state)


def _draw_text_block(layout, text, alert=False):
    box = layout.box()
    for line in str(text or "").split("\n")[:12]:
        state = _line_state(line)
        row = box.row()
        row.alert = bool(alert) or state in ("error", "blocked")
        if state in ("ok", "warning", "blocked", "error"):
            _status_label(row, "{0} {1}".format(_status_badge(state), _clip(_strip_check_marker(line), 88)), state)
        else:
            row.label(text=_clip(line, 88))


def _draw_preflight_block(layout, text):
    box = layout.box()
    for line in str(text or "").split("\n")[:16]:
        state = _line_state(line)
        row = box.row()
        row.alert = state in ("error", "blocked")
        _status_label(row, "{0} {1}".format(_status_badge(state), _clip(_strip_check_marker(line), 88)), state)


def _status_icon(state):
    return {"ok": "CHECKMARK", "warning": "QUESTION", "blocked": "CANCEL", "error": "CANCEL", "info": "INFO", "waiting": "TIME"}.get(state, "INFO")


def _status_icon_value(state):
    if _PREVIEWS is None:
        return 0
    key = "status_{0}".format(state if state in _STATUS_ICON_COLORS else "info")
    if key not in _PREVIEWS:
        return 0
    return _PREVIEWS[key].icon_id


def _status_label(layout, text, state):
    icon_value = _status_icon_value(state)
    if icon_value:
        layout.label(text=text, icon_value=icon_value)
    else:
        layout.label(text=text, icon=_status_icon(state))


def _status_badge(state):
    return {
        "ok": "[通过]",
        "warning": "[注意]",
        "blocked": "[阻断]",
        "error": "[错误]",
        "info": "[信息]",
        "waiting": "[等待]",
    }.get(state, "[信息]")


def _check_marker(status):
    return {"pass": "[通过]", "warning": "[注意]", "error": "[阻断]", "info": "[信息]"}.get(status, "[?]")


def _line_state(line):
    text = str(line or "")
    if text.startswith("状态：可导出"):
        return "warning" if "注意/阻断：0/0" not in text and "警告/阻断：0/0" not in text else "ok"
    if text.startswith("状态：不可导出"):
        return "blocked"
    if text.startswith("[阻断]") or text.startswith("[BLOCK]") or text.startswith("[FAIL]") or "不可导出" in text or "阻断" in text or "失败" in text:
        return "blocked"
    if text.startswith("[注意]") or text.startswith("[WARN]") or "警告" in text or "注意" in text:
        return "warning"
    if text.startswith("[通过]") or text.startswith("[PASS]") or "：通过" in text or " 通过" in text:
        return "ok"
    if "success" in text or "已导出" in text or "完成" in text or "可导出" in text:
        return "ok"
    if "0 贴图" in text or "需填写" in text or "多套候选" in text or "未发现 Image Texture" in text:
        return "warning"
    if "未扫描" in text or "等待" in text:
        return "waiting"
    if text.startswith("[信息]") or text.startswith("[INFO]"):
        return "info"
    return "info"


def _strip_check_marker(line):
    text = str(line or "")
    for marker in ("[通过] ", "[注意] ", "[阻断] ", "[信息] ", "[PASS] ", "[WARN] ", "[BLOCK] ", "[FAIL] ", "[INFO] "):
        if text.startswith(marker):
            return text[len(marker) :]
    return text


def _yes(value):
    return "是" if value else "否"


def _compact_color(value):
    values = list(value or [])[:3]
    if len(values) < 3:
        return "默认"
    return "({0:.2f},{1:.2f},{2:.2f})".format(float(values[0]), float(values[1]), float(values[2]))


def _clip(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[: max(0, limit - 3)] + "..."


def _write_ui_report(action, payload):
    report_dir = os.path.join(_repo_root(), "AssetForgeReports", "blender_ui")
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
    return os.path.join(_repo_root(), "AssetForgeReports", "dcc_packages", "blender")


def _default_log_path():
    return os.path.join(_repo_root(), "AssetForgeReports", "logs", "latest_blender.log")


def _register_previews():
    global _PREVIEWS
    if _PREVIEWS is not None:
        return
    try:
        import bpy.utils.previews  # type: ignore
        _PREVIEWS = bpy.utils.previews.new()
        _register_status_icons(_PREVIEWS)
        for filename in ("IconMayaHeader.png", "IconHeader.png", "Icon128.png"):
            icon_path = os.path.join(_repo_root(), "Plugins", "AssetForge", "Resources", filename)
            if os.path.exists(icon_path):
                _PREVIEWS.load("asset_forge_logo", icon_path, "IMAGE")
                break
    except Exception:
        _PREVIEWS = None


def _register_status_icons(previews):
    icon_dir = os.path.join(_repo_root(), "AssetForgeReports", "blender_ui", "status_icons")
    if not os.path.isdir(icon_dir):
        os.makedirs(icon_dir)
    for state, color in _STATUS_ICON_COLORS.items():
        icon_path = os.path.join(icon_dir, "status_{0}.png".format(state))
        if not os.path.exists(icon_path):
            _write_status_icon_png(icon_path, color)
        previews.load("status_{0}".format(state), icon_path, "IMAGE")


def _write_status_icon_png(path, color):
    width = 16
    height = 16
    pixels = []
    cx = 7.5
    cy = 7.5
    for y in range(height):
        for x in range(width):
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if dist <= 5.8:
                pixels.append(color)
            elif dist <= 7.0:
                pixels.append((max(0, color[0] - 36), max(0, color[1] - 36), max(0, color[2] - 36), color[3]))
            else:
                pixels.append((0, 0, 0, 0))
    _write_png_rgba(path, width, height, pixels)


def _write_png_rgba(path, width, height, pixels):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            row.extend(bytearray(pixels[y * width + x]))
        rows.append(bytes(row))
    raw = b"".join(rows)
    payload = b"\x89PNG\r\n\x1a\n"
    payload += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    payload += _png_chunk(b"IDAT", zlib.compress(raw))
    payload += _png_chunk(b"IEND", b"")
    with open(path, "wb") as stream:
        stream.write(payload)


def _png_chunk(kind, data):
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _unregister_previews():
    global _PREVIEWS
    if _PREVIEWS is None:
        return
    try:
        import bpy.utils.previews  # type: ignore
        bpy.utils.previews.remove(_PREVIEWS)
    except Exception:
        pass
    _PREVIEWS = None


def _logo_icon_value():
    if _PREVIEWS is None or "asset_forge_logo" not in _PREVIEWS:
        return 0
    return _PREVIEWS["asset_forge_logo"].icon_id
