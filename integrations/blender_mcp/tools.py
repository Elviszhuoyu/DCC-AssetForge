# -*- coding: utf-8 -*-
"""MCP tool definitions for local Blender bridge instances."""

from __future__ import absolute_import

import json

from integrations.blender_mcp.client import BlenderBridgeClient
from integrations.blender_mcp.protocol import validate_bridge_action
from integrations.blender_mcp_runtime.registry import (
    AmbiguousBlenderInstanceError,
    load_instances,
    strip_target_arguments,
)


def tool_definitions():
    return [
        _tool(
            "blender_instances",
            "列出本机已注册的 Blender MCP bridge 实例，用于多 Blender 窗口定向控制。",
            {"include_stale": {"type": "boolean", "default": False}},
        ),
        _tool("blender_status", "检查 Blender bridge、当前 .blend 和 Asset Forge 扩展状态。", {}),
        _tool("blender_get_selection", "读取当前 Blender 选择集，用于后续扫描和导出。", {}),
        _tool("blender_get_scene_summary", "读取当前 Blender 场景概要，不修改场景。", {}),
        _tool("blender_get_latest_log", "读取 Asset Forge Blender bridge 最新日志。", {"tail": {"type": "integer", "default": 200}}),
        _static_prop_tool("blender_scan_static_prop", "扫描当前 Blender selection，返回 Asset Forge Static Prop 分析结果。"),
        _static_prop_tool("blender_preflight_static_prop", "执行 Blender Static Prop 共享规则预检，但不导出 FBX。"),
        _static_prop_tool(
            "blender_build_static_prop_package_contract",
            "写出 Blender Static Prop package contract；FBX 仍为 planned，不能直接进入 UE accept-flow。",
            extra={
                "export_root": {"type": "string"},
                "target_path": {"type": "string", "default": "/Game/Props"},
                "use_asset_folder": {"type": "boolean", "default": True},
            },
            required=["export_root"],
        ),        _static_prop_tool(
            "blender_export_static_prop_package",
            "导出 Blender Static Prop FBX，并写出 UE accept-flow 可消费的 Asset Forge package。",
            extra={
                "export_root": {"type": "string"},
                "target_path": {"type": "string", "default": "/Game/Props"},
                "use_asset_folder": {"type": "boolean", "default": True},
            },
            required=["export_root"],
        ),
    ]


def call_tool(name, arguments=None, client=None):
    arguments = arguments or {}
    if name == "blender_instances":
        instances = load_instances(include_stale=bool(arguments.get("include_stale", False)))
        result = {
            "status": "success",
            "can_accept": True,
            "instance_count": len(instances),
            "instances": instances,
            "selection_summary": _selection_summary(instances),
            "next_action": "指定 blender_instance、blender_pid 或 blender_port 后调用具体 Blender 工具。" if len(instances) != 1 else "可以直接指定该实例调用 Blender 工具。",
        }
    else:
        validate_bridge_action(name)
        active_client = client or BlenderBridgeClient.from_arguments(arguments)
        result = active_client.call(name, strip_target_arguments(arguments))
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)}],
        "isError": False,
    }


def error_tool_result(exc):
    extra = {}
    if isinstance(exc, AmbiguousBlenderInstanceError):
        extra["instances"] = exc.instances
        next_action = "存在多个 Blender MCP 实例；请指定 blender_instance、blender_pid、blender_port 或 blender_scene_contains。"
    else:
        next_action = "确认 Blender bridge 已启动、端口/token 正确，并查看 latest Blender MCP 日志。"
    payload = {
        "status": "error",
        "can_accept": False,
        "warnings": [],
        "errors": [{"source": "blender_mcp_server", "message": str(exc)}],
        "next_action": next_action,
    }
    payload.update(extra)
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)}],
        "isError": True,
    }


def _static_prop_tool(name, description, extra=None, required=None):
    properties = {
        "selection": {"type": "array", "items": {"type": "string"}},
        "target_platform": {"type": "string"},
        "material_profile": {"type": "string", "default": "Props_Opaque_PainterUE_ARM"},
    }
    properties.update(extra or {})
    return _tool(name, description, properties, required=required)


def _tool(name, description, properties, required=None):
    merged = dict(properties or {})
    if name != "blender_instances":
        merged.update(_target_properties())
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": merged,
            "required": list(required or []),
            "additionalProperties": True,
        },
    }


def _target_properties():
    return {
        "blender_instance": {"type": "string"},
        "blender_instance_id": {"type": "string"},
        "blender_pid": {"type": "integer"},
        "blender_port": {"type": "integer"},
        "blender_scene_contains": {"type": "string"},
    }


def _selection_summary(instances):
    return [
        {
            "display_name": item.get("display_name", ""),
            "blender_instance": item.get("instance_id", ""),
            "blender_pid": item.get("pid", ""),
            "blender_port": item.get("port", ""),
            "blender_scene_contains": item.get("scene_name", ""),
        }
        for item in instances or []
    ]