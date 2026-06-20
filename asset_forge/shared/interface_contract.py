"""Maya -> UE Static Prop Bridge interface contract checks."""

from __future__ import absolute_import

import os

from asset_forge.shared.dcc_adapter import get_dcc_support_contracts
from asset_forge.shared.manifest_schema import ASSET_FORGE_SCHEMA_VERSION, read_manifest
from asset_forge.shared.material_profile_schema import get_material_profile
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.report_schema import REPORT_VERSION, attach_acceptance_summary, create_acceptance_summary, write_report
from asset_forge.shared.unreal_path import sanitize_unreal_package_path


CONTRACT_STAGE = "maya_ue_interface_contract"

REQUIRED_FIELDS = [
    "asset_name",
    "target_path",
    "fbx_path",
    "textures",
    "material_profile",
    "texture_import_policy",
    "static_mesh_import_policy",
]

REQUIRED_TEXTURE_POLICY_FIELDS = ["virtual_texture_policy", "texture_streaming_policy", "texture_group"]
REQUIRED_MESH_POLICY_FIELDS = ["nanite_policy", "lod_group", "import_lod_policy"]


def validate_manifest_contract(manifest, manifest_path=""):
    """Validate the minimum manifest contract needed by the Static Prop Bridge."""
    checks = []
    manifest = manifest if isinstance(manifest, dict) else {}
    checks.extend(_schema_version_checks(manifest))
    checks.extend(_required_field_checks(manifest))
    checks.extend(_path_checks(manifest))
    checks.extend(_texture_checks(manifest))
    checks.extend(_policy_checks(manifest))

    errors = [_message(item) for item in checks if item.get("status") == "error"]
    warnings = [_message(item) for item in checks if item.get("status") == "warning"]
    summary = create_acceptance_summary(
        "error" if errors else ("warning" if warnings else "pass"),
        warnings,
        errors,
        "修复接口契约阻断项后重新执行 package acceptance" if errors else ("检查接口契约 warning 后继续" if warnings else "接口契约检查通过"),
    )
    report = {
        "version": REPORT_VERSION,
        "schema_version": ASSET_FORGE_SCHEMA_VERSION,
        "asset_forge_schema_version": ASSET_FORGE_SCHEMA_VERSION,
        "stage": CONTRACT_STAGE,
        "status": summary.get("status", ""),
        "manifest_path": normalize_path(manifest_path),
        "asset_name": manifest.get("asset_name", ""),
        "target_path": manifest.get("target_path", ""),
        "checks": checks,
        "dcc_support": get_dcc_support_contracts(),
        "dcc_support_summary": _dcc_support_summary(),
        "import_policy_summary": _import_policy_summary(manifest),
        "manual_validation_required": _manual_validation_required(),
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def validate_package_contract(manifest_or_package_path, report_path=None):
    manifest_path = _resolve_manifest_path(manifest_or_package_path)
    if not manifest_path:
        report = _missing_manifest_report(manifest_or_package_path)
    else:
        report = validate_manifest_contract(read_manifest(manifest_path), manifest_path)
    if report_path:
        write_report(report_path, report)
        report["report_path"] = normalize_path(report_path)
    return report


def _resolve_manifest_path(path):
    if os.path.isfile(path):
        return path
    if not os.path.isdir(path):
        return ""
    for name in sorted(os.listdir(path)):
        if name.endswith("_manifest.json"):
            return os.path.join(path, name)
    return ""


def _missing_manifest_report(path):
    check = _check("manifest", "error", "manifest", "未找到 Asset Forge manifest：{0}".format(normalize_path(path)))
    summary = create_acceptance_summary(
        "error",
        [],
        [_message(check)],
        "确认资产包目录内存在 Asset Forge manifest 后重新执行接口契约检查",
    )
    report = {
        "version": REPORT_VERSION,
        "schema_version": ASSET_FORGE_SCHEMA_VERSION,
        "asset_forge_schema_version": ASSET_FORGE_SCHEMA_VERSION,
        "stage": CONTRACT_STAGE,
        "status": "error",
        "manifest_path": "",
        "asset_name": "",
        "target_path": "",
        "checks": [check],
        "dcc_support": get_dcc_support_contracts(),
        "dcc_support_summary": _dcc_support_summary(),
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _schema_version_checks(manifest):
    schema_version = manifest.get("schema_version") or manifest.get("asset_forge_schema_version")
    legacy_version = manifest.get("version")
    if schema_version:
        return [_check("schema_version", "pass", "schema_version", "接口契约版本已记录：{0}".format(schema_version))]
    if legacy_version:
        return [_check("schema_version", "warning", "version", "旧 manifest 仅包含 version={0}，建议重新导出以写入 schema_version。".format(legacy_version))]
    return [_check("schema_version", "warning", "schema_version", "旧 manifest 缺少 schema_version / asset_forge_schema_version，已按兼容模式继续检查。")]


def _required_field_checks(manifest):
    checks = []
    for field in REQUIRED_FIELDS:
        value = manifest.get(field)
        if field == "textures":
            if field not in manifest:
                checks.append(_check("field_" + field, "error", field, "manifest 缺少关键字段：textures"))
            elif isinstance(value, list):
                checks.append(_check("field_" + field, "pass", field, "textures 字段已记录"))
            else:
                checks.append(_check("field_" + field, "error", field, "textures 必须是列表。"))
            continue
        ok = value not in (None, "")
        checks.append(_check("field_" + field, "pass" if ok else "error", field, "{0} 已记录".format(field) if ok else "manifest 缺少关键字段：{0}".format(field)))
    return checks


def _path_checks(manifest):
    checks = []
    target_path = manifest.get("target_path", "")
    try:
        sanitized = sanitize_unreal_package_path(target_path)
        status = "warning" if str(target_path) != sanitized else "pass"
        message = "UE 目标路径已规范化：{0}".format(sanitized) if status == "warning" else "UE 目标路径合法：{0}".format(sanitized)
        checks.append(_check("target_path", status, "target_path", message))
    except ValueError as exc:
        checks.append(_check("target_path", "error", "target_path", str(exc)))

    fbx_path = manifest.get("fbx_path", "")
    normalized_fbx = normalize_path(fbx_path)
    if any(ord(ch) < 32 for ch in str(fbx_path)):
        checks.append(_check("fbx_path", "error", "fbx_path", "fbx_path 包含换行或隐藏控制字符。"))
    elif "\\" in str(fbx_path):
        checks.append(_check("fbx_path", "warning", "fbx_path", "fbx_path 包含 Windows 反斜杠，UE 侧会规范化为：{0}".format(normalized_fbx)))
    elif fbx_path:
        checks.append(_check("fbx_path", "pass", "fbx_path", "fbx_path 已记录：{0}".format(normalized_fbx)))
    return checks


def _texture_checks(manifest):
    textures = manifest.get("textures", [])
    checks = []
    if not isinstance(textures, list):
        return [_check("textures_shape", "error", "textures", "textures 必须是列表。")]
    if not textures:
        return [_check("textures", "warning", "textures", "manifest 未记录贴图清单；如资产不需要贴图，请在报告中确认。")]
    for index, texture in enumerate(textures):
        label = "textures[{0}]".format(index)
        if not isinstance(texture, dict):
            checks.append(_check("texture_shape", "error", label, "贴图条目必须是字典。"))
            continue
        usage = texture.get("usage", "")
        path = texture.get("package_path") or texture.get("source_path") or texture.get("path")
        checks.append(_check("texture_usage", "pass" if usage else "warning", label + ".usage", "贴图 usage 已记录：{0}".format(usage) if usage else "贴图缺少 usage。"))
        checks.append(_check("texture_path", "pass" if path else "warning", label + ".path", "贴图路径已记录：{0}".format(normalize_path(path)) if path else "贴图缺少 path/source_path/package_path。"))
    return checks


def _policy_checks(manifest):
    checks = []
    texture_policy = manifest.get("texture_import_policy", {}) or {}
    mesh_policy = manifest.get("static_mesh_import_policy", {}) or {}
    if not isinstance(texture_policy, dict):
        checks.append(_check("texture_import_policy", "error", "texture_import_policy", "texture_import_policy 必须是字典。"))
    else:
        for field in REQUIRED_TEXTURE_POLICY_FIELDS:
            checks.append(_check("texture_policy_" + field, "pass" if field in texture_policy else "warning", "texture_import_policy." + field, "{0} 已记录".format(field) if field in texture_policy else "texture_import_policy 缺少 {0}，将使用默认策略。".format(field)))
    if not isinstance(mesh_policy, dict):
        checks.append(_check("static_mesh_import_policy", "error", "static_mesh_import_policy", "static_mesh_import_policy 必须是字典。"))
    else:
        for field in REQUIRED_MESH_POLICY_FIELDS:
            checks.append(_check("mesh_policy_" + field, "pass" if field in mesh_policy else "warning", "static_mesh_import_policy." + field, "{0} 已记录".format(field) if field in mesh_policy else "static_mesh_import_policy 缺少 {0}，将使用默认策略。".format(field)))
    return checks


def _import_policy_summary(manifest):
    profile = get_material_profile(manifest.get("material_profile", "")) if manifest.get("material_profile") else {}
    profile = profile or {}
    return {
        "status": "manual_validation_required",
        "static_mesh_import_policy": dict(manifest.get("static_mesh_import_policy", {}) or {}),
        "texture_import_policy": dict(manifest.get("texture_import_policy", {}) or {}),
        "material_network_status": profile.get("material_network_status", ""),
        "manual_validation_required": _manual_validation_required(),
        "next_action": "接口契约仅验证策略字段可传递；真实 UE 导入后确认策略是否生效。",
    }


def _manual_validation_required():
    return [
        "真实 UE 5.6：确认 Static Mesh Nanite、LODGroup、LOD 导入结果。",
        "真实 UE 5.6：确认 Texture Virtual Texture、Streaming、Texture Group 属性。",
        "真实 UE 5.6：确认母材质网络节点、参数和连接。",
    ]


def _check(check_id, status, path, message):
    return {
        "id": check_id,
        "label": "Maya -> UE 接口契约",
        "status": status,
        "path": normalize_path(path),
        "message": message,
    }


def _dcc_support_summary():
    support = get_dcc_support_contracts()
    implemented = [item["display_name"] for item in support.values() if item.get("support") == "implemented"]
    roadmap = [item["display_name"] for item in support.values() if item.get("support") == "roadmap"]
    return {
        "implemented": implemented,
        "roadmap": roadmap,
        "message": "Maya is implemented for the TA portfolio MVP; Blender and 3ds Max are compatibility contracts and roadmap items only.",
    }


def _message(item):
    return {
        "source": CONTRACT_STAGE,
        "id": item.get("id", ""),
        "path": item.get("path", ""),
        "message": item.get("message", ""),
    }
