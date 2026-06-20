"""JSON checklist for real UE 5.6 validation tasks."""

from __future__ import absolute_import

from asset_forge.shared.report_schema import REPORT_VERSION, attach_acceptance_summary, create_acceptance_summary


def create_ue_validation_checklist(package_dir="", doctor_report=None, accept_flow_report=None):
    items = [
        _item("assetforge_mount", "检查 /AssetForge mount", "在 UE 5.6 Python 中运行插件 mount preflight", "/AssetForge content mount 为 pass", "content_mount warning/error", "保存 plugin_mount_preflight JSON 和 UE Output Log 截图"),
        _item("default_master_materials", "检查默认母材质", "运行 inspect_default_material_assets()", "M_AF_Props_Master/M_AF_Environment_Master/M_AF_Character_Master 均存在", "Material Instance 无 parent 或 parent_material_exists error", "保存 material_asset_validation JSON"),
        _item("material_functions", "检查 Material Functions", "运行 validate_assetforge_plugin_content()", "MF_AF_UnpackARM/MF_AF_OpacityMask/MF_AF_Emissive 存在", "材质参数或打包通道不可用", "保存 plugin_content_validation JSON"),
        _item("mpc", "检查 MPC", "运行 validate_assetforge_plugin_content()", "MPC_AF_Global 存在", "全局参数集合缺失", "保存 plugin_content_validation JSON"),
        _item("auto_materials_import", "auto-materials import", "运行 --accept-flow --run-import --auto-materials --strict --require-import <package>", "导入成功且 created_material_instances 有结果或复用成功", "bootstrap failed / parent missing / import skipped", "保存 accept-flow JSON、导入资产路径和 UE 日志"),
        _item("post_import_validation", "导入后验收", "查看 accept-flow post_import_validation", "post_import_validation.can_accept=true", "target_path/imported_assets error", "保存 post_import_validation JSON"),
    ]
    warnings = [{"source": "ue_validation_checklist", "message": "该清单不是 TAS-102 完成证据，必须在真实 UE 5.6 中执行并捕获 evidence"}]
    summary = create_acceptance_summary("warning", warnings, [], "在真实 UE 5.6 中逐项执行 checklist 并补充 evidence")
    report = {
        "version": REPORT_VERSION,
        "stage": "ue_validation_checklist",
        "status": "manual_validation_required",
        "package_dir": package_dir.replace("\\", "/"),
        "is_tas_102_completion_evidence": False,
        "disclaimer": "此 JSON 只是 UE 实机验收待办，不是 TAS-102 完成证据。",
        "doctor_reference": _reference(doctor_report),
        "accept_flow_reference": _reference(accept_flow_report),
        "items": items,
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _item(item_id, title, command, expected_result, failure_symptom, evidence_to_capture):
    return {
        "id": item_id,
        "title": title,
        "command": command,
        "expected_result": expected_result,
        "failure_symptom": failure_symptom,
        "evidence_to_capture": evidence_to_capture,
    }


def _reference(report):
    if not report:
        return {}
    return {
        "stage": report.get("stage", ""),
        "status": report.get("status", ""),
        "gate_status": report.get("gate_status", ""),
        "next_action": report.get("next_action", ""),
    }
