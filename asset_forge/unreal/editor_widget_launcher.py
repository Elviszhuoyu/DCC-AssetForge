"""Launch facade for the Asset Forge Unreal Gate UI."""

from __future__ import absolute_import

import os

from asset_forge.unreal.editor_widget_actions import UnrealEditorWidgetActions
from asset_forge.unreal.editor_widget_model import build_gate_panel_state, format_gate_panel_text
from asset_forge.unreal.editor_widget_schema import get_editor_widget_plan, validate_editor_widget_plan
from asset_forge.unreal.unreal_bridge import get_unreal


class UnrealEditorWidgetLauncher(object):
    """Resolve the UMG widget, or open a Python-driven Gate when the asset is absent."""

    def __init__(self, unreal_module=None, widget_plan=None, actions=None, gate_state_builder=None):
        self.unreal = unreal_module or get_unreal()
        self.widget_plan = widget_plan or get_editor_widget_plan()
        self.actions = actions or UnrealEditorWidgetActions()
        self.gate_state_builder = gate_state_builder or build_gate_panel_state

    def launch_plan(self):
        issues = validate_editor_widget_plan(self.widget_plan)
        asset_path = self.widget_plan.get("asset_path", "")
        asset_exists = self._asset_exists(asset_path)
        widget_asset_report = {}
        warnings = []
        if self.unreal is not None:
            widget_asset_report = self._ensure_widget_asset()
            asset_exists = self._asset_exists(asset_path)
            if widget_asset_report.get("status") in ("warning", "error"):
                report_issues = list(widget_asset_report.get("issues", []))
                missing_widgets = widget_asset_report.get("missing_widgets", [])
                tree_unavailable = "widget_tree is unavailable" in report_issues
                if asset_exists and tree_unavailable:
                    warnings.extend(report_issues)
                    if missing_widgets:
                        warnings.append("editor widget tree was not readable from Python; existing EUW asset will be launched directly")
                else:
                    issues.extend(report_issues)
                if missing_widgets and not (asset_exists and tree_unavailable):
                    issues.append("editor widget tree rebuild incomplete: {0} missing widgets".format(len(missing_widgets)))
            if not asset_exists:
                issues.extend(widget_asset_report.get("issues", []))
        if not asset_exists:
            issues.append("missing editor widget asset: {0}".format(asset_path))

        return {
            "status": "ready" if not issues else "missing_asset",
            "asset_path": asset_path,
            "unreal_available": self.unreal is not None,
            "asset_exists": asset_exists,
            "widget_asset_report": widget_asset_report,
            "fallback_ui": self.widget_plan.get("fallback_ui", "python_editor_dialog_gate"),
            "fallback_available": self.unreal is not None and not asset_exists,
            "issues": issues,
            "warnings": warnings,
            "actions": [item.get("id", "") for item in self.widget_plan.get("actions", [])],
        }

    def launch(self):
        plan = self.launch_plan()
        if plan["status"] != "ready":
            if self.unreal is None:
                return plan
            return self._launch_python_gate(plan)
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

    def _launch_python_gate(self, plan):
        export_root = _default_export_root()
        state = self.gate_state_builder(export_root=export_root, report_path=False)
        selected_package = state.get("selected_package_dir", "")
        self._show_message("Asset Forge Gate", format_gate_panel_text(state))

        selected_package = self._choose_package_directory(selected_package or export_root)
        if not selected_package:
            plan.update(
                {
                    "status": "empty",
                    "ui_mode": "python_dialog_gate",
                    "message": "未选择 Asset Forge 导出包。",
                    "history": state.get("history", {}),
                }
            )
            return plan

        preview_state = self.gate_state_builder(package_dir=selected_package, export_root=export_root)
        selected = preview_state.get("selected_package", {}) or {}
        import_report = {}
        plan.update(
            {
                "ui_mode": "python_dialog_gate",
                "displayed_sections": ["package_history", "mesh_status", "texture_status", "material_status", "profile_status", "gate_status", "action_buttons"],
                "history": preview_state.get("history", {}),
                "selected_package_dir": selected_package,
                "selected_package": selected,
                "can_import": bool(selected.get("can_accept")),
                "report_path": selected.get("report_path", ""),
            }
        )

        if not selected.get("can_accept"):
            self._show_message("Asset Forge Gate", format_gate_panel_text(preview_state))
            plan["status"] = "gate_blocked"
            plan["message"] = selected.get("next_action", "请先修复门禁阻断项，然后重新预检。")
            return plan

        if not self._confirm_import(format_gate_panel_text(preview_state) + "\n\n现在导入这个包体吗？"):
            plan["status"] = "ready_to_import"
            plan["message"] = "预检已通过，导入动作保留给用户确认。"
            return plan

        import_report = self.actions.import_selected_package(selected_package, selected.get("report_path", None))
        plan["status"] = "imported" if import_report.get("status") in ("success", "warning", "skipped") else import_report.get("status", "import_finished")
        plan["import_report"] = import_report
        self._show_message(
            "Asset Forge Gate",
            "导入完成：{0}\n报告：{1}".format(import_report.get("status", ""), import_report.get("report_path", selected.get("report_path", ""))),
        )
        return plan

    def _show_message(self, title, message):
        dialog = getattr(self.unreal, "EditorDialog", None) if self.unreal is not None else None
        if dialog is not None and hasattr(dialog, "show_message"):
            msg_type = getattr(getattr(self.unreal, "AppMsgType", None), "OK", None)
            try:
                dialog.show_message(title, message, msg_type)
                return
            except TypeError:
                dialog.show_message(title, message)
                return
        if self.unreal is not None and hasattr(self.unreal, "log"):
            self.unreal.log("{0}: {1}".format(title, message))

    def _confirm_import(self, message):
        dialog = getattr(self.unreal, "EditorDialog", None) if self.unreal is not None else None
        if dialog is None or not hasattr(dialog, "show_message"):
            return False
        msg_type = getattr(getattr(self.unreal, "AppMsgType", None), "YES_NO", None)
        try:
            result = dialog.show_message("Asset Forge Gate", message, msg_type)
        except TypeError:
            result = dialog.show_message("Asset Forge Gate", message)
        return _dialog_result_is_yes(result, self.unreal)

    def _choose_package_directory(self, default_path=""):
        desktop = getattr(self.unreal, "DesktopPlatform", None) if self.unreal is not None else None
        if desktop is None or not hasattr(desktop, "open_directory_dialog"):
            return _normalize_path(default_path) if _is_package_dir(default_path) else ""
        title = "选择 Asset Forge 导出包目录"
        for args in [(None, title, default_path or ""), (title, default_path or ""), (default_path or "")]:
            try:
                result = desktop.open_directory_dialog(*args)
            except TypeError:
                continue
            except Exception:
                return _normalize_path(default_path) if _is_package_dir(default_path) else ""
            selected = _directory_from_dialog_result(result)
            return selected or (_normalize_path(default_path) if _is_package_dir(default_path) else "")
        return _normalize_path(default_path) if _is_package_dir(default_path) else ""

    def _asset_exists(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None) if self.unreal else None
        if library and hasattr(library, "does_asset_exist"):
            return bool(library.does_asset_exist(asset_path) or library.does_asset_exist(_object_path(asset_path)))
        return False

    def _load_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None) if self.unreal else None
        if library and hasattr(library, "load_asset"):
            return library.load_asset(asset_path) or library.load_asset(_object_path(asset_path))
        return None

    def _editor_utility_subsystem(self):
        if self.unreal is None or not hasattr(self.unreal, "get_editor_subsystem"):
            return None
        subsystem_class = getattr(self.unreal, "EditorUtilitySubsystem", None)
        if subsystem_class is None:
            return None
        return self.unreal.get_editor_subsystem(subsystem_class)

    def _ensure_widget_asset(self):
        try:
            from asset_forge.unreal.editor_widget_asset import ensure_editor_widget_asset

            return ensure_editor_widget_asset(self.unreal, self.widget_plan)
        except Exception as exc:
            return {"status": "error", "issues": ["widget asset generation failed: {0}".format(exc)]}


def get_widget_launch_plan(unreal_module=None):
    return UnrealEditorWidgetLauncher(unreal_module).launch_plan()


def launch_asset_forge_widget(unreal_module=None):
    return UnrealEditorWidgetLauncher(unreal_module).launch()


def _default_export_root():
    for env_name in ("ASSET_FORGE_EXPORT_ROOT", "ASSET_FORGE_PACKAGE_ROOT"):
        value = os.environ.get(env_name, "")
        if value:
            return _normalize_path(value)
    source_root = os.environ.get("ASSET_FORGE_SOURCE_ROOT", "")
    if source_root:
        return _normalize_path(os.path.join(source_root, "AssetForgeExports"))
    return ""


def _directory_from_dialog_result(result):
    if isinstance(result, (list, tuple)):
        if len(result) >= 2 and result[0]:
            return _normalize_path(result[1])
        if len(result) == 1:
            return _normalize_path(result[0])
        return ""
    return _normalize_path(result) if result else ""


def _dialog_result_is_yes(result, unreal):
    if result is None:
        return False
    app_return_type = getattr(unreal, "AppReturnType", None) if unreal is not None else None
    yes_value = getattr(app_return_type, "YES", None) if app_return_type is not None else None
    if yes_value is not None:
        return result == yes_value
    return str(result).lower() in ("yes", "ok", "true", "1")


def _normalize_path(path):
    return (str(path or "")).replace("\\", "/")


def _object_path(asset_path):
    if not asset_path or "." in asset_path:
        return asset_path
    name = asset_path.rsplit("/", 1)[-1]
    return asset_path + "." + name


def _is_package_dir(path):
    if not path or not os.path.isdir(path):
        return False
    try:
        names = os.listdir(path)
    except Exception:
        return False
    return any(name == "manifest.json" or name.endswith("_manifest.json") for name in names)
