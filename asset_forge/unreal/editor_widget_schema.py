"""Planned Unreal Editor Utility Widget asset schema."""

from __future__ import absolute_import

from asset_forge.unreal.editor_widget_actions import get_action_plan


EDITOR_WIDGET_PLAN = {
    "widget_name": "EUW_AssetForgeBridge",
    "asset_type": "EditorUtilityWidgetBlueprint",
    "content_mount": "/AssetForge",
    "asset_path": "/AssetForge/Editor/EUW_AssetForgeBridge",
    "disk_directory": "Plugins/AssetForge/Content/Editor",
    "official_sources": [
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/editor-utility-widgets-in-unreal-engine",
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python",
    ],
    "layout_regions": [
        "package_picker",
        "manifest_picker",
        "validation_summary",
        "action_buttons",
        "report_output",
    ],
}


def get_editor_widget_plan():
    plan = dict(EDITOR_WIDGET_PLAN)
    plan["actions"] = get_action_plan()
    plan["action_count"] = len(plan["actions"])
    return plan


def validate_editor_widget_plan(plan=None):
    active_plan = plan or get_editor_widget_plan()
    issues = []
    asset_path = active_plan.get("asset_path", "")
    disk_directory = active_plan.get("disk_directory", "")
    action_ids = [item.get("id", "") for item in active_plan.get("actions", [])]

    if not asset_path.startswith("/AssetForge/"):
        issues.append("widget asset must live under /AssetForge")
    if asset_path.startswith("/Game/"):
        issues.append("widget asset must not live under project /Game content")
    if not disk_directory.startswith("Plugins/AssetForge/Content"):
        issues.append("widget disk directory must live under plugin Content")
    for required_action in ["select_package", "dry_run_package", "import_package"]:
        if required_action not in action_ids:
            issues.append("missing widget action: {0}".format(required_action))
    if active_plan.get("asset_type") != "EditorUtilityWidgetBlueprint":
        issues.append("widget asset type must be EditorUtilityWidgetBlueprint")
    return issues
