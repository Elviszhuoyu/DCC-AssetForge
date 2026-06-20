"""Validate imported texture assets and material instance bindings."""

from __future__ import absolute_import

from asset_forge.shared.material_profile_schema import resolve_material_profile


DEFAULT_TEXTURE_PREFIX = "/AssetForge/Textures/"


def validate_material_texture_bindings(
    material_binding_plan,
    texture_import_plan=None,
    material_parameter_report=None,
    imported_textures=None,
    material_profile=None,
    unreal_module=None,
):
    """Return a gate report for texture existence and material MI binding coverage."""

    material_binding_plan = material_binding_plan or {}
    texture_import_plan = texture_import_plan or {}
    material_parameter_report = material_parameter_report or {}
    imported_textures = list(imported_textures or [])
    profile = resolve_material_profile(material_profile or material_binding_plan.get("profile", ""))
    required_rules = _required_texture_rules(profile)
    planned_texture_paths = _planned_texture_paths(texture_import_plan)
    imported_texture_paths = _asset_path_set(imported_textures)
    parameter_rows = _parameter_rows(material_parameter_report)
    checks = []

    for material in material_binding_plan.get("materials", []):
        texture_parameters = material.get("texture_parameters", {}) or {}
        slots = material.get("slots", {}) or {}
        material_name = material.get("material_name", "") or material.get("maya_material_name", "")
        mi_path = material.get("target_asset_path", "") or material.get("material_instance_path", "")

        if not texture_parameters and not slots and required_rules:
            checks.append(
                    _check(
                        "material_required_textures_missing",
                        "error",
                    material_name,
                    mi_path,
                    "",
                    "",
                    "材质 {0} 没有匹配到任何贴图；UE 会创建材质实例，但必需贴图会退回默认贴图。".format(material_name or mi_path),
                )
            )

        for rule in required_rules:
            usage = rule.get("usage", "")
            parameter = rule.get("parameter", "")
            expected_path = texture_parameters.get(parameter) or slots.get(usage) or ""
            if not expected_path:
                checks.append(
                    _check(
                        "required_texture_parameter_missing",
                        "error",
                        material_name,
                        mi_path,
                        usage,
                        parameter,
                        "材质 {0} 缺少必需贴图 {1}->{2}，导入后会使用默认贴图。".format(material_name or mi_path, usage, parameter),
                    )
                )
                continue

            exists_in_plan = _path_in_set(expected_path, planned_texture_paths)
            exists_imported = _path_in_set(expected_path, imported_texture_paths)
            exists_in_unreal = _unreal_asset_exists(unreal_module, expected_path)
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
    return {
        "status": "error" if errors else ("warning" if warnings else "pass"),
        "material_count": len(material_binding_plan.get("materials", [])),
        "planned_texture_count": len(planned_texture_paths),
        "imported_texture_count": len(imported_texture_paths),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "can_accept": not errors,
        "next_action": "修复缺失贴图或材质贴图集匹配后重新导出/导入。" if (warnings or errors) else "材质贴图资产与材质实例绑定已验证。",
    }


def _required_texture_rules(profile):
    return [rule for rule in (profile or {}).get("texture_rules", []) if rule.get("required") and rule.get("parameter")]


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
