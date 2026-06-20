# -*- coding: utf-8 -*-
"""Shared material-to-texture-set binding helpers."""

from __future__ import absolute_import


def build_material_texture_set_mapping(materials, textures, folder_scan=None, asset_name="", allow_shared_texture_sets=False):
    material_entries = [dict(material, textures=[]) for material in (materials or [])]
    if not material_entries:
        material_entries.append({"name": "M_{0}".format(asset_name or "Asset"), "textures": []})

    textures_by_set = {}
    for texture in textures or []:
        set_name = texture.get("selected_texture_set", "") or ""
        textures_by_set.setdefault(set_name, []).append(texture)

    selected_sets = selected_texture_set_infos(folder_scan or {}, textures_by_set)
    assigned_sets = set()
    mapping = []

    for material in material_entries:
        binding = match_material_to_texture_set(material.get("name", ""), selected_sets, assigned_sets, allow_assigned=allow_shared_texture_sets)
        if not binding and len(material_entries) == 1 and len(selected_sets) == 1:
            binding = dict(selected_sets[0], binding_source="single_material_fallback")
        if binding:
            set_name = binding.get("set_name", "")
            assigned_sets.add(set_name)
            assigned_textures = list(textures_by_set.get(set_name, []))
            material["textures"] = assigned_textures
            material.update(
                {
                    "texture_set": set_name,
                    "texture_set_short_name": binding.get("short_name", ""),
                    "texture_set_binding_source": binding.get("binding_source", "material_name"),
                }
            )
            mapping.append(material_texture_set_entry(material, binding, assigned_textures, "bound"))
        elif len(material_entries) == 1 and textures:
            assigned_textures = list(textures or [])
            material["textures"] = assigned_textures
            material.update(
                {
                    "texture_set": ",".join([item.get("set_name", "") for item in selected_sets if item.get("set_name", "")]),
                    "texture_set_short_name": ",".join([item.get("short_name", "") for item in selected_sets if item.get("short_name", "")]),
                    "texture_set_binding_source": "single_material_multi_set_fallback",
                }
            )
            for item in selected_sets:
                assigned_sets.add(item.get("set_name", ""))
            mapping.append(material_texture_set_entry(material, {"binding_source": "single_material_multi_set_fallback"}, assigned_textures, "bound"))
        else:
            mapping.append(material_texture_set_entry(material, {"binding_source": "unmatched_material"}, [], "unmatched_material"))

    for item in selected_sets:
        set_name = item.get("set_name", "")
        if set_name in assigned_sets:
            continue
        mapping.append(
            {
                "status": "unassigned_texture_set",
                "material_name": "",
                "texture_set": set_name,
                "texture_set_short_name": item.get("short_name", ""),
                "binding_source": "no_matching_material",
                "texture_count": len(textures_by_set.get(set_name, [])),
                "usages": sorted(set(texture.get("usage", "") for texture in textures_by_set.get(set_name, []) if texture.get("usage", ""))),
                "textures": list(textures_by_set.get(set_name, [])),
            }
        )

    return {"materials": material_entries, "material_texture_sets": mapping}


def infer_texture_set_token_from_materials(materials, texture_sets):
    if not materials or not texture_sets:
        return ""
    selected = []
    selected_names = set()
    candidates = [
        {"set_name": item.get("set_name", ""), "short_name": item.get("short_name", short_texture_set_name(item.get("set_name", "")))}
        for item in texture_sets
        if item.get("set_name", "")
    ]
    for material in materials:
        match = match_material_to_texture_set(material.get("name", ""), candidates, selected_names)
        if not match:
            continue
        set_name = match.get("set_name", "")
        short_name = match.get("short_name", "") or short_texture_set_name(set_name)
        selected_names.add(set_name)
        selected.append(short_name or set_name)
    return ",".join(selected)


def selected_texture_set_infos(folder_scan, textures_by_set):
    texture_sets = folder_scan.get("texture_sets", []) if isinstance(folder_scan, dict) else []
    selected_names = folder_scan.get("selected_texture_sets", []) if isinstance(folder_scan, dict) else []
    result = []
    for set_name in selected_names:
        info = texture_set_info(texture_sets, set_name)
        result.append({"set_name": set_name, "short_name": info.get("short_name", short_texture_set_name(set_name))})
    for set_name in sorted(textures_by_set.keys()):
        if set_name and set_name not in selected_names:
            info = texture_set_info(texture_sets, set_name)
            result.append({"set_name": set_name, "short_name": info.get("short_name", short_texture_set_name(set_name))})
    return result


def texture_set_info(texture_sets, set_name):
    for item in texture_sets or []:
        if item.get("set_name", "") == set_name:
            return item
    return {}


def match_material_to_texture_set(material_name, selected_sets, assigned_sets, allow_assigned=False):
    normalized_material = tokenize_for_binding(material_name)
    for item in selected_sets:
        set_name = item.get("set_name", "")
        if set_name in assigned_sets and not allow_assigned:
            continue
        short_name = item.get("short_name", "")
        if short_name and "|{0}|".format(short_name.lower()) in normalized_material:
            return dict(item, binding_source="material_name_short_token")
        normalized_set = tokenize_for_binding(set_name)
        if normalized_set and normalized_set in normalized_material:
            return dict(item, binding_source="material_name_full_set")
    return None


def material_texture_set_entry(material, binding, textures, status):
    return {
        "status": status,
        "material_name": material.get("name", ""),
        "shading_group": material.get("shading_group", ""),
        "texture_set": material.get("texture_set", ""),
        "texture_set_short_name": material.get("texture_set_short_name", ""),
        "binding_source": binding.get("binding_source", ""),
        "texture_count": len(textures or []),
        "usages": sorted(set(texture.get("usage", "") for texture in textures or [] if texture.get("usage", ""))),
        "textures": list(textures or []),
    }


def short_texture_set_name(value):
    parts = [item for item in (value or "").replace("-", "_").split("_") if item]
    return parts[-1] if parts else value or ""


def tokenize_for_binding(value):
    tokens = []
    current = []
    for char in (value or "").lower():
        if char.isalnum():
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return "|" + "|".join(tokens) + "|" if tokens else ""
