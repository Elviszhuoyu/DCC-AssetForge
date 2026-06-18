"""Validate manifest material bindings against the Unreal material plan."""

from __future__ import absolute_import

from asset_forge.shared.report_schema import REPORT_VERSION, attach_acceptance_summary, create_acceptance_summary


def validate_material_binding_contract(manifest, material_binding_plan):
    manifest = manifest or {}
    material_binding_plan = material_binding_plan or {}
    bindings = list(manifest.get("material_texture_bindings", []) or [])
    planned_materials = list(material_binding_plan.get("materials", []) or [])
    planned_by_name = _planned_by_name(planned_materials)
    slots_by_index = _slots_by_index(manifest.get("material_slots", []))
    checks = []

    if not bindings:
        checks.append(_check("material_texture_bindings", "warning", "", "manifest 未记录 material_texture_bindings，无法二次核对 Maya -> UE 材质绑定合同"))
    else:
        checks.append(_check("material_texture_bindings", "pass", "", "manifest 已记录 material_texture_bindings：{0} 条".format(len(bindings))))

    if not planned_materials:
        checks.append(_check("material_binding_plan", "error", "", "material_binding_plan 没有材质项，无法核对 UE 材质实例计划"))
    else:
        checks.append(_check("material_binding_plan", "pass", "", "material_binding_plan 已生成材质项：{0} 条".format(len(planned_materials))))

    for binding in bindings:
        checks.extend(_binding_checks(binding, planned_by_name, slots_by_index))

    errors = [_message(item) for item in checks if item.get("status") == "error"]
    warnings = [_message(item) for item in checks if item.get("status") == "warning"]
    summary = create_acceptance_summary(
        "error" if errors else ("warning" if warnings else "pass"),
        warnings,
        errors,
        "Fix material_texture_bindings blocking errors, then rerun package acceptance" if errors else ("Review material_texture_bindings warnings before import" if warnings else "material_texture_bindings align with material_binding_plan"),
    )
    report = {
        "version": REPORT_VERSION,
        "stage": "material_binding_contract",
        "status": summary.get("status", ""),
        "binding_count": len(bindings),
        "material_plan_count": len(planned_materials),
        "planned_material_count": len(planned_materials),
        "checks": checks,
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _binding_checks(binding, planned_by_name, slots_by_index):
    material_name = binding.get("material_name", "") or binding.get("maya_material_name", "")
    slot_index = binding.get("slot_index", -1)
    ue_material_instance_path = binding.get("ue_material_instance_path", "")
    planned = planned_by_name.get(material_name)
    checks = []

    if not material_name:
        checks.append(_check("binding_material_name", "warning", "", "material_texture_bindings 存在未绑定 Maya 材质的贴图集"))
        return checks

    if not planned:
        checks.append(_check("binding_material_name", "warning", material_name, "manifest 材质未进入 UE material_binding_plan：{0}".format(material_name)))
        return checks

    checks.append(_check("binding_material_name", "pass", material_name, "manifest 材质已匹配 UE material_binding_plan：{0}".format(material_name)))
    planned_path = planned.get("material_instance_path", "") or planned.get("target_asset_path", "")
    if ue_material_instance_path:
        checks.append(
            _check(
                "binding_material_instance_path",
                "pass" if _same_path(ue_material_instance_path, planned_path) else "warning",
                ue_material_instance_path,
                "UE MI 路径一致：{0}".format(ue_material_instance_path)
                if _same_path(ue_material_instance_path, planned_path)
                else "UE MI 路径不一致：manifest={0} plan={1}".format(ue_material_instance_path, planned_path),
            )
        )
    else:
        checks.append(_check("binding_material_instance_path", "warning", material_name, "manifest 缺少 ue_material_instance_path：{0}".format(material_name)))

    if _is_valid_slot_index(slot_index):
        slot_material_name = slots_by_index.get(int(slot_index), "")
        slot_matches = not slot_material_name or slot_material_name == material_name
        checks.append(
            _check(
                "binding_slot_index",
                "pass" if slot_matches else "warning",
                str(slot_index),
                "slot_index 与 material_slots 一致：{0}".format(slot_index)
                if slot_matches
                else "slot_index 指向了其他材质槽：material={0} slot_material={1} slot_index={2}".format(material_name, slot_material_name, slot_index),
            )
        )
    else:
        checks.append(_check("binding_slot_index", "warning", material_name, "manifest 缺少有效 slot_index：{0}".format(material_name)))

    expected_usages = set((planned.get("slots", {}) or {}).keys())
    manifest_usages = set(binding.get("texture_usages", []) or [])
    missing_usages = sorted(manifest_usages - expected_usages)
    checks.append(
        _check(
            "binding_texture_usages",
            "warning" if missing_usages else "pass",
            material_name,
            "texture_usages 未进入 UE material plan slots：{0}".format(", ".join(missing_usages))
            if missing_usages
            else "texture_usages 已被 UE material plan slots 覆盖：{0}".format(material_name),
        )
    )

    return checks


def _planned_by_name(planned_materials):
    result = {}
    for material in planned_materials:
        material_name = material.get("material_name", "") or material.get("maya_material_name", "")
        if material_name and material_name not in result:
            result[material_name] = material
    return result


def _slots_by_index(slots):
    result = {}
    for fallback_index, slot in enumerate(slots or []):
        if isinstance(slot, dict):
            material_name = slot.get("name", "") or slot.get("material_name", "")
            index = slot.get("index", fallback_index)
        else:
            material_name = str(slot)
            index = fallback_index
        if _is_valid_slot_index(index):
            result[int(index)] = material_name
    return result


def _same_path(left, right):
    return _clean_path(left) == _clean_path(right)


def _clean_path(value):
    return str(value or "").replace("\\", "/").rstrip("/")


def _is_valid_slot_index(value):
    try:
        return int(value) >= 0
    except (TypeError, ValueError):
        return False


def _check(check_id, status, path, message):
    return {
        "id": check_id,
        "label": "Material Binding Contract",
        "status": status,
        "path": _clean_path(path),
        "message": message,
    }


def _message(item):
    return {
        "source": "material_binding_contract",
        "id": item.get("id", ""),
        "path": item.get("path", ""),
        "message": item.get("message", ""),
    }
