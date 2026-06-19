# -*- coding: utf-8 -*-
"""Whitelisted Maya actions exposed to the Asset Forge MCP bridge."""

from __future__ import absolute_import, print_function

import contextlib
import copy
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import traceback

from asset_forge.maya.cmds_bridge import get_cmds
from asset_forge.maya.operation_logger import MayaOperationLogger, latest_log_path, read_latest_log_tail
from asset_forge.maya.pipeline import ExportValidationError, MayaStaticPropPipeline
from asset_forge.maya.project_settings import default_project_settings, load_project_settings, normalize_project_settings
from asset_forge.maya.scanner import MayaAssetScanner
from asset_forge.shared.constants import ASSET_TYPE_STATIC_PROP, TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.path_utils import normalize_path


ACTION_VERSION = "0.2.0"
DEFAULT_TARGET_PATH = "/Game/Props"
DEFAULT_MESH_PREFIX = "SM_"
DEFAULT_TEXTURE_PREFIX = "T_"
DEFAULT_MATERIAL_PROFILE = "Props_Opaque_PainterUE_ARM"
_STATIC_PROP_UI_WINDOW = None
READONLY_PREFLIGHT_STEPS = [
    {
        "label": "读取 Maya 桥接状态",
        "action": "maya_status",
        "safety": "只读；不改场景、不改选择、不截取视口。",
    },
    {
        "label": "读取最近一次 Maya 日志",
        "action": "maya_get_latest_log",
        "safety": "只读；仅查看日志尾部，方便判断最近操作。",
    },
    {
        "label": "扫描当前静态道具",
        "action": "maya_scan_static_prop",
        "safety": "只读；只分析当前选择或已有上下文，不执行导出。",
    },
    {
        "label": "执行静态道具预检",
        "action": "maya_preflight_static_prop",
        "safety": "只读；只返回验证结果和阻塞项，不写入资源。",
    },
]


def dispatch_action(action, params=None):
    actions = {
        "maya_status": maya_status,
        "maya_load_asset_forge": maya_load_asset_forge,
        "maya_install_asset_forge_ui_shelf": maya_install_asset_forge_ui_shelf,
        "maya_install_mcp_bridge_shelf": maya_install_mcp_bridge_shelf,
        "maya_open_scene": maya_open_scene,
        "maya_import_fbx": maya_import_fbx,
        "maya_scan_static_prop": maya_scan_static_prop,
        "maya_preflight_static_prop": maya_preflight_static_prop,
        "maya_export_static_prop_package": maya_export_static_prop_package,
        "maya_run_static_prop_ui_flow": maya_run_static_prop_ui_flow,
        "maya_get_latest_log": maya_get_latest_log,
        "maya_viewport_screenshot": maya_viewport_screenshot,
        "maya_reset_session": maya_reset_session,
        "maya_run_python": maya_run_python,
    }
    if action not in actions:
        raise ValueError("Unsupported Maya MCP action: {0}".format(action))
    return actions[action](params or {})


def maya_status(params=None):
    params = params or {}
    cmds = _require_cmds()
    scene_path = cmds.file(query=True, sceneName=True) or ""
    selected_nodes = _current_selection(cmds)
    asset_forge_loaded = _is_asset_forge_loaded()
    ui_state = _current_static_prop_ui_state()
    portfolio_ready, portfolio_reasons = _portfolio_capture_readiness(
        asset_forge_loaded,
        selected_nodes,
        ui_state,
    )
    latest_log = latest_log_path(params.get("repo_root"))
    return _result(
        "pass",
        can_accept=True,
        next_action="Maya bridge 可用；下一步可执行 maya_load_asset_forge 或 preflight/export。",
        maya_version=cmds.about(version=True),
        scene_path=normalize_path(scene_path),
        selected_nodes=selected_nodes,
        asset_forge_loaded=asset_forge_loaded,
        repo_root=normalize_path(params.get("repo_root") or _repo_root()),
        bridge_version=ACTION_VERSION,
        latest_maya_log=latest_log,
        current_ui_state=ui_state,
        portfolio_capture_ready=portfolio_ready,
        portfolio_capture_ready_reasons=portfolio_reasons,
        portfolio_preflight_card=_portfolio_preflight_card(
            portfolio_ready,
            portfolio_reasons,
            asset_forge_loaded,
            selected_nodes,
            ui_state,
            latest_log,
        ),
        readonly_preflight_actions=[step["action"] for step in READONLY_PREFLIGHT_STEPS],
        readonly_preflight_steps=copy.deepcopy(READONLY_PREFLIGHT_STEPS),
    )


def maya_load_asset_forge(params=None):
    params = params or {}
    repo_root = normalize_path(params.get("repo_root") or _repo_root())
    open_ui = bool(params.get("open_ui", False))
    launcher = _load_python_file("asset_forge_maya_mcp_launcher", os.path.join(repo_root, "scripts", "maya_launch_asset_forge.py"))
    info = launcher.bootstrap(repo_root=repo_root, open_ui=open_ui, quiet=True)
    if not isinstance(info, dict):
        info = {"repo_root": repo_root, "opened_window": str(info or "")}
    output = _result(
        "success",
        can_accept=True,
        next_action="Asset Forge 已加载当前仓库版本；下一步可执行 maya_open_scene 或 maya_preflight_static_prop。",
        repo_root=normalize_path(info.get("repo_root", repo_root)),
        entry_script=normalize_path(info.get("entry_script", "")),
        module_file=normalize_path(info.get("module_file", "")),
        purged_module_count=len(info.get("purged_modules", [])),
        opened_ui=open_ui,
        opened_window=info.get("opened_window", ""),
    )
    _logger(repo_root).log("mcp_load_asset_forge", "success", inputs=params, outputs=output)
    return output


def maya_install_asset_forge_ui_shelf(params=None):
    params = params or {}
    repo_root = normalize_path(params.get("repo_root") or _repo_root())
    shelf_name = params.get("shelf_name") or "AssetForge"
    launcher = _load_python_file("asset_forge_maya_mcp_launcher", os.path.join(repo_root, "scripts", "maya_launch_asset_forge.py"))
    output = launcher.install_ui_shelf_button(repo_root=repo_root, shelf_name=shelf_name)
    output["repo_root"] = normalize_path(output.get("repo_root", repo_root))
    output["icon"] = normalize_path(output.get("icon", ""))
    _logger(repo_root).log("mcp_install_asset_forge_ui_shelf", "success", inputs=params, outputs=output)
    return output


def maya_install_mcp_bridge_shelf(params=None):
    params = params or {}
    repo_root = normalize_path(params.get("repo_root") or _repo_root())
    launcher = _load_python_file("asset_forge_maya_mcp_launcher", os.path.join(repo_root, "scripts", "maya_launch_asset_forge.py"))
    output = launcher.install_bridge_shelf_button(repo_root=repo_root)
    output["repo_root"] = normalize_path(output.get("repo_root", repo_root))
    output["icon"] = normalize_path(output.get("icon", ""))
    _logger(repo_root).log("mcp_install_mcp_bridge_shelf", "success", inputs=params, outputs=output)
    return output


def maya_open_scene(params=None):
    params = params or {}
    cmds = _require_cmds()
    scene_path = normalize_path(_required(params, "scene_path"))
    if not os.path.exists(scene_path):
        raise RuntimeError("找不到 Maya 场景文件: {0}".format(scene_path))
    if bool(params.get("save_current", False)):
        cmds.file(save=True)
    cmds.file(scene_path, open=True, force=bool(params.get("force", True)), prompt=False)
    current_scene = normalize_path(cmds.file(query=True, sceneName=True) or "")
    output = _result(
        "success",
        can_accept=True,
        next_action="场景已打开；下一步选择资产或传入 selection 后执行 maya_preflight_static_prop。",
        scene_path=current_scene,
    )
    _logger(params.get("repo_root")).log("mcp_open_scene", "success", inputs=params, outputs=output)
    return output


def maya_import_fbx(params=None):
    params = params or {}
    cmds = _require_cmds()
    fbx_path = normalize_path(_required(params, "fbx_path"))
    repo_root = params.get("repo_root")
    if not os.path.exists(fbx_path):
        output = _import_error(fbx_path, "找不到 FBX 文件: {0}".format(fbx_path))
        _logger(repo_root).log("mcp_import_fbx", "error", inputs=params, outputs=output, errors=output["errors"])
        return output

    namespace = str(params.get("namespace") or "AFMCP")
    new_scene = bool(params.get("new_scene", True))
    select_imported = bool(params.get("select_imported", True))
    rename_root = str(params.get("rename_root") or "")
    group_imported = bool(params.get("group_imported", True))
    force_load_plugin = bool(params.get("force_load_plugin", True))

    try:
        if force_load_plugin:
            _load_fbx_plugin(cmds)
        if new_scene:
            cmds.file(new=True, force=True)
        before_roots = _scene_assemblies(cmds)
        imported_nodes = _import_fbx_file(cmds, fbx_path, namespace)
        imported_roots = _imported_roots(cmds, imported_nodes, before_roots)
        if not imported_roots:
            output = _import_error(fbx_path, "FBX 导入没有产生可用根节点。", imported_nodes=imported_nodes)
            _logger(repo_root).log("mcp_import_fbx", "error", inputs=params, outputs=output, errors=output["errors"])
            return output
        selected = _stable_import_root(cmds, imported_roots, rename_root, group_imported)
        if select_imported:
            cmds.select(selected, replace=True)
        scan = MayaStaticPropPipeline().scan_assets(selected)
        if int(scan.get("mesh_count") or 0) <= 0:
            output = _import_error(
                fbx_path,
                "FBX 已导入，但选定根节点下没有 mesh，无法进入 Static Prop 流程。",
                imported_roots=imported_roots,
                selected=selected,
                scan=scan,
            )
            _logger(repo_root).log("mcp_import_fbx", "error", inputs=params, outputs=output, errors=output["errors"])
            return output
        output = _result(
            "success",
            can_accept=True,
            next_action="FBX 已导入并选中稳定资产根；下一步可直接执行 maya_preflight_static_prop。",
            fbx_path=fbx_path,
            imported_roots=imported_roots,
            selected=selected,
            mesh_count=scan.get("mesh_count", 0),
            materials=scan.get("materials", []),
            scan=scan,
        )
        _logger(repo_root).log("mcp_import_fbx", "success", inputs=params, outputs=output)
        return output
    except Exception as exc:
        output = _import_error(fbx_path, str(exc))
        _logger(repo_root).log("mcp_import_fbx", "error", inputs=params, outputs=output, errors=output["errors"])
        return output


def maya_scan_static_prop(params=None):
    params = params or {}
    preflight = _run_preflight(params)
    scan = preflight["scan"]
    validation = preflight["validation"]
    return _compact_static_prop_result("maya_scan_static_prop", scan, validation, preflight.get("texture_folder_scan", {}))


def maya_preflight_static_prop(params=None):
    params = params or {}
    preflight = _run_preflight(params)
    scan = preflight["scan"]
    validation = preflight["validation"]
    output = _compact_static_prop_result("maya_preflight_static_prop", scan, validation, preflight.get("texture_folder_scan", {}))
    _logger(params.get("repo_root")).log("mcp_preflight_static_prop", output["status"], inputs=params, outputs=output, warnings=output["warnings"], errors=output["errors"])
    return output


def maya_export_static_prop_package(params=None):
    params = params or {}
    selection = _select_nodes(params.get("selection"))
    if not selection:
        raise RuntimeError("没有选中资产，也没有传入 selection。")
    settings = _settings(params)
    pipeline = MayaStaticPropPipeline()
    rules = _active_rules(pipeline.rules, settings)
    try:
        result = pipeline.export_assets(
            selection,
            settings["export_root"],
            settings["target_platform"],
            settings["ue_target_path"],
            True,
        settings["material_profile"],
        settings["texture_root"],
        settings["texture_set_token"],
        settings["asset_name_override"],
        rules=rules,
        texture_import_policy=_texture_import_policy(settings),
        static_mesh_import_policy=_static_mesh_import_policy(settings),
        )
    except ExportValidationError as exc:
        output = _compact_static_prop_result("maya_export_static_prop_package", exc.scan, exc.validation, (exc.scan or {}).get("texture_folder_scan", {}))
        output.update(
            {
                "status": "error",
                "ui_flow": False,
                "evidence_kind": "backend_action",
                "can_continue_to_ue": False,
                "debug_report_path": normalize_path(exc.debug_report_path),
                "next_action": "Maya 预检阻断导出；这是后端 action 证据，不等同于 Maya 前端验收。按 errors 中的 next_action 修复后重新执行 UI flow。",
            }
        )
        _logger(params.get("repo_root")).log("mcp_export_static_prop_package", "error", inputs=params, outputs=output, errors=output["errors"], report_path=exc.debug_report_path)
        return output

    scan = result.get("scan", {})
    validation = result.get("validation", {})
    warnings, errors = _checks_by_status(validation)
    output = _result(
        "success",
        can_accept=True,
        next_action="Maya package 已导出；这是后端 action 证据，不等同于 Maya 前端验收。正式验收请运行 maya_run_static_prop_ui_flow。",
        ui_flow=False,
        evidence_kind="backend_action",
        asset_name=scan.get("asset_name", ""),
        package_dir=normalize_path(result.get("package_dir", "")),
        manifest_path=normalize_path(result.get("manifest_path", "")),
        fbx_path=normalize_path(result.get("fbx_path", "")),
        export_report_path=normalize_path(result.get("export_report_path", "")),
        latest_maya_log=latest_log_path(params.get("repo_root")),
        can_continue_to_ue=True,
        warnings=warnings,
        errors=errors,
    )
    _logger(params.get("repo_root")).log("mcp_export_static_prop_package", "success", inputs=params, outputs=output, warnings=warnings, errors=errors, report_path=output["export_report_path"])
    return output


def maya_run_static_prop_ui_flow(params=None):
    params = params or {}
    selection = _select_nodes(params.get("selection"))
    if not selection:
        raise RuntimeError("No selected asset and no selection parameter was provided.")

    settings = _ui_flow_settings(params)
    window, opened_ui = _get_or_create_static_prop_ui_window()
    _apply_ui_settings(window, settings)
    steps = []
    captured = {"export_result": {}, "renamed": []}

    try:
        _run_ui_callback(window, steps, "scan", "_scan", require_scan=True)
        if _scan_needs_prefix_fix(window.last_scan, settings["mesh_prefix"]):
            captured["renamed"] = _capture_rename_prefix(window, steps)
            _run_ui_callback(window, steps, "preflight_after_rename", "_validate", require_validation=True)
        else:
            _run_ui_callback(window, steps, "preflight", "_validate", require_validation=True)

        texture_scanned = False
        if settings.get("texture_root") and bool(params.get("scan_texture_dir", True)):
            _run_ui_callback(window, steps, "scan_texture_folder", "_scan_texture_folder")
            texture_scanned = True
        if bool(params.get("fix_texture_prefix", False)):
            _run_ui_callback(window, steps, "fix_texture_prefix", "_rename_texture_prefix")
            texture_scanned = True
        if texture_scanned:
            _run_ui_callback(window, steps, "preflight_after_texture", "_validate", require_validation=True)

        captured["export_result"] = _capture_ui_export(window, steps)
    except Exception as exc:
        steps.append(_ui_step_evidence(window, "ui_flow", "", "error", str(exc)))

    export_result = captured.get("export_result") or {}
    scan = export_result.get("scan") or getattr(window, "last_scan", {}) or {}
    validation = export_result.get("validation") or getattr(window, "last_validation", {}) or {}
    warnings, errors = _checks_by_status(validation)
    exported = bool(export_result.get("package_dir"))
    repair_actions = _repair_actions_for_state(scan, validation, getattr(window, "last_texture_scan", {}) or {})
    output = _result(
        "success" if exported else "error",
        can_accept=exported,
        next_action="Maya UI flow exported package; send package_dir to Unreal acceptance." if exported else _ui_step_next_action(scan, validation, getattr(window, "last_texture_scan", {}) or {}),
        ui_flow=True,
        evidence_kind="maya_ui_callback_flow",
        opened_ui=opened_ui,
        steps=steps,
        repair_actions=repair_actions,
        asset_name=scan.get("asset_name", ""),
        renamed=list(captured.get("renamed") or []),
        package_dir=normalize_path(export_result.get("package_dir", "")),
        manifest_path=normalize_path(export_result.get("manifest_path", "")),
        fbx_path=normalize_path(export_result.get("fbx_path", "")),
        export_report_path=normalize_path(export_result.get("export_report_path", "")),
        latest_maya_log=latest_log_path(params.get("repo_root")),
        texture_folder_scan=getattr(window, "last_texture_scan", {}) or {},
        asset_health_report=scan.get("asset_health_report", {}) or validation.get("asset_health_report", {}),
        material_texture_bindings=scan.get("material_texture_bindings", []),
        material_texture_binding_risks=scan.get("material_texture_binding_risks", []),
        warnings=warnings,
        errors=errors,
        can_continue_to_ue=exported,
    )
    _logger(params.get("repo_root")).log(
        "mcp_run_static_prop_ui_flow",
        output["status"],
        inputs=params,
        outputs=output,
        warnings=warnings,
        errors=errors,
        report_path=output["export_report_path"],
    )
    return output


def maya_get_latest_log(params=None):
    params = params or {}
    root = params.get("repo_root")
    tail = int(params.get("tail") or 200)
    path = latest_log_path(root)
    entries = read_latest_log_tail(root, tail)
    return _result(
        "success" if entries else "warning",
        can_accept=True,
        next_action="如日志为空，请先在 Maya 中执行一次 Asset Forge 操作。",
        latest_maya_log=path,
        entries=entries,
        entry_count=len(entries),
    )


def maya_viewport_screenshot(params=None):
    params = params or {}
    cmds = _require_cmds()
    output_path = normalize_path(_required(params, "output_path"))
    parent = os.path.dirname(output_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    width = int(params.get("width") or 1280)
    height = int(params.get("height") or 720)
    current_time = cmds.currentTime(query=True)
    result_path = cmds.playblast(
        frame=current_time,
        format="image",
        filename=output_path,
        viewer=False,
        showOrnaments=True,
        forceOverwrite=True,
        widthHeight=(width, height),
        percent=100,
        compression="png",
    )
    resolved_path = _resolve_playblast_image_path(result_path or output_path, output_path, current_time)
    alpha_flattened, flatten_warning = _flatten_png_alpha_to_rgb(resolved_path)
    warnings = []
    if flatten_warning:
        warnings.append({"id": "viewport_screenshot_alpha_flatten", "message": flatten_warning})
    return _result(
        "success",
        can_accept=True,
        next_action="截图已保存；它只作为辅助证据，最终验收仍以 report/manifest/log 为准。",
        warnings=warnings,
        output_path=resolved_path,
        playblast_template_path=normalize_path(result_path or output_path),
        alpha_flattened=alpha_flattened,
        width=width,
        height=height,
    )


def _resolve_playblast_image_path(result_path, requested_path, frame):
    """Return the concrete playblast image when Maya reports a #### template."""
    frame_number = int(round(float(frame or 0)))
    candidates = []
    for path in (result_path, requested_path):
        normalized = normalize_path(path or "")
        if not normalized:
            continue
        candidates.append(normalized)
        if "#" in normalized:
            candidates.append(
                re.sub(
                    r"#+",
                    lambda match: str(frame_number).zfill(len(match.group(0))),
                    normalized,
                    count=1,
                )
            )

    for candidate in candidates:
        if candidate and "#" not in candidate and os.path.exists(candidate):
            return normalize_path(candidate)
    for candidate in candidates:
        if candidate and "#" not in candidate:
            return normalize_path(candidate)
    return normalize_path(result_path or requested_path)


def _flatten_png_alpha_to_rgb(image_path, background_rgb=(83, 83, 83)):
    """Maya playblast PNG can contain alpha; flatten it so evidence screenshots do not look translucent."""
    if not image_path or not os.path.exists(image_path):
        return False, ""
    try:
        from PIL import Image
    except Exception:
        return False, "截图包含透明通道时可能被查看器显示成半透明；当前 Python 环境没有 Pillow，无法自动压成实心背景。"

    try:
        with Image.open(image_path) as image:
            if "A" not in image.mode:
                return False, ""
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            if alpha.getextrema() == (255, 255):
                return False, ""
            background = Image.new("RGBA", rgba.size, background_rgb + (255,))
            background.alpha_composite(rgba)
            background.convert("RGB").save(image_path, "PNG")
            return True, ""
    except Exception as exc:
        return False, "截图透明通道压平失败：{0}".format(exc)


def maya_reset_session(params=None):
    params = params or {}
    cmds = _require_cmds()
    cmds.select(clear=True)
    if bool(params.get("new_scene", False)):
        cmds.file(new=True, force=True)
    purged = []
    if bool(params.get("purge_asset_forge_modules", False)):
        purged = _purge_asset_forge_modules()
    return _result(
        "success",
        can_accept=True,
        next_action="Maya session 已重置；下一步可重新 load/open/preflight。",
        purged_module_count=len(purged),
    )


def maya_run_python(params=None):
    params = params or {}
    allow = os.environ.get("ASSET_FORGE_MAYA_MCP_ALLOW_PYTHON") == "1"
    if not allow:
        return _result(
            "error",
            can_accept=False,
            next_action="开发逃生口默认关闭；仅在本机环境变量 ASSET_FORGE_MAYA_MCP_ALLOW_PYTHON=1 后使用。",
            errors=[{"source": "maya_run_python", "message": "任意 Python 执行未启用。"}],
        )
    code = params.get("code", "")
    if not code:
        raise RuntimeError("maya_run_python 需要 code 参数。")
    stdout = io.StringIO()
    local_scope = {"cmds": _require_cmds()}
    try:
        with contextlib.redirect_stdout(stdout):
            exec(compile(code, "<maya_mcp_run_python>", "exec"), local_scope, local_scope)
        status = "success"
        errors = []
    except Exception:
        status = "error"
        errors = [{"source": "maya_run_python", "message": traceback.format_exc()}]
    text = stdout.getvalue()
    limit = int(params.get("max_output_chars") or 6000)
    output = _result(
        status,
        can_accept=status == "success",
        next_action="生产验收流不要依赖 maya_run_python；请把稳定能力沉淀为白名单 action。",
        stdout=text[:limit],
        truncated=len(text) > limit,
        errors=errors,
    )
    _logger(params.get("repo_root")).log("mcp_run_python", status, inputs={"code_length": len(code)}, outputs={"stdout_length": len(text)}, errors=errors)
    return output


def _run_preflight(params):
    selection = _select_nodes(params.get("selection"))
    if not selection:
        raise RuntimeError("没有选中资产，也没有传入 selection。")
    settings = _settings(params)
    pipeline = MayaStaticPropPipeline()
    return pipeline.preflight_assets(
        selection,
        target_platform=settings["target_platform"],
        material_profile=settings["material_profile"],
        texture_folder=settings["texture_root"],
        texture_set_token=settings["texture_set_token"],
        target_path=settings["ue_target_path"],
        asset_name_override=settings["asset_name_override"],
        rules=_active_rules(pipeline.rules, settings),
        texture_import_policy=_texture_import_policy(settings),
        static_mesh_import_policy=_static_mesh_import_policy(settings),
    )


def _settings(params):
    base = default_project_settings()
    if params.get("project_settings_path"):
        base.update(load_project_settings(params.get("project_settings_path")))
    aliases = {
        "export_root": "export_root",
        "texture_dir": "texture_root",
        "texture_folder": "texture_root",
        "texture_root": "texture_root",
        "texture_set_token": "texture_set_token",
        "asset_name_override": "asset_name_override",
        "export_asset_name": "asset_name_override",
        "target_path": "ue_target_path",
        "ue_target_path": "ue_target_path",
        "target_platform": "target_platform",
        "material_profile": "material_profile",
        "triangle_budget": "triangle_budget",
        "mesh_prefix": "mesh_prefix",
        "virtual_texture_policy": "virtual_texture_policy",
        "texture_streaming_policy": "texture_streaming_policy",
        "texture_group": "texture_group",
        "nanite_policy": "nanite_policy",
        "static_mesh_lod_group": "static_mesh_lod_group",
        "static_mesh_lod_import_policy": "static_mesh_lod_import_policy",
        "build_reversed_index_buffer": "build_reversed_index_buffer",
        "generate_lightmap_uvs": "generate_lightmap_uvs",
        "collision_complexity": "collision_complexity",
    }
    for source, target in aliases.items():
        if source in params and params.get(source) not in (None, ""):
            base[target] = params.get(source)
    if not base.get("export_root"):
        base["export_root"] = normalize_path(os.path.join(_repo_root(), "AssetForgeReports", "mcp_runs"))
    return normalize_project_settings(base)


def _ui_flow_settings(params):
    active = _settings(params)
    active["ue_target_path"] = params.get("target_path") or params.get("ue_target_path") or active.get("ue_target_path") or DEFAULT_TARGET_PATH
    active["mesh_prefix"] = params.get("mesh_prefix") or active.get("mesh_prefix") or DEFAULT_MESH_PREFIX
    active["texture_prefix"] = params.get("texture_prefix") or active.get("texture_prefix") or DEFAULT_TEXTURE_PREFIX
    active["material_profile"] = params.get("material_profile") or active.get("material_profile") or DEFAULT_MATERIAL_PROFILE
    active["texture_root"] = _ascii_safe_maya_ui_path(active.get("texture_root", ""))
    return normalize_project_settings(active)


def _ascii_safe_maya_ui_path(path):
    normalized = normalize_path(path or "")
    if not normalized or _is_ascii(normalized) or not os.path.isdir(normalized):
        return normalized
    if os.name != "nt":
        return normalized
    native_target = os.path.abspath(path)
    alias_root = os.path.join(_repo_root(), "AssetForgeReports", "runtime_alias")
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    base_name = re.sub(r"[^0-9A-Za-z_]+", "_", os.path.basename(normalized)).strip("_") or "path"
    alias_path = os.path.join(alias_root, "{0}_{1}".format(base_name, digest))
    if os.path.isdir(alias_path):
        return normalize_path(alias_path)
    if os.path.exists(alias_path):
        return normalized
    if not os.path.isdir(alias_root):
        os.makedirs(alias_root)
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", alias_path, native_target],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return normalize_path(alias_path) if completed.returncode == 0 and os.path.isdir(alias_path) else normalized


def _is_ascii(value):
    try:
        value.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _get_or_create_static_prop_ui_window():
    global _STATIC_PROP_UI_WINDOW
    cmds = _require_cmds()
    try:
        from asset_forge.maya.ui import AssetForgeMayaWindow, WINDOW_NAME
    except Exception as exc:
        raise RuntimeError("Cannot load Asset Forge Maya UI: {0}".format(exc))

    if _STATIC_PROP_UI_WINDOW is not None and getattr(_STATIC_PROP_UI_WINDOW, "controls", None):
        try:
            if cmds.window(WINDOW_NAME, exists=True):
                return _STATIC_PROP_UI_WINDOW, False
        except Exception:
            return _STATIC_PROP_UI_WINDOW, False

    _STATIC_PROP_UI_WINDOW = AssetForgeMayaWindow()
    _STATIC_PROP_UI_WINDOW.show()
    return _STATIC_PROP_UI_WINDOW, True


def _apply_ui_settings(window, settings):
    if hasattr(window, "_apply_project_settings"):
        window._apply_project_settings(settings)


def _run_ui_callback(window, steps, name, callback_name, require_scan=False, require_validation=False):
    callback = getattr(window, callback_name)
    callback()
    message = ""
    status = "success"
    if require_scan and not getattr(window, "last_scan", None):
        status = "error"
        message = "UI callback did not produce last_scan."
    if require_validation and not getattr(window, "last_validation", None):
        status = "error"
        message = "UI callback did not produce last_validation."
    step = _ui_step_evidence(window, name, callback_name, status, message)
    steps.append(step)
    if status == "error":
        raise RuntimeError(message)


def _ui_step_evidence(window, name, callback_name, status, message=""):
    scan = getattr(window, "last_scan", {}) or {}
    validation = getattr(window, "last_validation", {}) or {}
    texture_scan = getattr(window, "last_texture_scan", {}) or {}
    warnings, errors = _checks_by_status(validation)
    return {
        "name": name,
        "callback": callback_name,
        "status": status,
        "asset_name": scan.get("asset_name", ""),
        "can_export": bool(validation.get("can_export", False)) if validation else None,
        "warnings": warnings,
        "errors": errors,
        "next_action": _ui_step_next_action(scan, validation, texture_scan),
        "repair_actions": _repair_actions_for_state(scan, validation, texture_scan),
        "message": message,
        "texture_matched_count": texture_scan.get("matched_count", 0) if texture_scan else 0,
        "selected_texture_sets": texture_scan.get("selected_texture_sets", []) if texture_scan else [],
    }


def _ui_step_next_action(scan, validation, texture_scan):
    try:
        from asset_forge.maya.ui import format_next_action_summary

        return format_next_action_summary(scan or {}, validation or {}, texture_scan or {})
    except Exception:
        errors = (validation or {}).get("checks", [])
        blocking = [item for item in errors if item.get("status") == "error"]
        if blocking:
            return blocking[0].get("next_action") or blocking[0].get("message", "")
        if (validation or {}).get("can_export"):
            return "可以导出当前选择。"
        return "继续执行 Maya UI flow 的下一步。"


def _repair_actions_for_state(scan, validation, texture_scan):
    try:
        from asset_forge.maya.ui import repair_actions_for_state

        return repair_actions_for_state(scan or {}, validation or {}, texture_scan or {})
    except Exception:
        return []


def _scan_needs_prefix_fix(scan, prefix):
    active_prefix = prefix or DEFAULT_MESH_PREFIX
    asset_name = (scan or {}).get("asset_name", "")
    if asset_name and not asset_name.startswith(active_prefix):
        return True
    for transform in (scan or {}).get("transforms", []):
        short_name = str(transform or "").split("|")[-1]
        if short_name and not short_name.startswith(active_prefix):
            return True
    return False


def _capture_rename_prefix(window, steps):
    pipeline = getattr(window, "pipeline", None)
    renamed = {"nodes": []}
    originals = {}
    for method_name in ("rename_asset_root_with_prefix", "rename_selection_with_prefix"):
        if pipeline is not None and hasattr(pipeline, method_name):
            original = getattr(pipeline, method_name)
            originals[method_name] = original

            def _make_wrapper(active_original):
                def _wrapper(*args, **kwargs):
                    result = active_original(*args, **kwargs)
                    renamed["nodes"].extend(list(result or []))
                    return result

                return _wrapper

            setattr(pipeline, method_name, _make_wrapper(original))
            break
    if pipeline is not None and hasattr(pipeline, "rename_mesh_transforms_with_prefix"):
        original = getattr(pipeline, "rename_mesh_transforms_with_prefix")
        originals["rename_mesh_transforms_with_prefix"] = original

        def _make_mesh_wrapper(active_original):
            def _mesh_wrapper(*args, **kwargs):
                result = active_original(*args, **kwargs)
                renamed["nodes"].extend(list(result or []))
                return result

            return _mesh_wrapper

        setattr(pipeline, "rename_mesh_transforms_with_prefix", _make_mesh_wrapper(original))
    try:
        previous_skip = getattr(window, "skip_confirmations", False)
        setattr(window, "skip_confirmations", True)
        _run_ui_callback(window, steps, "fix_asset_name_prefix", "_rename_prefix", require_scan=True)
    finally:
        setattr(window, "skip_confirmations", previous_skip)
        for method_name, original in originals.items():
            setattr(pipeline, method_name, original)
    return renamed["nodes"]


def _capture_ui_export(window, steps):
    pipeline = getattr(window, "pipeline", None)
    if pipeline is None or not hasattr(pipeline, "export_assets"):
        _run_ui_callback(window, steps, "export_current_selection", "_export")
        return {}
    original = pipeline.export_assets
    captured = {"result": {}}

    def _wrapper(*args, **kwargs):
        result = original(*args, **kwargs)
        captured["result"] = result or {}
        return result

    pipeline.export_assets = _wrapper
    try:
        _run_ui_callback(window, steps, "export_current_selection", "_export")
    finally:
        pipeline.export_assets = original
    return captured["result"]


def _active_rules(rules, settings):
    result = copy.deepcopy(rules or {})
    static_rules = result.setdefault(ASSET_TYPE_STATIC_PROP, {})
    budgets = dict(static_rules.get("max_triangles", {}))
    if int(settings.get("triangle_budget") or 0) > 0:
        budgets[settings.get("target_platform") or TARGET_PLATFORM_HIGH_END_MOBILE] = int(settings.get("triangle_budget"))
    static_rules["max_triangles"] = budgets
    static_rules["name_prefix"] = settings.get("mesh_prefix") or "SM_"
    return result


def _texture_import_policy(settings):
    return {
        "virtual_texture_policy": settings.get("virtual_texture_policy", "project_default"),
        "texture_streaming_policy": settings.get("texture_streaming_policy", "project_default"),
        "texture_group": settings.get("texture_group", "project_default"),
    }


def _static_mesh_import_policy(settings):
    return {
        "nanite_policy": settings.get("nanite_policy", "project_default"),
        "lod_group": settings.get("static_mesh_lod_group", "project_default"),
        "import_lod_policy": settings.get("static_mesh_lod_import_policy", "import_existing"),
        "build_reversed_index_buffer": settings.get("build_reversed_index_buffer", "report_only"),
        "generate_lightmap_uvs": settings.get("generate_lightmap_uvs", "report_only"),
        "collision_complexity": settings.get("collision_complexity", "report_only"),
    }


def _select_nodes(selection):
    cmds = _require_cmds()
    if selection:
        nodes = list(selection)
        cmds.select(nodes, replace=True)
        return nodes
    selected = list(cmds.ls(selection=True, long=True) or cmds.ls(selection=True) or [])
    if selected:
        return selected
    inferred = MayaAssetScanner(cmds).get_current_selection()
    if inferred:
        cmds.select(inferred, replace=True)
    return inferred


def _load_fbx_plugin(cmds):
    try:
        loaded = bool(cmds.pluginInfo("fbxmaya", query=True, loaded=True))
    except Exception:
        loaded = False
    if not loaded:
        cmds.loadPlugin("fbxmaya", quiet=True)


def _import_fbx_file(cmds, fbx_path, namespace):
    try:
        nodes = cmds.file(
            fbx_path,
            i=True,
            type="FBX",
            ignoreVersion=True,
            mergeNamespacesOnClash=False,
            namespace=namespace,
            options="fbx",
            preserveReferences=True,
            returnNewNodes=True,
        )
    except TypeError:
        nodes = cmds.file(
            fbx_path,
            i=True,
            type="FBX",
            ignoreVersion=True,
            mergeNamespacesOnClash=False,
            namespace=namespace,
            options="fbx",
            preserveReferences=True,
        )
    return list(nodes or [])


def _scene_assemblies(cmds):
    return set(cmds.ls(assemblies=True, long=True) or [])


def _imported_roots(cmds, imported_nodes, before_roots):
    imported_long = _long_nodes(cmds, imported_nodes)
    imported_transforms = [node for node in imported_long if _node_type(cmds, node) == "transform"]
    imported_set = set(imported_transforms)
    roots = []
    for transform in imported_transforms:
        parents = cmds.listRelatives(transform, parent=True, fullPath=True) or []
        if not parents or parents[0] not in imported_set:
            roots.append(transform)
    if not roots:
        after_roots = set(cmds.ls(assemblies=True, long=True) or [])
        roots = sorted(after_roots - set(before_roots or []))
    return _unique_paths(roots)


def _long_nodes(cmds, nodes):
    if not nodes:
        return []
    try:
        return list(cmds.ls(nodes, long=True) or nodes)
    except Exception:
        return list(nodes or [])


def _node_type(cmds, node):
    try:
        return cmds.nodeType(node)
    except Exception:
        return ""


def _stable_import_root(cmds, imported_roots, rename_root="", group_imported=True):
    roots = list(imported_roots or [])
    if group_imported and len(roots) > 1:
        group_name = rename_root or "SM_{0}".format(_safe_node_name("AFMCP_Imported"))
        grouped = cmds.group(roots, name=group_name, world=True)
        return _long_nodes(cmds, [grouped]) or [grouped]
    if rename_root and len(roots) == 1:
        renamed = cmds.rename(roots[0], rename_root)
        return _long_nodes(cmds, [renamed]) or [renamed]
    return roots


def _unique_paths(paths):
    result = []
    for path in paths or []:
        if path and path not in result:
            result.append(path)
    return result


def _safe_node_name(value):
    result = []
    for char in value or "":
        result.append(char if char.isalnum() or char == "_" else "_")
    return "".join(result) or "Imported"


def _import_error(fbx_path, message, imported_nodes=None, imported_roots=None, selected=None, scan=None):
    return _result(
        "error",
        can_accept=False,
        next_action="确认 FBX 路径、fbxmaya 插件和导入后 mesh 根节点；修复后重新执行 maya_import_fbx。",
        fbx_path=normalize_path(fbx_path),
        imported_nodes=list(imported_nodes or []),
        imported_roots=list(imported_roots or []),
        selected=list(selected or []),
        mesh_count=(scan or {}).get("mesh_count", 0),
        materials=(scan or {}).get("materials", []),
        errors=[{"source": "maya_import_fbx", "message": message}],
    )


def _compact_static_prop_result(stage, scan, validation, texture_folder_scan):
    warnings, errors = _checks_by_status(validation)
    can_export = bool((validation or {}).get("can_export", False))
    return _result(
        "pass" if can_export else "error",
        can_accept=can_export,
        next_action="可以执行 maya_export_static_prop_package。" if can_export else "修复 errors 中的阻断项后重新执行 preflight。",
        stage=stage,
        ui_flow=False,
        evidence_kind="backend_action",
        asset_name=(scan or {}).get("asset_name", ""),
        selected_nodes=(scan or {}).get("asset_roots", []),
        mesh_count=(scan or {}).get("mesh_count", 0),
        material_slots=(scan or {}).get("materials", []),
        texture_folder_scan=texture_folder_scan or {},
        asset_health_report=(scan or {}).get("asset_health_report", {}) or (validation or {}).get("asset_health_report", {}),
        material_texture_bindings=(scan or {}).get("material_texture_bindings", []),
        material_texture_binding_risks=(scan or {}).get("material_texture_binding_risks", []),
        repair_actions=_repair_actions_for_state(scan or {}, validation or {}, texture_folder_scan or {}),
        blocking_errors=errors,
        warnings=warnings,
        errors=errors,
        can_export=can_export,
        scan=scan or {},
        validation=validation or {},
    )


def _checks_by_status(validation):
    checks = list((validation or {}).get("checks", []))
    warnings = [item for item in checks if item.get("status") == "warning"]
    errors = [item for item in checks if item.get("status") == "error"]
    return warnings, errors


def _result(status, can_accept=False, next_action="", warnings=None, errors=None, **kwargs):
    data = {
        "status": status,
        "can_accept": bool(can_accept),
        "warnings": warnings or [],
        "errors": errors or [],
        "next_action": next_action,
    }
    data.update(kwargs)
    return data


def _required(params, name):
    value = params.get(name)
    if value in (None, ""):
        raise RuntimeError("缺少必填参数: {0}".format(name))
    return value


def _logger(root=None):
    return MayaOperationLogger(root=root or _repo_root())


def _require_cmds():
    cmds = get_cmds()
    if cmds is None:
        raise RuntimeError("maya.cmds is not available. 请在已启动的 Maya 中运行 bridge。")
    return cmds


def _is_asset_forge_loaded():
    return any(name == "asset_forge_maya" or name == "asset_forge" or name.startswith("asset_forge.") for name in sys.modules)


def _current_selection(cmds):
    try:
        return list(cmds.ls(selection=True) or [])
    except Exception:
        return []


def _current_static_prop_ui_state():
    window = _STATIC_PROP_UI_WINDOW
    if window is None:
        try:
            from asset_forge.maya.ui import WINDOW_NAME

            cmds = get_cmds()
            if cmds is not None and cmds.window(WINDOW_NAME, exists=True):
                return {
                    "ui_loaded": True,
                    "window": WINDOW_NAME,
                    "has_scan": False,
                    "has_validation": False,
                    "has_texture_scan": False,
                }
        except Exception:
            pass
        return {
            "ui_loaded": False,
            "has_scan": False,
            "has_validation": False,
            "has_texture_scan": False,
        }
    scan = getattr(window, "last_scan", None) or {}
    validation = getattr(window, "last_validation", None) or {}
    texture_scan = getattr(window, "last_texture_scan", None) or {}
    return {
        "ui_loaded": True,
        "window": (getattr(window, "controls", {}) or {}).get("window", ""),
        "has_scan": bool(scan),
        "has_validation": bool(validation),
        "has_texture_scan": bool(texture_scan),
        "asset_name": scan.get("asset_name", ""),
        "validation_status": validation.get("status", ""),
        "can_export": bool(validation.get("can_export", False)),
        "texture_directory_status": texture_scan.get("directory_status", ""),
        "texture_matched_count": int(texture_scan.get("matched_count") or 0),
    }


def _portfolio_capture_readiness(asset_forge_loaded, selected_nodes, ui_state=None):
    ui_state = ui_state or {}
    reasons = []
    if not asset_forge_loaded:
        reasons.append("Asset Forge 尚未在当前 Maya 会话中加载。")
    if not selected_nodes and not ui_state.get("has_scan"):
        reasons.append("当前没有选择 Maya 节点，Asset Forge UI 中也没有可用的扫描结果。")
    return not reasons, reasons


def _portfolio_preflight_card(ready, reasons, asset_forge_loaded, selected_nodes, ui_state, latest_log):
    ui_state = ui_state or {}
    selected_count = len(selected_nodes or [])
    has_scan = bool(ui_state.get("has_scan"))
    has_log = bool(latest_log and os.path.exists(latest_log))
    asset_name = ui_state.get("asset_name") or ""
    if ready:
        if ui_state.get("has_validation"):
            next_step = "可以录制：展示扫描和预检结果，再进入导出或 UE 导入验证。"
        elif has_scan:
            next_step = "可以录制：先展示已有扫描结果，再执行预检生成验收证据。"
        else:
            next_step = "可以录制：当前已有选择，下一步扫描静态道具。"
    elif not asset_forge_loaded:
        next_step = "先加载 Asset Forge Maya 工具，再刷新状态。"
    else:
        next_step = "先选择一个静态道具，或在 Asset Forge 面板完成一次扫描。"
    return {
        "can_record": bool(ready),
        "status_label": "可录制" if ready else "待补齐",
        "selected_count": selected_count,
        "has_selection": bool(selected_count),
        "has_scan": has_scan,
        "has_latest_log": has_log,
        "asset_name": asset_name,
        "next_step": next_step,
        "tips": list(reasons or []),
    }


def _purge_asset_forge_modules():
    purged = []
    for module_name in sorted(list(sys.modules.keys()), reverse=True):
        if module_name in ("asset_forge_maya", "asset_forge") or module_name.startswith("asset_forge."):
            purged.append(module_name)
            del sys.modules[module_name]
    return purged


def _load_python_file(module_name, path):
    if not os.path.exists(path):
        raise RuntimeError("找不到 Python 文件: {0}".format(path))
    if sys.version_info[0] >= 3:
        import importlib.util

        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    import imp

    return imp.load_source(module_name, path)


def _repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
