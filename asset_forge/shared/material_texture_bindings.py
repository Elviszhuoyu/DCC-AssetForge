"""Stable material to texture set binding contract for Maya export packages."""

from __future__ import absolute_import

import re

from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.unreal_path import sanitize_unreal_package_path


def create_material_texture_bindings(scan_result, target_path=""):
    scan_result = scan_result or {}
    slots = _material_slots(scan_result)
    rows = []
    for entry in _mapping_entries(scan_result):
        material_name = entry.get("material_name", "")
        slot = slots.get(material_name, {})
        textures = list(entry.get("textures", []) or [])
        textures_by_usage = _textures_by_usage(textures)
        instance = _ue_material_instance(material_name, target_path) if material_name else {"name": "", "path": ""}
        rows.append(
            {
                "status": entry.get("status", ""),
                "material_name": material_name,
                "maya_material_name": material_name,
                "shading_group": entry.get("shading_group", ""),
                "texture_set": entry.get("texture_set", ""),
                "texture_set_short_name": entry.get("texture_set_short_name", ""),
                "binding_source": entry.get("binding_source", ""),
                "texture_usages": sorted(textures_by_usage.keys()),
                "textures_by_usage": textures_by_usage,
                "texture_count": len(textures),
                "slot_name": slot.get("name", material_name),
                "slot_index": slot.get("index", -1),
                "static_mesh_slot": {"name": slot.get("name", material_name), "index": slot.get("index", -1)},
                "ue_material_instance": instance,
                "ue_material_instance_name": instance.get("name", ""),
                "ue_material_instance_path": instance.get("path", ""),
            }
        )
    return {"bindings": rows, "risks": material_texture_binding_risks(rows)}


def material_texture_binding_risks(bindings):
    risks = []
    for item in bindings or []:
        if item.get("status") == "unmatched_material":
            risks.append(
                {
                    "id": "unmatched_material",
                    "severity": "error",
                    "material_name": item.get("material_name", ""),
                    "slot_name": item.get("slot_name", ""),
                    "message": "Maya material has no matching texture set; export is blocked to avoid default material textures.",
                }
            )
        elif item.get("status") == "unassigned_texture_set":
            risks.append(
                {
                    "id": "unassigned_texture_set",
                    "severity": "warning",
                    "texture_set": item.get("texture_set", ""),
                    "texture_count": item.get("texture_count", 0),
                    "message": "Texture set has no matching Maya material slot; export can continue but the set will not bind to a slot automatically.",
                }
            )

    risks.extend(_shared_texture_set_risks(bindings))
    risks.extend(_shared_texture_file_risks(bindings))
    risks.extend(_shared_material_instance_risks(bindings))
    risks.extend(_shared_slot_index_risks(bindings))
    return risks


def _mapping_entries(scan_result):
    mapping = list(scan_result.get("material_texture_sets", []) or [])
    if mapping:
        return mapping

    result = []
    has_texture_evidence = bool(scan_result.get("textures") or scan_result.get("texture_folder_scan"))
    for material in scan_result.get("materials", []) or []:
        material_name = material.get("name", "") or material.get("material_name", "")
        status = "bound" if material.get("textures") else "unmatched_material"
        if not material.get("textures") and not has_texture_evidence:
            status = "unbound_no_texture_evidence"
        result.append(
            {
                "status": status,
                "material_name": material_name,
                "shading_group": material.get("shading_group", ""),
                "texture_set": material.get("texture_set", ""),
                "texture_set_short_name": material.get("texture_set_short_name", ""),
                "binding_source": material.get("texture_set_binding_source", "maya_material"),
                "textures": list(material.get("textures", []) or []),
            }
        )
    return result


def _material_slots(scan_result):
    slots = scan_result.get("material_slots", [])
    result = {}
    if isinstance(slots, list):
        for index, slot in enumerate(slots):
            if not isinstance(slot, dict):
                continue
            name = slot.get("name", "") or slot.get("material_name", "")
            if name:
                result[name] = {"name": name, "index": int(slot.get("index", index))}
    for index, material in enumerate(scan_result.get("materials", []) or []):
        material_name = material.get("name", "") or material.get("material_name", "")
        if material_name and material_name not in result:
            result[material_name] = {"name": material_name, "index": index}
    return result


def _textures_by_usage(textures):
    result = {}
    for texture in textures or []:
        usage = texture.get("usage", "") or "unknown"
        result.setdefault(usage, []).append(texture)
    return result


def _ue_material_instance(material_name, target_path):
    name = _material_instance_name(material_name)
    if not target_path:
        return {"name": name, "path": ""}
    target_dir = "{0}/Materials".format(sanitize_unreal_package_path(target_path))
    return {"name": name, "path": "{0}/{1}".format(target_dir, name)}


def _material_instance_name(material_name):
    clean_name = _sanitize_asset_name(material_name or "Material")
    if clean_name.startswith("MI_") or clean_name.endswith("_INST"):
        return clean_name
    return "MI_{0}".format(clean_name)


def _sanitize_asset_name(value):
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", value or "Material").strip("_")
    return cleaned or "Material"


def _shared_texture_set_risks(bindings):
    by_set = {}
    for item in bindings or []:
        set_name = item.get("texture_set", "")
        material_name = item.get("material_name", "")
        if not set_name or not material_name:
            continue
        by_set.setdefault(set_name, set()).add(material_name)

    risks = []
    for set_name, materials in sorted(by_set.items()):
        if len(materials) <= 1:
            continue
        risks.append(
            {
                "id": "shared_texture_set",
                "severity": "warning",
                "texture_set": set_name,
                "materials": sorted(materials),
                "message": "Texture set is bound to multiple Maya materials; confirm this is intentional material sharing.",
            }
        )
    return risks


def _shared_texture_file_risks(bindings):
    by_path = {}
    for item in bindings or []:
        for textures in item.get("textures_by_usage", {}).values():
            for texture in textures:
                path = normalize_path(texture.get("source_path") or texture.get("path") or texture.get("package_path") or "")
                if not path:
                    continue
                by_path.setdefault(path, set()).add(item.get("material_name", ""))

    risks = []
    for path, materials in sorted(by_path.items()):
        active = sorted(item for item in materials if item)
        if len(active) <= 1:
            continue
        risks.append(
            {
                "id": "shared_texture_file",
                "severity": "warning",
                "path": path,
                "materials": active,
                "message": "Texture file is referenced by multiple Maya materials; confirm this shared skin is intended.",
            }
        )
    return risks


def _shared_material_instance_risks(bindings):
    by_instance = {}
    for item in bindings or []:
        key = item.get("ue_material_instance_path") or item.get("ue_material_instance_name", "")
        material_name = item.get("material_name", "")
        if not key or not material_name:
            continue
        by_instance.setdefault(key, set()).add(material_name)

    risks = []
    for instance, materials in sorted(by_instance.items()):
        if len(materials) <= 1:
            continue
        risks.append(
            {
                "id": "shared_material_instance",
                "severity": "warning",
                "ue_material_instance": instance,
                "materials": sorted(materials),
                "message": "Multiple Maya materials resolve to the same UE Material Instance name; rename materials or confirm intentional sharing.",
            }
        )
    return risks


def _shared_slot_index_risks(bindings):
    by_index = {}
    for item in bindings or []:
        index = item.get("slot_index", -1)
        material_name = item.get("material_name", "")
        if index is None or int(index) < 0 or not material_name:
            continue
        by_index.setdefault(int(index), set()).add(material_name)

    risks = []
    for index, materials in sorted(by_index.items()):
        if len(materials) <= 1:
            continue
        risks.append(
            {
                "id": "shared_slot_index",
                "severity": "warning",
                "slot_index": index,
                "materials": sorted(materials),
                "message": "Multiple Maya materials resolve to the same Static Mesh material slot index; confirm slot extraction before import.",
            }
        )
    return risks
