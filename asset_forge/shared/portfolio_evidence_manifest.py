"""Small evidence checklist for portfolio demo capture."""

from __future__ import absolute_import

import os

from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.report_schema import REPORT_VERSION, attach_acceptance_summary, create_acceptance_summary


MISSING_DEMO_PACK_ACTION = "先运行 --portfolio-demo-pack 生成作品集演示包，再刷新捕获清单。"


def create_portfolio_evidence_manifest(demo_pack=None, evidence_root=None):
    """Turn a portfolio demo pack into a compact capture checklist."""
    demo_pack = demo_pack or {}
    steps = list(demo_pack.get("steps", []))
    root = normalize_path(evidence_root or "")
    captures = [_capture_from_step(index, step, root) for index, step in enumerate(steps, 1)]
    missing = [item for item in captures if item["status"] != "pass"]
    warnings = [
        {"source": "portfolio_evidence_manifest", "id": item["id"], "message": item["missing_action"]}
        for item in missing
        if item.get("missing_action")
    ]
    if not steps:
        warnings.append(
            {
                "source": "portfolio_evidence_manifest",
                "id": "missing_demo_pack_steps",
                "message": MISSING_DEMO_PACK_ACTION,
            }
        )
    next_action = missing[0]["missing_action"] if missing else "作品集证据清单已闭环。"
    if not steps:
        next_action = MISSING_DEMO_PACK_ACTION
    summary = create_acceptance_summary("warning" if (missing or not steps) else "pass", warnings, [], next_action)
    capture_summary = _capture_summary(captures, missing, "demo_pack_steps" if not steps else (missing[0]["id"] if missing else ""))
    report = {
        "version": REPORT_VERSION,
        "stage": "portfolio_evidence_manifest",
        "status": summary.get("status", ""),
        "source_stage": demo_pack.get("stage", ""),
        "evidence_root": root,
        "capture_directory_plan": _capture_directory_plan(root, captures),
        "captures": captures,
        "capture_tasks": _capture_tasks(captures),
        "capture_shooting_cards": _capture_shooting_cards(captures),
        "capture_summary": capture_summary,
        "capture_review_index": _capture_review_index(captures, root),
        "ready_capture_count": len(captures) - len(missing),
        "missing_capture_count": len(missing),
        "next_capture": missing[0]["id"] if missing else ("demo_pack_steps" if not steps else ""),
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _capture_directory_plan(root, captures):
    captured_count = len([item for item in captures if item.get("capture_file_exists")])
    needs_directory_create = bool(root and not os.path.isdir(root))
    return {
        "evidence_root": root,
        "needs_directory_create": needs_directory_create,
        "missing_task_count": len(captures) - captured_count,
        "captured_task_count": captured_count,
    }


def _capture_tasks(captures):
    return [
        {
            "step_id": item.get("step_id", ""),
            "capture_type": item.get("capture_type", ""),
            "suggested_capture_path": item.get("suggested_capture_path", ""),
            "capture_file_status": item.get("capture_file_status", ""),
            "next_step": item.get("next_step", ""),
        }
        for item in captures
    ]


def _capture_shooting_cards(captures):
    return [
        {
            "step_id": item.get("step_id", ""),
            "title": item.get("title", ""),
            "capture_type": item.get("capture_type", ""),
            "scene_focus": _capture_scene_focus(item.get("step_id", "")),
            "verify_points": _capture_verify_points(item.get("step_id", "")),
            "suggested_capture_path": item.get("suggested_capture_path", ""),
            "capture_file_status": item.get("capture_file_status", ""),
            "next_step": item.get("next_step", ""),
        }
        for item in captures
    ]


def _capture_summary(captures, missing, next_capture):
    screenshot_count = len([item for item in captures if item.get("capture_type") == "screenshot"])
    recording_count = len([item for item in captures if item.get("capture_type") == "recording"])
    captured_count = len([item for item in captures if item.get("capture_file_exists")])
    return {
        "total_capture_count": len(captures),
        "ready_capture_count": len(captures) - len(missing),
        "missing_capture_count": len(missing),
        "captured_capture_count": captured_count,
        "screenshot_capture_count": screenshot_count,
        "recording_capture_count": recording_count,
        "next_capture": next_capture,
    }


def _capture_review_index(captures, root):
    states = {
        "captured": _capture_type_counts(),
        "missing": _capture_type_counts(),
        "ready": _capture_type_counts(),
    }
    for item in captures:
        capture_type = item.get("capture_type") or "screenshot"
        if item.get("capture_file_exists"):
            _bump_capture_type(states["captured"], capture_type)
        else:
            _bump_capture_type(states["missing"], capture_type)
        if item.get("status") == "pass":
            _bump_capture_type(states["ready"], capture_type)

    return {
        "states": states,
        "next_review": _next_review_item(captures, root),
    }


def _capture_type_counts():
    return {"total": 0, "screenshot": 0, "recording": 0}


def _bump_capture_type(counts, capture_type):
    counts["total"] += 1
    if capture_type not in counts:
        counts[capture_type] = 0
    counts[capture_type] += 1


def _next_review_item(captures, root):
    if not captures:
        return {
            "step_id": "demo_pack_steps",
            "capture_type": "",
            "capture_file_status": "missing",
            "review_status": "missing",
            "suggested_capture_path": "",
            "prompt": MISSING_DEMO_PACK_ACTION,
        }

    for item in captures:
        if not item.get("capture_file_exists"):
            return {
                "step_id": item.get("step_id", ""),
                "capture_type": item.get("capture_type", ""),
                "capture_file_status": item.get("capture_file_status", "missing"),
                "review_status": item.get("status", ""),
                "suggested_capture_path": item.get("suggested_capture_path", ""),
                "prompt": _next_missing_capture_prompt(item, root),
            }

    for item in captures:
        if item.get("status") != "pass":
            return {
                "step_id": item.get("step_id", ""),
                "capture_type": item.get("capture_type", ""),
                "capture_file_status": item.get("capture_file_status", ""),
                "review_status": item.get("status", ""),
                "suggested_capture_path": item.get("suggested_capture_path", ""),
                "prompt": "下一步复核 {0} 的素材：确认画面、操作结果和报告一致。".format(
                    item.get("step_id", "")
                ),
            }

    return {
        "step_id": "",
        "capture_type": "",
        "capture_file_status": "captured",
        "review_status": "ready",
        "suggested_capture_path": "",
        "prompt": "素材已齐，可以复核最终剪辑顺序。",
    }


def _next_missing_capture_prompt(item, root):
    capture_name = "录屏" if item.get("capture_type") == "recording" else "截图"
    if not root:
        return "先指定证据目录 evidence_root，再采集 {0} 的{1}素材。".format(
            item.get("step_id", ""),
            capture_name,
        )
    return "下一步采集 {0} 的{1}素材，保存到 {2}。".format(
        item.get("step_id", ""),
        capture_name,
        item.get("suggested_capture_path", ""),
    )


def _capture_from_step(index, step, root):
    step_id = step.get("id", "step_{0}".format(index))
    status = _capture_status(step)
    capture_type = step.get("capture_type") or _capture_type(step_id)
    gap = "" if status == "pass" else _gap(step)
    suggested_path = _suggested_path(root, index, step_id, capture_type)
    capture_file = _capture_file_status(suggested_path)
    capture = {
        "id": "{0}_capture".format(step_id),
        "step_id": step_id,
        "title": step.get("title", ""),
        "status": status,
        "evidence_refs": list(step.get("evidence_refs", []) or []),
        "capture_type": capture_type,
        "gap": gap,
        "next_step": _next_step(status, gap, suggested_path),
        "missing_action": gap,
        "suggested_capture_path": suggested_path,
        "portfolio_use": _portfolio_use(step_id),
    }
    capture.update(capture_file)
    return capture


def _capture_file_status(suggested_path):
    exists = bool(suggested_path and os.path.isabs(suggested_path) and os.path.isfile(suggested_path))
    return {
        "capture_file_exists": exists,
        "capture_file_size": os.path.getsize(suggested_path) if exists else 0,
        "capture_file_status": "captured" if exists else "missing",
    }


def _capture_status(step):
    status = step.get("status", "missing")
    refs = step.get("evidence_refs", []) or []
    if status == "pass" and refs:
        return "pass"
    if status == "pass":
        return "manual_validation_required"
    return status or "missing"


def _suggested_path(root, index, step_id, capture_type="screenshot"):
    extension = "mp4" if capture_type == "recording" else "png"
    filename = "{0:02d}_{1}.{2}".format(index, step_id, extension)
    if not root:
        return filename
    return normalize_path(os.path.join(root, filename))


def _gap(step):
    return step.get("missing_action", "") or "补真实截图或录屏证据。"


def _next_step(status, gap, suggested_path):
    if status == "pass":
        return "引用证据已通过；建议把对应画面保存到 {0}，用于最终作品集剪辑。".format(suggested_path)
    return "{0} 建议保存到 {1}。".format(gap, suggested_path)


def _capture_type(step_id):
    recordings = set(["maya_scan", "ue_gate_review", "clean_install"])
    return "recording" if step_id in recordings else "screenshot"


def _portfolio_use(step_id):
    uses = {
        "pain_point": "开场：说明手工导入、材质核对和报告追踪的痛点。",
        "maya_scan": "Maya 段：展示扫描、阻断项、修复按钮和下一步。",
        "package_export": "Package 段：展示发布清单、导出报告和可追踪包体。",
        "ue_gate_review": "UE 段：展示包体列表、审批区、报告回看和打开报告。",
        "material_result": "结果段：展示材质实例、贴图绑定、材质注释框和预览结果。",
        "clean_install": "收口段：证明插件可安装、可编译、可迁移。",
    }
    return uses.get(step_id, "作为作品集证据链的一段。")


def _capture_scene_focus(step_id):
    focus = {
        "pain_point": "展示手工导入、材质核对和报告追踪的痛点。",
        "maya_scan": "展示 Maya 发布工作台、资产概览、风险检查和修复队列。",
        "package_export": "展示导出结果、Package 路径、manifest 和报告路径。",
        "ue_gate_review": "展示 UE Gate 包体列表、审批区、状态提示和打开报告动作。",
        "material_result": "展示 Static Mesh、材质实例、贴图绑定和母材质注释框。",
        "clean_install": "展示关闭 Editor 后 UBT、干净工程安装和发布边界。",
    }
    return focus.get(step_id, "展示该步骤的操作结果和对应报告。")


def _capture_verify_points(step_id):
    points = {
        "pain_point": ["问题清楚", "目标用户能理解", "不要只拍空界面"],
        "maya_scan": ["资产名可见", "修复队列可见", "报告路径可见", "下一步可见"],
        "package_export": ["Package 路径可见", "manifest/report 可追踪", "UE 目标路径可见"],
        "ue_gate_review": ["选中包体可见", "预检/审批状态可见", "打开报告入口可见"],
        "material_result": ["材质实例可见", "贴图绑定可见", "Comment Box 或参数分组可见"],
        "clean_install": ["项目路径可见", "UBT 结果可见", "不要把 dry-run 说成真实安装"],
    }
    return list(points.get(step_id, ["操作结果可见", "报告路径可追踪"]))
