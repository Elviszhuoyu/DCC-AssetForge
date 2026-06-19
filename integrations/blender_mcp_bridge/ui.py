# -*- coding: utf-8 -*-
"""Blender UI for the independent MCP bridge."""

from __future__ import absolute_import

import time

import bpy  # type: ignore

from . import bridge


BRIDGE_VERSION = "0.1.0"


class BLENDERMCP_PG_settings(bpy.types.PropertyGroup):
    last_action: bpy.props.StringProperty(name="Action", default="idle")  # type: ignore
    log_text: bpy.props.StringProperty(name="Log", default="Bridge log is empty.")  # type: ignore


class BLENDERMCP_OT_refresh_status(bpy.types.Operator):
    bl_idname = "blender_mcp.refresh_status"
    bl_label = "Refresh"
    bl_description = "Refresh Blender MCP Bridge status"

    def execute(self, context):
        settings = context.scene.blender_mcp_settings
        settings.last_action = "refresh"
        _append_log(settings, "Refresh status | {0}".format(_status_line()))
        return {"FINISHED"}


class BLENDERMCP_OT_start_bridge(bpy.types.Operator):
    bl_idname = "blender_mcp.start_bridge"
    bl_label = "Start Bridge"
    bl_description = "Start the independent Blender MCP Bridge"

    def execute(self, context):
        settings = context.scene.blender_mcp_settings
        payload = bridge.start_bridge()
        settings.last_action = "start"
        _append_log(settings, "Start Bridge | {0}:{1} | instance {2}".format(payload.get("host", "127.0.0.1"), payload.get("port", ""), payload.get("instance_id", "")))
        return {"FINISHED"}


class BLENDERMCP_OT_stop_bridge(bpy.types.Operator):
    bl_idname = "blender_mcp.stop_bridge"
    bl_label = "Stop Bridge"
    bl_description = "Stop the independent Blender MCP Bridge"

    def execute(self, context):
        settings = context.scene.blender_mcp_settings
        bridge.stop_bridge()
        settings.last_action = "stop"
        _append_log(settings, "Stop Bridge")
        return {"FINISHED"}


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
        box.label(text="Version: {0} | Action: {1}".format(BRIDGE_VERSION, settings.last_action), icon="INFO")

        controls = box.row(align=True)
        start = controls.row(align=True)
        start.enabled = not bool(active)
        start.operator("blender_mcp.start_bridge", text="Start", icon="PLAY")
        stop = controls.row(align=True)
        stop.enabled = bool(active)
        stop.operator("blender_mcp.stop_bridge", text="Stop", icon="PAUSE")

        detail = layout.box()
        detail.label(text="Bridge Details", icon="TEXT")
        _detail_line(detail, "Status", "running" if active else "stopped", "ok" if active else "warning")
        _detail_line(detail, "Health", "healthy" if active else "offline", "ok" if active else "warning")
        _detail_line(detail, "Instance", payload.get("instance_id", "-"), "info")
        _detail_line(detail, "PID", payload.get("pid", "-"), "info")
        _detail_line(detail, "Host", payload.get("host", "127.0.0.1"), "info")
        _detail_line(detail, "Port", payload.get("port", "-"), "info")
        _detail_line(detail, "Scene", _scene_label(payload.get("scene_path") or _scene_path()), "info")
        if active:
            uptime = max(0, int(time.time() - float(getattr(active, "started_at_epoch", time.time()) or time.time())))
            _detail_line(detail, "Uptime", "{0}s".format(uptime), "info")

        log_box = layout.box()
        log_box.label(text="Session Log", icon="CONSOLE")
        for line in str(settings.log_text or "").split("\n")[-8:]:
            log_box.label(text=_clip(line, 90))


CLASSES = (
    BLENDERMCP_PG_settings,
    BLENDERMCP_OT_refresh_status,
    BLENDERMCP_OT_start_bridge,
    BLENDERMCP_OT_stop_bridge,
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


def _append_log(settings, message):
    stamp = time.strftime("%H:%M:%S")
    existing = str(settings.log_text or "")
    if existing == "Bridge log is empty.":
        existing = ""
    settings.log_text = (existing + "\n" + stamp + " | " + message).strip()


def _status_line():
    active = bridge.current_bridge()
    if not active:
        return "Health: offline | Active: 0 | Action: idle"
    return "Health: healthy | Active: 1 | Action: running | Port: {0}".format(active.port)


def _status_row(layout, text, state):
    row = layout.row(align=True)
    row.alert = state in ("warning", "error")
    row.label(text=_clip(text, 90), icon="CHECKMARK" if state == "ok" else "ERROR")


def _detail_line(layout, key, value, state):
    row = layout.row(align=True)
    row.alert = state == "warning"
    row.label(text="{0}: {1}".format(key, _clip(value, 78)), icon="CHECKMARK" if state == "ok" else "INFO")


def _scene_path():
    return getattr(getattr(bpy, "data", None), "filepath", "") or ""


def _scene_label(path):
    return path if path else "Unsaved Scene"


def _clip(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[: max(0, limit - 3)] + "..."