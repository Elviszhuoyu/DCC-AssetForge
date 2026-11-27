"""Register DCC AssetForge Unreal editor menu and toolbar actions."""

from __future__ import absolute_import

import json
import os

from asset_forge.unreal.editor_widget_model import build_package_summary
from asset_forge.unreal.operation_logger import UnrealOperationLogger
from asset_forge.unreal.unreal_bridge import get_unreal


MENU_ENTRY_NAME = "AssetForge.ImportPackage"
MENU_LABEL = "DCC AssetForge 导入门禁工作台"
MENU_TOOLTIP = "打开 DCC AssetForge 导出包扫描、预检、审批和导入历史工作台。"
MENU_COMMAND = (
    "from asset_forge.unreal.editor_widget_launcher import launch_asset_forge_widget; "
    "launch_asset_forge_widget()"
)


def register_asset_forge_menus(unreal_module=None):
    unreal = unreal_module or get_unreal()
    report = {
        "status": "skipped",
        "registered": [],
        "issues": [],
        "command": MENU_COMMAND,
    }
    if unreal is None:
        report["issues"].append("Unreal Python module is unavailable.")
        return report

    tool_menus_class = getattr(unreal, "ToolMenus", None)
    if tool_menus_class is None or not hasattr(tool_menus_class, "get"):
        report["issues"].append("unreal.ToolMenus is unavailable.")
        return report

    menus = tool_menus_class.get()
    main_menu = ("LevelEditor.MainMenu.Tools", "AssetForge")
    if _add_menu_entry(unreal, menus, main_menu[0], main_menu[1]):
        report["registered"].append(main_menu[0])
    else:
        report["issues"].append("Unable to register menu entry: {0}".format(main_menu[0]))

    toolbar_registered = False
    for menu_name, section_name in [
        ("LevelEditor.LevelEditorToolBar.User", "AssetForge"),
        ("LevelEditor.LevelEditorToolBar", "AssetForge"),
    ]:
        if _add_menu_entry(unreal, menus, menu_name, section_name):
            report["registered"].append(menu_name)
            toolbar_registered = True
            break
    if not toolbar_registered:
        report["issues"].append("Unable to register toolbar entry: LevelEditor.LevelEditorToolBar.User or LevelEditor.LevelEditorToolBar")

    from asset_forge.unreal.review_editor import register_review_menus
    register_review_menus(unreal, menus)

    if hasattr(menus, "refresh_all_widgets"):
        menus.refresh_all_widgets()

    report["status"] = "success" if report["registered"] else "warning"
    _log_operation("unreal_menu_register", report["status"], outputs=report, warnings=report["issues"])
    return report


def run_accept_flow_from_directory_dialog(default_path="", unreal_module=None):
    default_path = default_path or latest_maya_package_dir()
    package_dir = choose_package_directory(default_path, unreal_module)
    if not package_dir:
        message = "没有找到 DCC AssetForge 导出包。请先从 DCC 导出一次，再打开 DCC AssetForge 门禁。"
        report = {"status": "error", "message": message, "default_path": default_path}
        _notify_user("DCC AssetForge Import", message, unreal_module)
        _log_operation("unreal_menu_accept_flow", "error", outputs=report, errors=[message])
        return report
    if not _confirm_import_package(package_dir, unreal_module):
        report = {"status": "cancelled", "message": "用户取消导入。", "package_dir": package_dir}
        _log_operation("unreal_menu_accept_flow", "cancelled", inputs={"package_dir": package_dir}, outputs=report)
        _notify_user("DCC AssetForge Import", "已取消导入：\n{0}".format(package_dir), unreal_module)
        return report
    _notify_user("DCC AssetForge Import", "开始导入：\n{0}".format(package_dir), unreal_module)
    return run_accept_flow_for_package_dir(package_dir, unreal_module=unreal_module, confirmed=True)


def run_accept_flow_for_package_dir(package_dir, report_path=None, unreal_module=None, confirmed=False, import_options=None):
    from asset_forge.unreal.acceptance_runner import run_asset_forge_package_acceptance

    if not confirmed:
        report = {"status": "cancelled", "message": "导入需要用户明确确认。", "package_dir": package_dir}
        _notify_user("DCC AssetForge Import", "导入需要用户明确确认：\n{0}".format(package_dir), unreal_module)
        _log_operation("unreal_menu_accept_flow", "cancelled", inputs={"package_dir": package_dir}, outputs=report)
        return report

    report = run_asset_forge_package_acceptance(
        package_dir,
        report_path=report_path,
        run_import=True,
        auto_bootstrap_material_assets=False,
        require_import=True,
        import_options=import_options,
        command_args=["ue_menu", "--accept-flow", "--run-import", package_dir],
    )
    _log_operation(
        "unreal_menu_accept_flow",
        report.get("status", ""),
        inputs={"package_dir": package_dir, "import_options": dict(import_options or {})},
        outputs={
            "report_path": report.get("report_path", ""),
            "status": report.get("status", ""),
            "gate_passed": report.get("gate_passed", None),
        },
        warnings=report.get("warnings", []),
        errors=report.get("errors", []),
        report_path=report.get("report_path", ""),
    )
    _log_unreal("DCC AssetForge accept-flow finished: {0}".format(report.get("status", "")), unreal_module)
    _notify_user(
        "DCC AssetForge Import",
        "导入完成：{0}\n报告：{1}".format(report.get("status", ""), report.get("report_path", "")),
        unreal_module,
    )
    return report


def preview_gate_for_package_dir(package_dir, report_path=None, unreal_module=None, import_options=None):
    """Run the package gate check without writing UE assets."""
    from asset_forge.unreal.acceptance_runner import run_asset_forge_package_acceptance

    report = run_asset_forge_package_acceptance(
        package_dir,
        report_path=report_path,
        run_import=False,
        auto_bootstrap_material_assets=False,
        require_import=False,
        import_options=import_options,
        command_args=["ue_gate", "--check", package_dir],
    )
    report["ui_action"] = "gate_check"
    _log_operation(
        "unreal_gate_check",
        report.get("status", ""),
        inputs={"package_dir": package_dir, "import_options": dict(import_options or {})},
        outputs={
            "report_path": report.get("report_path", ""),
            "status": report.get("status", ""),
            "gate_passed": report.get("gate_passed", None),
        },
        warnings=report.get("warnings", []),
        errors=report.get("errors", []),
        report_path=report.get("report_path", ""),
    )
    _notify_user(
        "DCC AssetForge Gate",
        "检查报告完成：{0}\n报告：{1}".format(report.get("status", ""), report.get("report_path", "")),
        unreal_module,
    )
    return report


def dry_run_gate_for_package_dir(package_dir, report_path=None, unreal_module=None, import_options=None):
    """Run the package gate dry-run stage without writing UE assets."""
    from asset_forge.unreal.acceptance_runner import run_asset_forge_package_acceptance

    report = run_asset_forge_package_acceptance(
        package_dir,
        report_path=report_path,
        run_import=False,
        auto_bootstrap_material_assets=False,
        require_import=False,
        import_options=import_options,
        command_args=["ue_gate", "--dry-run", package_dir],
    )
    report["ui_action"] = "dry_run_gate"
    _log_operation(
        "unreal_gate_dry_run",
        report.get("status", ""),
        inputs={"package_dir": package_dir, "import_options": dict(import_options or {})},
        outputs={
            "report_path": report.get("report_path", ""),
            "status": report.get("status", ""),
            "gate_passed": report.get("gate_passed", None),
        },
        warnings=report.get("warnings", []),
        errors=report.get("errors", []),
        report_path=report.get("report_path", ""),
    )
    _notify_user(
        "DCC AssetForge Gate",
        "导入计划检查完成：{0}\n报告：{1}".format(report.get("status", ""), report.get("report_path", "")),
        unreal_module,
    )
    return report


_NATIVE_GATE = None


def _run_native_gate(action, package_dir, import_options=None, confirmation_token="", unreal_module=None):
    from asset_forge.unreal.gate_workbench import GateWorkbench

    global _NATIVE_GATE
    if _NATIVE_GATE is None:
        _NATIVE_GATE = GateWorkbench()
    report = _NATIVE_GATE.execute(action, package_dir, import_options, confirmation_token, unreal_module)
    _log_operation(
        "unreal_gate_workbench_" + action, report.get("status", ""),
        inputs={"package_dir": package_dir, "import_options": dict(import_options or {})},
        outputs={key: report.get(key) for key in ("gate_passed", "cache_hit", "import_succeeded", "timings_ms")},
        warnings=report["operator_warnings"], errors=report["operator_errors"], report_path=report.get("report_path", ""),
    )
    return report


def workbench_check_package(package_dir, import_options=None, unreal_module=None):
    return _run_native_gate("check", package_dir, import_options, unreal_module=unreal_module)


def workbench_dry_run_package(package_dir, import_options=None, unreal_module=None):
    return _run_native_gate("dry_run", package_dir, import_options, unreal_module=unreal_module)


def workbench_prepare_package(package_dir, import_options=None, unreal_module=None):
    return _run_native_gate("prepare", package_dir, import_options, unreal_module=unreal_module)


def workbench_apply_package(package_dir, import_options=None, confirmation_token="", unreal_module=None):
    return _run_native_gate("apply", package_dir, import_options, confirmation_token, unreal_module)


def workbench_read_reports(package_dir, import_options=None, report_path=None, unreal_module=None):
    from asset_forge.unreal.gate_workbench import GateWorkbench

    return (_NATIVE_GATE or GateWorkbench()).read_reports(package_dir, report_path, unreal_module)


def imported_review_paths(report, unreal_module=None):
    """Resolve only the StaticMeshes produced by this completed gate invocation."""
    if not report.get("run_import") or not report.get("gate_passed") or report.get("errors"):
        return []
    imported = report.get("import", {})
    if imported.get("status") not in ("success", "warning"):
        return []
    unreal = unreal_module or get_unreal()
    paths = []
    for path in imported.get("imported_assets", []):
        mesh = unreal.load_asset(path)
        if isinstance(mesh, unreal.StaticMesh) and mesh.get_path_name() not in paths:
            paths.append(mesh.get_path_name())
    return paths


def import_approved_package_dir(package_dir, report_path=None, unreal_module=None, import_options=None):
    """Import one selected package after the user confirms the Slate gate action."""
    if not _confirm_import_package(package_dir, unreal_module):
        report = {"status": "cancelled", "message": "用户取消导入。", "package_dir": package_dir}
        _log_operation("unreal_gate_import", "cancelled", inputs={"package_dir": package_dir}, outputs=report)
        _notify_user("DCC AssetForge Import", "已取消导入：\n{0}".format(package_dir), unreal_module)
        return report
    return run_accept_flow_for_package_dir(
        package_dir,
        report_path=report_path,
        unreal_module=unreal_module,
        confirmed=True,
        import_options=import_options,
    )


def cleanup_asset_forge_generated_props(package_dir="", report_path=None, unreal_module=None, import_options=None):
    """Clean old DCC AssetForge test-import folders under a UE target path."""
    options = import_options or {}
    unreal = unreal_module or get_unreal()
    target_path = _cleanup_target_path(package_dir, options)
    plan = _generated_props_cleanup_plan(target_path, unreal)
    if not plan["candidates"]:
        _notify_user("DCC AssetForge Cleanup", "没有发现可清理的历史测试目录：{0}".format(target_path), unreal)
        _log_operation("unreal_cleanup_generated_props", "skipped", inputs={"target_path": target_path}, outputs=plan)
        return plan
    if not options.get("confirmed_cleanup") and not _confirm_cleanup(plan, unreal):
        plan["status"] = "cancelled"
        _log_operation("unreal_cleanup_generated_props", "cancelled", inputs={"target_path": target_path}, outputs=plan)
        return plan

    library = getattr(unreal, "EditorAssetLibrary", None) if unreal is not None else None
    deleted = []
    failed = []
    for candidate in plan["candidates"]:
        path = candidate["path"]
        try:
            if library is not None and hasattr(library, "delete_directory") and library.delete_directory(path):
                deleted.append(path)
            else:
                failed.append(path)
        except Exception:
            failed.append(path)
    plan.update({"status": "success" if not failed else "warning", "deleted": deleted, "failed": failed})
    _log_operation("unreal_cleanup_generated_props", plan["status"], inputs={"target_path": target_path}, outputs=plan)
    _notify_user(
        "DCC AssetForge Cleanup",
        "清理完成：删除 {0} 个，失败 {1} 个。\n目标：{2}".format(len(deleted), len(failed), target_path),
        unreal,
    )
    return plan


def preview_generated_props_cleanup(package_dir="", unreal_module=None, import_options=None):
    """Return the safe cleanup candidate list without deleting UE assets."""
    options = import_options or {}
    unreal = unreal_module or get_unreal()
    target_path = _cleanup_target_path(package_dir, options)
    plan = _generated_props_cleanup_plan(target_path, unreal)
    plan["status"] = "preview" if plan.get("candidates") else "empty"
    plan["dry_run"] = True
    _log_operation("unreal_preview_generated_props_cleanup", plan["status"], inputs={"target_path": target_path}, outputs=plan)
    return plan


def choose_package_directory(default_path="", unreal_module=None):
    unreal = unreal_module or get_unreal()
    if unreal is None:
        return _normalize_path(default_path) if _is_asset_forge_package_dir(default_path) else ""
    desktop = getattr(unreal, "DesktopPlatform", None)
    if desktop is None or not hasattr(desktop, "open_directory_dialog"):
        return _normalize_path(default_path) if _is_asset_forge_package_dir(default_path) else ""

    title = "选择 DCC AssetForge 导出包目录"
    attempts = [
        (None, title, default_path or ""),
        (title, default_path or ""),
        (default_path or ""),
    ]
    for args in attempts:
        try:
            result = desktop.open_directory_dialog(*args)
        except TypeError:
            continue
        except Exception:
            return _normalize_path(default_path) if _is_asset_forge_package_dir(default_path) else ""
        selected_path = _directory_from_dialog_result(result)
        if selected_path:
            return selected_path
        return _normalize_path(default_path) if _is_asset_forge_package_dir(default_path) else ""
    return _normalize_path(default_path) if _is_asset_forge_package_dir(default_path) else ""


def latest_maya_package_dir(log_path=None):
    paths = [log_path] if log_path else _latest_maya_log_candidates()
    package_dir = ""
    for path in paths:
        if not path or not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8-sig", errors="replace") as stream:
            for line in stream:
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if entry.get("operation") == "export_success":
                    package_dir = (entry.get("outputs") or {}).get("package_dir", "") or package_dir
        if _is_asset_forge_package_dir(package_dir):
            break
    return package_dir.replace("\\", "/") if package_dir else ""


def _default_latest_maya_log():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(repo_root, "AssetForgeReports", "logs", "latest_maya.log")


def _latest_maya_log_candidates():
    candidates = []
    env_log = os.environ.get("ASSET_FORGE_LATEST_MAYA_LOG", "")
    if env_log:
        candidates.append(env_log)
    env_root = os.environ.get("ASSET_FORGE_SOURCE_ROOT", "")
    if env_root:
        candidates.append(os.path.join(env_root, "AssetForgeReports", "logs", "latest_maya.log"))
    metadata = _read_install_metadata()
    if metadata.get("source_latest_maya_log"):
        candidates.append(metadata.get("source_latest_maya_log"))
    if metadata.get("source_repo_root"):
        candidates.append(os.path.join(metadata.get("source_repo_root"), "AssetForgeReports", "logs", "latest_maya.log"))
    candidates.append(_default_latest_maya_log())
    unique = []
    for path in candidates:
        normalized = (path or "").replace("\\", "/")
        if normalized and normalized not in unique:
            unique.append(normalized)
    return unique


def _read_install_metadata():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "asset_forge_install.json")
    try:
        with open(path, "r", encoding="utf-8-sig") as stream:
            return json.load(stream)
    except Exception:
        return {}


def _is_asset_forge_package_dir(path):
    if not path or not os.path.isdir(path):
        return False
    try:
        names = os.listdir(path)
    except Exception:
        return False
    return any(name == "manifest.json" or name.endswith("_manifest.json") for name in names)


def _add_menu_entry(unreal, menus, menu_name, section_name):
    menu = _find_menu(menus, menu_name)
    if menu is None:
        return False
    entry = _make_menu_entry(unreal, menu_name)
    if entry is None:
        return False
    if hasattr(menu, "add_menu_entry"):
        menu.add_menu_entry(section_name, entry)
        return True
    return False


def _find_menu(menus, menu_name):
    if hasattr(menus, "find_menu"):
        menu = menus.find_menu(menu_name)
        if menu is not None:
            return menu
    if hasattr(menus, "extend_menu"):
        return menus.extend_menu(menu_name)
    return None


def _make_menu_entry(unreal, menu_name=""):
    entry_class = getattr(unreal, "ToolMenuEntry", None)
    if entry_class is None:
        return None

    kwargs = {"name": MENU_ENTRY_NAME}
    multi_block_type = getattr(unreal, "MultiBlockType", None)
    if multi_block_type is not None:
        if "ToolBar" in menu_name and hasattr(multi_block_type, "TOOL_BAR_BUTTON"):
            kwargs["type"] = multi_block_type.TOOL_BAR_BUTTON
        elif hasattr(multi_block_type, "MENU_ENTRY"):
            kwargs["type"] = multi_block_type.MENU_ENTRY
    try:
        entry = entry_class(**kwargs)
    except TypeError:
        entry = entry_class(MENU_ENTRY_NAME)

    if hasattr(entry, "set_label"):
        entry.set_label(MENU_LABEL)
    if hasattr(entry, "set_tool_tip"):
        entry.set_tool_tip(MENU_TOOLTIP)
    command_type = getattr(getattr(unreal, "ToolMenuStringCommandType", None), "PYTHON", None)
    if hasattr(entry, "set_string_command"):
        entry.set_string_command(command_type, "", MENU_COMMAND)
    else:
        entry.command = MENU_COMMAND
    return entry


def _directory_from_dialog_result(result):
    if isinstance(result, (list, tuple)):
        if len(result) >= 2 and result[0]:
            return str(result[1]).replace("\\", "/")
        if len(result) == 1:
            return str(result[0]).replace("\\", "/")
        return ""
    if result:
        return str(result).replace("\\", "/")
    return ""


def _normalize_path(path):
    return (path or "").replace("\\", "/")


def _cleanup_target_path(package_dir="", import_options=None):
    options = import_options or {}
    if options.get("cleanup_target_path"):
        return str(options.get("cleanup_target_path") or "/Game/Props")
    summary = build_package_summary(package_dir) if package_dir else {}
    return str(summary.get("target_path") or "/Game/Props")


def _generated_props_cleanup_plan(target_path="/Game/Props", unreal=None):
    target_path = _normalize_path(target_path or "/Game/Props").rstrip("/")
    protected = set(["Materials", "Textures"])
    prefixes = ("Blender", "Maya", "AssetForge")
    library = getattr(unreal, "EditorAssetLibrary", None) if unreal is not None else None
    directories = []
    if library is not None and hasattr(library, "list_assets"):
        try:
            assets = list(library.list_assets(target_path, False, True) or [])
        except TypeError:
            assets = list(library.list_assets(target_path, False) or [])
        for asset_path in assets:
            name = os.path.basename(str(asset_path).rstrip("/"))
            if name and name not in directories:
                directories.append(name)
    candidates = []
    for name in sorted(directories):
        if name in protected:
            continue
        if name.startswith(prefixes):
            candidates.append({"name": name, "path": "{0}/{1}".format(target_path, name)})
    return {
        "status": "ready" if candidates else "empty",
        "target_path": target_path,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "protected": sorted(protected),
        "rule": "只清理名称以 Blender / Maya / AssetForge 开头的历史测试目录；保留 Materials、Textures 和根目录规范资产。",
    }


def _confirm_cleanup(plan, unreal=None):
    dialog = getattr(unreal, "EditorDialog", None) if unreal is not None else None
    if dialog is None or not hasattr(dialog, "show_message"):
        return False
    names = ", ".join(item["name"] for item in plan.get("candidates", [])[:20])
    message = (
        "DCC AssetForge 历史导入清理\n\n"
        "目标路径：{0}\n"
        "候选目录：{1}\n\n"
        "{2}\n\n"
        "确认删除这些历史测试目录？"
    ).format(plan.get("target_path", ""), names, plan.get("rule", ""))
    msg_type = getattr(getattr(unreal, "AppMsgType", None), "YES_NO", None)
    try:
        result = dialog.show_message("DCC AssetForge Cleanup", message, msg_type)
    except TypeError:
        result = dialog.show_message("DCC AssetForge Cleanup", message)
    return _dialog_result_is_yes(result, unreal)


def _dialog_result_is_yes(result, unreal):
    if result is None:
        return False
    app_return_type = getattr(unreal, "AppReturnType", None) if unreal is not None else None
    yes_value = getattr(app_return_type, "YES", None) if app_return_type is not None else None
    if yes_value is not None:
        return result == yes_value
    text = str(result).lower()
    return text in ("yes", "ok", "true", "1")


def _existing_assets_under_target(target_path, unreal=None):
    if unreal is None:
        return []
    library = getattr(unreal, "EditorAssetLibrary", None)
    if library is None or not hasattr(library, "list_assets"):
        return []
    try:
        return list(library.list_assets(target_path, True, False) or [])
    except TypeError:
        try:
            return list(library.list_assets(target_path, True) or [])
        except Exception:
            return []
    except Exception:
        return []


def _confirm_import_package(package_dir, unreal_module=None):
    unreal = unreal_module or get_unreal()
    summary = _package_import_summary(package_dir, unreal)
    message = (
        "DCC AssetForge 导入门禁\n\n"
        "包体目录：\n{package_dir}\n\n"
        "Manifest：\n{manifest_path}\n\n"
        "资产：{asset_name}\n"
        "UE 目标：{target_path}\n"
        "包内数量：网格 {asset_count} / 贴图 {texture_count} / 材质实例 {material_count}\n"
        "目标路径现有资产：{existing_count}\n\n"
        "门禁：{gate_status_label} / 可导入：{can_accept}\n"
        "包体检查：{warning_count} 项警告 / {error_count} 项阻断\n"
        "覆盖策略：{overwrite_strategy}\n"
        "下一步：{next_action}\n\n"
        "UE 运行版本：{ue_runtime_version}\n"
        "工程版本标记：{engine_association}\n"
        "报告路径：\n{report_path}\n\n"
        "{duplicate_hint}\n\n"
        "本次只写入项目目标路径下的资产，不会重建 /AssetForge 插件母材质与默认贴图。\n"
        "确认导入？"
    ).format(**summary)
    dialog = getattr(unreal, "EditorDialog", None) if unreal is not None else None
    if dialog is None or not hasattr(dialog, "show_message"):
        _log_unreal("DCC AssetForge Import blocked because EditorDialog is unavailable.", unreal)
        return False
    msg_type = getattr(getattr(unreal, "AppMsgType", None), "YES_NO", None)
    try:
        result = dialog.show_message("DCC AssetForge Import", message, msg_type)
    except TypeError:
        result = dialog.show_message("DCC AssetForge Import", message)
    return _dialog_result_is_yes(result, unreal)


def _package_import_summary(package_dir, unreal=None):
    summary = build_package_summary(package_dir, _preview_package_acceptance(package_dir))
    target_path = summary.get("target_path", "") or "/Game/Props"
    existing_assets = _existing_assets_under_target(target_path, unreal)
    duplicate_hint = (
        "提示：目标路径已有资产，导入时会按同名网格、贴图和材质实例策略复用或更新。"
        if existing_assets
        else "目标路径下暂未发现现有资产。"
    )
    summary.update(
        {
            "manifest_path": summary.get("manifest_path", "") or "Not found",
            "existing_count": len(existing_assets),
            "existing_assets": existing_assets,
            "ue_runtime_version": _ue_runtime_version(unreal),
            "engine_association": _project_engine_association(unreal),
            "report_path": summary.get("report_path", "") or _default_accept_flow_report_path(package_dir),
            "duplicate_hint": duplicate_hint,
        }
    )
    return summary


def _preview_package_acceptance(package_dir):
    try:
        from asset_forge.unreal.package_acceptance import UnrealPackageAcceptanceValidator

        report_path = _default_accept_flow_report_path(package_dir)
        return UnrealPackageAcceptanceValidator().validate(package_dir, report_path=report_path)
    except Exception as exc:
        return {
            "status": "warning",
            "report_path": _default_accept_flow_report_path(package_dir),
            "summary": {
                "status": "warning",
                "can_accept": False,
                "warning_count": 1,
                "error_count": 0,
                "next_action": "门禁预检未能完成，请查看日志后重试。",
            },
            "warnings": [{"source": "editor_menu", "message": "门禁预检失败：{0}".format(exc)}],
            "errors": [],
        }


def _default_accept_flow_report_path(package_dir):
    try:
        from asset_forge.shared.report_artifacts import default_report_path

        return _normalize_path(default_report_path(package_dir, "package_acceptance_flow"))
    except Exception:
        return _normalize_path(os.path.join(package_dir, "AssetForgeReports", "package_acceptance_flow.json"))


def _read_json(path):
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as stream:
            return json.load(stream)
    except Exception:
        return {}


def _project_engine_association(unreal=None):
    project_path = _unreal_project_file_path(unreal)
    if not project_path:
        return "Unknown"
    data = _read_json(project_path)
    return str(data.get("EngineAssociation", "") or "Unknown")


def _unreal_project_file_path(unreal=None):
    if unreal is None:
        return ""
    paths = getattr(unreal, "Paths", None)
    if paths is not None and hasattr(paths, "get_project_file_path"):
        try:
            return paths.get_project_file_path()
        except Exception:
            return ""
    return ""


def _ue_runtime_version(unreal=None):
    if unreal is None:
        return "Unknown"
    system_library = getattr(unreal, "SystemLibrary", None)
    if system_library is not None and hasattr(system_library, "get_engine_version"):
        try:
            return str(system_library.get_engine_version() or "Unknown")
        except Exception:
            return "Unknown"
    return "Unknown"


def _log_operation(operation, status, inputs=None, outputs=None, warnings=None, errors=None, report_path=""):
    try:
        return UnrealOperationLogger().log(
            operation,
            status,
            inputs=inputs or {},
            outputs=outputs or {},
            warnings=warnings or [],
            errors=errors or [],
            report_path=report_path or "",
        )
    except Exception:
        return {}


def _log_unreal(message, unreal_module=None):
    unreal = unreal_module or get_unreal()
    if unreal is not None and hasattr(unreal, "log"):
        unreal.log(message)


def _notify_user(title, message, unreal_module=None):
    unreal = unreal_module or get_unreal()
    if unreal is None:
        return
    dialog = getattr(unreal, "EditorDialog", None)
    if dialog is not None and hasattr(dialog, "show_message"):
        msg_type = getattr(getattr(unreal, "AppMsgType", None), "OK", None)
        try:
            dialog.show_message(title, message, msg_type)
            return
        except TypeError:
            try:
                dialog.show_message(title, message)
                return
            except Exception:
                pass
        except Exception:
            pass
    if hasattr(unreal, "log_warning"):
        unreal.log_warning("{0}: {1}".format(title, message))
    elif hasattr(unreal, "log"):
        unreal.log("{0}: {1}".format(title, message))
