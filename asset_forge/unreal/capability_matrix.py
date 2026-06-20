"""Acceptance coverage and capability matrix."""

from __future__ import absolute_import

from asset_forge.shared.report_schema import REPORT_VERSION, attach_acceptance_summary, create_acceptance_summary


def create_capability_matrix(evidence=None):
    evidence = evidence or {}
    items = [
        _item(
            "dcc_compatibility_contract",
            "manual_validation_required",
            [
                "Maya is the MVP real export path.",
                "Blender and 3ds Max are roadmap/contract-only DCC targets.",
            ],
            ["No Blender/3ds Max real-chain validation is claimed in MVP."],
            "Keep Maya as the MVP real chain; treat Blender/3ds Max as roadmap contract coverage only.",
        ),
        _item("maya_export", "warning", evidence.get("maya_export", []), ["当前离线 bundle 未运行 Maya 导出"], "在 Maya 侧生成 export report 后补充证据"),
        _item("material_profile", "pass", evidence.get("material_profile", ["Material Profile schema/lint 离线测试"]), [], "继续保持 profile snapshot 回归"),
        _item("package_acceptance", _status_from_report(evidence.get("package_acceptance_report")), _evidence_from_report(evidence.get("package_acceptance_report")), [], "使用 --validate-package 或 accept-flow 生成包验收证据"),
        _item("dry_run", _status_from_report(evidence.get("dry_run_report")), _evidence_from_report(evidence.get("dry_run_report")), [], "使用 --package --dry-run 或 accept-flow dry-run 证据"),
        _item("import", "blocked", [], ["未启动真实 UE Editor import"], "TAS-102 完成前需要 UE 5.6 实机 import 证据"),
        _item("post_import_validation", "blocked", [], ["未启动真实 UE Editor post-import validation"], "TAS-102 完成前需要 UE 5.6 post-import validation 证据"),
        _item("batch", _status_from_report(evidence.get("batch_flow_report")), _evidence_from_report(evidence.get("batch_flow_report")), [], "使用 --accept-flow-all 生成批量证据"),
        _item("doctor", _status_from_report(evidence.get("doctor_report")), _evidence_from_report(evidence.get("doctor_report")), [], "使用 --doctor 生成环境自检证据"),
        _item("strict_gate", _gate_status(evidence), _gate_evidence(evidence), [], "使用 --strict 生成 gate_passed 证据"),
        _item("real_ue_plugin_content", "manual_validation_required", [], ["未捕获真实 /AssetForge mount 与母材质资产证据"], "按 UE validation checklist 捕获 TAS-102 实机证据"),
    ]
    warnings = [
        {"source": "capability_matrix", "id": item["id"], "message": "缺少证据：{0}".format(", ".join(item["missing_evidence"]))}
        for item in items
        if item["missing_evidence"]
    ]
    summary = create_acceptance_summary("warning" if warnings else "pass", warnings, [], "补齐 missing_evidence 后更新能力矩阵" if warnings else "能力矩阵证据完整")
    report = {
        "version": REPORT_VERSION,
        "stage": "capability_matrix",
        "status": summary.get("status", ""),
        "items": items,
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _item(item_id, status, evidence, missing_evidence, next_action):
    return {
        "id": item_id,
        "status": status,
        "evidence": list(evidence or []),
        "missing_evidence": list(missing_evidence or []),
        "next_action": next_action,
    }


def _status_from_report(report):
    if not report:
        return "warning"
    if report.get("gate_status") == "failed":
        return "warning"
    return report.get("status", "warning")


def _evidence_from_report(report):
    if not report:
        return []
    return ["{0}:{1}".format(report.get("stage", ""), report.get("status", ""))]


def _gate_status(evidence):
    reports = [evidence.get("package_acceptance_report"), evidence.get("accept_flow_report"), evidence.get("batch_flow_report")]
    gate_reports = [item for item in reports if item and "gate_passed" in item]
    if not gate_reports:
        return "warning"
    return "pass" if all(item.get("gate_passed", False) for item in gate_reports) else "warning"


def _gate_evidence(evidence):
    result = []
    for report in [evidence.get("package_acceptance_report"), evidence.get("accept_flow_report"), evidence.get("batch_flow_report")]:
        if report and "gate_passed" in report:
            result.append("{0}:gate_passed={1}".format(report.get("stage", ""), report.get("gate_passed")))
    return result
