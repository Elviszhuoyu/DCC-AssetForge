"""DCC AssetForge Unreal Python bootstrap.

Unreal loads plugin Content/Python scripts when the Python plugin is enabled.
This file keeps the development repository importable without manual console
sys.path setup.
"""

from __future__ import absolute_import

import os
import sys


def bootstrap():
    plugin_python_dir = _plugin_python_dir()
    repo_root = _repo_root_from_plugin_python()
    added_paths = _ensure_python_paths(repo_root, plugin_python_dir)
    action_plan, action_issues = _safe_load("action plan", _load_action_plan, [])
    widget_launch_plan, widget_issues = _safe_load("widget launch plan", _load_widget_launch_plan, {"issues": []})
    material_asset_plan, material_issues = _safe_load("material asset plan", _load_material_asset_plan, {"issues": []})
    tool_menu_report, tool_menu_issues = _safe_load(
        "ToolMenus registration",
        _register_tool_menu,
        {"status": "error", "registered": [], "issues": [], "command": ""},
    )
    issues = (
        action_issues
        + widget_issues
        + material_issues
        + tool_menu_issues
        + list(widget_launch_plan.get("issues", []))
        + list(material_asset_plan.get("issues", []))
        + list(tool_menu_report.get("issues", []))
    )
    report = {
        "repo_root": repo_root.replace("\\", "/"),
        "plugin_python_dir": plugin_python_dir.replace("\\", "/"),
        "added_repo_root": repo_root in added_paths,
        "added_python_paths": [path.replace("\\", "/") for path in added_paths],
        "action_count": len(action_plan),
        "actions": [item.get("id", "") for item in action_plan],
        "widget_asset_path": widget_launch_plan.get("asset_path", ""),
        "widget_launch_status": widget_launch_plan.get("status", ""),
        "widget_launch_issues": widget_launch_plan.get("issues", []),
        "material_asset_count": material_asset_plan.get("asset_count", 0),
        "material_content_mount": material_asset_plan.get("content_mount", ""),
        "content_mount": material_asset_plan.get("content_mount", ""),
        "tool_menu_status": tool_menu_report.get("status", ""),
        "tool_menu_entries": tool_menu_report.get("entries", tool_menu_report.get("registered", [])),
        "tool_menu_command": tool_menu_report.get("command", ""),
        "menu_register_status": tool_menu_report.get("status", ""),
        "menu_registered": tool_menu_report.get("registered", tool_menu_report.get("entries", [])),
        "menu_register_issues": tool_menu_report.get("issues", []),
        "issues": issues,
    }
    log_entry = _log_unreal_operation(report)
    report["unreal_log_path"] = log_entry.get("log_path", "")
    _log_unreal("DCC AssetForge Python bootstrap loaded")
    return report


def _safe_load(label, loader, default_value):
    try:
        return loader(), []
    except Exception as exc:
        message = "DCC AssetForge Python bootstrap {0} failed: {1}".format(label, exc)
        _log_unreal(message, error=True)
        return default_value, [message]


def _plugin_python_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _repo_root_from_plugin_python():
    current_dir = _plugin_python_dir()
    return os.path.abspath(os.path.join(current_dir, "..", "..", "..", ".."))


def _ensure_python_paths(repo_root, plugin_python_dir):
    added = []
    for path in [plugin_python_dir, repo_root]:
        package_dir = os.path.join(path, "asset_forge")
        if not os.path.isdir(package_dir):
            continue
        if path not in sys.path:
            sys.path.insert(0, path)
            added.append(path)
    return added


def _load_action_plan():
    from asset_forge.unreal.editor_widget_actions import get_action_plan

    return get_action_plan()


def _load_widget_launch_plan():
    from asset_forge.unreal.editor_widget_launcher import get_widget_launch_plan

    return get_widget_launch_plan()


def _load_material_asset_plan():
    from asset_forge.unreal.material_asset_bootstrap import plan_default_material_assets

    return plan_default_material_assets()


def _register_tool_menu():
    if _cpp_editor_module_declared() and os.environ.get("ASSET_FORGE_PYTHON_MENU_FALLBACK") != "1":
        return {
            "status": "skipped",
            "registered": [],
            "issues": [],
            "command": "AssetForgeEditor C++ Slate UI owns the visible menu entry.",
        }
    from asset_forge.unreal.editor_menu import register_asset_forge_menus

    return register_asset_forge_menus()


def _cpp_editor_module_declared():
    try:
        import json

        descriptor_path = os.path.abspath(os.path.join(_plugin_python_dir(), "..", "..", "AssetForge.uplugin"))
        if not os.path.exists(descriptor_path):
            return False
        with open(descriptor_path, "r", encoding="utf-8") as stream:
            descriptor = json.load(stream)
        return any(item.get("Name") == "AssetForgeEditor" for item in descriptor.get("Modules", []))
    except Exception:
        return False


def _log_unreal(message, error=False):
    try:
        import unreal
    except Exception:
        return
    if error and hasattr(unreal, "log_error"):
        unreal.log_error(message)
    elif hasattr(unreal, "log"):
        unreal.log(message)


def _log_unreal_operation(report):
    try:
        from asset_forge.unreal.operation_logger import UnrealOperationLogger

        return UnrealOperationLogger().log(
            "unreal_bootstrap",
            "success",
            inputs={"repo_root": report.get("repo_root", "")},
            outputs={
                "repo_root": report.get("repo_root", ""),
                "added_repo_root": report.get("added_repo_root", False),
                "action_count": report.get("action_count", 0),
                "material_asset_count": report.get("material_asset_count", 0),
                "content_mount": report.get("content_mount", ""),
                "tool_menu_status": report.get("tool_menu_status", ""),
                "menu_registered": report.get("menu_registered", []),
                "tool_menu_command": report.get("tool_menu_command", ""),
                "issues": report.get("issues", []),
            },
            warnings=report.get("issues", []),
        )
    except Exception as exc:
        return {"log_path": "", "errors": [str(exc)]}


BOOTSTRAP_REPORT = bootstrap()
