"""vNext manifest lint checks for Static Prop Bridge packages."""

from __future__ import absolute_import

import os

from asset_forge.shared.material_profile_schema import get_material_profile
from asset_forge.shared.report_schema import REPORT_VERSION, attach_acceptance_summary, create_acceptance_summary


ALLOWED_STRATEGIES = set(["overwrite", "reuse", "skip", "error"])
KNOWN_TEXTURE_USAGES = set(["base_color", "normal", "packed_arm", "emissive", "opacity", "opacity_mask", "imperfection_mask", "height", "decal", "glass", "world_aligned"])
ALLOWED_VT_POLICIES = set(["project_default", "auto", "force_on", "force_off"])
ALLOWED_STREAMING_POLICIES = set(["project_default", "streaming", "never_stream"])
ALLOWED_LOD_IMPORT_POLICIES = set(["project_default", "import_existing", "ignore_lods", "report_only"])
ALLOWED_NANITE_POLICIES = set(["project_default", "enable", "disable", "report_only"])


def lint_static_prop_manifest(manifest):
    checks = []
    checks.extend(_material_profile_checks(manifest))
    checks.extend(_texture_checks(manifest.get("textures", [])))
    checks.extend(_strategy_checks(manifest))
    checks.extend(_import_policy_checks(manifest))

    errors = [_message(item) for item in checks if item.get("status") == "error"]
    warnings = [_message(item) for item in checks if item.get("status") == "warning"]
    summary = create_acceptance_summary(
        "error" if errors else ("warning" if warnings else "pass"),
        warnings,
        errors,
        "修复 Manifest lint 阻断项后重新验收" if errors else ("检查 Manifest lint 警告后继续" if warnings else "Manifest lint 通过"),
    )
    report = {
        "version": REPORT_VERSION,
        "stage": "manifest_lint",
        "status": summary.get("status", ""),
        "asset_name": manifest.get("asset_name", ""),
        "checks": checks,
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _material_profile_checks(manifest):
    profile = manifest.get("material_profile", "")
    snapshot_path = manifest.get("material_profiles_snapshot_path", "")
    checks = []
    if not profile:
        checks.append(_check("material_profile", "warning", "", "manifest 未指定 material_profile"))
    elif get_material_profile(profile):
        checks.append(_check("material_profile", "pass", profile, "material_profile 可解析"))
    else:
        checks.append(_check("material_profile", "warning", profile, "未知 material_profile：{0}".format(profile)))

    if not snapshot_path:
        checks.append(_check("material_profiles_snapshot_path", "warning", "", "manifest 未记录 material_profiles_snapshot_path"))
    elif os.path.exists(snapshot_path):
        checks.append(_check("material_profiles_snapshot_path", "pass", snapshot_path, "Material Profile 快照路径存在"))
    else:
        checks.append(_check("material_profiles_snapshot_path", "warning", snapshot_path, "Material Profile 快照路径不存在"))
    return checks


def _texture_checks(textures):
    checks = []
    if not textures:
        checks.append(_check("textures", "warning", "", "manifest 未记录贴图条目"))
        return checks
    for index, texture in enumerate(textures):
        usage = texture.get("usage", "")
        label = "textures[{0}]".format(index)
        if usage in KNOWN_TEXTURE_USAGES:
            checks.append(_check("texture_usage", "pass", label + ".usage", "贴图 usage 可识别：{0}".format(usage)))
        else:
            checks.append(_check("texture_usage", "warning", label + ".usage", "未知贴图 usage：{0}".format(usage or "空")))

        path = texture.get("package_path") or texture.get("source_path") or texture.get("path")
        checks.append(_check("texture_path", "pass" if path else "warning", path or label, "贴图路径已记录" if path else "贴图缺少 path/source_path/package_path"))

        for field in ["width", "height"]:
            value = texture.get(field)
            checks.append(
                _check(
                    "texture_" + field,
                    "pass" if isinstance(value, int) and value > 0 else "warning",
                    label + "." + field,
                    "贴图 {0} 已记录".format(field) if isinstance(value, int) and value > 0 else "贴图 {0} 缺失或无效".format(field),
                )
            )

        checks.append(_typed_check(texture, label, "srgb", bool))
        compression = texture.get("compression", "")
        checks.append(_check("texture_compression", "pass" if compression else "warning", label + ".compression", "贴图 compression 已记录" if compression else "贴图 compression 缺失"))
    return checks


def _strategy_checks(manifest):
    checks = []
    for field in ["existing_mesh_strategy", "existing_texture_strategy", "existing_material_strategy"]:
        value = manifest.get(field, "")
        if not value:
            checks.append(_check(field, "warning", field, "manifest 未显式记录 {0}，将使用默认策略".format(field)))
        elif value in ALLOWED_STRATEGIES:
            checks.append(_check(field, "pass", field, "{0} 有效：{1}".format(field, value)))
        else:
            checks.append(_check(field, "warning", field, "{0} 未知：{1}".format(field, value)))
    return checks


def _import_policy_checks(manifest):
    checks = []
    texture_policy = manifest.get("texture_import_policy", {}) or {}
    vt_policy = texture_policy.get("virtual_texture_policy", "project_default")
    streaming_policy = texture_policy.get("texture_streaming_policy", "project_default")
    texture_group = texture_policy.get("texture_group", "project_default")
    checks.append(_choice_check("virtual_texture_policy", vt_policy, ALLOWED_VT_POLICIES, "Virtual Texture 策略"))
    checks.append(_choice_check("texture_streaming_policy", streaming_policy, ALLOWED_STREAMING_POLICIES, "Texture Streaming 策略"))
    checks.append(_check("texture_group", "pass" if texture_group else "warning", "texture_import_policy.texture_group", "Texture Group 已记录：{0}".format(texture_group or "空")))

    mesh_policy = manifest.get("static_mesh_import_policy", {}) or {}
    nanite_policy = mesh_policy.get("nanite_policy", "project_default")
    lod_group = mesh_policy.get("lod_group", "project_default")
    lod_policy = mesh_policy.get("import_lod_policy", "import_existing")
    checks.append(_choice_check("nanite_policy", nanite_policy, ALLOWED_NANITE_POLICIES, "Nanite 策略"))
    checks.append(_check("static_mesh_lod_group", "pass" if lod_group else "warning", "static_mesh_import_policy.lod_group", "Static Mesh LODGroup 已记录：{0}".format(lod_group or "空")))
    checks.append(_choice_check("static_mesh_import_lod_policy", lod_policy, ALLOWED_LOD_IMPORT_POLICIES, "Static Mesh LOD 导入策略"))
    return checks


def _choice_check(check_id, value, allowed, label):
    return _check(
        check_id,
        "pass" if value in allowed else "warning",
        check_id,
        "{0} 有效：{1}".format(label, value) if value in allowed else "{0} 未知：{1}".format(label, value),
    )


def _typed_check(texture, label, field, expected_type):
    value = texture.get(field)
    return _check(
        "texture_" + field,
        "pass" if isinstance(value, expected_type) else "warning",
        label + "." + field,
        "贴图 {0} 类型有效".format(field) if isinstance(value, expected_type) else "贴图 {0} 缺失或类型无效".format(field),
    )


def _check(check_id, status, path, message):
    return {
        "id": check_id,
        "label": "Manifest Lint",
        "status": status,
        "path": str(path).replace("\\", "/"),
        "message": message,
    }


def _message(item):
    return {
        "source": "manifest_lint",
        "id": item.get("id", ""),
        "path": item.get("path", ""),
        "message": item.get("message", ""),
    }
