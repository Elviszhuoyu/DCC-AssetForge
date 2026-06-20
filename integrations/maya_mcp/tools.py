# -*- coding: utf-8 -*-
"""MCP tool definitions for local Maya bridge instances."""

from __future__ import absolute_import

import json

from integrations.maya_mcp.client import MayaBridgeClient
from integrations.maya_mcp.protocol import validate_bridge_action
from integrations.maya_mcp_runtime.registry import (
    AmbiguousMayaInstanceError,
    load_instances,
    strip_target_arguments,
)


def tool_definitions():
    return [
        _tool(
            "maya_instances",
            "列出本机已注册的 Maya MCP bridge 实例，用于多 Maya 窗口定向控制。",
            {
                "include_stale": {"type": "boolean", "default": False},
            },
        ),
        _tool("maya_status", "检查 Maya bridge、当前场景和 Asset Forge 加载状态。", {}),
        _tool(
            "maya_load_asset_forge",
            "清理旧模块缓存并加载当前仓库版本的 Asset Forge Maya 入口。",
            {
                "repo_root": {"type": "string"},
                "open_ui": {"type": "boolean", "default": False},
            },
        ),
        _tool(
            "maya_install_asset_forge_ui_shelf",
            "安装或刷新 Asset Forge Maya 发布工作台 shelf 按钮，使用统一 AF 图标并强制加载当前仓库代码。",
            {
                "repo_root": {"type": "string"},
                "shelf_name": {"type": "string", "default": "AssetForge"},
            },
        ),
        _tool(
            "maya_install_mcp_bridge_shelf",
            "安装或刷新 Asset Forge Maya MCP shelf 按钮，使用 Maya 专用 MCP 图标并指向当前仓库 bridge。",
            {
                "repo_root": {"type": "string"},
            },
        ),
        _tool(
            "maya_open_scene",
            "在 Maya 中打开指定 .ma/.mb 场景。",
            {
                "scene_path": {"type": "string"},
                "force": {"type": "boolean", "default": True},
                "save_current": {"type": "boolean", "default": False},
            },
            required=["scene_path"],
        ),
        _tool(
            "maya_import_fbx",
            "导入 FBX 并生成稳定选择根，供 Static Prop scan/preflight/export 继续使用。",
            {
                "fbx_path": {"type": "string"},
                "namespace": {"type": "string", "default": "AFMCP"},
                "new_scene": {"type": "boolean", "default": True},
                "select_imported": {"type": "boolean", "default": True},
                "rename_root": {"type": "string"},
                "group_imported": {"type": "boolean", "default": True},
                "force_load_plugin": {"type": "boolean", "default": True},
            },
            required=["fbx_path"],
        ),
        _static_prop_tool("maya_scan_static_prop", "扫描当前选择或指定节点并返回 Static Prop 分析结果。"),
        _static_prop_tool("maya_preflight_static_prop", "执行 Static Prop 导出前检查，但不导出 FBX。"),
        _static_prop_tool(
            "maya_export_static_prop_package",
            "导出标准 Asset Forge Static Prop package。",
            extra={
                "export_root": {"type": "string"},
                "target_path": {"type": "string", "default": "/Game/Props"},
                "force_rescan": {"type": "boolean", "default": True},
            },
        ),
        _static_prop_tool(
            "maya_run_static_prop_ui_flow",
            "Run the Asset Forge Maya UI flow through whitelisted window callbacks: scan, optional prefix fixes, preflight, optional texture scan, and export.",
            extra={
                "export_root": {"type": "string"},
                "target_path": {"type": "string", "default": "/Game/Props"},
                "texture_prefix": {"type": "string", "default": "T_"},
                "scan_texture_dir": {"type": "boolean", "default": True},
                "fix_texture_prefix": {"type": "boolean", "default": False},
            },
        ),
        _tool("maya_get_latest_log", "读取 AssetForgeReports/logs/latest_maya.log。", {"tail": {"type": "integer", "default": 200}}),
        _tool(
            "maya_viewport_screenshot",
            "保存当前 Maya viewport 截图，作为辅助验收证据。",
            {
                "output_path": {"type": "string"},
                "width": {"type": "integer", "default": 1280},
                "height": {"type": "integer", "default": 720},
            },
            required=["output_path"],
        ),
        _tool(
            "maya_reset_session",
            "清理选择，并可选新建空场景与清理 Asset Forge 模块缓存。",
            {
                "new_scene": {"type": "boolean", "default": False},
                "purge_asset_forge_modules": {"type": "boolean", "default": False},
            },
        ),
        _tool(
            "maya_run_python",
            "开发期逃生口。默认关闭，生产验收流不得依赖。",
            {
                "code": {"type": "string"},
                "max_output_chars": {"type": "integer", "default": 6000},
            },
            required=["code"],
        ),
    ]


def call_tool(name, arguments=None, client=None):
    arguments = arguments or {}
    if name == "maya_instances":
        instances = load_instances(include_stale=bool(arguments.get("include_stale", False)))
        result = {
            "status": "success",
            "can_accept": True,
            "instance_count": len(instances),
            "instances": instances,
            "selection_summary": _selection_summary(instances),
            "next_action": "指定 maya_instance、maya_pid 或 maya_port 后调用具体 Maya 工具。" if len(instances) != 1 else "可以直接指定该实例调用 Maya 工具。",
        }
    else:
        validate_bridge_action(name)
        active_client = client or MayaBridgeClient.from_arguments(arguments)
        result = active_client.call(name, strip_target_arguments(arguments))
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)}],
        "isError": False,
    }


def error_tool_result(exc):
    extra = {}
    if isinstance(exc, AmbiguousMayaInstanceError):
        extra["instances"] = exc.instances
        next_action = "存在多个 Maya MCP 实例；请指定 maya_instance、maya_pid、maya_port 或 maya_scene_contains。"
    else:
        next_action = "确认 Maya bridge 已启动、端口/token 正确，并查看 latest_maya.log。"
    payload = {
        "status": "error",
        "can_accept": False,
        "warnings": [],
        "errors": [{"source": "maya_mcp_server", "message": str(exc)}],
        "next_action": next_action,
    }
    payload.update(extra)
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)}],
        "isError": True,
    }


def _static_prop_tool(name, description, extra=None):
    properties = {
        "selection": {"type": "array", "items": {"type": "string"}},
        "texture_dir": {"type": "string"},
        "texture_set_token": {"type": "string"},
        "project_settings_path": {"type": "string"},
        "project_preset": {"type": "object"},
        "preset_name": {"type": "string"},
        "preset_version": {"type": "string"},
        "updated_at": {"type": "string"},
        "target_platform": {"type": "string"},
        "material_profile": {"type": "string", "default": "Props_Opaque_PainterUE_ARM"},
        "triangle_budget": {"type": "integer"},
        "mesh_prefix": {"type": "string", "default": "SM_"},
        "package_name_override": {"type": "string"},
        "package_version_mode": {"type": "string", "enum": ["overwrite", "auto_increment"], "default": "overwrite"},
        "package_version_padding": {"type": "integer", "default": 3},
        "package_version_start": {"type": "integer", "default": 1},
        "virtual_texture_policy": {"type": "string"},
        "texture_streaming_policy": {"type": "string"},
        "texture_group": {"type": "string"},
        "nanite_policy": {"type": "string"},
        "static_mesh_lod_group": {"type": "string"},
        "static_mesh_lod_import_policy": {"type": "string"},
    }
    properties.update(extra or {})
    return _tool(name, description, properties)


def _tool(name, description, properties, required=None):
    merged = dict(properties or {})
    if name != "maya_instances":
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
        "maya_instance": {"type": "string"},
        "maya_instance_id": {"type": "string"},
        "maya_pid": {"type": "integer"},
        "maya_port": {"type": "integer"},
        "maya_scene_contains": {"type": "string"},
    }


def _selection_summary(instances):
    return [
        {
            "display_name": item.get("display_name", ""),
            "maya_instance": item.get("instance_id", ""),
            "maya_pid": item.get("pid", ""),
            "maya_port": item.get("port", ""),
            "maya_scene_contains": item.get("scene_name", ""),
        }
        for item in instances or []
    ]
