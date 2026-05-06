"""End-to-end Asset Forge report schema."""

from __future__ import absolute_import

import io
import json

from asset_forge.shared.path_utils import normalize_path


REPORT_VERSION = "0.1"


def summarize_validation(validation_result):
    checks = validation_result.get("checks", [])
    return {
        "status": validation_result.get("status", ""),
        "score": validation_result.get("score", 0),
        "can_export": validation_result.get("can_export", False),
        "errors": [item for item in checks if item.get("status") == "error"],
        "warnings": [item for item in checks if item.get("status") == "warning"],
    }


def summarize_pipeline(export_report=None, import_report=None):
    export_report = export_report or {}
    import_report = import_report or {}
    validation = export_report.get("validation", {})
    texture_folder_scan = export_report.get("texture_folder_scan", {})
    export_material_profile = export_report.get("material_profile_validation", {})
    mesh_policy = import_report.get("static_mesh_import_policy_report", {})
    plugin_content = import_report.get("plugin_content_validation", {})
    material_profile_validation = import_report.get("material_profile_validation", {})
    texture_plan = import_report.get("texture_import_plan", {})
    texture_policy = import_report.get("texture_import_policy_report", {})
    texture_configuration = import_report.get("texture_configuration_report", {})
    material_plan = import_report.get("material_binding_plan", {})
    material_policy = import_report.get("material_instance_policy_report", {})
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
    warnings.extend(_plain_messages("static_mesh_import_policy", mesh_policy.get("issues", [])))
    warnings.extend(_plain_messages("texture_import", import_report.get("texture_import_issues", [])))
    warnings.extend(_plain_messages("texture_import_policy", texture_policy.get("issues", [])))
    warnings.extend(_plain_messages("texture_configuration", texture_configuration.get("issues", [])))
    warnings.extend(_plain_messages("material_instance", import_report.get("material_instance_issues", [])))
    warnings.extend(_plain_messages("material_instance_policy", material_policy.get("issues", [])))
    warnings.extend(_plain_messages("material_assignment", material_assignment.get("issues", [])))
    _append_checks(post_import.get("checks", []), "post_import", warnings, errors)

    blocking_error_count = len(errors)
    non_blocking_warning_count = len(warnings)
    return {
        "status": import_report.get("status") or validation.get("status", ""),
        "export_status": validation.get("status", ""),
        "export_material_profile_status": export_material_profile.get("status", ""),
        "import_status": import_report.get("status", ""),
        "plugin_content_status": plugin_content.get("status", ""),
        "material_profile_status": material_profile_validation.get("status", ""),
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


def create_export_report(scan_result, validation_result, manifest, paths):
    return {
        "version": REPORT_VERSION,
        "stage": "maya_export",
        "asset_name": scan_result.get("asset_name", ""),
        "asset_type": manifest.get("asset_type", ""),
        "source_dcc": manifest.get("source_dcc", ""),
        "target_engine": manifest.get("target_engine", ""),
        "target_platform": manifest.get("target_platform", ""),
        "package_dir": normalize_path(paths.get("package_dir", "")),
        "fbx_path": normalize_path(paths.get("fbx_path", "")),
        "manifest_path": normalize_path(paths.get("manifest_path", "")),
        "material_profiles_snapshot_path": normalize_path(paths.get("material_profiles_snapshot_path", "")),
        "mesh_count": scan_result.get("mesh_count", 0),
        "triangles": scan_result.get("triangles", 0),
        "material_slots": scan_result.get("material_slots", 0),
        "materials": scan_result.get("materials", []),
        "textures": scan_result.get("textures", []),
        "texture_folder_scan": scan_result.get("texture_folder_scan", {}),
        "material_profile_validation": scan_result.get("material_profile_validation", {}),
        "validation": summarize_validation(validation_result),
    }


def create_skeletal_package_report(scan_result, validation_result, manifest, paths):
    return {
        "version": REPORT_VERSION,
        "stage": "skeletal_package",
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
        "validation": summarize_validation(validation_result),
    }


def create_end_to_end_report(export_report=None, import_report=None):
    export_report = export_report or {}
    import_report = import_report or {}
    pipeline_summary = summarize_pipeline(export_report, import_report)
    return {
        "version": REPORT_VERSION,
        "stage": "end_to_end",
        "asset_name": export_report.get("asset_name") or import_report.get("asset_name", ""),
        "export": export_report,
        "import": import_report,
        "pipeline_summary": pipeline_summary,
        "status": import_report.get("status") or export_report.get("validation", {}).get("status", ""),
    }


def create_batch_report(export_root, dry_run, reports):
    counts = {"success": 0, "failed": 0, "skipped": 0}
    warning_count = 0
    error_count = 0
    blocked_assets = []
    warning_assets = []
    for report in reports:
        status = report.get("status", "")
        if status in counts:
            counts[status] += 1
        summary = summarize_pipeline(import_report=report)
        warning_count += summary.get("warning_count", 0)
        error_count += summary.get("error_count", 0)
        if summary.get("error_count", 0):
            blocked_assets.append(report.get("asset_name", ""))
        elif summary.get("warning_count", 0):
            warning_assets.append(report.get("asset_name", ""))

    return {
        "version": REPORT_VERSION,
        "stage": "batch_import",
        "export_root": normalize_path(export_root),
        "dry_run": bool(dry_run),
        "total": len(reports),
        "counts": counts,
        "summary": {
            "can_accept": error_count == 0,
            "warning_count": warning_count,
            "error_count": error_count,
            "blocked_assets": [asset for asset in blocked_assets if asset],
            "warning_assets": [asset for asset in warning_assets if asset],
        },
        "reports": reports,
    }


def write_report(path, report):
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2))
        stream.write("\n")
    return path


def read_report(path):
    with io.open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def _append_checks(checks, source, warnings, errors):
    for item in checks:
        status = item.get("status", "")
        if status == "warning":
            warnings.append(_message(source, item))
        elif status == "error":
            errors.append(_message(source, item))


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
