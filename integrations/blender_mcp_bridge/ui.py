# -*- coding: utf-8 -*-
"""Small Blender UI for the independent MCP bridge."""

from __future__ import absolute_import

import bpy  # type: ignore

from . import bridge


class BLENDERMCP_OT_refresh_status(bpy.types.Operator):
    bl_idname = "blender_mcp.refresh_status"
    bl_label = "刷新"
    bl_description = "刷新 Blender MCP Bridge 状态"

    def execute(self, context):
        return {"FINISHED"}


class BLENDERMCP_OT_start_bridge(bpy.types.Operator):
    bl_idname = "blender_mcp.start_bridge"
    bl_label = "启动"
    bl_description = "启动独立 Blender MCP Bridge"

    def execute(self, context):
        bridge.start_bridge()
        return {"FINISHED"}


class BLENDERMCP_OT_stop_bridge(bpy.types.Operator):
    bl_idname = "blender_mcp.stop_bridge"
    bl_label = "停止"
    bl_description = "停止独立 Blender MCP Bridge"

    def execute(self, context):
        bridge.stop_bridge()
        return {"FINISHED"}


class BLENDERMCP_PT_bridge_panel(bpy.types.Panel):
    bl_idname = "BLENDERMCP_PT_bridge_panel"
    bl_label = "Blender MCP Bridge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MCP Bridge"

    def draw(self, context):
        layout = self.layout
        active = bridge.current_bridge()
        box = layout.box()
        row = box.row(align=True)
        row.label(text="Codex 通讯桥", icon="NETWORK_DRIVE")
        row.operator("blender_mcp.refresh_status", text="", icon="FILE_REFRESH")
        if active:
            box.label(text="运行中 127.0.0.1:{0}".format(active.port), icon="LINKED")
        else:
            box.label(text="未运行", icon="UNLINKED")
        scene_path = getattr(getattr(bpy, "data", None), "filepath", "") or "未保存场景"
        box.label(text=scene_path[-64:], icon="FILE_BLEND")
        row = box.row(align=True)
        row.operator("blender_mcp.start_bridge", text="启动", icon="PLAY")
        row.operator("blender_mcp.stop_bridge", text="停止", icon="PAUSE")


CLASSES = (
    BLENDERMCP_OT_refresh_status,
    BLENDERMCP_OT_start_bridge,
    BLENDERMCP_OT_stop_bridge,
    BLENDERMCP_PT_bridge_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass