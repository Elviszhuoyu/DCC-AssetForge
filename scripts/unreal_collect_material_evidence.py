"""Collect real UE material evidence for an existing DCC AssetForge import report."""

from __future__ import absolute_import

import json
import os
import sys


def _ensure_project_root():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    for name in list(sys.modules):
        if name == "asset_forge" or name.startswith("asset_forge."):
            del sys.modules[name]
    return project_root


def collect_material_evidence(report_path, output_path=None, cold_start_readback=False):
    _ensure_project_root()
    from asset_forge.shared.report_schema import attach_acceptance_summary, read_report, summarize_pipeline, write_report
    from asset_forge.unreal.material_asset_bootstrap import UnrealMaterialAssetBootstrap
    from asset_forge.unreal.material_evidence_collector import UnrealMaterialEvidenceCollector
    from asset_forge.unreal.material_graph_evidence import build_material_graph_evidence_report

    data = read_report(report_path)
    import_report = data.get("import", data)
    evidence = UnrealMaterialEvidenceCollector().collect(import_report)
    import_report.update(evidence)
    if cold_start_readback:
        _mark_cold_start_comment_readback(import_report.get("real_ue_material_graph", {}))
    network_reports = import_report.get("material_asset_bootstrap_report", {}).get("material_network_reports", [])
    if not network_reports:
        network_reports = UnrealMaterialAssetBootstrap().plan().get("material_network_plans", [])
    import_report["material_graph_evidence_report"] = build_material_graph_evidence_report(
        material_binding_plan=import_report.get("material_binding_plan", {}),
        parent_material_validation=import_report.get("parent_material_validation", {}),
        material_network_reports=network_reports,
        material_parameter_report=import_report.get("material_parameter_report", {}),
        material_assignment_report=import_report.get("material_assignment_report", {}),
        material_sampler_policy_validation=import_report.get("material_sampler_policy_validation", {}),
        compile_log_evidence=import_report.get("material_compile_log_evidence", {}),
        real_ue_material_graph=import_report.get("real_ue_material_graph", {}),
        material_texture_binding_validation=import_report.get("material_texture_binding_validation", {}),
    )
    import_report["summary"] = summarize_pipeline(import_report=import_report)
    attach_acceptance_summary(import_report, import_report["summary"])
    visual_review_fields = _attach_top_level_visual_review(import_report)
    if "import" in data:
        data["import"] = import_report
        data["status"] = import_report.get("summary", {}).get("status", data.get("status", ""))
        data["can_accept"] = import_report.get("can_accept", data.get("can_accept", False))
        data["warnings"] = list(import_report.get("warnings", []) or [])
        data["errors"] = list(import_report.get("errors", []) or [])
        data["next_action"] = import_report.get("next_action", data.get("next_action", ""))
        data.update(visual_review_fields)
        data.setdefault("summary", {})
        data["summary"].update(
            {
                "status": data["status"],
                "can_accept": data["can_accept"],
                "warnings": list(data["warnings"]),
                "errors": list(data["errors"]),
                "warning_count": len(data["warnings"]),
                "error_count": len(data["errors"]),
                "next_action": data["next_action"],
            }
        )
        _attach_visual_review_summary(data["summary"], visual_review_fields)
    else:
        data = import_report
    target = output_path or report_path
    write_report(target, data)
    return data


def _mark_cold_start_comment_readback(real_ue_material_graph):
    if not isinstance(real_ue_material_graph, dict):
        return
    for material in real_ue_material_graph.get("materials", []) or []:
        comment_blocks = material.get("comment_blocks", {}) or {}
        if comment_blocks.get("status") != "pass":
            continue
        comment_blocks["cold_start_readback_status"] = "pass"
        comment_blocks["cold_start_readback_required"] = False
        comment_blocks["persistence_status"] = "cold_start_readback_provided"
        comment_blocks["persistence_boundary"] = "fresh_unreal_process_readback"


def _attach_top_level_visual_review(import_report):
    graph = import_report.get("material_graph_evidence_report", {}) or {}
    visual_review = dict(graph.get("ta_visual_review", {}) or {})
    if not visual_review:
        return {}

    fields = {
        "ta_visual_review": visual_review,
        "ta_visual_review_status": visual_review.get("status", ""),
        "screenshot_evidence_status": visual_review.get("screenshot_evidence", ""),
        "comment_box_persistence_status": visual_review.get("comment_box_persistence_status", ""),
        "comment_box_cold_start_readback_required": visual_review.get("cold_start_readback_required", False),
        "comment_box_real_ue_screenshot_required": visual_review.get("real_ue_screenshot_required", False),
        "ta_visual_review_next_action": visual_review.get("next_action", ""),
    }
    import_report.update(fields)
    _attach_visual_review_summary(import_report.get("summary", {}), fields)
    return fields


def _attach_visual_review_summary(summary, visual_review_fields):
    if not isinstance(summary, dict) or not visual_review_fields:
        return
    for name in (
        "ta_visual_review_status",
        "screenshot_evidence_status",
        "comment_box_persistence_status",
        "comment_box_cold_start_readback_required",
        "comment_box_real_ue_screenshot_required",
        "ta_visual_review_next_action",
    ):
        summary[name] = visual_review_fields.get(name, "")


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    if not argv:
        raise SystemExit("Usage: unreal_collect_material_evidence.py <report_path> [output_path] [--cold-start-readback]")
    cold_start_readback = "--cold-start-readback" in argv
    argv = [item for item in argv if item != "--cold-start-readback"]
    report = collect_material_evidence(argv[0], argv[1] if len(argv) > 1 else None, cold_start_readback=cold_start_readback)
    import_report = report.get("import", report)
    graph = import_report.get("material_graph_evidence_report", {})
    print(
        json.dumps(
            {
                "status": report.get("status", ""),
                "can_accept": report.get("can_accept", False),
                "import_status": import_report.get("status", ""),
                "import_summary": import_report.get("summary", {}).get("status", ""),
                "material_graph_evidence_status": graph.get("status", ""),
                "real_ue_evidence": graph.get("real_ue_evidence", ""),
                "ta_visual_review_status": import_report.get("ta_visual_review_status", ""),
                "screenshot_evidence_status": import_report.get("screenshot_evidence_status", ""),
                "comment_box_persistence_status": import_report.get("comment_box_persistence_status", ""),
                "comment_box_cold_start_readback_required": import_report.get("comment_box_cold_start_readback_required", False),
                "comment_box_real_ue_screenshot_required": import_report.get("comment_box_real_ue_screenshot_required", False),
                "ta_visual_review_next_action": import_report.get("ta_visual_review_next_action", ""),
                "compile_log_status": import_report.get("material_compile_log_evidence", {}).get("status", ""),
                "real_graph_status": import_report.get("real_ue_material_graph", {}).get("status", ""),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
