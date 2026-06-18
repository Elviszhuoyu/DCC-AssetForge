"""Collect offline stage validation reports into one JSON bundle."""

from __future__ import absolute_import

import datetime
import os

from asset_forge.shared.interface_contract import validate_package_contract
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.report_artifacts import attach_report_artifact_metadata, default_report_path, report_artifacts_dir
from asset_forge.shared.report_schema import (
    REPORT_VERSION,
    attach_acceptance_summary,
    attach_report_schema_validation,
    create_acceptance_summary,
    validate_report_schema,
    write_report,
)
from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.acceptance_runner import run_all_asset_forge_package_acceptance, run_asset_forge_package_acceptance
from asset_forge.unreal.capability_matrix import create_capability_matrix
from asset_forge.unreal.doctor import run_asset_forge_doctor
from asset_forge.unreal.manifest_finder import find_latest_manifest
from asset_forge.unreal.north_star_readiness import create_north_star_readiness
from asset_forge.unreal.package_acceptance import validate_asset_forge_package
from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline
from asset_forge.unreal.plugin_installer import install_assetforge_plugin
from asset_forge.unreal.ue_validation_checklist import create_ue_validation_checklist


def collect_offline_evidence_bundle(output_root=None, report_path=None, command_args=None):
    """Generate a sample Static Prop package and collect all offline evidence."""
    base_dir = os.path.abspath(output_root) if output_root else os.path.join(report_artifacts_dir(os.getcwd()), "offline_evidence")
    report_base_dir = base_dir if output_root else os.getcwd()
    sample_root = os.path.join(base_dir, "offline_static_prop_sample")
    sample = create_offline_static_prop_package(sample_root)
    package_dir = sample["package_dir"]
    active_report_path = normalize_path(report_path or default_report_path(report_base_dir, "offline_evidence_bundle"))
    report = collect_stage_validation_bundle(
        package_dir,
        active_report_path,
        command_args or ["--offline-evidence-bundle"],
        include_batch=True,
        test_summary=_offline_test_summary(),
        stage="offline_evidence_bundle",
    )
    report["sample_package"] = {
        "package_dir": normalize_path(package_dir),
        "manifest_path": normalize_path(sample.get("manifest_path", "")),
        "fbx_path": normalize_path(sample.get("fbx_path", "")),
        "texture_count": len(sample.get("textures", [])),
    }
    report["offline_evidence"] = {
        "status": report.get("status", ""),
        "can_accept": report.get("can_accept", False),
        "sample_package_dir": normalize_path(package_dir),
        "report_paths": dict(report.get("report_paths", {})),
        "manual_validation_required": list(report.get("manual_validation_required", [])),
    }
    write_report(active_report_path, report)
    return report


def collect_stage_validation_bundle(
    package_dir,
    report_path=None,
    command_args=None,
    include_batch=True,
    test_summary=None,
    stage="stage_validation_bundle",
):
    command_args = list(command_args or [])
    manifest_path = find_latest_manifest(package_dir)
    stage_report_paths = _stage_report_paths(package_dir)
    doctor = _safe_stage("doctor", lambda: run_asset_forge_doctor(os.getcwd(), stage_report_paths["doctor"], command_args=["--pretest-check"]))
    contract_check = _safe_stage("contract_check", lambda: validate_package_contract(package_dir, stage_report_paths["contract_check"]))
    package_acceptance = _safe_stage("package_acceptance", lambda: validate_asset_forge_package(package_dir, stage_report_paths["package_acceptance"], command_args=command_args))
    dry_run = _safe_stage("dry_run", lambda: _run_dry_run(manifest_path, stage_report_paths["dry_run"]))
    accept_flow = _safe_stage("accept_flow", lambda: run_asset_forge_package_acceptance(package_dir, stage_report_paths["accept_flow"], command_args=command_args))
    plugin_install_smoke = _safe_stage("plugin_install_smoke", lambda: _run_plugin_install_smoke(package_dir, stage_report_paths["plugin_install_smoke"]))
    batch_flow = _safe_stage(
        "batch_flow",
        lambda: run_all_asset_forge_package_acceptance(os.path.dirname(os.path.abspath(package_dir)), stage_report_paths["batch_flow"], command_args=command_args),
    ) if include_batch else _missing_stage("batch_flow", "未请求批量 flow")
    report_schema_validation = validate_report_schema(package_acceptance, require_gate=True)
    capability_matrix = create_capability_matrix(
        {
            "contract_check_report": contract_check,
            "package_acceptance_report": package_acceptance,
            "dry_run_report": dry_run,
            "accept_flow_report": accept_flow,
            "plugin_install_smoke_report": plugin_install_smoke,
            "batch_flow_report": batch_flow,
            "doctor_report": doctor,
            "report_schema_validation": report_schema_validation,
        }
    )
    ue_checklist = create_ue_validation_checklist(package_dir, doctor, accept_flow)

    stages = {
        "doctor": doctor,
        "contract_check": contract_check,
        "package_acceptance": package_acceptance,
        "dry_run": dry_run,
        "accept_flow": accept_flow,
        "plugin_install_smoke": plugin_install_smoke,
        "batch_flow": batch_flow,
        "report_schema_validation": report_schema_validation,
        "capability_matrix": capability_matrix,
        "ue_validation_checklist": ue_checklist,
        "test_summary": test_summary or _missing_stage("test_summary", "未提供测试摘要"),
    }
    summary = _bundle_summary(stages)
    stages["north_star_readiness"] = create_north_star_readiness(
        {
            "stages": stages,
            "gate_status": "passed" if not summary.get("errors") else "failed",
            "report_paths": stage_report_paths,
        },
        capability_matrix,
    )
    report = {
        "version": REPORT_VERSION,
        "stage": stage,
        "status": summary.get("status", ""),
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "package_dir": normalize_path(package_dir),
        "manifest_path": normalize_path(manifest_path or ""),
        "command_args": command_args,
        "stages": stages,
        "stage_summaries": dict((name, _stage_summary(stage)) for name, stage in stages.items()),
        "report_paths": stage_report_paths,
        "manual_validation_required": _manual_validation_required(),
        "summary": summary,
        "tas_102_real_ue_evidence": "not_provided",
        "tas_102_note": "本 bundle 不启动真实 UE Editor，也不是 TAS-102 实机验收证据。",
    }
    report["field_validation_plan"] = _field_validation_plan(report)
    attach_acceptance_summary(report, summary)
    active_report_path = normalize_path(report_path or default_report_path(package_dir, stage))
    attach_report_artifact_metadata(report, active_report_path, command_args)
    attach_report_schema_validation(report, require_gate=False)
    write_report(active_report_path, report)
    return report


def _bundle_summary(stages):
    warnings = []
    errors = []
    for name, report in stages.items():
        warnings.extend(_tag(name, report.get("warnings", [])))
        errors.extend(_tag(name, report.get("errors", [])))
        if report.get("status") in ("missing", "manual_validation_required"):
            warnings.append({"source": name, "message": report.get("next_action", report.get("message", "阶段结果缺失"))})
    summary = create_acceptance_summary(
        "error" if errors else ("warning" if warnings else "pass"),
        warnings,
        errors,
        "离线证据已生成；真实 Maya/UE 复测后补充实机证据。" if warnings or errors else "阶段验收 bundle 可用于离线回归",
    )
    return summary


def _stage_summary(report):
    return {
        "stage": report.get("stage", ""),
        "status": report.get("status", ""),
        "can_accept": report.get("can_accept", False),
        "next_action": report.get("next_action", ""),
        "gate_status": report.get("gate_status", ""),
        "gate_passed": report.get("gate_passed", ""),
    }


def _field_validation_plan(report):
    stages = report.get("stages", {})
    return [
        _field_validation_item(
            "maya_screen_recording",
            _field_stage_status(stages, "maya_ui_flow"),
            ["maya_ui_flow", "doctor", "package_acceptance"],
            "录制真实 Maya UI 流程：扫描、风险检查、导出和报告路径。",
        ),
        _field_validation_item(
            "ue_gate_clicks",
            _field_stage_status(stages, "ue_gate_visual_review"),
            ["ue_gate_visual_review", "accept_flow"],
            "在真实 UE Editor 点击 UE Gate：选择包体、预检、批准导入，并打开报告。",
        ),
        _field_validation_item(
            "material_preview_comment_box",
            _field_stage_status(stages, "material_graph_evidence"),
            ["material_graph_evidence", "dry_run", "accept_flow"],
            "在 UE 中截图材质预览、Comment Box 和 linked_graph_comments 证据。",
        ),
        _clean_install_field_validation_item(stages),
    ]


def _field_stage_status(stages, stage_name):
    stage = stages.get(stage_name, {})
    if stage.get("status") in ("pass", "ready", "success"):
        return "pass"
    return "manual_validation_required"


def _field_validation_item(item_id, status, source_stages, next_action):
    return {
        "id": item_id,
        "status": status,
        "source_stages": source_stages,
        "next_action": "" if status == "pass" else next_action,
    }


def _clean_install_field_validation_item(stages):
    smoke = stages.get("plugin_install_smoke", {})
    validation = stages.get("clean_install_validation", {})
    release_boundary = smoke.get("release_boundary", {}) if isinstance(smoke, dict) else {}
    can_claim = bool(release_boundary.get("can_claim_clean_install"))
    validation_status = validation.get("status", "") if isinstance(validation, dict) else ""
    if can_claim:
        status = "pass"
    elif validation_status in ("blocked", "error", "failed"):
        status = validation_status
    elif validation_status in ("pass", "ready", "success"):
        status = "pass"
    else:
        status = "manual_validation_required"
    item = _field_validation_item(
        "closed_editor_ubt_clean_install_smoke",
        status,
        ["plugin_install_smoke", "clean_install_validation"],
        "关闭 UE Editor，运行 UBT，然后在干净 UE 工程执行非 dry-run 安装 smoke。",
    )
    item["release_boundary_status"] = release_boundary.get("status", "")
    item["can_claim_clean_install"] = can_claim
    if isinstance(validation, dict):
        if validation.get("next_action"):
            item["next_action"] = validation.get("next_action")
        for key in ("assetforge_editor_linked", "blocked_by_plugin", "blocker_summary", "ubt_log_path"):
            if validation.get(key) not in ("", None):
                item[key] = validation.get(key)
    return item


def _safe_stage(stage, fn):
    try:
        report = fn()
        return report if isinstance(report, dict) else _missing_stage(stage, "阶段未返回 JSON 报告", status="error")
    except Exception as exc:
        return _missing_stage(stage, "阶段执行失败：{0}".format(exc), status="error")


def _missing_stage(stage, message, status="missing"):
    summary = create_acceptance_summary("warning" if status == "missing" else "error", [{"source": stage, "message": message}] if status == "missing" else [], [{"source": stage, "message": message}] if status == "error" else [], message)
    report = {
        "version": REPORT_VERSION,
        "stage": stage,
        "status": status,
        "message": message,
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _run_dry_run(manifest_path, report_path):
    if not manifest_path:
        return _missing_stage("dry_run", "未找到 manifest，无法执行 dry-run", status="error")
    return UnrealStaticMeshImportPipeline().dry_run_manifest(manifest_path, report_path)


def _run_plugin_install_smoke(package_dir, report_path):
    smoke_root = os.path.join(report_artifacts_dir(package_dir), "plugin_install_smoke_project")
    os.makedirs(smoke_root, exist_ok=True)
    project_file = os.path.join(smoke_root, "AF_CleanInstallSmoke.uproject")
    if not os.path.exists(project_file):
        with open(project_file, "w", encoding="utf-8") as stream:
            stream.write('{\n  "FileVersion": 3,\n  "Plugins": []\n}\n')
    report = install_assetforge_plugin(project_file, dry_run=True)
    report["stage"] = "plugin_install_smoke"
    report["smoke_project_file"] = normalize_path(project_file)
    write_report(report_path, report)
    return report


def _stage_report_paths(package_dir):
    reports_dir = report_artifacts_dir(package_dir)
    return {
        "doctor": normalize_path(os.path.join(reports_dir, "doctor_report.json")),
        "contract_check": normalize_path(os.path.join(reports_dir, "contract_check_report.json")),
        "package_acceptance": normalize_path(os.path.join(reports_dir, "package_acceptance_report.json")),
        "dry_run": normalize_path(os.path.join(reports_dir, "dry_run_report.json")),
        "accept_flow": normalize_path(os.path.join(reports_dir, "accept_flow_report.json")),
        "plugin_install_smoke": normalize_path(os.path.join(reports_dir, "plugin_install_smoke_report.json")),
        "batch_flow": normalize_path(os.path.join(reports_dir, "batch_acceptance_flow_report.json")),
    }


def _manual_validation_required():
    return [
        "真实 Maya：从用户工程导出 Static Prop 包并确认 UI 状态。",
        "真实 UE 5.6：执行 --run-import 导入并保存 Static Mesh、Texture、材质实例结果。",
        "真实 UE 5.6：打开资产确认 Nanite、LODGroup、Texture Group、母材质网络与参数连接。",
    ]


def _offline_test_summary():
    summary = create_acceptance_summary("pass", [], [], "离线 sample 包已生成，可继续真实 Maya/UE 复测。")
    report = {
        "version": REPORT_VERSION,
        "stage": "offline_sample_generation",
        "status": "pass",
        "message": "已生成离线 Static Prop sample package。",
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _tag(source, messages):
    result = []
    for item in messages or []:
        if isinstance(item, dict):
            tagged = dict(item)
            tagged.setdefault("source", source)
            result.append(tagged)
        else:
            result.append({"source": source, "message": str(item)})
    return result
