"""Validate imported texture assets and material instance bindings."""

from __future__ import absolute_import

from asset_forge.shared.material_profile_schema import resolve_material_profile
from asset_forge.unreal.material_library import PARAMETER_API_MAPPING
from asset_forge.unreal.material_package_schema import DEFAULT_TEXTURE_PATHS


_DEFAULT_USAGE_ALIASES = {
    "opacity": "opacity_mask", "packed_orm": "packed_arm", "arm": "packed_arm", "orm": "packed_arm",
}
_DEFAULT_PARAMETER_USAGES = {
    "BaseColor": "base_color", "Normal": "normal", "ARM": "packed_arm", "ORM": "packed_arm",
    "OpacityMask": "opacity_mask", "Opacity": "opacity_mask", "Emissive": "emissive",
    "ImperfectionMask": "imperfection_mask",
}


def is_official_texture_default(path, usage=None):
    """Match only registered plugin defaults, including Unreal's object-path form."""
    package, dot, name = str(path or "").replace("\\", "/").casefold().partition(".")
    if dot and name != package.rsplit("/", 1)[-1]:
        return False
    paths = (DEFAULT_TEXTURE_PATHS.get(_DEFAULT_USAGE_ALIASES.get(usage, usage), ""),) if usage else DEFAULT_TEXTURE_PATHS.values()
    return bool(package) and any(package == candidate.casefold() for candidate in paths)


def official_texture_parameter_usage(parameter):
    """Return the role of a built-in named parameter, including its editor alias."""
    return next((usage for name, usage in _DEFAULT_PARAMETER_USAGES.items()
                 if parameter.casefold() in (name.casefold(), PARAMETER_API_MAPPING[name].casefold())), "")


def required_texture_rules(profile):
    return [rule for rule in profile.get("texture_rules", []) if rule.get("required") and rule.get("parameter")]


def texture_parameter_names(profile, parameter):
    """Support canonical names and the names displayed by the actual UE parent."""
    explicit = profile.get("parameter_api_mapping", {}).get(parameter)
    return tuple(dict.fromkeys(name for name in (parameter, explicit, PARAMETER_API_MAPPING.get(parameter)) if name))


def texture_binding_check_status(report, check):
    status = check.get("status")
    return "warning" if status == "error" and report.get("blocks_acceptance") is False else status


def validate_material_texture_bindings(
    material_binding_plan,
    texture_import_plan=None,
    material_parameter_report=None,
    imported_textures=None,
    material_profile=None,
    unreal_module=None,
    after_import=False,
):
    """Return a gate report for texture existence and material MI binding coverage."""

    material_binding_plan = material_binding_plan or {}
    texture_import_plan = texture_import_plan or {}
    material_parameter_report = material_parameter_report or {}
    imported_textures = list(imported_textures or [])
    profile = resolve_material_profile(material_profile or material_binding_plan.get("profile", ""))
    required_rules = required_texture_rules(profile)
    planned_texture_paths = _planned_texture_paths(texture_import_plan)
    imported_texture_paths = _asset_path_set(imported_textures)
    parameter_rows = _parameter_rows(material_parameter_report)
    checks = []
    require_readback = bool(after_import and profile.get("require_complete_texture_sets"))
    load_asset = getattr(unreal_module, "load_asset", None)
    editor = getattr(unreal_module, "MaterialEditingLibrary", None)
    can_readback = bool(after_import and load_asset and getattr(editor, "get_material_instance_texture_parameter_value", None))
    instances = {}
    materials = material_binding_plan.get("materials", [])
    if require_readback and not materials:
        checks.append(_check("material_instances_missing", "error", "", "", "", "", "导入后没有可验证的材质实例。"))

    for material in materials:
        texture_parameters = material.get("texture_parameters", {}) or {}
        slots = material.get("slots", {}) or {}
        material_name = material.get("material_name", "") or material.get("maya_material_name", "")
        mi_path = material.get("target_asset_path", "") or material.get("material_instance_path", "")

        if can_readback and mi_path not in instances:
            try:
                instances[mi_path] = load_asset(mi_path) if mi_path else None
            except (RuntimeError, TypeError, ValueError):
                instances[mi_path] = None

        if not texture_parameters and not slots and required_rules:
            checks.append(
                _check(
                    "material_required_textures_missing",
                    "warning" if all(rule.get("missing_severity") == "warning" for rule in required_rules) else "error",
                    material_name,
                    mi_path,
                    "",
                    "",
                    "材质 {0} 没有匹配到任何贴图；UE 会创建材质实例，但必需贴图会退回默认贴图。".format(material_name or mi_path),
                )
            )

        for rule in required_rules:
            usage = rule.get("usage", "")
            parameter = rule["parameter"]
            names = texture_parameter_names(profile, parameter)
            expected_path = next((texture_parameters[name] for name in names if texture_parameters.get(name)), slots.get(usage) or "")
            actual_path, reason = ("", "")
            if require_readback or can_readback:
                actual_path, reason = _read_texture_parameter(editor, instances.get(mi_path), names)
            missing_status = "warning" if rule.get("missing_severity") == "warning" else "error"
            target_name = (mi_path or material_name).rsplit("/", 1)[-1].split(".", 1)[0]
            if not expected_path or is_official_texture_default(expected_path):
                texture_state = ("当前继承母材质默认贴图" if is_official_texture_default(actual_path) else
                                 "当前使用工程中已有贴图" if actual_path else
                                 "导入时可能使用母材质默认贴图")
                checks.append(
                    _check(
                        "required_texture_parameter_missing",
                        missing_status,
                        material_name,
                        mi_path,
                        usage,
                        parameter,
                        "材质实例 {0} 的 {1} 槽缺少包内交付贴图，{2}。请补齐该槽贴图并重新导出。".format(target_name, parameter, texture_state),
                        expected_path=expected_path,
                        actual_path=actual_path,
                    )
                )
                continue

            exists_in_plan = _path_in_set(expected_path, planned_texture_paths)
            exists_imported = _path_in_set(expected_path, imported_texture_paths)
            exists_in_unreal = bool(imported_texture_paths and not exists_imported and _unreal_asset_exists(unreal_module, expected_path))
            status = "pass" if exists_in_plan and (not imported_texture_paths or exists_imported or exists_in_unreal) else "error"
            checks.append(
                _check(
                    "texture_asset_exists",
                    status,
                    material_name,
                    mi_path,
                    usage,
                    parameter,
                    "贴图资产已在导入计划/UE 资产中确认：{0}".format(expected_path)
                    if status == "pass"
                    else "材质 {0} 需要贴图 {1}，但导入后未确认该 UE 贴图资产存在。".format(material_name or mi_path, expected_path),
                    expected_path=expected_path,
                    planned=exists_in_plan,
                    imported=exists_imported,
                    unreal_exists=exists_in_unreal,
                )
            )

            if require_readback or can_readback:
                leaf = expected_path.rsplit("/", 1)[-1]
                expected_object_path = expected_path if "." in leaf else expected_path + "." + leaf
                matches = actual_path.lower() == expected_object_path.lower()
                fallback = not actual_path or is_official_texture_default(actual_path)
                readback_status = "pass" if matches else (missing_status if fallback and reason in ("", "参数未绑定") else
                                                           "error" if require_readback else "warning")
                checks.append(_check(
                    "material_instance_texture_readback", readback_status, material_name,
                    mi_path, usage, parameter,
                    "材质实例 {0} 的 {1} 槽应绑定 {2}，实际为 {3}。{4}".format(
                        target_name, parameter, expected_path.rsplit("/", 1)[-1], actual_path or reason,
                        "" if matches else "请打开材质实例核对该槽绑定。"),
                    expected_path=expected_object_path, actual_path=actual_path, reason=reason,
                ))
                continue

            parameter_row = parameter_rows.get((mi_path, parameter))
            if parameter_row:
                applied = bool(parameter_row.get("applied"))
                checks.append(
                    _check(
                        "material_instance_texture_parameter_applied",
                        "pass" if applied else "error",
                        material_name,
                        mi_path,
                        usage,
                        parameter,
                        "材质实例参数已绑定：{0}.{1} -> {2}".format(mi_path, parameter, expected_path)
                        if applied
                        else "材质实例参数绑定失败：{0}.{1} -> {2}".format(mi_path, parameter, expected_path),
                        expected_path=expected_path,
                        actual_path=parameter_row.get("texture_asset_path", ""),
                    )
                )

    warnings = [item for item in checks if item.get("status") == "warning"]
    errors = [item for item in checks if item.get("status") == "error"]
    if warnings or errors:
        next_action = "修复缺失贴图或材质贴图集匹配后重新导出或导入。"
    elif can_readback:
        next_action = "已读回材质实例的必需贴图绑定。"
    elif after_import:
        next_action = "导入计划已核对，请在 UE 中确认材质实例实际绑定。"
    else:
        next_action = "导入计划已关联声明的必需贴图槽。"
    return {
        "status": "error" if errors else ("warning" if warnings else "pass"),
        "runtime_readback_required": require_readback,
        "runtime_readback_available": can_readback,
        "material_count": len(materials),
        "planned_texture_count": len(planned_texture_paths),
        "imported_texture_count": len(imported_texture_paths),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "can_accept": not errors,
        "next_action": next_action,
    }


def _read_texture_parameter(editing, instance, names):
    if instance is None:
        return "", "材质实例未载入"
    getter = getattr(editing, "get_material_instance_texture_parameter_value", None)
    if not getter:
        return "", "当前 UE 无法读取材质实例的贴图参数"
    reason = "参数未绑定"
    for name in names:
        try:
            texture = getter(instance, name)
            if texture is not None:
                return str(texture.get_path_name()), ""
        except (AttributeError, TypeError, RuntimeError, ValueError):
            reason = "当前 UE 未能读取该参数"
    return "", reason


def _planned_texture_paths(texture_import_plan):
    paths = set()
    for texture in (texture_import_plan or {}).get("textures", []):
        for key in ("target_asset_path", "asset_path"):
            value = texture.get(key, "")
            if value:
                paths.update(_path_variants(value))
    return paths


def _asset_path_set(paths):
    result = set()
    for path in paths or []:
        result.update(_path_variants(str(path)))
    return result


def _parameter_rows(report):
    rows = {}
    for item in (report or {}).get("texture_parameters", []):
        key = (item.get("material_instance_path", ""), item.get("name", ""))
        if key[0] and key[1]:
            rows[key] = item
    return rows


def _path_in_set(path, path_set):
    return any(candidate in path_set for candidate in _path_variants(path))


def _path_variants(path):
    path = (path or "").replace("\\", "/")
    if not path:
        return []
    variants = [path]
    if "." in path.rsplit("/", 1)[-1]:
        variants.append(path.rsplit(".", 1)[0])
    else:
        leaf = path.rsplit("/", 1)[-1]
        variants.append("{0}.{1}".format(path, leaf))
    return variants


def _unreal_asset_exists(unreal_module, asset_path):
    if unreal_module is None or not asset_path:
        return False
    library = getattr(unreal_module, "EditorAssetLibrary", None)
    if library is None or not hasattr(library, "does_asset_exist"):
        return False
    try:
        return any(bool(library.does_asset_exist(candidate)) for candidate in _path_variants(asset_path))
    except Exception:
        return False


def _check(check_id, status, material_name, material_instance_path, usage, parameter, message, **extra):
    item = {
        "id": check_id,
        "label": "材质贴图绑定",
        "status": status,
        "material_name": material_name,
        "material_instance_path": material_instance_path,
        "usage": usage,
        "parameter": parameter,
        "message": message,
    }
    item.update(extra)
    return item
