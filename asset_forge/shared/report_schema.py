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
    plugin_content = import_report.get("plugin_content_validation", {})
    texture_plan = import_report.get("texture_import_plan", {})
    texture_configuration = import_report.get("texture_configuration_report", {})
    material_plan = import_report.get("material_binding_plan", {})
    material_assignment = import_report.get("material_assignment_report", {})
    post_import = import_report.get("post_import_validation", {})

    warnings = []
    errors = []
    warnings.extend(_messages("maya_validation", validation.get("warnings", [])))
    errors.extend(_messages("maya_validation", validation.get("errors", [])))

    import_issues = _plain_messages("unreal_import", import_report.get("issues", []))
    if import_report.get("status") == "failed":
        errors.extend(import_issues)
    else:
        warnings.extend(import_issues)

    _append_checks(plugin_content.get("checks", []), "plugin_content", warnings, errors)
    warnings.extend(_plain_messages("texture_import", import_report.get("texture_import_issues", [])))
    warnings.extend(_plain_messages("texture_configuration", texture_configuration.get("issues", [])))
    warnings.extend(_plain_messages("material_instance", import_report.get("material_instance_issues", [])))
    warnings.extend(_plain_messages("material_assignment", material_assignment.get("issues", [])))
    _append_checks(post_import.get("checks", []), "post_import", warnings, errors)

    return {
        "status": import_report.get("status") or validation.get("status", ""),
        "export_status": validation.get("status", ""),
        "import_status": import_report.get("status", ""),
        "plugin_content_status": plugin_content.get("status", ""),
        "texture_import_count": texture_plan.get("count", 0),
        "imported_texture_count": len(import_report.get("imported_textures", [])),
        "texture_configuration_status": texture_configuration.get("status", ""),
        "configured_texture_count": len(texture_configuration.get("configured", [])),
        "material_plan_count": material_plan.get("count", 0),
        "created_material_instance_count": len(import_report.get("created_material_instances", [])),
        "material_assignment_status": material_assignment.get("status", ""),
        "material_assignment_count": len(material_assignment.get("assigned", [])),
        "post_import_status": post_import.get("status", ""),
        "warning_count": len(warnings),
        "error_count": len(errors),
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
        "mesh_count": scan_result.get("mesh_count", 0),
        "triangles": scan_result.get("triangles", 0),
        "material_slots": scan_result.get("material_slots", 0),
        "materials": scan_result.get("materials", []),
        "textures": scan_result.get("textures", []),
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
    for report in reports:
        status = report.get("status", "")
        if status in counts:
            counts[status] += 1

    return {
        "version": REPORT_VERSION,
        "stage": "batch_import",
        "export_root": normalize_path(export_root),
        "dry_run": bool(dry_run),
        "total": len(reports),
        "counts": counts,
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
    return [{"source": source, "message": str(item)} for item in items]


def _message(source, item):
    if isinstance(item, dict):
        return {
            "source": source,
            "id": item.get("id", ""),
            "path": item.get("path", ""),
            "message": item.get("message", item.get("name", "")),
        }
    return {"source": source, "message": str(item)}
