# -*- coding: utf-8 -*-
"""Data model for the Asset Forge Unreal intake/gate panel."""

from __future__ import absolute_import

import datetime
import io
import json
import os

from asset_forge.shared.path_utils import normalize_path
from asset_forge.unreal.manifest_finder import find_manifest_files, find_latest_manifest


STATUS_LABELS = {
    "ready": "已就绪",
    "empty": "暂无包体",
    "pass": "通过",
    "success": "导入成功",
    "warning": "需复核",
    "error": "阻断",
    "failed": "导入失败",
    "skipped": "预检通过",
    "not_checked": "待审批",
    "missing": "缺失",
    "missing_source": "源文件缺失",
}

SOURCE_DCC_LABELS = {
    "maya": "Maya",
    "blender": "Blender",
    "houdini": "Houdini",
    "unreal": "Unreal",
}

DCC_PACKAGE_ROOT_NAME = "dcc_packages"
HISTORY_SKIP_DIR_NAMES = set(["backups", "debug", "field_validation", "logs", "portfolio_captures", "runtime_alias"])

try:
    text_type = unicode
except NameError:
    text_type = str


def discover_package_history(export_root="", latest_maya_log_path=None, latest_unreal_log_path=None, limit=20, latest_blender_log_path=None):
    """Find recent Asset Forge packages from Maya/UE logs and an optional root."""
    records = []
    maya_log_path = _default_latest_maya_log() if latest_maya_log_path is None else latest_maya_log_path
    unreal_log_path = _default_latest_unreal_log() if latest_unreal_log_path is None else latest_unreal_log_path
    blender_log_path = _default_latest_blender_log() if latest_blender_log_path is None else latest_blender_log_path
    records.extend(_records_from_log(maya_log_path, "maya_export"))
    records.extend(_records_from_log(blender_log_path, "blender_export"))
    records.extend(_records_from_log(unreal_log_path, "unreal_import"))
    records.extend(_records_from_export_root(export_root))
    import_records = [record for record in records if _is_import_record(record)]

    packages = []
    seen = set()
    for record in sorted(records, key=_record_sort_key, reverse=True):
        package_dir = record.get("package_dir", "")
        if not package_dir or package_dir in seen or _skip_history_package_dir(package_dir):
            continue
        seen.add(package_dir)
        summary = build_package_summary(package_dir)
        summary.update(
            {
                "history_source": record.get("source", ""),
                "history_operation": record.get("operation", ""),
                "history_status": record.get("status", ""),
                "history_status_label": _status_label(record.get("status", "")),
                "history_timestamp": record.get("timestamp", ""),
            }
        )
        _attach_last_import(summary, import_records)
        packages.append(summary)
        if limit and len(packages) >= int(limit):
            break

    latest = packages[0]["package_dir"] if packages else ""
    return {
        "status": "ready" if packages else "empty",
        "status_label": "已发现 {0} 个可审包体".format(len(packages)) if packages else "暂无可审包体",
        "empty_title": "" if packages else "还没有发现 Asset Forge 导出包",
        "empty_message": "" if packages else "请选择导出目录，或先从 DCC 导出一个包含 manifest 的包体。",
        "latest_package_dir": latest,
        "package_count": len(packages),
        "packages": packages,
    }


def build_gate_panel_state(package_dir="", export_root="", latest_maya_log_path=None, latest_unreal_log_path=None, report_path=None, acceptance_validator=None):
    """Build the visible UE Gate state: history, selected package, and preflight summary."""
    if isinstance(package_dir, (list, tuple, set)) and not export_root:
        export_root = package_dir
        package_dir = ""
    history = discover_package_history(export_root, latest_maya_log_path, latest_unreal_log_path)
    selected_package_dir = normalize_path(package_dir or history.get("latest_package_dir", ""))
    selected = build_package_summary(selected_package_dir) if selected_package_dir else {}
    preview = {}
    if selected_package_dir and report_path is not False:
        preview = preview_package_gate(selected_package_dir, report_path=report_path, acceptance_validator=acceptance_validator)
        selected = preview
    return {
        "status": "ready" if selected_package_dir else history.get("status", "empty"),
        "status_label": "导入门禁已就绪" if selected_package_dir else history.get("status_label", "暂无可审包体"),
        "title": "Asset Forge 导入门禁工作台",
        "subtitle": "扫描本地 AF 导出包，生成入审报告、预演导入计划后再正式导入。",
        "export_root": _display_export_roots(export_root),
        "latest_package_dir": history.get("latest_package_dir", ""),
        "history": history,
        "selected_package_dir": selected_package_dir,
        "selected_package": selected,
        "preview": preview,
        "sections": _panel_sections(selected),
        "can_import": bool(selected.get("can_accept")),
        "next_action": selected.get("next_action", "从 DCC 导出 Asset Forge 包体后刷新门禁工作台。"),
        "approval": _approval_summary(selected),
    }


def preview_package_gate(package_dir, report_path=None, acceptance_validator=None):
    """Run package acceptance and return a compact UI-ready summary."""
    validator = acceptance_validator
    if validator is None:
        from asset_forge.unreal.package_acceptance import UnrealPackageAcceptanceValidator

        validator = UnrealPackageAcceptanceValidator()
    report = validator.validate(package_dir, report_path=report_path)
    return build_package_summary(package_dir, acceptance_report=report)


def latest_package_dir_from_maya_log(log_path=""):
    records = _records_from_log(log_path or _default_latest_maya_log(), "maya_export")
    for record in sorted(records, key=_record_sort_key, reverse=True):
        if record.get("package_dir"):
            return record.get("package_dir")
    return ""


def build_package_summary(package_dir, acceptance_report=None):
    manifest_path = _first_manifest_path(package_dir)
    manifest = _read_json(manifest_path)
    package_dir = normalize_path(package_dir)
    has_manifest = bool(manifest_path and manifest)
    target_path = manifest.get("target_path", "") or "/Game/Props"
    asset_name = manifest.get("asset_name", "") or os.path.basename(os.path.normpath(package_dir))
    textures = list(manifest.get("textures", []) or [])
    materials = list(manifest.get("materials", []) or [])
    gate = _gate_summary(acceptance_report)
    profile = _profile_summary(manifest, acceptance_report)
    source_dcc = manifest.get("source_dcc", "")
    package_naming = manifest.get("package_naming", {}) if isinstance(manifest.get("package_naming", {}), dict) else {}
    project_preset = manifest.get("project_preset", {}) if isinstance(manifest.get("project_preset", {}), dict) else {}
    schema_version = manifest.get("asset_forge_schema_version", "") or manifest.get("schema_version", "") or manifest.get("version", "")
    export_time = _manifest_export_time(manifest, package_dir)
    mesh_count = _asset_count(manifest)
    risk = _risk_summary(manifest, gate, has_manifest)
    last_import = _latest_import_summary(package_dir)
    recent_reports = _recent_report_summaries(package_dir, acceptance_report)
    latest_report = recent_reports[0] if recent_reports else {}
    active_report_path = normalize_path((acceptance_report or {}).get("report_path", "")) or latest_report.get("report_path", "")
    active_report = _matching_report_summary(recent_reports, active_report_path)
    return {
        "package_dir": package_dir,
        "package_name": os.path.basename(os.path.normpath(package_dir)) or asset_name,
        "manifest_package_name": package_naming.get("package_name", ""),
        "package_version_mode": package_naming.get("version_mode", ""),
        "package_version_label": package_naming.get("version_label", ""),
        "package_naming": package_naming,
        "project_preset_name": project_preset.get("preset_name", ""),
        "project_preset_version": project_preset.get("preset_version", ""),
        "project_preset": project_preset,
        "manifest_path": normalize_path(manifest_path) if manifest_path else "",
        "asset_name": asset_name,
        "display_name": asset_name,
        "source_dcc": source_dcc,
        "source_dcc_label": _source_dcc_label(source_dcc),
        "schema_version": schema_version,
        "export_time": export_time,
        "export_time_label": export_time or "使用文件修改时间",
        "target_path": target_path,
        "fbx_path": normalize_path(_manifest_fbx_path(manifest)),
        "asset_count": mesh_count,
        "mesh_count": mesh_count,
        "mesh_status": _mesh_status(manifest),
        "mesh_status_label": _status_label(_mesh_status(manifest)),
        "texture_count": len(textures),
        "texture_status": _item_status(textures, "ready"),
        "texture_status_label": _status_label(_item_status(textures, "ready")),
        "material_count": len(materials),
        "material_status": _item_status(materials, "ready"),
        "material_status_label": _status_label(_item_status(materials, "ready")),
        "profile_name": profile.get("name", ""),
        "profile_count": profile.get("count", 0),
        "profile_status": profile.get("status", "missing"),
        "profile_status_label": _status_label(profile.get("status", "missing")),
        "profile_snapshot_path": profile.get("snapshot_path", ""),
        "textures": _texture_rows(textures),
        "materials": _material_rows(materials),
        "can_accept": gate.get("can_accept"),
        "gate_status": gate.get("status", "not_checked"),
        "gate_status_label": _status_label(gate.get("status", "not_checked")),
        "risk_status": risk.get("status", ""),
        "risk_status_code": risk.get("code", ""),
        "risk_message": risk.get("message", ""),
        "warning_count": gate.get("warning_count", 0),
        "error_count": gate.get("error_count", 0),
        "warnings": gate.get("warnings", []),
        "errors": gate.get("errors", []),
        "blocking_checks": gate.get("blocking_checks", []),
        "warning_checks": gate.get("warning_checks", []),
        "next_action": gate.get("next_action", "先生成入审报告，再决定是否预演导入计划。"),
        "overwrite_strategy": _overwrite_strategy(manifest, acceptance_report),
        "report_path": active_report_path,
        "latest_report_path": latest_report.get("report_path", ""),
        "can_open_report": bool(active_report.get("can_open", False)),
        "recent_reports": recent_reports,
        "recent_imports": [report for report in recent_reports if report.get("kind") == "import"],
        "last_import_status": last_import.get("status", "暂无导入记录"),
        "last_import_status_code": last_import.get("status_code", ""),
        "last_import_operation": last_import.get("operation", ""),
        "last_import_time": last_import.get("timestamp", ""),
        "last_import_report_path": last_import.get("report_path", ""),
        "ui_summary": _ui_summary(asset_name, source_dcc, target_path, mesh_count, len(textures), len(materials), risk),
    }


def format_gate_panel_text(state):
    selected = state.get("selected_package", {}) or {}
    history = state.get("history", {}) or {}
    packages = history.get("packages", []) or []
    lines = [
        "Asset Forge 导入门禁工作台",
        "",
        "扫描目录: {0}".format(state.get("export_root", "") or "最近日志"),
        "包体队列: {0}".format(history.get("package_count", 0)),
    ]
    for index, package in enumerate(packages[:5], 1):
        lines.append(
            "  {0}. {1}  [{2}]".format(
                index,
                package.get("asset_name", "") or package.get("package_dir", ""),
                package.get("risk_status", "待审批"),
            )
        )
    lines.extend(["", "当前包体:", selected.get("package_dir", "") or "未选择"])
    if selected:
        lines.extend(
            [
                "资产: {0}".format(selected.get("asset_name", "")),
                "目标: {0}".format(selected.get("target_path", "")),
                "来源: {0} / Schema {1}".format(selected.get("source_dcc_label", ""), selected.get("schema_version", "")),
                "包体: {0} / {1}".format(selected.get("manifest_package_name", "") or selected.get("package_name", ""), selected.get("package_version_mode", "") or "overwrite"),
                "预设: {0} v{1}".format(selected.get("project_preset_name", "") or "未记录", selected.get("project_preset_version", "") or "-"),
                "Mesh: {0} ({1})".format(selected.get("mesh_status_label", ""), selected.get("mesh_count", 0)),
                "贴图: {0} ({1})".format(selected.get("texture_status_label", ""), selected.get("texture_count", 0)),
                "材质: {0} ({1})".format(selected.get("material_status_label", ""), selected.get("material_count", 0)),
                "Profile: {0} ({1})".format(selected.get("profile_status_label", ""), selected.get("profile_name", "") or "无"),
                "风险: {0}".format(selected.get("risk_status", "")),
                "最近导入: {0}".format(selected.get("last_import_status", "")),
                "下一步: {0}".format(selected.get("next_action", "")),
            ]
        )
        lines.extend(_message_lines("警告", selected.get("warnings", [])))
        lines.extend(_message_lines("错误", selected.get("errors", [])))
    return "\n".join(lines)


def _records_from_log(path, source):
    records = []
    for entry in _read_jsonl(path):
        package_dir = _entry_package_dir(entry)
        if package_dir:
            report_path = normalize_path(entry.get("report_path", "") if isinstance(entry, dict) else "")
            records.append(
                {
                    "source": source,
                    "operation": entry.get("operation", ""),
                    "status": entry.get("status", ""),
                    "timestamp": entry.get("timestamp", ""),
                    "package_dir": package_dir,
                    "report_path": report_path,
                    "asset_name": ((entry.get("outputs", {}) or {}).get("asset_name", "") if isinstance(entry, dict) else ""),
                    "mtime": _package_mtime(package_dir),
                }
            )
    return records


def _records_from_export_root(export_root):
    records = []
    for root in _effective_export_roots(export_root):
        for manifest_path in find_manifest_files(root):
            package_dir = normalize_path(os.path.dirname(manifest_path))
            if _skip_history_package_dir(package_dir):
                continue
            records.append(
                {
                    "source": "export_root",
                    "operation": "scan_manifest",
                    "status": "found",
                    "timestamp": "",
                    "package_dir": package_dir,
                    "report_path": "",
                    "mtime": _package_mtime(package_dir),
                }
            )
    return records


def _effective_export_roots(export_root):
    roots = []
    for root in _iter_export_roots(export_root):
        if _is_asset_forge_reports_root(root):
            dcc_root = normalize_path(os.path.join(root, DCC_PACKAGE_ROOT_NAME))
            if os.path.isdir(dcc_root):
                roots.append(dcc_root)
                continue
        roots.append(root)
    return roots


def _is_asset_forge_reports_root(path):
    return os.path.basename(os.path.normpath(normalize_path(path))).lower() == "assetforgereports"


def _skip_history_package_dir(package_dir):
    normalized = normalize_path(package_dir)
    if not normalized:
        return True
    parts = [part.lower() for part in normalized.replace("\\", "/").split("/") if part]
    if DCC_PACKAGE_ROOT_NAME.lower() in parts:
        return False
    return any(part in HISTORY_SKIP_DIR_NAMES for part in parts)


def _entry_package_dir(entry):
    outputs = entry.get("outputs", {}) if isinstance(entry, dict) else {}
    inputs = entry.get("inputs", {}) if isinstance(entry, dict) else {}
    candidates = [
        outputs.get("package_dir"),
        inputs.get("package_dir"),
        outputs.get("manifest_path"),
        inputs.get("manifest_path"),
        entry.get("report_path"),
    ]
    for candidate in candidates:
        path = normalize_path(candidate or "")
        if not path:
            continue
        if os.path.isfile(path):
            report_package_dir = _package_dir_from_report(path)
            if report_package_dir:
                return report_package_dir
            return normalize_path(os.path.dirname(path))
        if os.path.isdir(path):
            return path
        manifest = find_latest_manifest(path)
        if manifest:
            return normalize_path(os.path.dirname(manifest))
    return ""


def _iter_export_roots(export_root):
    if not export_root:
        return []
    if isinstance(export_root, (list, tuple, set)):
        return [normalize_path(item) for item in export_root if item]
    if isinstance(export_root, text_type) and os.pathsep in export_root:
        return [normalize_path(item) for item in export_root.split(os.pathsep) if item]
    return [normalize_path(export_root)]


def _display_export_roots(export_root):
    roots = _iter_export_roots(export_root)
    return "; ".join(roots)


def _record_sort_key(record):
    return (float(record.get("mtime", 0.0) or 0.0), record.get("timestamp", ""))


def _package_mtime(package_dir):
    manifest_path = _first_manifest_path(package_dir)
    try:
        return os.path.getmtime(manifest_path or package_dir)
    except Exception:
        return 0.0


def _format_mtime(path_or_dir):
    try:
        value = os.path.getmtime(path_or_dir)
    except Exception:
        value = 0.0
    if not value:
        return ""
    return datetime.datetime.fromtimestamp(value).replace(microsecond=0).isoformat()


def _first_manifest_path(package_dir):
    if os.path.isfile(package_dir):
        return package_dir
    if not package_dir or not os.path.isdir(package_dir):
        return ""
    manifest_path = find_latest_manifest(package_dir)
    return manifest_path or ""


def _read_json(path):
    if not path:
        return {}
    try:
        with io.open(path, "r", encoding="utf-8-sig") as stream:
            return json.load(stream)
    except Exception:
        return {}


def _read_jsonl(path):
    if not path or not os.path.exists(path):
        return []
    entries = []
    try:
        with io.open(path, "r", encoding="utf-8-sig") as stream:
            lines = stream.readlines()
    except IOError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


def _package_dir_from_report(report_path):
    report = _read_json(report_path)
    if not report:
        return ""
    for key in ("package_dir", "selected_package_dir"):
        value = normalize_path(report.get(key, ""))
        if value and os.path.isdir(value):
            return value
    for key in ("manifest_path", "fbx_path"):
        value = normalize_path(report.get(key, ""))
        if value and os.path.isfile(value):
            return normalize_path(os.path.dirname(value))
    nested_import = report.get("import") if isinstance(report.get("import"), dict) else {}
    if nested_import:
        return _package_dir_from_report_value(nested_import)
    return ""


def _package_dir_from_report_value(report):
    for key in ("package_dir", "selected_package_dir"):
        value = normalize_path(report.get(key, ""))
        if value and os.path.isdir(value):
            return value
    for key in ("manifest_path", "fbx_path"):
        value = normalize_path(report.get(key, ""))
        if value and os.path.isfile(value):
            return normalize_path(os.path.dirname(value))
    return ""


def _asset_count(manifest):
    checks = manifest.get("checks", {}) if isinstance(manifest, dict) else {}
    if isinstance(checks, dict):
        mesh_check = checks.get("mesh_exists", {})
        if isinstance(mesh_check, dict):
            try:
                value = int(mesh_check.get("value", 0))
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                return value
    for key in ("source_mesh_count", "mesh_count", "expected_static_mesh_count"):
        try:
            value = int(manifest.get(key, 0))
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    roots = manifest.get("asset_roots", []) or manifest.get("transforms", []) or []
    if roots:
        return len(roots)
    return 1 if manifest.get("asset_name") or _manifest_fbx_path(manifest) else 0


def _manifest_fbx_path(manifest):
    return manifest.get("fbx_path", "") or manifest.get("fbx", "") or manifest.get("mesh_path", "")


def _manifest_export_time(manifest, package_dir):
    for key in ("export_time", "exported_at", "timestamp", "created_at"):
        if manifest.get(key):
            return str(manifest.get(key))
    manifest_path = _first_manifest_path(package_dir)
    return _format_mtime(manifest_path or package_dir)


def _source_dcc_label(source_dcc):
    key = str(source_dcc or "").lower()
    return SOURCE_DCC_LABELS.get(key, source_dcc or "未知 DCC")


def _status_label(status):
    key = str(status or "").lower()
    return STATUS_LABELS.get(key, status or "未检查")


def _risk_summary(manifest, gate, has_manifest):
    if not has_manifest:
        return {"code": "error", "status": "阻断", "message": "包体缺少 manifest，无法正式导入。"}
    gate_status = str(gate.get("status", "") or "").lower()
    if gate_status in ("error", "failed", "fail"):
        return {"code": "error", "status": "阻断", "message": "门禁发现阻断项，需要修复后再导入。"}
    if gate.get("error_count", 0):
        return {"code": "error", "status": "阻断", "message": "存在错误项，需要修复后再导入。"}
    if gate_status in ("warning",) or gate.get("warning_count", 0):
        return {"code": "warning", "status": "需复核", "message": "存在警告项，可由 TA 审核后决定是否导入。"}
    if gate_status in ("pass", "success") or gate.get("can_accept") is True:
        return {"code": "pass", "status": "可导入", "message": "门禁通过，可以执行导入。"}
    if _manifest_risks(manifest):
        return {"code": "warning", "status": "需复核", "message": "manifest 中包含材质或贴图风险，需要人工确认。"}
    if _mesh_status(manifest) == "missing_source":
        return {"code": "warning", "status": "需复核", "message": "FBX 源文件路径存在但当前不可访问。"}
    return {"code": "unchecked", "status": "待入审", "message": "尚未生成入审报告。"}


def _manifest_risks(manifest):
    risks = []
    risks.extend(manifest.get("material_texture_binding_risks", []) or [])
    risks.extend(manifest.get("risks", []) or [])
    return [risk for risk in risks if risk]


def _ui_summary(asset_name, source_dcc, target_path, mesh_count, texture_count, material_count, risk):
    return {
        "headline": "{0} · {1}".format(asset_name or "未命名资产", risk.get("status", "待审批")),
        "source": _source_dcc_label(source_dcc),
        "target_path": target_path,
        "counts": "Mesh {0} / 贴图 {1} / 材质 {2}".format(mesh_count, texture_count, material_count),
        "risk": risk.get("message", ""),
    }


def _attach_last_import(summary, import_records):
    record_summary = _last_import_from_records(summary.get("package_dir", ""), import_records)
    if not record_summary:
        record_summary = _latest_import_summary(summary.get("package_dir", ""))
    summary.update(
        {
            "last_import_status": record_summary.get("status", "暂无导入记录"),
            "last_import_status_code": record_summary.get("status_code", ""),
            "last_import_operation": record_summary.get("operation", ""),
            "last_import_time": record_summary.get("timestamp", ""),
            "last_import_report_path": record_summary.get("report_path", ""),
        }
    )
    return summary


def _is_import_record(record):
    if record.get("source") != "unreal_import":
        return False
    operation = str(record.get("operation", "") or "").lower()
    return "import" in operation and "dry_run" not in operation


def _last_import_from_records(package_dir, import_records):
    package_dir = normalize_path(package_dir)
    matches = [record for record in import_records if normalize_path(record.get("package_dir", "")) == package_dir]
    if not matches:
        return {}
    record = sorted(matches, key=_record_sort_key, reverse=True)[0]
    return _import_summary_from_record(record)


def _import_summary_from_record(record):
    status_code = record.get("status", "")
    report_path = normalize_path(record.get("report_path", ""))
    report_summary = _import_summary_from_report(report_path)
    if report_summary.get("status_code"):
        return report_summary
    return {
        "status": _status_label(status_code) if status_code else "暂无导入记录",
        "status_code": status_code,
        "operation": record.get("operation", ""),
        "timestamp": record.get("timestamp", ""),
        "report_path": report_path,
    }


def _latest_import_summary(package_dir):
    report_path = _latest_import_report_path(package_dir)
    if report_path:
        return _import_summary_from_report(report_path)
    return {
        "status": "暂无导入记录",
        "status_code": "",
        "operation": "",
        "timestamp": "",
        "report_path": "",
    }


def _latest_import_report_path(package_dir):
    package_dir = normalize_path(package_dir)
    if not package_dir or not os.path.isdir(package_dir):
        return ""
    candidates = []
    try:
        for file_name in os.listdir(package_dir):
            lower = file_name.lower()
            if lower.endswith("_import_report.json") or lower == "package_import_report.json":
                candidates.append(os.path.join(package_dir, file_name))
    except Exception:
        return ""
    if not candidates:
        return ""
    return normalize_path(max(candidates, key=lambda path: os.path.getmtime(path)))


def _recent_report_summaries(package_dir, acceptance_report=None):
    reports = []
    seen = set()
    acceptance_path = normalize_path((acceptance_report or {}).get("report_path", ""))
    if acceptance_path:
        reports.append(_report_summary_from_report(acceptance_path, "gate_preview", acceptance_report))
        seen.add(acceptance_path)
    for report_path in _report_candidate_paths(package_dir):
        normalized = normalize_path(report_path)
        if normalized in seen:
            continue
        seen.add(normalized)
        reports.append(_report_summary_from_report(normalized, _report_kind_from_path(normalized)))
    reports = [report for report in reports if report.get("report_path")]
    return sorted(reports, key=lambda item: (item.get("mtime", 0.0), item.get("timestamp", "")), reverse=True)[:10]


def _matching_report_summary(reports, report_path):
    report_path = normalize_path(report_path)
    for report in reports or []:
        if normalize_path(report.get("report_path", "")) == report_path:
            return report
    return {}


def _report_candidate_paths(package_dir):
    package_dir = normalize_path(package_dir)
    if not package_dir or not os.path.isdir(package_dir):
        return []
    candidates = []
    try:
        for file_name in os.listdir(package_dir):
            lower = file_name.lower()
            if _is_gate_report_file(lower):
                candidates.append(os.path.join(package_dir, file_name))
    except Exception:
        return []
    return candidates


def _is_gate_report_file(lower_name):
    if not lower_name.endswith(".json"):
        return False
    return (
        lower_name.endswith("_import_report.json")
        or lower_name == "package_import_report.json"
        or lower_name.endswith("_gate_report.json")
        or lower_name.endswith("_acceptance_report.json")
        or lower_name in ("package_acceptance_flow.json", "package_acceptance_flow_report.json")
    )


def _report_kind_from_path(report_path):
    lower = os.path.basename(report_path).lower()
    if lower.endswith("_import_report.json") or lower == "package_import_report.json":
        return "import"
    return "gate_preview"


def _report_summary_from_report(report_path, report_kind, report=None):
    report_path = normalize_path(report_path)
    report = report if report is not None else _read_json(report_path)
    if not report:
        return {
            "kind": report_kind,
            "status": "missing",
            "status_code": "",
            "operation": "",
            "timestamp": _format_mtime(report_path),
            "report_path": report_path,
            "can_open": bool(report_path and os.path.isfile(report_path)),
            "mtime": _path_mtime(report_path),
        }
    import_report = report.get("import") if isinstance(report.get("import"), dict) else report
    summary = import_report.get("summary", {}) if isinstance(import_report.get("summary", {}), dict) else {}
    status_code = import_report.get("status", "") or summary.get("status", "")
    return {
        "kind": report_kind,
        "status": _status_label(status_code) if status_code else "已生成报告",
        "status_code": status_code,
        "operation": import_report.get("stage", "") or report.get("stage", "") or report_kind,
        "timestamp": import_report.get("timestamp", "") or report.get("timestamp", "") or _format_mtime(report_path),
        "report_path": report_path,
        "can_open": bool(report_path and os.path.isfile(report_path)),
        "mtime": _path_mtime(report_path),
    }


def _path_mtime(path):
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0


def _import_summary_from_report(report_path):
    report_path = normalize_path(report_path)
    report = _read_json(report_path)
    if not report:
        return {}
    import_report = report.get("import") if isinstance(report.get("import"), dict) else report
    summary = import_report.get("summary", {}) if isinstance(import_report.get("summary", {}), dict) else {}
    status_code = import_report.get("status", "") or summary.get("status", "")
    return {
        "status": _status_label(status_code) if status_code else "暂无导入记录",
        "status_code": status_code,
        "operation": import_report.get("stage", "") or report.get("stage", "") or "unreal_import",
        "timestamp": import_report.get("timestamp", "") or report.get("timestamp", "") or _format_mtime(report_path),
        "report_path": report_path or normalize_path(import_report.get("report_path", "")),
    }


def _texture_rows(textures):
    rows = []
    for texture in textures:
        if not isinstance(texture, dict):
            texture = {"path": texture}
        rows.append(
            {
                "name": os.path.basename(texture.get("package_path") or texture.get("path") or texture.get("source_path") or ""),
                "usage": texture.get("usage", ""),
                "path": normalize_path(texture.get("package_path") or texture.get("path") or texture.get("source_path") or ""),
                "status": texture.get("texture_metadata_status", texture.get("status", "")),
            }
        )
    return rows


def _material_rows(materials):
    rows = []
    for material in materials:
        if not isinstance(material, dict):
            material = {"name": material}
        rows.append(
            {
                "name": material.get("name", ""),
                "texture_count": len(material.get("textures", []) or []),
                "slot": material.get("slot", material.get("shading_group", "")),
            }
        )
    return rows


def _panel_sections(summary):
    if not summary:
        return []
    return [
        _status_section("mesh", "Mesh", summary.get("mesh_status_label", ""), summary.get("mesh_count", 0)),
        _status_section("texture", "贴图", summary.get("texture_status_label", ""), summary.get("texture_count", 0)),
        _status_section("material", "材质", summary.get("material_status_label", ""), summary.get("material_count", 0)),
        _status_section("profile", "Profile", summary.get("profile_status_label", ""), summary.get("profile_name", "")),
        _status_section("gate", "门禁", summary.get("risk_status", ""), summary.get("can_accept", None)),
    ]


def _status_section(section_id, label, status, value):
    return {
        "id": section_id,
        "label": label,
        "status": status or "missing",
        "value": value,
    }


def _mesh_status(manifest):
    fbx_path = normalize_path(_manifest_fbx_path(manifest))
    if fbx_path and os.path.exists(fbx_path):
        return "ready"
    if fbx_path:
        return "missing_source"
    return "missing"


def _item_status(items, ready_status):
    if not items:
        return "empty"
    if any(item.get("status") == "error" for item in items if isinstance(item, dict)):
        return "error"
    return ready_status


def _profile_summary(manifest, acceptance_report):
    profile = manifest.get("material_profile", "")
    profile_name = profile.get("name", "inline_profile") if isinstance(profile, dict) else str(profile or "")
    snapshot_path = normalize_path(manifest.get("material_profiles_snapshot_path", ""))
    snapshot_status = _acceptance_check_status(acceptance_report, "material_profile_snapshot")
    reference_status = _acceptance_check_status(acceptance_report, "material_profile_reference")
    profile_status = reference_status or ("ready" if profile_name else "missing")
    if snapshot_status == "error" or reference_status == "error":
        profile_status = "error"
    elif snapshot_status == "warning" or reference_status == "warning":
        profile_status = "warning"
    return {
        "name": profile_name,
        "count": 1 if profile_name else 0,
        "status": profile_status,
        "snapshot_path": snapshot_path,
    }


def _acceptance_check_status(report, check_id):
    for check in (report or {}).get("checks", []) or []:
        if check.get("id") == check_id:
            return check.get("status", "")
    return ""


def _message_lines(prefix, messages):
    return ["{0}: {1}".format(prefix, message) for message in (messages or [])[:5]]


def _gate_summary(report):
    if not report:
        return {
            "status": "not_checked",
            "can_accept": None,
            "warning_count": 0,
            "error_count": 0,
            "warnings": [],
            "errors": [],
            "blocking_checks": [],
            "warning_checks": [],
            "next_action": "先生成入审报告，再决定是否预演导入计划。",
        }
    summary = report.get("summary", {}) or {}
    warnings = _messages_from_items(summary.get("warnings", []))
    errors = _messages_from_items(summary.get("errors", []))
    return {
        "status": report.get("status", summary.get("status", "")),
        "can_accept": summary.get("can_accept", report.get("gate_passed", None)),
        "warning_count": summary.get("warning_count", len(warnings)),
        "error_count": summary.get("error_count", len(errors)),
        "warnings": warnings,
        "errors": errors,
        "blocking_checks": list(summary.get("blocking_checks", []) or []),
        "warning_checks": list(summary.get("warning_checks", []) or []),
        "next_action": summary.get("next_action", report.get("next_action", "")),
    }


def _messages_from_items(items):
    messages = []
    for item in items or []:
        if isinstance(item, dict):
            message = item.get("message", "")
            if message:
                messages.append(message)
        elif item:
            messages.append(str(item))
    return messages


def _overwrite_strategy(manifest, report):
    if report and report.get("import_strategy_summary"):
        return dict(report.get("import_strategy_summary") or {})
    return {
        "existing_mesh_strategy": manifest.get("existing_mesh_strategy", "overwrite"),
        "existing_texture_strategy": manifest.get("existing_texture_strategy", "overwrite"),
        "existing_material_strategy": manifest.get("existing_material_strategy", "reuse"),
    }


def _approval_summary(summary):
    if not summary:
        return {
            "enabled": False,
            "label": "等待选择包体",
            "message": "请先扫描或选择一个 Asset Forge 导出包。",
        }
    if summary.get("can_accept"):
        return {
            "enabled": True,
            "label": "正式导入",
            "message": "门禁通过，可以导入到 {0}".format(summary.get("target_path", "")),
        }
    return {
        "enabled": False,
        "label": "暂不导入",
        "message": summary.get("risk_message", "") or "需要先生成入审报告。",
    }


def _repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


def _default_latest_maya_log():
    return normalize_path(os.path.join(_repo_root(), "AssetForgeReports", "logs", "latest_maya.log"))


def _default_latest_unreal_log():
    return normalize_path(os.path.join(_repo_root(), "AssetForgeReports", "logs", "latest_unreal.log"))


def _default_latest_blender_log():
    return normalize_path(os.path.join(_repo_root(), "AssetForgeReports", "logs", "latest_blender.log"))
