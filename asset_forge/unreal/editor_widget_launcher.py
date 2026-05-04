"""Launch facade for the planned Asset Forge Unreal Editor Utility Widget."""

from __future__ import absolute_import

from asset_forge.unreal.editor_widget_schema import get_editor_widget_plan, validate_editor_widget_plan
from asset_forge.unreal.unreal_bridge import get_unreal


class UnrealEditorWidgetLauncher(object):
    """Resolve and optionally launch the Asset Forge Editor Utility Widget."""

    def __init__(self, unreal_module=None, widget_plan=None):
        self.unreal = unreal_module or get_unreal()
        self.widget_plan = widget_plan or get_editor_widget_plan()

    def launch_plan(self):
        issues = validate_editor_widget_plan(self.widget_plan)
        asset_path = self.widget_plan.get("asset_path", "")
        asset_exists = self._asset_exists(asset_path)
        if not asset_exists:
            issues.append("missing editor widget asset: {0}".format(asset_path))

        return {
            "status": "ready" if not issues else "missing_asset",
            "asset_path": asset_path,
            "unreal_available": self.unreal is not None,
            "asset_exists": asset_exists,
            "issues": issues,
            "actions": [item.get("id", "") for item in self.widget_plan.get("actions", [])],
        }

    def launch(self):
        plan = self.launch_plan()
        if plan["status"] != "ready":
            return plan
        if self.unreal is None:
            plan["status"] = "skipped"
            plan["issues"].append("unreal module is not available")
            return plan

        widget_asset = self._load_asset(plan["asset_path"])
        subsystem = self._editor_utility_subsystem()
        if subsystem is None or widget_asset is None:
            plan["status"] = "skipped"
            plan["issues"].append("EditorUtilitySubsystem or widget asset is unavailable")
            return plan

        if hasattr(subsystem, "spawn_and_register_tab"):
            subsystem.spawn_and_register_tab(widget_asset)
            plan["status"] = "launched"
            return plan

        plan["status"] = "skipped"
        plan["issues"].append("EditorUtilitySubsystem.spawn_and_register_tab is unavailable")
        return plan

    def _asset_exists(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None) if self.unreal else None
        if library and hasattr(library, "does_asset_exist"):
            return bool(library.does_asset_exist(asset_path))
        return False

    def _load_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None) if self.unreal else None
        if library and hasattr(library, "load_asset"):
            return library.load_asset(asset_path)
        return None

    def _editor_utility_subsystem(self):
        if self.unreal is None or not hasattr(self.unreal, "get_editor_subsystem"):
            return None
        subsystem_class = getattr(self.unreal, "EditorUtilitySubsystem", None)
        if subsystem_class is None:
            return None
        return self.unreal.get_editor_subsystem(subsystem_class)


def get_widget_launch_plan(unreal_module=None):
    return UnrealEditorWidgetLauncher(unreal_module).launch_plan()


def launch_asset_forge_widget(unreal_module=None):
    return UnrealEditorWidgetLauncher(unreal_module).launch()
