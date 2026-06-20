"""Portfolio demo evidence pack for the short TA sprint."""

from __future__ import absolute_import

import os

from asset_forge.shared.report_artifacts import attach_report_artifact_metadata, default_report_path
from asset_forge.shared.report_schema import REPORT_VERSION, create_acceptance_summary, read_report, write_report


def create_portfolio_demo_pack(evidence_path=None, report_path=None, command_args=None):
    evidence = _read_evidence(evidence_path)
    steps = [
        _step(
            "pain_point",
            "痛点",
            "DCC 静态道具安全进入 UE，并保留可追踪报告。",
            "pass",
            ["sprint_scope"],
            "",
        ),
        _step(
            "maya_scan",
            "Maya 扫描与风险检查",
            "扫描资产、贴图集、材质槽，并把阻断项转成 repair actions。",
            _stage_status(evidence, "maya_ui_flow", fallback=_repair_action_status(evidence)),
            _stage_refs(evidence, "maya_ui_flow") + _repair_action_refs(evidence),
            "补真实 Maya UI 截图或录屏。",
        ),
        _step(
            "package_export",
            "AF Package 导出",
            "写出 manifest、FBX、贴图、export report 和 schema 信号。",
            _best_stage_status(evidence, ["contract_check", "package_acceptance", "accept_flow"]),
            _stage_refs(evidence, "contract_check") + _stage_refs(evidence, "package_acceptance") + _stage_refs(evidence, "accept_flow"),
            "保留真实 package_dir、manifest_path、export_report_path。",
        ),
        _step(
            "ue_gate_review",
            "UE Gate 审批与报告回看",
            "选择包体、预检、预演、审批，并打开报告。",
            _stage_status(evidence, "ue_gate_visual_review", fallback=_ue_gate_source_status(evidence)),
            _stage_refs(evidence, "ue_gate_visual_review") + _source_refs(evidence, ["HandleOpenReportClicked", "打开报告"]),
            "补真实 UE Gate 点击截图：列表、审批区、报告路径和打开报告按钮。",
        ),
        _step(
            "material_result",
            "材质实例与图表证据",
            "验证母材质、材质实例、贴图覆盖、slot 绑定和 Comment Box 读回。",
            _material_result_status(evidence),
            _material_result_refs(evidence),
            "补材质预览截图和 linked_graph_comments 冷启动证据。",
        ),
        _step(
            "clean_install",
            "干净工程安装冒烟",
            "证明插件不依赖当前测试工程的本机路径或已加载 DLL。",
            _clean_install_status(evidence),
            _stage_refs(evidence, "clean_install_validation") + _stage_refs(evidence, "plugin_install_smoke"),
            "关闭 UE Editor 后复跑正式 UBT，并在干净 UE 工程执行安装 smoke。",
        ),
    ]
    _apply_material_result_boundary(evidence, steps)
    for step in steps:
        field_refs = _field_validation_refs(evidence, step["id"])
        if field_refs:
            step["field_validation_refs"] = field_refs

    next_demo_actions = _next_demo_actions(steps)
    capture_root_hint = _portfolio_capture_root_hint(evidence, report_path)
    recording_runbook = _recording_runbook(steps, next_demo_actions, capture_root_hint)
    missing = [item["missing_action"] for item in steps if item["missing_action"]]
    status = "pass" if not missing else "warning"
    summary = create_acceptance_summary(status, _warnings(missing), [], missing[0] if missing else "作品演示证据已闭环。")
    report = {
        "version": REPORT_VERSION,
        "stage": "portfolio_demo_pack",
        "status": status,
        "evidence_path": _normalize_path(evidence_path or ""),
        "evidence_stage": evidence.get("stage", ""),
        "demo_duration_minutes": 3,
        "portfolio_capture_root_hint": capture_root_hint,
        "steps": steps,
        "next_demo_actions": next_demo_actions,
        "recording_runbook": recording_runbook,
        "missing_captures": missing,
        "can_show_as_portfolio_wip": True,
        "can_claim_production_ready": not bool(missing),
        "summary": summary,
    }
    if report_path:
        attach_report_artifact_metadata(report, report_path, command_args)
        write_report(report_path, report)
    return report


def _recording_runbook(steps, next_demo_actions, capture_root_hint):
    steps_by_id = dict((step.get("id", ""), step) for step in steps)
    actions_by_step = dict((item.get("step_id", ""), item) for item in next_demo_actions)
    capture_root = _normalize_path((capture_root_hint or {}).get("path", ""))
    groups = [
        ("opening", "0:00-0:20", "先讲清楚痛点和目标", ["pain_point"], "01_opening_context.png"),
        ("maya_scan", "0:20-0:55", "展示 Maya 侧扫描、阻断项和可修复队列", ["maya_scan"], "02_maya_scan.mp4"),
        ("package_export", "0:55-1:25", "展示 Package 产物和可追踪报告路径", ["package_export"], "03_package_export.png"),
        ("ue_gate", "1:25-2:05", "展示 UE Gate 选择包体、预检、审批和报告入口", ["ue_gate_review"], "04_ue_gate_review.mp4"),
        ("material_result", "2:05-2:40", "展示材质实例、贴图绑定和图表注释证据", ["material_result"], "05_material_result.png"),
        ("closing", "2:40-3:00", "用干净工程安装边界收尾，只讲已经验证到的事实", ["clean_install"], "06_clean_install_boundary.png"),
    ]
    return [
        _runbook_item(item_id, duration, goal, related_steps, capture_root, capture_name, steps_by_id, actions_by_step)
        for item_id, duration, goal, related_steps, capture_name in groups
    ]


def _runbook_item(item_id, duration, goal, related_steps, capture_root, capture_name, steps_by_id, actions_by_step):
    linked_steps = [steps_by_id[step_id] for step_id in related_steps if step_id in steps_by_id]
    talking_points = []
    for step in linked_steps:
        talking_points.extend(step.get("operator_checklist", [])[:1])
    evidence_fields = []
    for step in linked_steps:
        step_id = step.get("id", "")
        evidence_fields.append("steps.{0}.status".format(step_id))
        if step.get("evidence_refs"):
            evidence_fields.append("steps.{0}.evidence_refs".format(step_id))
        if step.get("field_validation_refs"):
            evidence_fields.append("steps.{0}.field_validation_refs".format(step_id))
    next_action = ""
    for step_id in related_steps:
        if step_id in actions_by_step:
            next_action = actions_by_step[step_id].get("missing_action", "")
            break
    return {
        "id": item_id,
        "duration": duration,
        "goal": goal,
        "related_steps": list(related_steps),
        "step_statuses": dict((step.get("id", ""), step.get("status", "")) for step in linked_steps),
        "talking_points": talking_points[:2],
        "evidence_fields": _dedupe(evidence_fields),
        "capture_hint": _capture_path_hint(capture_root, capture_name),
        "next_action": next_action,
    }


def _capture_path_hint(capture_root, capture_name):
    if capture_root:
        return _normalize_path(os.path.join(capture_root, capture_name))
    return capture_name


def _next_demo_actions(steps):
    actions = []
    for step in steps:
        if not step.get("missing_action"):
            continue
        checklist = step.get("operator_checklist") or []
        actions.append(
            {
                "step_id": step.get("id", ""),
                "title": step.get("title", ""),
                "missing_action": step.get("missing_action", ""),
                "operator_checklist": checklist[0] if checklist else "",
                "field_validation_refs": list(step.get("field_validation_refs", [])),
            }
        )
    return actions


def _read_evidence(evidence_path):
    if isinstance(evidence_path, dict):
        return evidence_path
    if not evidence_path:
        cwd = os.getcwd()
        for stage in ("offline_evidence_bundle", "stage_validation_bundle"):
            candidate = default_report_path(cwd, stage)
            if os.path.exists(candidate):
                return read_report(candidate)
        return {}
    if os.path.isdir(evidence_path):
        for stage in ("offline_evidence_bundle", "stage_validation_bundle"):
            candidate = default_report_path(evidence_path, stage)
            if os.path.exists(candidate):
                return read_report(candidate)
        return {}
    return read_report(evidence_path) if os.path.exists(evidence_path) else {}


def _portfolio_capture_root_hint(evidence, report_path=None):
    root = _existing_capture_root(evidence)
    if not root:
        report_dir = _report_directory(evidence, report_path)
        root = os.path.join(report_dir, "portfolio_captures") if report_dir else os.path.join("AssetForgeReports", "portfolio_captures")
    return {
        "path": _normalize_path(root),
        "source": "capture_manifest_expected_evidence_root",
        "reason": "将该目录作为 portfolio capture manifest 的 evidence_root。",
    }


def _existing_capture_root(evidence):
    if not isinstance(evidence, dict):
        return ""
    for key in ("portfolio_capture_root", "capture_root", "evidence_root"):
        if evidence.get(key):
            return evidence.get(key)
    return ""


def _report_directory(evidence, report_path=None):
    if report_path:
        return os.path.dirname(os.path.abspath(report_path))
    if not isinstance(evidence, dict):
        return ""
    artifact = evidence.get("report_artifact", {}) or {}
    if isinstance(artifact, dict) and artifact.get("directory"):
        return artifact.get("directory")
    if evidence.get("report_path"):
        return os.path.dirname(os.path.abspath(evidence.get("report_path")))
    return ""


def _step(step_id, title, user_value, status, evidence_refs, missing_action):
    active_status = _normalize_status(status)
    return {
        "id": step_id,
        "title": title,
        "user_value": user_value,
        "status": active_status,
        "evidence_refs": _dedupe([item for item in evidence_refs if item]),
        "missing_action": "" if active_status == "pass" else missing_action,
        "operator_checklist": _operator_checklist(step_id, evidence_refs),
    }


def _operator_checklist(step_id, evidence_refs=None):
    checklists = {
        "pain_point": [
            "指出本段要解决的 DCC 到 UE 交接风险。",
            "展示可追踪报告路径，再进入工具流程。",
        ],
        "maya_scan": [
            "展示 Maya 扫描状态和资产/贴图/材质数量。",
            "展开 repair actions，指出当前阻断项和修复下一步。",
        ],
        "package_export": [
            "展示 manifest、FBX、贴图目录和导出报告路径。",
            "切到 UE 前指出 schema/contract 检查结果。",
        ],
        "ue_gate_review": [
            "展示包体列表、选中包体和审批区。",
            "点击打开报告，并确认报告路径可见。",
        ],
        "material_result": [
            "展示 UE 中的材质实例和贴图绑定。",
            "展示 Comment Box 或图表证据，再截取视口结果图。",
        ],
        "clean_install": [
            "展示 source hash、目标插件路径和复制文件数量。",
            "确认 UE Editor 已关闭，再展示 UBT/build readiness。",
        ],
    }
    checklist = list(checklists.get(step_id, []))
    if step_id == "material_result" and _has_comment_box_persistence_boundary_ref(evidence_refs or []):
        checklist = _ensure_material_boundary_checklist(checklist)
    return checklist


def _stage_status(evidence, name, fallback="missing"):
    stage = _stage(evidence, name)
    return stage.get("status", fallback) if stage else fallback


def _best_stage_status(evidence, names):
    statuses = [_normalize_status(_stage_status(evidence, name)) for name in names]
    if "pass" in statuses:
        return "pass"
    if "warning" in statuses:
        return "warning"
    if "manual_validation_required" in statuses:
        return "manual_validation_required"
    return statuses[0] if statuses else "missing"


def _material_result_status(evidence):
    if _comment_box_persistence_boundary_status(evidence):
        return "warning"
    return _best_stage_status(evidence, ["material_graph_evidence_report", "material_graph_evidence", "accept_flow", "dry_run"])


def _material_result_refs(evidence):
    refs = (
        _stage_refs(evidence, "material_graph_evidence_report")
        + _stage_refs(evidence, "material_graph_evidence")
        + _stage_refs(evidence, "accept_flow")
        + _stage_refs(evidence, "dry_run")
    )
    if _comment_box_persistence_boundary_status(evidence):
        refs.append("material_result:comment_box_persistence_boundary=current_session_readback_is_not_cold_start_persistence")
    return refs


def _material_result_missing_action(evidence):
    if _comment_box_persistence_boundary_status(evidence):
        return "当前会话读回不等于冷启动持久化通过；请关闭并重开 UE，重新读取材质 Comment Box/中文分组注释，再补现场证据。"
    return "Add material preview screenshot and linked_graph_comments cold-start evidence."


def _apply_material_result_boundary(evidence, steps):
    if not _comment_box_persistence_boundary_status(evidence):
        return
    for step in steps:
        if step.get("id") != "material_result":
            continue
        step["status"] = "warning"
        step["missing_action"] = _material_result_missing_action(evidence)
        step["evidence_refs"] = _dedupe(
            list(step.get("evidence_refs", []))
            + ["material_result:comment_box_persistence_boundary=current_session_readback_is_not_cold_start_persistence"]
        )
        step["operator_checklist"] = _ensure_material_boundary_checklist(step.get("operator_checklist", []))
        return


def _comment_box_persistence_boundary_status(evidence):
    status = _comment_box_persistence_status(evidence)
    if status in ("needs_on_site_review", "cold_start_readback_required"):
        return status
    return ""


def _comment_box_persistence_status(evidence):
    for name in ("material_graph_evidence_report", "material_graph_evidence"):
        visual = (_stage(evidence, name).get("ta_visual_review", {}) or {})
        if isinstance(visual, dict) and visual.get("comment_box_persistence_status"):
            return visual.get("comment_box_persistence_status")
    return ""


def _has_comment_box_persistence_boundary_ref(evidence_refs):
    for ref in evidence_refs:
        if "comment_box_persistence_status=needs_on_site_review" in ref:
            return True
        if "comment_box_persistence_status=cold_start_readback_required" in ref:
            return True
        if "current_session_readback_is_not_cold_start_persistence" in ref:
            return True
    return False


def _ensure_material_boundary_checklist(checklist):
    item = "明确提示：当前会话读回不等于冷启动持久化通过，Comment Box/中文分组注释仍需关闭并重开 UE 现场复核。"
    result = [entry for entry in checklist if entry != item]
    return [item] + result


def _stage(evidence, name):
    stages = evidence.get("stages", {}) if isinstance(evidence, dict) else {}
    stage = stages.get(name, {}) if isinstance(stages, dict) else {}
    if not stage and isinstance(evidence.get(name), dict):
        stage = evidence.get(name)
    if not stage and evidence.get("stage") == name:
        stage = evidence
    return stage if isinstance(stage, dict) else {}


def _stage_refs(evidence, name):
    stage = _stage(evidence, name)
    refs = []
    for key in ("report_path", "manifest_path", "package_dir"):
        if stage.get(key):
            refs.append("{0}:{1}".format(name, _normalize_path(stage.get(key))))
    for key in (
        "target_plugin_dir",
        "source_hash",
        "source_hash_algorithm",
        "planned_copied_file_count",
        "copied_file_count",
        "can_build_after_editor_closed",
        "blocked_by_running_editor",
        "requires_cpp_compile",
        "dry_run",
        "real_ue_evidence",
        "assetforge_editor_linked",
        "blocked_by_plugin",
        "blocker_summary",
        "ubt_log_path",
    ):
        if key in stage and _is_compact_ref_value(stage.get(key)):
            refs.append("{0}:{1}={2}".format(name, key, _normalize_path(stage.get(key))))
    refs.extend(_ue_gate_refs(name, stage))
    refs.extend(_screenshot_refs(name, stage))
    refs.extend(_installer_refs(name, stage))
    refs.extend(_material_refs(name, stage))
    report_paths = evidence.get("report_paths", {}) if isinstance(evidence, dict) else {}
    if isinstance(report_paths, dict) and report_paths.get(name):
        refs.append("{0}:{1}".format(name, _normalize_path(report_paths.get(name))))
    return refs


def _field_validation_refs(evidence, step_id):
    plan_by_step = {
        "maya_scan": ["maya_screen_recording"],
        "ue_gate_review": ["ue_gate_clicks"],
        "material_result": ["material_preview_comment_box"],
        "clean_install": ["closed_editor_ubt_clean_install_smoke"],
    }
    wanted = set(plan_by_step.get(step_id, []))
    plan = evidence.get("field_validation_plan", []) if isinstance(evidence, dict) else []
    refs = []
    for item in plan if isinstance(plan, list) else []:
        if not isinstance(item, dict) or item.get("id") not in wanted:
            continue
        item_id = item.get("id")
        refs.append("field_validation_plan:{0}".format(item_id))
        for key in (
            "status",
            "release_boundary_status",
            "can_claim_clean_install",
            "assetforge_editor_linked",
            "blocked_by_plugin",
            "blocker_summary",
            "ubt_log_path",
        ):
            if key in item and item.get(key) not in ("", None):
                refs.append("field_validation_plan:{0}.{1}={2}".format(item_id, key, item.get(key)))
    return _dedupe(refs)


def _screenshot_refs(name, stage):
    refs = []
    screenshots = stage.get("screenshots", {}) if isinstance(stage, dict) else {}
    if not isinstance(screenshots, dict):
        return refs
    for key, path in sorted(screenshots.items()):
        if _is_compact_ref_value(path):
            refs.append("{0}:screenshot.{1}={2}".format(name, key, _normalize_path(path)))
    return refs


def _ue_gate_refs(name, stage):
    refs = []
    for key in ("opened_report_path", "selected_report_path", "report_opened_path"):
        if stage.get(key):
            refs.append("{0}:{1}={2}".format(name, key, _normalize_path(stage.get(key))))
    for key in ("open_report_action", "open_report_callable", "clicked_action"):
        if stage.get(key):
            refs.append("{0}:{1}={2}".format(name, key, stage.get(key)))
    return refs


def _installer_refs(name, stage):
    refs = []
    install_smoke = stage.get("install_smoke", {}) or {}
    if isinstance(install_smoke, dict):
        for key in ("requires_cpp_compile", "source_hash", "planned_copied_file_count", "copied_file_count"):
            if key in install_smoke and install_smoke.get(key) not in ("", None):
                refs.append("{0}:install_smoke.{1}={2}".format(name, key, _normalize_path(install_smoke.get(key))))

    release_boundary = stage.get("release_boundary", {}) or install_smoke.get("release_boundary", {})
    if isinstance(release_boundary, dict):
        for key in ("status", "can_claim_clean_install"):
            if key in release_boundary and release_boundary.get(key) not in ("", None):
                refs.append("{0}:release_boundary.{1}={2}".format(name, key, release_boundary.get(key)))
        for action in release_boundary.get("next_actions", []) or []:
            refs.append("{0}:release_boundary.next_action={1}".format(name, action))

    build_readiness = stage.get("build_readiness", {}) or install_smoke.get("build_readiness", {})
    if isinstance(build_readiness, dict):
        for key in ("status", "native_editor_module", "target_binary", "next_action"):
            if key in build_readiness and build_readiness.get(key) not in ("", None):
                refs.append("{0}:build_readiness.{1}={2}".format(name, key, _normalize_path(build_readiness.get(key))))
    return refs


def _material_refs(name, stage):
    refs = []
    visual = stage.get("ta_visual_review", {}) or {}
    if isinstance(visual, dict):
        for key in ("status", "screenshot_evidence", "next_action", "comment_box_persistence_status"):
            if key in visual and visual.get(key) not in ("", None):
                refs.append("{0}:ta_visual_review.{1}={2}".format(name, key, _normalize_path(visual.get(key))))

    for check in stage.get("checks", []) or []:
        if not isinstance(check, dict):
            continue
        if check.get("id") == "material_comment_blocks":
            for key in ("linked_graph_comments", "comment_block_summary", "visual_review_risk", "next_action"):
                if key in check and check.get(key) not in ("", None):
                    refs.append("{0}:material_comment_blocks.{1}={2}".format(name, key, _normalize_path(check.get(key))))

    real_graph = stage.get("real_ue_material_graph", {}) or {}
    if isinstance(real_graph, dict):
        screenshot = real_graph.get("screenshot_evidence", {}) or {}
        if isinstance(screenshot, dict):
            for key in ("status", "path", "count"):
                if key in screenshot and screenshot.get(key) not in ("", None):
                    refs.append("{0}:screenshot_evidence.{1}={2}".format(name, key, _normalize_path(screenshot.get(key))))
        for material in real_graph.get("materials", []) or []:
            if isinstance(material, dict) and (material.get("screenshot_path") or material.get("graph_screenshot")):
                refs.append(
                    "{0}:material_screenshot={1}".format(
                        name,
                        _normalize_path(material.get("screenshot_path") or material.get("graph_screenshot")),
                    )
                )
    return refs


def _repair_action_status(evidence):
    for stage_name in ("maya_ui_flow", "preflight", "maya_export"):
        if _stage(evidence, stage_name).get("repair_actions"):
            return "pass"
    return "manual_validation_required"


def _repair_action_refs(evidence):
    refs = []
    for stage_name in ("maya_ui_flow", "preflight", "maya_export"):
        if _stage(evidence, stage_name).get("repair_actions"):
            refs.append("{0}:repair_actions".format(stage_name))
    return refs


def _ue_gate_source_status(evidence):
    raw = str(evidence)
    return "warning" if "HandleOpenReportClicked" in raw or "打开报告" in raw else "manual_validation_required"


def _clean_install_status(evidence):
    validation_status = _stage_status(evidence, "clean_install_validation", fallback="")
    if validation_status:
        return validation_status
    smoke = _stage(evidence, "plugin_install_smoke")
    if not smoke:
        return "missing"
    if smoke.get("status") in ("pass", "success", "ready"):
        return smoke.get("status")
    if smoke.get("install_smoke") or smoke.get("source_hash"):
        return "warning"
    return smoke.get("status", "missing")


def _source_refs(evidence, tokens):
    raw = str(evidence)
    return ["source:{0}".format(token) for token in tokens if token in raw]


def _normalize_status(status):
    if status in ("pass", "success", "ready"):
        return "pass"
    if status in ("warning", "review_required"):
        return "warning"
    if status in ("manual_validation_required", "blocked", "error", "failed"):
        return status
    return "missing"


def _is_compact_ref_value(value):
    return value not in ("", None) and not isinstance(value, (dict, list, tuple, set))


def _warnings(missing):
    return [{"source": "portfolio_demo_pack", "message": item} for item in missing]


def _dedupe(items):
    result = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _normalize_path(path):
    if path is None:
        return ""
    return str(path).replace("\\", "/")
