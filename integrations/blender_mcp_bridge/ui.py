# -*- coding: utf-8 -*-
"""Blender UI for the independent MCP bridge."""

from __future__ import absolute_import

import time

import bpy  # type: ignore

from . import bridge


BRIDGE_VERSION = getattr(bridge, "BRIDGE_VERSION", "0.2.0")


class BLENDERMCP_PG_settings(bpy.types.PropertyGroup):
    last_action: bpy.props.StringProperty(name="动作", default="idle")  # type: ignore
    log_text: bpy.props.StringProperty(name="日志", default="Bridge 日志为空。")  # type: ignore


class BLENDERMCP_OT_refresh_status(bpy.types.Operator):
    bl_idname = "blender_mcp.refresh_status"
    bl_label = "刷新状态"
    bl_description = "刷新 Blender MCP Bridge 状态"

    def execute(self, context):
        settings = context.scene.blender_mcp_settings
        settings.last_action = "refresh"
        _append_log(settings, "刷新状态 | {0}".format(_status_line()))
        return {"FINISHED"}


class BLENDERMCP_OT_start_bridge(bpy.types.Operator):
    bl_idname = "blender_mcp.start_bridge"
    bl_label = "启动 Bridge"
    bl_description = "启动独立 Blender MCP Bridge"

    def execute(self, context):
        settings = context.scene.blender_mcp_settings
        payload = bridge.start_bridge()
        settings.last_action = "start"
        _append_log(settings, "启动 Bridge | {0}:{1} | 实例 {2}".format(payload.get("host", "127.0.0.1"), payload.get("port", ""), payload.get("instance_id", "")))
        return {"FINISHED"}


class BLENDERMCP_OT_stop_bridge(bpy.types.Operator):
    bl_idname = "blender_mcp.stop_bridge"
    bl_label = "停止 Bridge"
    bl_description = "停止独立 Blender MCP Bridge"

    def execute(self, context):
        settings = context.scene.blender_mcp_settings
        bridge.stop_bridge()
        settings.last_action = "stop"
        _append_log(settings, "停止 Bridge")
        return {"FINISHED"}


class BLENDERMCP_OT_restart_bridge(bpy.types.Operator):
    bl_idname = "blender_mcp.restart_bridge"
    bl_label = "重启 Bridge"
    bl_description = "安全停止并重新启动独立 Blender MCP Bridge；不保存 .blend 或用户偏好"

    def execute(self, context):
        settings = context.scene.blender_mcp_settings
        bridge.stop_bridge()
        payload = bridge.start_bridge()
        settings.last_action = "restart"
        _append_log(settings, "重启 Bridge | {0}:{1} | 实例 {2}".format(payload.get("host", "127.0.0.1"), payload.get("port", ""), payload.get("instance_id", "")))
        return {"FINISHED"}


class BLENDERMCP_OT_refresh_asset_forge_modules(bpy.types.Operator):
    bl_idname = "blender_mcp.refresh_asset_forge_modules"
    bl_label = "刷新 DCC AssetForge 模块"
    bl_description = "刷新 DCC AssetForge Blender 业务模块缓存，不保存 .blend 或用户偏好"

    def execute(self, context):
        settings = context.scene.blender_mcp_settings
        active = bridge.current_bridge()
        if not active:
            settings.last_action = "refresh_modules_failed"
            _append_log(settings, "刷新模块失败 | Bridge 未运行")
            return {"CANCELLED"}
        result = active.handle_request({"id": "ui-refresh-modules", "action": "blender_refresh_asset_forge_modules", "params": {}})
        if result.get("ok"):
            settings.last_action = "refresh_modules"
            modules = ", ".join(result.get("result", {}).get("refreshed_modules", []))
            _append_log(settings, "刷新模块 | {0}".format(modules or "完成"))
            return {"FINISHED"}
        settings.last_action = "refresh_modules_failed"
        _append_log(settings, "刷新模块失败 | {0}".format(result.get("error", {}).get("message", "")))
        return {"CANCELLED"}


class BLENDERMCP_PT_bridge_panel(bpy.types.Panel):
    bl_idname = "BLENDERMCP_PT_bridge_panel"
    bl_label = "Blender MCP Bridge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MCP Bridge"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.blender_mcp_settings
        active = bridge.current_bridge()
        payload = active.instance_payload() if active else {}

        box = layout.box()
        row = box.row(align=True)
        row.label(text="Blender MCP Bridge", icon="NETWORK_DRIVE")
        row.operator("blender_mcp.refresh_status", text="", icon="FILE_REFRESH")
        _status_row(box, _status_line(), "ok" if active else "warning")
        if active:
            box.label(text="版本：{0} | 手动运行中".format(BRIDGE_VERSION), icon="INFO")
        else:
            box.label(text="版本：{0} | 默认不随 Blender 启动".format(BRIDGE_VERSION), icon="INFO")

        controls = box.row(align=True)
        start = controls.row(align=True)
        start.enabled = not bool(active)
        start.operator("blender_mcp.start_bridge", text="启动", icon="PLAY")
        restart = controls.row(align=True)
        restart.enabled = bool(active)
        restart.operator("blender_mcp.restart_bridge", text="重启", icon="FILE_REFRESH")
        stop = controls.row(align=True)
        stop.enabled = bool(active)
        stop.operator("blender_mcp.stop_bridge", text="停止", icon="PAUSE")
        refresh_modules = box.row(align=True)
        refresh_modules.enabled = bool(active)
        refresh_modules.operator("blender_mcp.refresh_asset_forge_modules", text="刷新 DCC AssetForge 模块", icon="FILE_REFRESH")

        detail = layout.box()
        detail.label(text="Bridge 详情", icon="TEXT")
        _detail_line(detail, "状态", "运行中" if active else "已停止", "ok" if active else "warning")
        _detail_line(detail, "健康", "可用" if active else "离线", "ok" if active else "warning")
        _detail_line(detail, "实例", payload.get("instance_id", "-"), "info")
        _detail_line(detail, "PID", payload.get("pid", "-"), "info")
        _detail_line(detail, "Host", payload.get("host", "127.0.0.1"), "info")
        _detail_line(detail, "端口", payload.get("port", "-"), "info")
        _detail_line(detail, "场景", _scene_label(payload.get("scene_path") or _scene_path()), "info")
        if active:
            uptime = max(0, int(time.time() - float(getattr(active, "started_at_epoch", time.time()) or time.time())))
            _detail_line(detail, "运行时长", "{0}s".format(uptime), "info")

        log_box = layout.box()
        log_box.label(text="会话日志", icon="CONSOLE")
        for line in _session_log_lines(settings, active):
            log_box.label(text=_clip(line, 90))


CLASSES = (
    BLENDERMCP_PG_settings,
    BLENDERMCP_OT_refresh_status,
    BLENDERMCP_OT_start_bridge,
    BLENDERMCP_OT_stop_bridge,
    BLENDERMCP_OT_restart_bridge,
    BLENDERMCP_OT_refresh_asset_forge_modules,
    BLENDERMCP_PT_bridge_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.blender_mcp_settings = bpy.props.PointerProperty(type=BLENDERMCP_PG_settings)


def unregister():
    if hasattr(bpy.types.Scene, "blender_mcp_settings"):
        del bpy.types.Scene.blender_mcp_settings
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass


def _session_log_lines(settings, active):
    lines = []
    if active and getattr(active, "event_log", None):
        for item in active.event_log[-8:]:
            lines.append("{0} | {1} | {2} | {3}".format(item.get("time", ""), item.get("status", ""), item.get("action", ""), item.get("message", "")))
    local_text = str(settings.log_text or "")
    if local_text and local_text not in ("Bridge log is empty.", "Bridge 日志为空。"):
        lines.extend(local_text.split("\n")[-4:])
    return lines[-8:] or ["Bridge 日志为空。"]

def _append_log(settings, message):
    stamp = time.strftime("%H:%M:%S")
    existing = str(settings.log_text or "")
    if existing in ("Bridge log is empty.", "Bridge 日志为空。"):
        existing = ""
    settings.log_text = (existing + "\n" + stamp + " | " + message).strip()


def _status_line():
    active = bridge.current_bridge()
    if not active:
        return "健康：离线 | 活跃：0 | 操作：等待启动"
    return "健康：可用 | 活跃：1 | 操作：运行中 | 端口：{0}".format(active.port)


def _status_row(layout, text, state):
    row = layout.row(align=True)
    row.alert = state == "error"
    row.label(text=_clip(text, 90), icon="CHECKMARK" if state == "ok" else "ERROR")


def _detail_line(layout, key, value, state):
    row = layout.row(align=True)
    row.alert = state == "error"
    row.label(text="{0}: {1}".format(key, _clip(value, 78)), icon="CHECKMARK" if state == "ok" else "INFO")


def _scene_path():
    return getattr(getattr(bpy, "data", None), "filepath", "") or ""


def _scene_label(path):
    return path if path else "未保存场景"


def _clip(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[: max(0, limit - 3)] + "..."
