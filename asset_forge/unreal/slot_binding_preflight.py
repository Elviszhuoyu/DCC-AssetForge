"""Offline Static Mesh material slot binding preflight."""

from __future__ import absolute_import

from asset_forge.shared.report_schema import REPORT_VERSION, attach_acceptance_summary, create_acceptance_summary


def validate_static_mesh_slot_bindings(manifest, material_binding_plan):
    slots = _manifest_slots(manifest)
    materials = list(material_binding_plan.get("materials", []))
    checks = []
    if not slots:
        checks.append(_check("material_slots", "warning", "", "manifest 未记录 material_slots，无法离线预验证 Static Mesh slot 绑定"))
    else:
        checks.append(_check("material_slot_count", "pass" if len(slots) == len(materials) else "warning", "", "material_slots 数量：{0}，材质实例计划数量：{1}".format(len(slots), len(materials))))
        material_names = set(item.get("material_name", "") for item in materials)
        for slot in slots:
            slot_name = slot.get("name", "")
            checks.append(
                _check(
                    "material_slot_name",
                    "pass" if slot_name in material_names else "warning",
                    slot_name,
                    "slot 可匹配材质实例计划：{0}".format(slot_name) if slot_name in material_names else "slot 名称无法匹配材质实例计划：{0}".format(slot_name),
                )
            )
    if materials:
        checks.append(_check("material_instance_plan", "pass", "", "材质实例计划存在"))
    else:
        checks.append(_check("material_instance_plan", "error", "", "缺少材质实例计划，无法绑定 Static Mesh slots"))

    errors = [_message(item) for item in checks if item.get("status") == "error"]
    warnings = [_message(item) for item in checks if item.get("status") == "warning"]
    summary = create_acceptance_summary(
        "error" if errors else ("warning" if warnings else "pass"),
        warnings,
        errors,
        "修复材质 slot 预验证阻断项后重新生成材质计划" if errors else ("检查材质 slot 预验证警告后继续" if warnings else "Static Mesh slot 预验证通过"),
    )
    report = {
        "version": REPORT_VERSION,
        "stage": "static_mesh_slot_binding_preflight",
        "status": summary.get("status", ""),
        "slot_count": len(slots),
        "material_plan_count": len(materials),
        "checks": checks,
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _manifest_slots(manifest):
    slots = manifest.get("material_slots", [])
    if isinstance(slots, int):
        return [{"name": item.get("name", "")} for item in manifest.get("materials", [])[:slots]]
    if isinstance(slots, list):
        result = []
        for item in slots:
            if isinstance(item, dict):
                result.append(item)
            else:
                result.append({"name": str(item)})
        return result
    return []


def _check(check_id, status, path, message):
    return {
        "id": check_id,
        "label": "Static Mesh Slot 预验证",
        "status": status,
        "path": str(path).replace("\\", "/"),
        "message": message,
    }


def _message(item):
    return {
        "source": "slot_binding_preflight",
        "id": item.get("id", ""),
        "path": item.get("path", ""),
        "message": item.get("message", ""),
    }
