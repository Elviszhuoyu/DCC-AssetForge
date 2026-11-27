"""Material Profile parameter contract checks."""

from __future__ import absolute_import

from asset_forge.shared.material_profile_schema import resolve_material_profile
from asset_forge.shared.report_schema import REPORT_VERSION, attach_acceptance_summary, create_acceptance_summary


def validate_material_profile_contract(material_profile, material_binding_plan=None):
    profile = resolve_material_profile(material_profile)
    material_binding_plan = material_binding_plan or {}
    checks = []
    checks.append(_master_material_check(profile))
    if material_binding_plan.get("slot_variant_error"):
        checks.append(_check("material_slot_variant", "error", profile.get("name", ""), material_binding_plan["slot_variant_error"]))
    for parent in sorted({item.get("parent_material") for item in material_binding_plan.get("materials", []) if item.get("parent_material")}):
        if parent != profile.get("master_material"):
            checks.append(_master_material_check(profile, parent))
    checks.extend(_pbr_parameter_contract_checks(profile))
    checks.append(_material_network_check(profile))
    checks.append(_virtual_texture_sampling_check(profile))
    checks.extend(_texture_parameter_checks(profile, material_binding_plan))
    checks.extend(_scalar_parameter_checks(profile, material_binding_plan))
    checks.extend(_vector_parameter_checks(profile, material_binding_plan))

    errors = [_message(item) for item in checks if item.get("status") == "error"]
    warnings = [_message(item) for item in checks if item.get("status") == "warning"]
    summary = create_acceptance_summary(
        "error" if errors else ("warning" if warnings else "pass"),
        warnings,
        errors,
        "修复 Material Profile 参数契约后重新生成材质实例计划" if errors else ("检查 Material Profile 契约警告后继续" if warnings else "Material Profile 参数契约通过"),
    )
    report = {
        "version": REPORT_VERSION,
        "stage": "material_profile_contract",
        "status": summary.get("status", ""),
        "profile": profile.get("name", ""),
        "checks": checks,
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _master_material_check(profile, master=None):
    master = profile.get("master_material", "") if master is None else master
    if master.startswith("/AssetForge/"):
        return _check("master_material_path", "pass", master, "母材质路径位于 /AssetForge 插件内容根")
    if master.startswith("/") and profile.get("allow_external_master_material", False):
        return _check("master_material_path", "pass", master, "母材质使用外部路径，已由 profile 显式允许")
    return _check("master_material_path", "error", master, "母材质必须位于 /AssetForge/...，或在 profile 中显式允许外部母材质")


def _pbr_parameter_contract_checks(profile):
    rules = profile.get("texture_rules", [])
    by_usage = dict((item.get("usage", ""), item.get("parameter", "")) for item in rules)
    checks = []
    for usage, expected in [("base_color", "BaseColor"), ("normal", "Normal")]:
        parameter = by_usage.get(usage, "")
        custom_parameter = profile.get("allow_external_master_material") and bool(parameter)
        valid = parameter == expected or custom_parameter
        checks.append(_check(
            "pbr_texture_parameter", "pass" if valid else "warning", usage,
            "PBR texture binding: {0} -> {1}".format(usage, parameter) if valid else "Expected {0} for {1}".format(expected, usage),
        ))
    packed_parameter = by_usage.get("packed_arm") or by_usage.get("packed_orm") or by_usage.get("arm") or by_usage.get("orm")
    checks.append(
        _check(
            "pbr_packed_parameter",
            "pass" if packed_parameter else "warning",
            "packed_arm",
            "PBR 打包贴图参数已配置：{0}".format(packed_parameter) if packed_parameter else "建议配置 ARM/ORM/PackedARM 参数，便于 UE 母材质读取 AO/Roughness/Metallic。",
        )
    )
    return checks


def _material_network_check(profile):
    status = profile.get("material_network_status", "placeholder")
    if status in ("generated_pbr", "verified_pbr", "pbr_parameterized"):
        return _check(
            "parent_material_network",
            "pass" if status == "verified_pbr" else "warning",
            profile.get("master_material", ""),
            "母材质网络状态：{0}；generated_pbr 表示 UE Python 可生成节点，真实验收仍需 UE 现场确认。".format(status),
        )
    return _check(
        "parent_material_network",
        "warning",
        profile.get("master_material", ""),
        "当前母材质网络仍按 placeholder 处理；贴图导入成功不等于材质已真实生效。",
    )


def _virtual_texture_sampling_check(profile):
    texture_policy = profile.get("texture_import_policy", {}) or {}
    vt_policy = texture_policy.get("virtual_texture_policy", "project_default")
    supports_vt = bool((profile.get("supports", {}) or {}).get("virtual_texture_sampling", False))
    if vt_policy in ("force_on", "auto") and not supports_vt:
        return _check(
            "virtual_texture_sampling",
            "warning",
            profile.get("master_material", ""),
            "贴图策略可能使用 Virtual Texture，但 profile 未声明母材质支持 VT 采样；需要真实 UE 中确认 VT Sample 节点。",
        )
    return _check(
        "virtual_texture_sampling",
        "pass",
        profile.get("master_material", ""),
        "Virtual Texture 采样契约已记录：{0}".format("支持" if supports_vt else "按项目默认/非强制"),
    )


def _texture_parameter_checks(profile, material_binding_plan):
    checks = []
    planned_materials = material_binding_plan.get("materials", [])
    for rule in profile.get("texture_rules", []):
        usage = rule.get("usage", "")
        parameter = rule.get("parameter", "")
        if not parameter:
            checks.append(_check("texture_parameter_mapping", "warning", usage, "贴图 usage 缺少材质参数映射：{0}".format(usage)))
            continue
        if not planned_materials:
            checks.append(_check("texture_parameter_mapping", "pass", usage, "贴图 usage 已配置材质参数：{0}->{1}".format(usage, parameter)))
            continue
        for material in planned_materials:
            has_usage = usage in material.get("slots", {})
            if profile.get("require_complete_texture_sets") and rule.get("required") and not has_usage:
                checks.append(_check(
                    "required_slot_texture", rule.get("missing_severity", "error"),
                    material.get("target_asset_path", ""), "材质槽缺少必需贴图：{0}".format(parameter),
                ))
                continue
            has_parameter = parameter in material.get("texture_parameters", {})
            status = "pass" if (not has_usage or has_parameter) else "warning"
            message = "贴图参数映射有效：{0}->{1}".format(usage, parameter) if status == "pass" else "材质实例计划缺少贴图参数：{0}->{1}".format(usage, parameter)
            checks.append(_check("texture_parameter_mapping", status, material.get("target_asset_path", usage), message))
    return checks


def _scalar_parameter_checks(profile, material_binding_plan):
    checks = []
    scalar_parameters = profile.get("scalar_parameters", {})
    planned_materials = material_binding_plan.get("materials", [])
    if not scalar_parameters:
        return [_check("scalar_parameters", "pass", "", "profile 未配置 scalar 默认参数，跳过")]
    if not planned_materials:
        return [_check("scalar_parameters", "pass", "", "profile scalar 默认参数已配置")]
    for material in planned_materials:
        planned = material.get("scalar_parameters", {})
        for name in scalar_parameters:
            checks.append(
                _check(
                    "scalar_parameter_plan",
                    "pass" if name in planned else "warning",
                    material.get("target_asset_path", ""),
                    "scalar 默认参数已进入材质实例计划：{0}".format(name) if name in planned else "scalar 默认参数未进入材质实例计划：{0}".format(name),
                )
            )
    return checks


def _vector_parameter_checks(profile, material_binding_plan):
    vector_parameters = profile.get("vector_parameters", {})
    planned_materials = material_binding_plan.get("materials", [])
    if not vector_parameters:
        return [_check("vector_parameters", "pass", "", "profile 未配置 vector 默认参数，跳过")]
    if not planned_materials:
        return [_check("vector_parameters", "pass", "", "profile vector 默认参数已配置")]
    checks = []
    for material in planned_materials:
        planned = material.get("vector_parameters", {})
        for name in vector_parameters:
            checks.append(
                _check(
                    "vector_parameter_plan",
                    "pass" if name in planned else "warning",
                    material.get("target_asset_path", ""),
                    "vector 默认参数已进入材质实例计划：{0}".format(name) if name in planned else "vector 默认参数未进入材质实例计划：{0}".format(name),
                )
            )
    return checks


def _check(check_id, status, path, message):
    return {
        "id": check_id,
        "label": "Material Profile 参数契约",
        "status": status,
        "path": str(path).replace("\\", "/"),
        "message": message,
    }


def _message(item):
    return {
        "source": "material_profile_contract",
        "id": item.get("id", ""),
        "path": item.get("path", ""),
        "message": item.get("message", ""),
    }
