"""North Star readiness scoring for DCC AssetForge offline validation."""

from __future__ import absolute_import

from asset_forge.shared.report_schema import REPORT_VERSION, attach_acceptance_summary, create_acceptance_summary


DIMENSIONS = [
    ("package_protocol", 10),
    ("dcc_compatibility_contract", 0),
    ("material_profile", 15),
    ("texture_quality", 10),
    ("reporting", 10),
    ("idempotency", 10),
    ("batch", 10),
    ("doctor", 10),
    ("stage_gate", 10),
    ("real_ue_validation", 15),
]


def create_north_star_readiness(stage_bundle=None, capability_matrix=None):
    """Score readiness from offline evidence without pretending real UE passed."""
    stage_bundle = stage_bundle or {}
    capability_matrix = capability_matrix or {}
    capability_items = dict((item.get("id"), item) for item in capability_matrix.get("items", []))
    real_ue_ready = _real_ue_validation_ready(stage_bundle)
    items = [
        _dimension(
            "dcc_compatibility_contract",
            0,
            False,
            [
                "Maya is the MVP real export path.",
                "Blender and 3ds Max are roadmap/contract-only DCC targets.",
            ],
            ["No Blender/3ds Max real-chain validation is claimed in MVP."],
            "Keep roadmap DCC targets contract-only until real adapter/export/import evidence exists.",
        ),
        _dimension("package_protocol", 10, _package_protocol_ready(stage_bundle), ["contract-check", "package acceptance report"], [], "保持 package acceptance 与接口契约证据可读"),
        _dimension("material_profile", 15, _material_profile_ready(stage_bundle, capability_items), ["Material Profile lint/contract"], [], "修复 profile lint/contract 警告"),
        _dimension("texture_quality", 10, _texture_quality_ready(stage_bundle), ["texture quality validation", "dry-run report"], [], "保持贴图尺寸/格式/sRGB/compression 证据"),
        _dimension("reporting", 10, _reporting_ready(stage_bundle), ["report schema validation"], [], "保持报告 schema 自检通过"),
        _dimension("idempotency", 10, _idempotency_ready(stage_bundle, capability_items), ["same-name strategy simulation", "gate evidence"], [], "保留 overwrite/reuse/skip/error 策略证据"),
        _dimension("batch", 10, _has_stage(stage_bundle, "batch_flow"), ["batch acceptance flow"], [], "运行 --accept-flow-all 作为批量证据"),
        _dimension("doctor", 10, _has_stage(stage_bundle, "doctor"), ["doctor report"], [], "运行 --doctor 或 --pretest-check 并保留 JSON"),
        _dimension("stage_gate", 10, _has_gate(stage_bundle), ["gate_status/gate_passed"], [], "保留 gate_status/gate_passed 证据"),
        _dimension(
            "real_ue_validation",
            15,
            real_ue_ready,
            _real_ue_validation_evidence(stage_bundle) if real_ue_ready else [],
            [] if real_ue_ready else ["真实 UE 5.6 evidence 缺失"],
            "在 UE 5.6 中执行 checklist、真实导入和导入后验证。",
        ),
    ]
    total_weight = sum(item["weight"] for item in items)
    weighted_score = sum(item["score"] * item["weight"] for item in items) / float(total_weight)
    warnings = [
        {"source": "north_star_readiness", "id": item["id"], "message": "缺少证据：{0}".format(", ".join(item["missing_evidence"]))}
        for item in items
        if item["missing_evidence"]
    ]
    next_action = "离线 evidence 可提升 readiness；真实 UE validation 仍需人工复测后补证据。"
    if real_ue_ready and not warnings:
        next_action = "北极星核心证据已闭合；进入提交边界、发布交付和作品集演示收口。"
    elif real_ue_ready:
        next_action = "真实 UE 验证证据已接入；继续修复剩余 warning 并整理提交边界。"
    summary = create_acceptance_summary(
        "warning" if warnings else "pass",
        warnings,
        [],
        next_action,
    )
    report = {
        "version": REPORT_VERSION,
        "stage": "north_star_readiness",
        "status": summary.get("status", ""),
        "score": round(weighted_score, 2),
        "max_score": 100,
        "items": items,
        "manual_validation_required": _manual_validation_required(real_ue_ready),
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _dimension(item_id, weight, passed, evidence, missing_evidence, next_action):
    status = "pass" if passed else ("manual_validation_required" if item_id == "real_ue_validation" else "warning")
    return {
        "id": item_id,
        "weight": weight,
        "score": 100 if passed else 0,
        "status": status,
        "evidence": list(evidence or []),
        "missing_evidence": [] if passed else list(missing_evidence or ["离线证据缺失"]),
        "next_action": next_action,
    }


def _stage(bundle, name):
    if not isinstance(bundle, dict):
        return {}
    stage = bundle.get("stages", {}).get(name, {})
    if not stage and bundle.get("stage") == name:
        stage = bundle
    return stage if isinstance(stage, dict) else {}


def _has_stage(bundle, name):
    stage = _stage(bundle, name)
    return bool(stage and stage.get("status") not in ("missing", "error"))


def _has_gate(bundle):
    if "gate_status" in bundle:
        return True
    for stage in bundle.get("stages", {}).values():
        if isinstance(stage, dict) and "gate_status" in stage:
            return True
    return False


def _real_ue_validation_ready(bundle):
    if not isinstance(bundle, dict):
        return False
    if _is_real_ue_completion_stage(bundle):
        return True
    marker = bundle.get("tas_102_real_ue_evidence")
    if _is_real_ue_completion_stage(marker):
        return True
    for stage_name in ("real_ue_validation", "tas_102_real_ue_validation", "ue_import_validation", "accept_flow"):
        if _is_real_ue_completion_stage(_stage(bundle, stage_name)):
            return True
    return False


def _is_real_ue_completion_stage(stage):
    if not isinstance(stage, dict):
        return False
    if not stage.get("is_tas_102_completion_evidence", False):
        return False
    if stage.get("status") not in ("pass", "success"):
        return False
    if "gate_passed" in stage and not stage.get("gate_passed"):
        return False
    if "can_accept" in stage and not stage.get("can_accept"):
        return False
    post_import = stage.get("post_import_validation", {})
    if post_import and post_import.get("status") not in ("pass", "success"):
        return False
    return True


def _real_ue_validation_evidence(bundle):
    evidence = []
    if _is_real_ue_completion_stage(bundle):
        evidence.append(bundle.get("stage", "top_level_real_ue_validation"))
    if _is_real_ue_completion_stage(bundle.get("tas_102_real_ue_evidence")):
        evidence.append("tas_102_real_ue_evidence")
    for stage_name in ("real_ue_validation", "tas_102_real_ue_validation", "ue_import_validation", "accept_flow"):
        if _is_real_ue_completion_stage(_stage(bundle, stage_name)):
            evidence.append(stage_name)
    return evidence or ["real UE validation evidence"]


def _manual_validation_required(real_ue_ready):
    if real_ue_ready:
        return []
    return [
        "真实 UE 5.6：执行实际导入。",
        "真实 UE 5.6：确认 Static Mesh、Texture、材质实例与母材质网络。",
        "真实 Maya：用用户工程执行一次 UI 导出复测。",
    ]


def _capability_status(items, item_id):
    return items.get(item_id, {}).get("status", "missing")


def _package_protocol_ready(bundle):
    return _has_stage(bundle, "package_acceptance") and (_has_stage(bundle, "contract_check") or _has_stage(bundle, "maya_ue_interface_contract"))


def _material_profile_ready(bundle, capability_items):
    if _has_stage(bundle, "package_acceptance"):
        return True
    return _capability_status(capability_items, "material_profile") not in ("missing", "blocked", "error")


def _texture_quality_ready(bundle):
    package_acceptance = _stage(bundle, "package_acceptance")
    if _has_stage(bundle, "dry_run") and _has_stage(bundle, "package_acceptance"):
        return True
    return bool(package_acceptance.get("texture_quality_validation"))


def _reporting_ready(bundle):
    return bool(bundle.get("report_schema_validation")) or _has_stage(bundle, "report_schema_validation")


def _idempotency_ready(bundle, capability_items):
    if _has_stage(bundle, "package_acceptance"):
        acceptance = _stage(bundle, "package_acceptance")
        if acceptance.get("same_name_strategy_simulation"):
            return True
    return _capability_status(capability_items, "strict_gate") not in ("missing", "blocked", "error")
