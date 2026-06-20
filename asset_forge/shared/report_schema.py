"""End-to-end Asset Forge report schema."""

from __future__ import absolute_import

import io
import json
import os

from asset_forge.shared.manifest_schema import ASSET_FORGE_SCHEMA_VERSION
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.report_artifacts import ensure_report_parent

try:
    text_type = unicode
    binary_type = str
except NameError:
    text_type = str
    binary_type = bytes


REPORT_VERSION = "0.1"

NEXT_ACTIONS = {
    "pass": "可以验收",
    "warning": "检查 warnings，确认可接受后继续",
    "error": "修复 errors 后重新执行验收",
    "skipped": "步骤已跳过，按需执行下一步",
    "not_in_unreal": "请在真实 UE 5.6 Editor Python 环境中重新执行该步骤",
    "missing_parent_material": "先确认 AssetForge 插件内容已挂载，并执行默认材质 Bootstrap 后重新检查母材质",
    "missing_manifest": "确认资产包目录内存在 Asset Forge manifest 后重新执行验收",
}


def next_action_for(status="", reason="", can_accept=None, warnings=None, errors=None):
    """Return a stable Chinese next_action for common acceptance states."""
    if reason and reason in NEXT_ACTIONS:
        return NEXT_ACTIONS[reason]
    errors = list(errors or [])
    warnings = list(warnings or [])
    if can_accept is None:
        can_accept = len(errors) == 0 and not _status_blocks_acceptance(status)
    if status in NEXT_ACTIONS and status not in ("pass", "warning", "error"):
        return NEXT_ACTIONS[status]
    if not can_accept or errors or status == "error":
        return NEXT_ACTIONS["error"]
    if warnings or status == "warning":
        return NEXT_ACTIONS["warning"]
    return NEXT_ACTIONS["pass"]


def create_acceptance_summary(status="", warnings=None, errors=None, next_action="", next_action_reason=""):
    """Create the small common acceptance summary shared by Maya/UE/batch reports."""
    warnings = list(warnings or [])
    errors = list(errors or [])
    can_accept = len(errors) == 0 and not _status_blocks_acceptance(status)
    active_next_action = next_action or next_action_for(status, next_action_reason, can_accept, warnings, errors)
    summary = {
        "status": _summary_status(status, warnings, errors),
        "can_accept": can_accept,
        "can_import": can_accept,
        "warnings": warnings,
        "errors": errors,
        "warning_count": len(warnings),
        "error_count": len(errors),
        "next_action": active_next_action,
    }
    summary.update(create_report_guidance(status, warnings, errors, active_next_action, can_accept))
    return summary


def attach_acceptance_summary(report, summary):
    """Attach common acceptance fields without removing existing report data."""
    report["can_accept"] = summary.get("can_accept", False)
    report["can_import"] = summary.get("can_import", summary.get("can_accept", False))
    report["warnings"] = list(summary.get("warnings", []))
    report["errors"] = list(summary.get("errors", []))
    report["next_action"] = summary.get("next_action", "")
    report["decision"] = summary.get("decision", "")
    report["why"] = list(summary.get("why", []))
    report["next_steps"] = list(summary.get("next_steps", []))
    return report


def create_report_guidance(status="", warnings=None, errors=None, next_action="", can_accept=None):
    """Create user-facing guidance while keeping report JSON machine-readable."""
    warnings = list(warnings or [])
    errors = list(errors or [])
    if can_accept is None:
        can_accept = len(errors) == 0 and not _status_blocks_acceptance(status)

    summary_status = _summary_status(status, warnings, errors)
    if not can_accept or errors or _status_blocks_acceptance(summary_status):
        decision = "blocked"
        label = "暂不能导入"
    elif warnings or summary_status == "warning":
        decision = "review_required"
        label = "可导入但需确认"
    elif summary_status == "skipped":
        decision = "not_run"
        label = "步骤未执行"
    else:
        decision = "ready"
        label = "可以导入/验收"

    return {
        "decision": decision,
        "decision_label": label,
        "why": _guidance_why(warnings, errors, decision),
        "next_steps": _guidance_next_steps(warnings, errors, next_action, decision),
    }


def validate_report_schema(report, require_gate=None):
    """Validate the common report envelope used by stage/CI outputs."""
    checks = []
    for field in ["version", "stage", "status", "summary", "can_accept", "warnings", "errors", "next_action"]:
        checks.append(_field_check(report, field))

    summary = report.get("summary", {})
    if isinstance(summary, dict):
        for field in ["status", "can_accept", "warnings", "errors", "next_action"]:
            checks.append(_field_check(summary, field, prefix="summary"))
    else:
        checks.append(_schema_check("summary_shape", "error", "summary 必须是字典"))

    gate_expected = bool(require_gate) if require_gate is not None else any(
        field in report for field in ["gate_status", "gate_passed", "blocking_reasons"]
    )
    if gate_expected:
        for field in ["gate_status", "gate_passed", "blocking_reasons"]:
            checks.append(_field_check(report, field))

    errors = [item for item in checks if item.get("status") == "error"]
    warnings = [item for item in checks if item.get("status") == "warning"]
    validation_summary = create_acceptance_summary(
        "error" if errors else ("warning" if warnings else "pass"),
        warnings,
        errors,
        "修复报告 schema 缺失字段后重新生成报告" if errors else "报告 schema 自检通过",
    )
    return {
        "version": REPORT_VERSION,
        "stage": "report_schema_validation",
        "status": validation_summary.get("status", ""),
        "report_stage": report.get("stage", ""),
        "checks": checks,
        "summary": validation_summary,
        "can_accept": validation_summary.get("can_accept", False),
        "warnings": warnings,
        "errors": errors,
        "next_action": validation_summary.get("next_action", ""),
    }


def attach_report_schema_validation(report, require_gate=None):
    report["report_schema_validation"] = validate_report_schema(report, require_gate)
    return report


def summarize_validation(validation_result):
    checks = validation_result.get("checks", [])
    summary = {
        "status": validation_result.get("status", ""),
        "score": validation_result.get("score", 0),
        "can_export": validation_result.get("can_export", False),
        "errors": [item for item in checks if item.get("status") == "error"],
        "warnings": [item for item in checks if item.get("status") == "warning"],
    }
    summary["next_action"] = next_action_for(summary["status"], can_accept=not summary["errors"], warnings=summary["warnings"], errors=summary["errors"])
    return summary


def summarize_pipeline(export_report=None, import_report=None):
    export_report = export_report or {}
    import_report = import_report or {}
    validation = export_report.get("validation", {})
    texture_folder_scan = export_report.get("texture_folder_scan", {})
    export_material_profile = export_report.get("material_profile_validation", {})
    mesh_policy = import_report.get("static_mesh_import_policy_report", {})
    plugin_content = import_report.get("plugin_content_validation", {})
    material_profile_validation = import_report.get("material_profile_validation", {})
    texture_quality_validation = import_report.get("texture_quality_validation", {})
    texture_plan = import_report.get("texture_import_plan", {})
    texture_policy = import_report.get("texture_import_policy_report", {})
    texture_configuration = import_report.get("texture_configuration_report", {})
    material_plan = import_report.get("material_binding_plan", {})
    material_policy = import_report.get("material_instance_policy_report", {})
    material_texture_binding = import_report.get("material_texture_binding_validation", {})
    material_sampler_policy = import_report.get("material_sampler_policy_validation", {})
    material_graph_evidence = import_report.get("material_graph_evidence_report", {})
    parent_material = import_report.get("parent_material_validation", {})
    material_assignment = import_report.get("material_assignment_report", {})
    post_import = import_report.get("post_import_validation", {})

    warnings = []
    errors = []
    warnings.extend(_messages("maya_validation", validation.get("warnings", [])))
    errors.extend(_messages("maya_validation", validation.get("errors", [])))
    warnings.extend(_plain_messages("texture_folder_scan", texture_folder_scan.get("issues", [])))
    _append_checks(export_material_profile.get("checks", []), "export_material_profile", warnings, errors)

    import_issues = _plain_messages("unreal_import", import_report.get("issues", []))
    if import_report.get("status") == "failed":
        errors.extend(import_issues)
    else:
        warnings.extend(import_issues)

    _append_checks(plugin_content.get("checks", []), "plugin_content", warnings, errors)
    _append_checks(material_profile_validation.get("checks", []), "material_profile", warnings, errors)
    _append_checks(texture_quality_validation.get("checks", []), "texture_quality", warnings, errors)
    warnings.extend(_plain_messages("static_mesh_import_policy", mesh_policy.get("issues", [])))
    warnings.extend(_plain_messages("texture_import", import_report.get("texture_import_issues", [])))
    warnings.extend(_plain_messages("texture_import_policy", texture_policy.get("issues", [])))
    warnings.extend(_plain_messages("texture_configuration", texture_configuration.get("issues", [])))
    warnings.extend(_plain_messages("material_instance", import_report.get("material_instance_issues", [])))
    warnings.extend(_plain_messages("material_instance_policy", material_policy.get("issues", [])))
    _append_material_texture_binding_checks(material_texture_binding, warnings, errors)
    _append_checks(material_sampler_policy.get("checks", []), "material_sampler_policy", warnings, errors)
    _append_checks(material_graph_evidence.get("checks", []), "material_graph_evidence", warnings, errors)
    _append_checks(parent_material.get("checks", []), "parent_material", warnings, errors)
    warnings.extend(_plain_messages("material_assignment", material_assignment.get("issues", [])))
    _append_checks(post_import.get("checks", []), "post_import", warnings, errors)
    if import_report.get("status") == "failed" and not errors:
        errors.append({"source": "unreal_import", "message": import_report.get("message", "Unreal import failed")})

    blocking_error_count = len(errors)
    non_blocking_warning_count = len(warnings)
    pipeline_summary = {
        "status": import_report.get("status") or validation.get("status", ""),
        "export_status": validation.get("status", ""),
        "export_material_profile_status": export_material_profile.get("status", ""),
        "import_status": import_report.get("status", ""),
        "plugin_content_status": plugin_content.get("status", ""),
        "material_profile_status": material_profile_validation.get("status", ""),
        "texture_quality_status": texture_quality_validation.get("status", ""),
        "static_mesh_import_policy_status": mesh_policy.get("status", ""),
        "static_mesh_import_policy_action_count": len(mesh_policy.get("actions", [])),
        "texture_import_count": texture_plan.get("count", 0),
        "imported_texture_count": len(import_report.get("imported_textures", [])),
        "texture_import_policy_status": texture_policy.get("status", ""),
        "texture_import_policy_action_count": len(texture_policy.get("actions", [])),
        "texture_configuration_status": texture_configuration.get("status", ""),
        "configured_texture_count": len(texture_configuration.get("configured", [])),
        "material_plan_count": material_plan.get("count", 0),
        "created_material_instance_count": len(import_report.get("created_material_instances", [])),
        "material_instance_policy_status": material_policy.get("status", ""),
        "material_instance_policy_action_count": len(material_policy.get("actions", [])),
        "material_texture_binding_status": material_texture_binding.get("status", ""),
        "material_texture_binding_warning_count": len(material_texture_binding.get("warnings", [])),
        "material_texture_binding_error_count": len(material_texture_binding.get("errors", [])),
        "material_sampler_policy_status": material_sampler_policy.get("status", ""),
        "material_graph_evidence_status": material_graph_evidence.get("status", ""),
        "parent_material_status": parent_material.get("status", ""),
        "material_assignment_status": material_assignment.get("status", ""),
        "material_assignment_count": len(material_assignment.get("assigned", [])),
        "post_import_status": post_import.get("status", ""),
        "warning_count": non_blocking_warning_count,
        "error_count": blocking_error_count,
        "can_accept": blocking_error_count == 0,
        "blocking_error_count": blocking_error_count,
        "non_blocking_warning_count": non_blocking_warning_count,
        "warnings": warnings,
        "errors": errors,
    }
    pipeline_summary["next_action"] = next_action_for(
        pipeline_summary["status"],
        can_accept=pipeline_summary["can_accept"],
        warnings=warnings,
        errors=errors,
    )
    pipeline_summary["can_import"] = pipeline_summary["can_accept"]
    pipeline_summary.update(
        create_report_guidance(
            pipeline_summary["status"],
            warnings,
            errors,
            pipeline_summary["next_action"],
            pipeline_summary["can_accept"],
        )
    )
    return pipeline_summary


def create_export_report(scan_result, validation_result, manifest, paths):
    validation_summary = summarize_validation(validation_result)
    report = {
        "version": REPORT_VERSION,
        "schema_version": ASSET_FORGE_SCHEMA_VERSION,
        "asset_forge_schema_version": ASSET_FORGE_SCHEMA_VERSION,
        "stage": "maya_export",
        "status": validation_summary.get("status", ""),
        "asset_name": scan_result.get("asset_name", ""),
        "asset_type": manifest.get("asset_type", ""),
        "source_dcc": manifest.get("source_dcc", ""),
        "target_engine": manifest.get("target_engine", ""),
        "target_platform": manifest.get("target_platform", ""),
        "package_dir": normalize_path(paths.get("package_dir", "")),
        "package_name": paths.get("package_name", ""),
        "fbx_path": normalize_path(paths.get("fbx_path", "")),
        "manifest_path": normalize_path(paths.get("manifest_path", "")),
        "material_profiles_snapshot_path": normalize_path(paths.get("material_profiles_snapshot_path", "")),
        "mesh_count": scan_result.get("mesh_count", 0),
        "triangles": scan_result.get("triangles", 0),
        "material_slots": scan_result.get("material_slots", 0),
        "asset_name_candidates": scan_result.get("asset_name_candidates", []),
        "package_naming": manifest.get("package_naming", scan_result.get("package_naming", {})),
        "project_preset": manifest.get("project_preset", scan_result.get("project_preset", {})),
        "materials": scan_result.get("materials", []),
        "material_texture_sets": scan_result.get("material_texture_sets", []),
        "material_texture_bindings": scan_result.get("material_texture_bindings", []),
        "material_texture_binding_risks": scan_result.get("material_texture_binding_risks", []),
        "textures": scan_result.get("textures", []),
        "texture_folder_scan": scan_result.get("texture_folder_scan", {}),
        "asset_health_report": scan_result.get("asset_health_report", {}),
        "texture_import_policy": manifest.get("texture_import_policy", {}),
        "static_mesh_import_policy": manifest.get("static_mesh_import_policy", {}),
        "material_profile_validation": scan_result.get("material_profile_validation", {}),
        "validation": validation_summary,
        "summary": create_acceptance_summary(
            validation_summary.get("status", ""),
            validation_summary.get("warnings", []),
            validation_summary.get("errors", []),
            validation_summary.get("next_action", ""),
        ),
    }
    return attach_acceptance_summary(report, report["summary"])


def create_skeletal_package_report(scan_result, validation_result, manifest, paths):
    validation_summary = summarize_validation(validation_result)
    report = {
        "version": REPORT_VERSION,
        "schema_version": ASSET_FORGE_SCHEMA_VERSION,
        "asset_forge_schema_version": ASSET_FORGE_SCHEMA_VERSION,
        "stage": "skeletal_package",
        "status": validation_summary.get("status", ""),
        "asset_name": scan_result.get("asset_name", ""),
        "asset_type": manifest.get("asset_type", "skeletal_mesh"),
        "source_dcc": manifest.get("source_dcc", ""),
        "target_engine": manifest.get("target_engine", ""),
        "target_platform": manifest.get("target_platform", ""),
        "package_dir": normalize_path(paths.get("package_dir", "")),
        "fbx_path": normalize_path(paths.get("fbx_path", "")),
        "manifest_path": normalize_path(paths.get("manifest_path", "")),
        "skeleton_dir": normalize_path(paths.get("skeleton_dir", "")),
        "animations_dir": normalize_path(paths.get("animations_dir", "")),
        "morph_targets_dir": normalize_path(paths.get("morph_targets_dir", "")),
        "skeleton_manifest_path": normalize_path(paths.get("skeleton_manifest_path", "")),
        "animation_manifest_path": normalize_path(paths.get("animation_manifest_path", "")),
        "morph_target_manifest_path": normalize_path(paths.get("morph_target_manifest_path", "")),
        "root_joint": scan_result.get("root_joint", ""),
        "joint_count": scan_result.get("joint_count", 0),
        "skin_cluster_count": scan_result.get("skin_cluster_count", 0),
        "max_influences": scan_result.get("max_influences", 0),
        "lod_count": scan_result.get("lod_count", 0),
        "material_slots": scan_result.get("material_slots", 0),
        "validation": validation_summary,
        "summary": create_acceptance_summary(
            validation_summary.get("status", ""),
            validation_summary.get("warnings", []),
            validation_summary.get("errors", []),
            validation_summary.get("next_action", ""),
        ),
    }
    return attach_acceptance_summary(report, report["summary"])


def create_end_to_end_report(export_report=None, import_report=None):
    export_report = export_report or {}
    import_report = import_report or {}
    pipeline_summary = summarize_pipeline(export_report, import_report)
    report = {
        "version": REPORT_VERSION,
        "stage": "end_to_end",
        "asset_name": export_report.get("asset_name") or import_report.get("asset_name", ""),
        "export": export_report,
        "import": import_report,
        "pipeline_summary": pipeline_summary,
        "status": import_report.get("status") or export_report.get("validation", {}).get("status", ""),
        "summary": create_acceptance_summary(
            pipeline_summary.get("status", ""),
            pipeline_summary.get("warnings", []),
            pipeline_summary.get("errors", []),
            pipeline_summary.get("next_action", ""),
        ),
        "user_guidance": _user_guidance_from_summary(pipeline_summary),
    }
    return attach_acceptance_summary(report, report["summary"])


def create_batch_report(export_root, dry_run, reports):
    counts = {"success": 0, "failed": 0, "skipped": 0}
    warning_count = 0
    error_count = 0
    warnings = []
    errors = []
    blocked_assets = []
    warning_assets = []
    for report in reports:
        status = report.get("status", "")
        if status in counts:
            counts[status] += 1
        summary = summarize_pipeline(import_report=report)
        warning_count += summary.get("warning_count", 0)
        error_count += summary.get("error_count", 0)
        warnings.extend(summary.get("warnings", []))
        errors.extend(summary.get("errors", []))
        if summary.get("error_count", 0):
            blocked_assets.append(report.get("asset_name", ""))
        elif summary.get("warning_count", 0):
            warning_assets.append(report.get("asset_name", ""))

    batch_summary = create_acceptance_summary(
        "failed" if error_count else ("warning" if warning_count else "success"),
        warnings,
        errors,
        "检查阻断资产并重新执行批量导入" if error_count else ("检查警告资产后可验收" if warning_count else "批量导入报告可验收"),
    )
    batch_summary.update(
        {
            "can_accept": error_count == 0,
            "warning_count": warning_count,
            "error_count": error_count,
            "blocked_assets": [asset for asset in blocked_assets if asset],
            "warning_assets": [asset for asset in warning_assets if asset],
        }
    )
    report = {
        "version": REPORT_VERSION,
        "stage": "batch_import",
        "export_root": normalize_path(export_root),
        "dry_run": bool(dry_run),
        "total": len(reports),
        "counts": counts,
        "summary": batch_summary,
        "reports": reports,
        "asset_decisions": _asset_decisions(reports),
        "user_guidance": _user_guidance_from_summary(batch_summary),
    }
    return attach_acceptance_summary(report, batch_summary)


def write_report(path, report):
    ensure_report_parent(path)
    report = normalize_report_value(report)
    temp_path = path + ".tmp"
    with io.open(temp_path, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2))
        stream.write("\n")
    os.replace(temp_path, path)
    return path


def read_report(path):
    with io.open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def normalize_report_value(value):
    if isinstance(value, dict):
        return dict((normalize_report_value(key), normalize_report_value(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return [normalize_report_value(item) for item in value]
    if isinstance(value, binary_type) and not isinstance(value, text_type):
        for encoding in ("utf-8", "mbcs"):
            try:
                return value.decode(encoding)
            except Exception:
                pass
        return value.decode("utf-8", "replace")
    if isinstance(value, text_type):
        return _repair_report_mojibake(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if hasattr(value, "name") and isinstance(getattr(value, "name"), text_type):
        return getattr(value, "name")
    return str(value)


def _normalize_report_value(value):
    return normalize_report_value(value)


def _guidance_why(warnings, errors, decision):
    messages = [_message_text(item) for item in errors] + [_message_text(item) for item in warnings]
    messages = [item for item in messages if item]
    if messages:
        return messages[:5]
    if decision == "ready":
        return ["未发现阻断项"]
    if decision == "not_run":
        return ["该步骤尚未执行"]
    return ["需要查看报告详情"]


def _guidance_next_steps(warnings, errors, next_action, decision):
    steps = []
    for index, item in enumerate(errors[:3]):
        steps.append(
            {
                "id": "fix_error_{0}".format(index + 1),
                "source": item.get("source", "") if isinstance(item, dict) else "",
                "blocking": True,
                "label": "修复阻断项",
                "detail": _message_text(item),
            }
        )
    if not steps and warnings:
        steps.append(
            {
                "id": "review_warnings",
                "source": "warnings",
                "blocking": False,
                "label": "检查警告",
                "detail": "确认警告是否可接受；严格 gate 下警告也可能阻断。",
            }
        )
    if not steps:
        steps.append(
            {
                "id": "import_or_accept",
                "source": "summary",
                "blocking": False,
                "label": "继续导入或验收",
                "detail": next_action or ("继续导入" if decision == "ready" else "查看报告详情"),
            }
        )
    elif next_action:
        steps.append(
            {
                "id": "rerun",
                "source": "summary",
                "blocking": False,
                "label": "重新执行",
                "detail": next_action,
            }
        )
    return steps


def _user_guidance_from_summary(summary):
    return {
        "decision": summary.get("decision", ""),
        "decision_label": summary.get("decision_label", ""),
        "can_import": summary.get("can_import", summary.get("can_accept", False)),
        "why": list(summary.get("why", [])),
        "next_steps": list(summary.get("next_steps", [])),
    }


def _asset_decisions(reports):
    decisions = []
    for report in reports:
        summary = report.get("summary", {})
        decisions.append(
            {
                "asset_name": report.get("asset_name", ""),
                "status": report.get("status", ""),
                "decision": summary.get("decision", report.get("decision", "")),
                "can_accept": summary.get("can_accept", report.get("can_accept", False)),
                "can_import": summary.get("can_import", report.get("can_import", False)),
                "warning_count": summary.get("warning_count", len(report.get("warnings", []))),
                "error_count": summary.get("error_count", len(report.get("errors", []))),
                "next_action": summary.get("next_action", report.get("next_action", "")),
            }
        )
    return decisions


def _message_text(item):
    if isinstance(item, dict):
        parts = []
        if item.get("source"):
            parts.append(str(item.get("source")))
        if item.get("path"):
            parts.append(str(item.get("path")))
        message = item.get("message", item.get("name", ""))
        if message:
            parts.append(str(message))
        return ": ".join(parts)
    return str(item) if item else ""


def _repair_report_mojibake(value):
    if not isinstance(value, text_type):
        return value
    markers = [
        chr(0x5A34),
        chr(0x762F),
        chr(0x9365),
        chr(0x74BA),
        chr(0x93B5),
        chr(0x7035),
        chr(0x95C3),
        chr(0x74A7),
    ]
    if not any(marker in value for marker in markers):
        return value
    try:
        repaired = value.encode("gbk").decode("utf-8")
    except Exception:
        return value
    return repaired or value


def _append_checks(checks, source, warnings, errors):
    for item in checks:
        status = item.get("status", "")
        if status == "warning":
            warnings.append(_message(source, item))
        elif status == "error":
            errors.append(_message(source, item))


def _append_material_texture_binding_checks(report, warnings, errors):
    checks = (report or {}).get("checks", [])
    if (report or {}).get("blocks_acceptance", True):
        _append_checks(checks, "material_texture_binding", warnings, errors)
        return
    for item in checks:
        status = item.get("status", "")
        if status in ("warning", "error"):
            message = _message("material_texture_binding", item)
            if status == "error":
                message["demoted_from_status"] = "error"
            warnings.append(message)


def _messages(source, items):
    return [_message(source, item) for item in items]


def _plain_messages(source, items):
    result = []
    for item in items:
        if isinstance(item, dict):
            result.append(_message(source, item))
        else:
            result.append({"source": source, "message": str(item)})
    return result


def _message(source, item):
    if isinstance(item, dict):
        return {
            "source": source,
            "id": item.get("id", ""),
            "path": item.get("path", ""),
            "message": item.get("message", item.get("name", "")),
        }
    return {"source": source, "message": str(item)}


def _summary_status(status, warnings, errors):
    if errors:
        return "error"
    if _status_blocks_acceptance(status):
        return "error"
    if warnings and status in ("", "pass", "success", "skipped"):
        return "warning"
    return status or ("warning" if warnings else "pass")


def _status_blocks_acceptance(status):
    return str(status or "").lower() in ("error", "failed", "fail")


def _field_check(data, field, prefix="report"):
    exists = field in data
    return _schema_check(
        "required_field",
        "pass" if exists else "error",
        "{0}.{1} 存在".format(prefix, field) if exists else "{0}.{1} 缺失".format(prefix, field),
        field=field,
        path="{0}.{1}".format(prefix, field),
    )


def _schema_check(check_id, status, message, **extra):
    item = {
        "id": check_id,
        "label": "报告 Schema",
        "status": status,
        "message": message,
    }
    item.update(extra)
    return item
