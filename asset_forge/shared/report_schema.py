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


def create_end_to_end_report(export_report=None, import_report=None):
    export_report = export_report or {}
    import_report = import_report or {}
    return {
        "version": REPORT_VERSION,
        "stage": "end_to_end",
        "asset_name": export_report.get("asset_name") or import_report.get("asset_name", ""),
        "export": export_report,
        "import": import_report,
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
