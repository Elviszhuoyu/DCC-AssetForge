"""Portfolio-oriented readiness review for DCC AssetForge.

This report is intentionally product-facing: it answers whether the tool is
good enough to show as a TA pipeline work, not only whether tests pass.
"""

from __future__ import absolute_import

from asset_forge.shared.report_schema import REPORT_VERSION, attach_acceptance_summary, create_acceptance_summary


def create_portfolio_readiness(north_star_readiness=None, capability_matrix=None, evidence_bundle=None):
    north_star_readiness = north_star_readiness or {}
    capability_matrix = capability_matrix or {}
    evidence_bundle = evidence_bundle or {}
    capability_items = dict((item.get("id"), item) for item in capability_matrix.get("items", []))

    dimensions = [
        _dimension(
            "pipeline_core",
            "Maya -> AF Package -> UE Gate 主链路",
            20,
            _score_from_status(_capability_status(capability_items, "package_acceptance"), 80),
            "核心数据链路可作为作品主线展示，但仍要靠真实端到端录像/报告收口。",
            ["保留样例包、清单、UE 预演/导入报告和导入后校验证据。"],
        ),
        _dimension(
            "dcc_artist_experience",
            "DCC 侧 TA/模型师体验",
            15,
            _maya_score(capability_items, evidence_bundle),
            "Maya 工作台已具备扫描、检查、导出和日志，但作品级还需要更少术语、更明确的修复按钮和真实 UI 录屏。",
            ["补真实 Maya 界面流程截图或录屏。", "继续压缩工程术语，把阻断项转成可点击修复动作。"],
        ),
        _dimension(
            "ue_gate_experience",
            "UE 导入门禁体验",
            15,
            _ue_gate_score(evidence_bundle),
            "UE Gate 已从脚本入口进化为门禁工作台，但审美和真实点击验收仍是作品级短板。",
            ["按 UE 详情面板风格继续打磨列表、分组、状态色和审批区。", "补真实编辑器点击验收截图。"],
        ),
        _dimension(
            "material_pipeline",
            "材质库与材质证据",
            20,
            _material_score(capability_items, evidence_bundle),
            "参数化母材质、材质实例计划和注释框证据已进入强项区，但仍要补材质图截图与真实着色器/预览证据。",
            ["保留 linked_graph_comments=7 的冷启动证据。", "补材质预览截图、编译日志和贴图采样核对。"],
        ),
        _dimension(
            "validation_evidence",
            "真实验收与可证明性",
            15,
            _real_validation_score(north_star_readiness),
            "离线证据体系已经成熟；作品级上限仍被真实 Maya/UE 现场证据限制。",
            ["把真实 UE 导入结果标记为 TAS-102 完成证据。", "把真实 Maya 界面流程报告纳入证据包。"],
        ),
        _dimension(
            "release_hygiene",
            "发布边界与可移植性",
            10,
            _release_score(evidence_bundle),
            "代码结构和日志体系已经像工具产品，但还需要打包边界、干净安装和演示工程流程收口。",
            ["清理暂存边界，区分仓库源码、测试工程现场补丁和报告证据。", "补一次干净 UE 项目安装验证。"],
        ),
        _dimension(
            "portfolio_story",
            "作品表达与面试叙事",
            5,
            _portfolio_story_score(north_star_readiness),
            "技术深度足够，但作品展示还需要一个短而清晰的故事：痛点、流程、前后对比、失败保护和结果。",
            ["准备 3 分钟演示路线：Maya 扫描 -> 风险检查 -> 导出 -> UE Gate -> 材质实例与报告。"],
        ),
    ]

    portfolio_missing_evidence = _portfolio_missing_evidence(evidence_bundle)
    portfolio_capture_progress = _portfolio_capture_progress(evidence_bundle)
    score = round(sum(item["weighted_score"] for item in dimensions), 2)
    score = _apply_portfolio_evidence_cap(score, portfolio_missing_evidence)
    level = _quality_level(score)
    missing = _missing_from_dimensions(dimensions)
    for item in portfolio_missing_evidence:
        action = item.get("next_action", "")
        if action and action not in missing:
            missing.append(action)
    warnings = [{"source": "portfolio_readiness", "id": item["id"], "message": item["risk"]} for item in dimensions if item["status"] != "pass"]
    warnings.extend(_missing_evidence_warnings(portfolio_missing_evidence))
    next_action = _next_action(level, missing)
    portfolio_action_center = _portfolio_action_center(
        score,
        portfolio_missing_evidence,
        portfolio_capture_progress,
        evidence_bundle,
        missing,
    )
    portfolio_review_sheet = _portfolio_review_sheet(
        score,
        level,
        portfolio_capture_progress,
        portfolio_action_center,
        missing,
    )
    summary = create_acceptance_summary("warning" if warnings else "pass", warnings, [], next_action)

    report = {
        "version": REPORT_VERSION,
        "stage": "portfolio_readiness",
        "status": summary.get("status", ""),
        "score": score,
        "max_score": 100,
        "quality_level": level,
        "portfolio_grade": _portfolio_grade(score),
        "positioning": "TA 管线工具作品 / 静态道具 DCC 到 UE 桥接工具",
        "dimensions": dimensions,
        "portfolio_capture_progress": portfolio_capture_progress,
        "portfolio_missing_evidence": portfolio_missing_evidence,
        "portfolio_action_center": portfolio_action_center,
        "portfolio_review_sheet": portfolio_review_sheet,
        "risks": [item.get("message", "") for item in warnings if item.get("message")],
        "remaining_top_priorities": missing[:8],
        "recommended_next_features": _recommended_next_features(),
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _dimension(item_id, title, weight, score, risk, next_actions):
    score = max(0, min(100, int(score)))
    status = "pass" if score >= 85 else ("warning" if score >= 55 else "manual_validation_required")
    return {
        "id": item_id,
        "title": title,
        "weight": weight,
        "score": score,
        "weighted_score": round(score * weight / 100.0, 2),
        "status": status,
        "risk": risk,
        "next_actions": list(next_actions or []),
    }


def _capability_status(items, item_id):
    return items.get(item_id, {}).get("status", "missing")


def _score_from_status(status, default_warning_score=60):
    if status in ("pass", "success"):
        return 90
    if status in ("warning", "skipped"):
        return default_warning_score
    if status == "manual_validation_required":
        return 55
    return 35


def _maya_score(capability_items, evidence_bundle):
    score = _score_from_status(_capability_status(capability_items, "maya_export"), 60)
    if _has_stage(evidence_bundle, "maya_ui_flow"):
        score = max(score, 85)
    return score


def _ue_gate_score(evidence_bundle):
    if _has_stage(evidence_bundle, "ue_gate_visual_review"):
        return 88
    if _has_stage(evidence_bundle, "stage_gate"):
        return 74
    return 68


def _material_score(capability_items, evidence_bundle):
    score = _score_from_status(_capability_status(capability_items, "material_profile"), 75)
    material_evidence = _stage(evidence_bundle, "material_graph_evidence")
    if material_evidence.get("status") in ("pass", "success"):
        score = max(score, 88)
    if _material_comment_links_ready(evidence_bundle):
        score = max(score, 86)
    return score


def _real_validation_score(north_star_readiness):
    items = dict((item.get("id"), item) for item in north_star_readiness.get("items", []))
    real_ue = items.get("real_ue_validation", {})
    if real_ue.get("status") == "pass":
        return 92
    score = north_star_readiness.get("score", 0)
    if score >= 70:
        return 62
    return 45


def _release_score(evidence_bundle):
    if _has_stage(evidence_bundle, "clean_install_validation"):
        return 90
    if _has_stage(evidence_bundle, "doctor"):
        return 72
    return 65


def _portfolio_story_score(north_star_readiness):
    if north_star_readiness.get("score", 0) >= 85:
        return 78
    return 68


def _stage(bundle, name):
    if not isinstance(bundle, dict):
        return {}
    stages = bundle.get("stages", {})
    stage = stages.get(name, {}) if isinstance(stages, dict) else {}
    if not stage and bundle.get("stage") == name:
        stage = bundle
    return stage if isinstance(stage, dict) else {}


def _has_stage(bundle, name):
    stage = _stage(bundle, name)
    return bool(stage and stage.get("status") not in ("missing", "manual_validation_required", "blocked", "error", "failed"))


def _material_comment_links_ready(bundle):
    for stage_name in ("material_graph_evidence", "real_ue_validation", "accept_flow", "ue_import_validation"):
        stage = _stage(bundle, stage_name)
        raw = str(stage)
        if "linked_graph_comments=7" in raw or "'linked_graph_comments': 7" in raw or '"linked_graph_comments": 7' in raw:
            return True
    return False


def _portfolio_missing_evidence(evidence_bundle):
    missing = []
    missing.extend(_field_validation_missing(evidence_bundle))
    missing.extend(_demo_pack_missing(evidence_bundle))
    missing.extend(_capture_manifest_missing(evidence_bundle))
    return _dedupe_missing_evidence(missing)


def _field_validation_missing(evidence_bundle):
    plan = evidence_bundle.get("field_validation_plan", []) if isinstance(evidence_bundle, dict) else []
    result = []
    for item in plan if isinstance(plan, list) else []:
        if not isinstance(item, dict) or _is_pass_status(item.get("status")):
            continue
        item_id = item.get("id", "field_validation")
        result.append(
            {
                "source": "field_validation_plan",
                "id": item_id,
                "status": item.get("status", "missing"),
                "next_action": item.get("next_action", "") or _field_validation_next_action(item_id),
            }
        )
    return result


def _demo_pack_missing(evidence_bundle):
    demo_pack = _embedded_report(evidence_bundle, "portfolio_demo_pack")
    result = []
    next_demo_actions = demo_pack.get("next_demo_actions", [])
    for item in next_demo_actions if isinstance(next_demo_actions, list) else []:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "source": "portfolio_demo_pack",
                "id": item.get("step_id", "demo_step"),
                "status": "manual_validation_required",
                "next_action": item.get("missing_action", "") or item.get("operator_checklist", "") or "补作品集演示现场证据。",
            }
        )
    missing_captures = demo_pack.get("missing_captures", [])
    for action in missing_captures if isinstance(missing_captures, list) else []:
        result.append(
            {
                "source": "portfolio_demo_pack",
                "id": "missing_capture",
                "status": "manual_validation_required",
                "next_action": action or "补作品集演示截图或录屏。",
            }
        )
    return result


def _capture_manifest_missing(evidence_bundle):
    manifest = _embedded_report(evidence_bundle, "portfolio_evidence_manifest")
    result = []
    captures = manifest.get("captures", [])
    for item in captures if isinstance(captures, list) else []:
        if not isinstance(item, dict) or _is_pass_status(item.get("status")):
            continue
        result.append(
            {
                "source": "portfolio_evidence_manifest",
                "id": item.get("id", item.get("step_id", "capture")),
                "status": item.get("status", "missing"),
                "next_action": item.get("next_step", "") or item.get("missing_action", "") or "补作品集截图或录屏证据。",
            }
        )
    summary = manifest.get("capture_summary", {}) if isinstance(manifest.get("capture_summary", {}), dict) else {}
    if summary.get("missing_capture_count", 0) and not result:
        result.append(
            {
                "source": "portfolio_evidence_manifest",
                "id": summary.get("next_capture", "capture_summary"),
                "status": "manual_validation_required",
                "next_action": "补作品集截图/录屏清单中标记缺失的证据。",
            }
        )
    return result


def _portfolio_capture_progress(evidence_bundle):
    manifest = _embedded_report(evidence_bundle, "portfolio_evidence_manifest")
    summary = manifest.get("capture_summary", {}) if isinstance(manifest.get("capture_summary", {}), dict) else {}
    if not summary:
        return {}
    total = _int_count(summary.get("total_capture_count"))
    captured = _int_count(summary.get("captured_capture_count"))
    missing = _int_count(summary.get("missing_capture_count"))
    if total is None and captured is not None and missing is not None:
        total = captured + missing
    return {
        "total": total if total is not None else 0,
        "captured": captured if captured is not None else 0,
        "missing": missing if missing is not None else 0,
        "next_capture": summary.get("next_capture", ""),
    }


def _portfolio_action_center(score, portfolio_missing_evidence, portfolio_capture_progress, evidence_bundle, missing):
    cards = []
    field_missing = [item for item in portfolio_missing_evidence if item.get("source") == "field_validation_plan"]

    cap_reason = _portfolio_cap_reason(field_missing)
    if cap_reason:
        _append_action_card(
            cards,
            {
                "id": "score_cap",
                "title": "解除作品分封顶",
                "status": "blocked_by_field_evidence",
                "reason": "{0} 当前作品分：{1}。".format(cap_reason, score),
                "next_action": _first_next_action(field_missing, "先补真实 Maya/UE 现场证据，再重新生成作品分。"),
                "source": "portfolio_missing_evidence",
            },
        )

    if field_missing:
        _append_action_card(
            cards,
            {
                "id": "field_evidence",
                "title": "补齐现场验收证据",
                "status": "manual_validation_required",
                "reason": "仍有 {0} 项现场证据缺失；离线报告只能说明链路存在，不能替代真实点击/录屏。".format(len(field_missing)),
                "next_action": _first_next_action(field_missing, "按 Maya -> UE Gate -> 材质预览顺序补现场截图或录屏。"),
                "source": "field_validation_plan",
            },
        )

    if portfolio_capture_progress.get("missing", 0):
        total = portfolio_capture_progress.get("total", 0)
        captured = portfolio_capture_progress.get("captured", 0)
        next_capture = portfolio_capture_progress.get("next_capture", "") or "下一张缺失截图/录屏"
        _append_action_card(
            cards,
            {
                "id": "capture_manifest",
                "title": "收口作品集截图/录屏",
                "status": "evidence_missing",
                "reason": "作品集媒体证据进度 {0}/{1}，还有 {2} 项未补。".format(
                    captured,
                    total,
                    portfolio_capture_progress.get("missing", 0),
                ),
                "next_action": "优先补 {0}，再刷新截图/录屏清单。".format(next_capture),
                "source": "portfolio_capture_progress",
            },
        )

    material_comment_action = _material_comment_persistence_action(evidence_bundle)
    if material_comment_action:
        _append_action_card(cards, material_comment_action)

    release_action = _release_boundary_action(evidence_bundle, field_missing)
    if release_action:
        _append_action_card(
            cards,
            {
                "id": "release_boundary",
                "title": "验证发布/安装边界",
                "status": "manual_validation_required",
                "reason": "作品集收口前需要证明插件能脱离当前测试工程安装和编译。",
                "next_action": release_action,
                "source": "clean_install_validation",
            },
        )

    dcc_support_action = _dcc_support_action(evidence_bundle)
    if dcc_support_action:
        _append_action_card(cards, dcc_support_action)

    if len(cards) < 2 and missing:
        _append_action_card(
            cards,
            {
                "id": "demo_story",
                "title": "压缩 3 分钟演示路线",
                "status": "next_best_action",
                "reason": "当前最需要把技术链路翻译成面试官能快速看懂的作品叙事。",
                "next_action": missing[0],
                "source": "remaining_top_priorities",
            },
        )

    return cards[:4]


def _portfolio_review_sheet(score, level, portfolio_capture_progress, portfolio_action_center, missing):
    first_actions = []
    for item in portfolio_action_center:
        action = item.get("next_action", "")
        if action and action not in first_actions:
            first_actions.append(action)
    for action in missing:
        if action and action not in first_actions:
            first_actions.append(action)
    first_actions = first_actions[:3]

    if portfolio_capture_progress:
        capture_line = "作品集素材：已捕获 {0}/{1}，缺 {2}；下一项：{3}".format(
            portfolio_capture_progress.get("captured", 0),
            portfolio_capture_progress.get("total", 0),
            portfolio_capture_progress.get("missing", 0),
            portfolio_capture_progress.get("next_capture", "") or "暂无",
        )
    else:
        capture_line = "作品集素材：未接入截图/录屏清单。"

    proof_boundary = "离线报告只证明链路存在；作品集收口仍以真实 Maya/UE 截图、录屏和关闭 Editor 后 UBT 为准。"
    return {
        "summary_line": "当前作品集成熟度 {0}/100，级别 {1}。".format(score, level),
        "capture_line": capture_line,
        "first_actions": first_actions,
        "proof_boundary": proof_boundary,
    }


def _portfolio_cap_reason(field_missing):
    if len(field_missing) >= 4:
        return "4 项现场验收未完成，作品分最高按 79 分处理。"
    if len(field_missing) >= 2:
        return "2 项以上现场验收未完成，作品分最高按 84 分处理。"
    return ""


def _append_action_card(cards, card):
    if any(item.get("id") == card.get("id") for item in cards):
        return
    cards.append(card)


def _first_next_action(items, fallback):
    for item in items:
        action = item.get("next_action", "")
        if action:
            return action
    return fallback


def _release_boundary_action(evidence_bundle, field_missing):
    for item in field_missing:
        if item.get("id") == "closed_editor_ubt_clean_install_smoke" and item.get("next_action"):
            return item["next_action"]
    if not _has_stage(evidence_bundle, "clean_install_validation"):
        return "关闭 UE Editor 后跑 UBT，并在干净 UE 工程执行非预演安装冒烟测试。"
    return ""


def _material_comment_persistence_action(evidence_bundle):
    material_report = _embedded_report(evidence_bundle, "material_graph_evidence")
    if not material_report:
        material_report = _embedded_report(evidence_bundle, "material_graph_evidence_report")
    visual = material_report.get("ta_visual_review", {}) if isinstance(material_report.get("ta_visual_review", {}), dict) else {}
    status = visual.get("comment_box_persistence_status", "")
    cold_required = bool(visual.get("cold_start_readback_required"))
    screenshot_required = bool(visual.get("real_ue_screenshot_required"))
    if status not in ("needs_on_site_review", "blocked") and not (cold_required or screenshot_required):
        return {}
    missing_bits = []
    if cold_required:
        missing_bits.append("冷启动读回")
    if screenshot_required:
        missing_bits.append("真实 UE 材质图截图")
    if not missing_bits:
        missing_bits.append("现场复核")
    return {
        "id": "material_comment_persistence",
        "title": "复核材质注释框持久化",
        "status": "manual_validation_required",
        "reason": "当前会话读回不能证明 Comment Box/中文分组注释在关闭并重开 UE 后仍然存在。",
        "next_action": "补 {0}，再刷新材质证据报告。".format(" + ".join(missing_bits)),
        "source": "material_graph_evidence",
    }


def _dcc_support_action(evidence_bundle):
    summary = _dcc_support_summary_from_evidence(evidence_bundle)
    roadmap = summary.get("roadmap", []) if isinstance(summary, dict) else []
    if not roadmap:
        return {}
    return {
        "id": "dcc_support_contract",
        "title": "说明多 DCC 兼容边界",
        "status": "roadmap_contract",
        "reason": "Maya 是本轮作品集真实链路；{0} 仍是兼容契约和后续路线，不计入 P0 完成度。".format(" / ".join(roadmap)),
        "next_action": "演示时把 Blender / 3ds Max 讲成路线图，不要包装成已完成导出器。",
        "source": "dcc_support_summary",
    }


def _dcc_support_summary_from_evidence(evidence_bundle):
    if not isinstance(evidence_bundle, dict):
        return {}
    summary = evidence_bundle.get("dcc_support_summary", {})
    if isinstance(summary, dict):
        return summary
    for stage_name in ("interface_contract", "maya_ue_interface_contract", "package_acceptance"):
        stage = _embedded_report(evidence_bundle, stage_name)
        summary = stage.get("dcc_support_summary", {}) if isinstance(stage, dict) else {}
        if isinstance(summary, dict) and summary:
            return summary
    return {}


def _int_count(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _embedded_report(evidence_bundle, stage_name):
    if not isinstance(evidence_bundle, dict):
        return {}
    if evidence_bundle.get("stage") == stage_name:
        return evidence_bundle
    direct = evidence_bundle.get(stage_name, {})
    if isinstance(direct, dict):
        return direct
    return _stage(evidence_bundle, stage_name)


def _is_pass_status(status):
    return status in ("pass", "success", "ready")


def _field_validation_next_action(item_id):
    actions = {
        "maya_screen_recording": "录制真实 Maya UI 流程：扫描、风险检查、导出和报告路径。",
        "ue_gate_clicks": "在真实 UE Editor 中点击 UE Gate，并捕获审批与打开报告证据。",
        "material_preview_comment_box": "补 UE 材质预览、注释框和 linked_graph_comments 现场截图。",
        "closed_editor_ubt_clean_install_smoke": "关闭 UE Editor 后跑 UBT，并在干净 UE 工程执行非预演安装冒烟测试。",
    }
    return actions.get(item_id, "补真实现场验证证据。")


def _dedupe_missing_evidence(items):
    result = []
    seen = set()
    for item in items:
        key = (item.get("source", ""), item.get("id", ""), item.get("next_action", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _apply_portfolio_evidence_cap(score, portfolio_missing_evidence):
    field_missing = [item for item in portfolio_missing_evidence if item.get("source") == "field_validation_plan"]
    if len(field_missing) >= 4:
        return min(score, 79)
    if len(field_missing) >= 2:
        return min(score, 84)
    return score


def _missing_evidence_warnings(items):
    return [
        {
            "source": "portfolio_readiness",
            "id": item.get("id", "portfolio_missing_evidence"),
            "message": "{0}: {1}".format(item.get("source", "portfolio_evidence"), item.get("next_action", "")),
        }
        for item in items
        if item.get("next_action")
    ]


def _quality_level(score):
    if score >= 90:
        return "portfolio_ready"
    if score >= 80:
        return "strong_portfolio_wip"
    if score >= 65:
        return "functional_vertical_slice"
    if score >= 50:
        return "internal_alpha"
    return "prototype"


def _portfolio_grade(score):
    if score >= 90:
        return "可作为完整 TA 管线工具作品展示"
    if score >= 80:
        return "可作为强作品展示，但需要说明仍在打磨真实验收和发布边界"
    if score >= 65:
        return "功能纵切片成立，适合展示工程能力，不宜宣称生产级"
    if score >= 50:
        return "内部 Alpha，适合继续开发，不适合作品主展示"
    return "原型阶段"


def _missing_from_dimensions(dimensions):
    result = []
    for item in dimensions:
        if item["status"] == "pass":
            continue
        for action in item.get("next_actions", []):
            if action not in result:
                result.append(action)
    return result


def _next_action(level, missing):
    if level in ("portfolio_ready", "strong_portfolio_wip"):
        return "收口真实验收截图、演示路线和发布边界，然后准备作品展示。"
    if missing:
        return missing[0]
    return "继续补齐真实 Maya/UE 证据和 UE Gate 交互打磨。"


def _recommended_next_features():
    return [
        {"id": "visual_diff_pack", "title": "导入前后视觉对比包", "why": "让 TA 一眼确认模型、贴图、材质是否正确进入 UE。"},
        {"id": "one_click_fix_queue", "title": "Maya 阻断项一键修复队列", "why": "把命名、前缀、贴图集选择从报告问题变成可执行动作。"},
        {"id": "ue_gate_review_mode", "title": "UE Gate 复核模式", "why": "集中展示 Mesh、Texture、Material Instance、日志和报告链接。"},
        {"id": "material_preview_sheet", "title": "材质预览板", "why": "把母材质参数、实例贴图和预览截图放进同一张证据表。"},
        {"id": "clean_install_smoke", "title": "干净工程安装冒烟测试", "why": "证明插件不是只在当前测试工程能跑。"},
    ]
