# -*- coding: utf-8 -*-
"""Blender Asset Forge workbench UI."""

from __future__ import absolute_import

import importlib
import json
import os
import sys
import time
import traceback

import bpy  # type: ignore

from asset_forge.blender.provider_asset_forge import BlenderAssetForgeProvider
from asset_forge.shared.constants import TARGET_PLATFORM_HIGH_END_MOBILE, TARGET_PLATFORM_MOBILE, TARGET_PLATFORM_PC


DEFAULT_TARGET_PATH = "/Game/Props/Blender"
DEFAULT_MATERIAL_PROFILE = "Props_Opaque_PainterUE_ARM"
_PREVIEWS = None


class ASSETFORGE_PG_settings(bpy.types.PropertyGroup):
    target_platform: bpy.props.EnumProperty(name="目标平台", items=[(TARGET_PLATFORM_PC, "pc", "PC"), (TARGET_PLATFORM_HIGH_END_MOBILE, "high_end_mobile", "高端移动"), (TARGET_PLATFORM_MOBILE, "mobile", "移动")], default=TARGET_PLATFORM_HIGH_END_MOBILE)  # type: ignore
    export_root: bpy.props.StringProperty(name="导出根目录", subtype="DIR_PATH", default="")  # type: ignore
    target_path: bpy.props.StringProperty(name="UE 目标路径", default=DEFAULT_TARGET_PATH)  # type: ignore
    material_profile: bpy.props.StringProperty(name="材质匹配规则", default=DEFAULT_MATERIAL_PROFILE)  # type: ignore
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
    next_action: bpy.props.StringProperty(name="下一步", default="下一步 | 选中资产根节点 -> 扫描资产")  # type: ignore
    last_asset_name: bpy.props.StringProperty(name="资产", default="未扫描")  # type: ignore
    last_texture_status: bpy.props.StringProperty(name="贴图", default="未扫描")  # type: ignore
    last_issue_status: bpy.props.StringProperty(name="风险", default="未预检")  # type: ignore
    last_export_status: bpy.props.StringProperty(name="发布", default="等待扫描")  # type: ignore
    asset_detail: bpy.props.StringProperty(name="资产详情", default="当前资产根节点：未扫描\n当前导出资产名：未扫描\n来源：未扫描")  # type: ignore
    texture_detail: bpy.props.StringProperty(name="贴图详情", default="贴图匹配：未扫描\nBlender 会读取材质 Image Texture 节点；缺失槽位会生成可追踪占位贴图。")  # type: ignore
    preflight_detail: bpy.props.StringProperty(name="检查详情", default="风险检查：未预检")  # type: ignore
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


class ASSETFORGE_OT_scan_selection(bpy.types.Operator):
    bl_idname = "asset_forge.scan_selection"
    bl_label = "1 扫描资产"
    bl_description = "扫描当前选择；若只激活子物体，会自动提升到最上层父组"

    def execute(self, context):
        return _run_provider_action(context, "scan")


class ASSETFORGE_OT_preflight_selection(bpy.types.Operator):
    bl_idname = "asset_forge.preflight_selection"
    bl_label = "2 检查风险"
    bl_description = "运行 Static Prop 共享规则检查"

    def execute(self, context):
        return _run_provider_action(context, "preflight")


class ASSETFORGE_OT_export_package(bpy.types.Operator):
    bl_idname = "asset_forge.export_package"
    bl_label = "3 导出 Package 给 UE Gate"
    bl_description = "导出 FBX、材质/贴图占位与 manifest，交给 UE Gate 接收"

    def execute(self, context):
        return _run_provider_action(context, "export")


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
        mcp = row.row(align=True)
        _draw_mcp_header_controls(mcp)
        row.operator("asset_forge.refresh_status", text="", icon="FILE_REFRESH")
        _status_line(box, _bridge_line(), _bridge_state())
        _status_line(box, _root_line(context), "info")
        _status_line(box, settings.next_action, "info")


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
    bl_label = "发布动作"
    bl_parent_id = "ASSETFORGE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.operator("asset_forge.scan_selection", text="1 扫描", icon="VIEWZOOM")
        row.operator("asset_forge.preflight_selection", text="2 检查", icon="CHECKMARK")
        layout.operator("asset_forge.export_package", text="3 导出 Package 给 UE Gate", icon="EXPORT")
        bridge_row = layout.row(align=True)
        bridge_row.operator("asset_forge.start_bridge", text="启动 MCP", icon="PLAY")
        bridge_row.operator("asset_forge.stop_bridge", text="停止 MCP", icon="PAUSE")


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
        layout.prop(s, "triangle_budget")
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
    bl_label = "4 风险检查"
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
        layout.label(text="基础导入：Blender 写 Package，UE Gate 入审/预演/导入。", icon="FILE_TICK")
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
    ASSETFORGE_OT_scan_selection,
    ASSETFORGE_OT_preflight_selection,
    ASSETFORGE_OT_export_package,
    ASSETFORGE_OT_open_last_report,
    ASSETFORGE_PT_main_panel,
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
        "texture_folder": bpy.path.abspath(s.texture_root) if s.texture_root else "",
        "texture_set_token": s.texture_set_token,
        "export_root": bpy.path.abspath(s.export_root) if s.export_root else "",
        "texture_import_policy": _texture_import_policy(s),
        "static_mesh_import_policy": _static_mesh_import_policy(s),
    }


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
        s.last_issue_status = "风险 | 未预检"
        s.last_export_status = "发布 | 等待检查"
        s.preflight_detail = "风险检查：未预检\n下一步：点击“2 检查风险”。"
        s.result_detail = "扫描完成。\n报告：{0}".format(report_path)
        s.next_action = "下一步 | 检查风险 -> 修复阻断项 -> 导出 Package"
        return
    s.preflight_detail = _format_preflight_detail(validation)
    if errors:
        s.last_issue_status = "阻断 | {0} 项 / 警告 {1}".format(errors, warnings)
        s.last_export_status = "发布 | 已阻断"
        s.next_action = _next_action_from_checks(checks)
    elif warnings:
        s.last_issue_status = "警告 | {0} 项".format(warnings)
        s.last_export_status = "发布 | 可导出" if result.get("can_export") else "发布 | 待确认"
        s.next_action = "下一步 | 可导出，但建议确认警告项后再进入 UE Gate。"
    else:
        s.last_issue_status = "通过 | 0 阻断"
        s.last_export_status = "发布 | 可导出"
        s.next_action = "下一步 | 导出 Package 给 UE Gate。"
    if action == "preflight":
        s.last_status = "已检查 | 可导出 {0}".format(bool(result.get("can_export")))
        s.result_detail = "风险检查完成。\n报告：{0}".format(report_path)
    else:
        s.last_status = "导出 {0} | FBX {1}".format(result.get("status", ""), result.get("fbx_export_status", ""))
        s.result_detail = _format_export_result(result, report_path)


def _format_asset_detail(scan):
    if not scan:
        return "当前资产根节点：未扫描\n当前导出资产名：未扫描\n来源：未扫描"
    lines = [
        "当前资产根节点：{0}".format(", ".join(scan.get("asset_roots", []) or [])),
        "当前导出资产名：{0}".format(scan.get("asset_name", "")),
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
    if not textures:
        lines.append("未发现 Image Texture 节点；导出时会生成 BaseColor/Normal/ARM 占位贴图，UE Gate 可追踪。")
    else:
        usages = sorted(set(item.get("usage", "") for item in textures if item.get("usage")))
        lines.append("已发现节点贴图：{0}".format(", ".join(usages)))
    for material in materials[:8]:
        material_textures = list(material.get("textures", []) or [])
        texture_usages = sorted(set(item.get("usage", "") for item in material_textures if item.get("usage")))
        usage_text = ", ".join(texture_usages) if texture_usages else "占位待导出"
        lines.append("- {0} | {1} | BaseColor {2}".format(material.get("name", ""), usage_text, _compact_color(material.get("base_color", []))))
    return "\n".join(lines)


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
        return "风险检查：未预检"
    summary = validation.get("summary", {}) or {}
    lines = ["状态：{0} | 分数：{1} | 通过/警告/阻断：{2}/{3}/{4}".format("可导出" if validation.get("can_export") else "不可导出", validation.get("score", 0), summary.get("passes", 0), summary.get("warnings", 0), summary.get("errors", 0))]
    for item in validation.get("checks", []) or []:
        lines.append("{0} {1}：{2}".format(_check_marker(item.get("status")), item.get("label") or item.get("id"), item.get("message", "")))
    return "\n".join(lines)


def _format_export_result(result, report_path):
    return "导出状态：{0}\nFBX：{1}\nPackage：{2}\n报告：{3}\n下一步：{4}".format(result.get("status", ""), result.get("fbx_export_status", ""), result.get("package_dir", ""), report_path, result.get("next_action", ""))


def _next_action_from_checks(checks):
    for item in checks or []:
        if item.get("status") == "error":
            if item.get("id") == "frozen_transform":
                return "下一步 | 冻结/应用根节点 Transform 后重新检查。"
            return "下一步 | 修复阻断项“{0}”后重新检查。".format(item.get("label") or item.get("id"))
    return "下一步 | 确认警告项后导出 Package。"


def _bridge_module(try_enable=False):
    try:
        import blender_mcp_bridge.bridge as module  # type: ignore
        return module, "independent"
    except Exception:
        if try_enable:
            try:
                import addon_utils  # type: ignore
                addon_utils.enable("blender_mcp_bridge", default_set=True, persistent=True)
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
    return "MCP：{0} 运行中 127.0.0.1:{1}".format(source, active.port)


def _draw_mcp_header_controls(layout):
    active = _current_bridge()
    status = layout.row(align=True)
    if active:
        status.label(text="MCP: {0} 运行中".format(active.port), icon="CHECKMARK")
    else:
        status.label(text="MCP: 未运行", icon="TIME")
    start = layout.row(align=True)
    start.enabled = not bool(active)
    start.operator("asset_forge.start_bridge", text="启动", icon="PLAY")
    layout.operator("asset_forge.refresh_status", text="状态", icon="INFO")


def _bridge_state():
    return "ok" if _current_bridge() else "warning"


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
    return "waiting" if "未扫描" in s.last_texture_status else "warning" if "0 贴图" in s.last_texture_status else "ok"


def _issue_state(s):
    text = s.last_issue_status or ""
    if "失败" in text:
        return "error"
    if "阻断" in text:
        return "blocked"
    if "警告" in text:
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
    item.label(text=_clip(text, 32), icon=_status_icon(state))


def _status_line(layout, text, state):
    row = layout.row(align=True)
    row.alert = state in ("error", "blocked")
    row.label(text=_clip(text, 70), icon=_status_icon(state))


def _draw_text_block(layout, text, alert=False):
    box = layout.box()
    for line in str(text or "").split("\n")[:12]:
        row = box.row()
        row.alert = bool(alert)
        row.label(text=_clip(line, 88))


def _draw_preflight_block(layout, text):
    box = layout.box()
    for line in str(text or "").split("\n")[:16]:
        state = _line_state(line)
        row = box.row()
        row.alert = state in ("error", "blocked")
        row.label(text=_clip(_strip_check_marker(line), 88), icon=_status_icon(state))


def _status_icon(state):
    return {"ok": "CHECKMARK", "warning": "ERROR", "blocked": "CANCEL", "error": "CANCEL", "info": "INFO", "waiting": "TIME"}.get(state, "INFO")


def _check_marker(status):
    return {"pass": "[PASS]", "warning": "[WARN]", "error": "[BLOCK]", "info": "[INFO]"}.get(status, "[?]")


def _line_state(line):
    text = str(line or "")
    if text.startswith("[BLOCK]") or text.startswith("[FAIL]") or "不可导出" in text or "阻断" in text or "失败" in text:
        return "blocked"
    if text.startswith("[WARN]") or "警告" in text:
        return "warning"
    if text.startswith("[PASS]") or "：通过" in text or " 通过" in text:
        return "ok"
    if text.startswith("[INFO]"):
        return "info"
    return "info"


def _strip_check_marker(line):
    text = str(line or "")
    for marker in ("[PASS] ", "[WARN] ", "[BLOCK] ", "[FAIL] ", "[INFO] "):
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
    return os.path.join(_repo_root(), "AssetForgeReports", "blender_ui_exports")


def _default_log_path():
    return os.path.join(_repo_root(), "AssetForgeReports", "logs", "latest_blender.log")


def _register_previews():
    global _PREVIEWS
    if _PREVIEWS is not None:
        return
    try:
        import bpy.utils.previews  # type: ignore
        _PREVIEWS = bpy.utils.previews.new()
        for filename in ("IconMayaHeader.png", "IconHeader.png", "Icon128.png"):
            icon_path = os.path.join(_repo_root(), "Plugins", "AssetForge", "Resources", filename)
            if os.path.exists(icon_path):
                _PREVIEWS.load("asset_forge_logo", icon_path, "IMAGE")
                break
    except Exception:
        _PREVIEWS = None


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
