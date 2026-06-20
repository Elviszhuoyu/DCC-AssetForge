"""Structured asset health summary for Maya preflight/export results."""

from __future__ import absolute_import


def create_asset_health_report(scan_result, validation_result, texture_folder_scan=None):
    scan_result = scan_result or {}
    validation_result = validation_result or {}
    texture_folder_scan = texture_folder_scan if texture_folder_scan is not None else scan_result.get("texture_folder_scan", {})
    score = int(validation_result.get("score") or 0)
    errors = _checks_with_status(validation_result, "error")
    warnings = _checks_with_status(validation_result, "warning")
    texture_risks = _texture_set_risks(scan_result, texture_folder_scan or {})
    auto_fix_suggestions = _auto_fix_suggestions(scan_result, validation_result, texture_folder_scan or {})

    return {
        "status": _health_status(validation_result, errors, warnings, texture_risks),
        "grade": _grade(score),
        "score": score,
        "can_export": bool(validation_result.get("can_export", False)),
        "asset_name": scan_result.get("asset_name", ""),
        "mesh_count": scan_result.get("mesh_count", 0),
        "triangles": scan_result.get("triangles", 0),
        "material_slots": scan_result.get("material_slots", 0),
        "texture_count": len(scan_result.get("textures", []) or []),
        "check_summary": {
            "errors": len(errors),
            "warnings": len(warnings),
            "passes": int((validation_result.get("summary") or {}).get("passes", 0)),
        },
        "blocking_checks": errors,
        "warning_checks": warnings,
        "auto_fix_suggestions": auto_fix_suggestions,
        "texture_set_risks": texture_risks,
        "next_action": _next_action(validation_result, errors, warnings, texture_risks, auto_fix_suggestions),
    }


def _checks_with_status(validation_result, status):
    return [item for item in validation_result.get("checks", []) if item.get("status") == status]


def _health_status(validation_result, errors, warnings, texture_risks):
    if errors or not validation_result.get("can_export", False):
        return "blocked"
    if warnings or texture_risks.get("risk_count", 0):
        return "review"
    return "ready"


def _grade(score):
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def _auto_fix_suggestions(scan_result, validation_result, texture_folder_scan):
    suggestions = []
    for check in validation_result.get("checks", []):
        if check.get("status") not in ("error", "warning"):
            continue
        check_id = check.get("id", "")
        suggestion = _suggestion_for_check(check_id, check, scan_result)
        if suggestion:
            suggestions.append(suggestion)

    naming = (texture_folder_scan or {}).get("texture_naming_validation", {})
    for item in naming.get("rename_suggestions", []) or []:
        suggestions.append(
            {
                "id": "texture_missing_t_prefix",
                "action": "preview_texture_prefix_rename",
                "target": item.get("path", ""),
                "will_modify_scene": False,
                "will_modify_disk": False,
                "message": item.get("message", ""),
            }
        )
    if texture_folder_scan.get("requires_texture_set_selection"):
        suggestions.append(
            {
                "id": "texture_set_selection",
                "action": "set_texture_set_token",
                "target": texture_folder_scan.get("texture_folder", ""),
                "will_modify_scene": False,
                "will_modify_disk": False,
                "message": "Choose one texture set token before export.",
            }
        )
    return suggestions


def _suggestion_for_check(check_id, check, scan_result):
    if check_id == "name_prefix":
        return {
            "id": check_id,
            "action": "rename_asset_root_with_prefix",
            "target": scan_result.get("asset_name_source_path", scan_result.get("asset_root", "")),
            "will_modify_scene": True,
            "will_modify_disk": False,
            "message": "Add the required asset prefix before export.",
        }
    if check_id == "frozen_transform":
        return {
            "id": check_id,
            "action": "freeze_transforms",
            "target": scan_result.get("asset_root", ""),
            "will_modify_scene": True,
            "will_modify_disk": False,
            "message": "Freeze translate/rotate/scale on export roots and mesh transforms.",
        }
    if check_id == "hidden_objects":
        return {
            "id": check_id,
            "action": "review_hidden_objects",
            "target": ", ".join(scan_result.get("hidden_objects", [])[:8]),
            "will_modify_scene": False,
            "will_modify_disk": False,
            "message": "Unhide or remove hidden objects before packaging.",
        }
    if check_id == "history_nodes":
        return {
            "id": check_id,
            "action": "delete_non_deformer_history",
            "target": ", ".join(scan_result.get("history_nodes", [])[:8]),
            "will_modify_scene": True,
            "will_modify_disk": False,
            "message": "Clean construction history after artist review.",
        }
    if check_id == "collision_naming":
        return {
            "id": check_id,
            "action": "rename_collision_prefix",
            "target": ", ".join(scan_result.get("invalid_collision_nodes", [])[:8]),
            "will_modify_scene": True,
            "will_modify_disk": False,
            "message": "Use UE collision prefixes such as UCX_, UBX_, USP_, or UCP_.",
        }
    if check_id == "lightmap_uv":
        return {
            "id": check_id,
            "action": "review_lightmap_uv",
            "target": scan_result.get("asset_root", ""),
            "will_modify_scene": False,
            "will_modify_disk": False,
            "message": "Add or confirm a secondary UV set when static lighting is required.",
        }
    if check_id == "uv0":
        return {
            "id": check_id,
            "action": "create_uv0",
            "target": scan_result.get("asset_root", ""),
            "will_modify_scene": True,
            "will_modify_disk": False,
            "message": "Create a base UV set before export.",
        }
    if check_id == "empty_mesh":
        return {
            "id": check_id,
            "action": "remove_empty_meshes",
            "target": ", ".join(scan_result.get("empty_meshes", [])[:8]),
            "will_modify_scene": True,
            "will_modify_disk": False,
            "message": "Remove empty mesh nodes before export.",
        }
    return None


def _texture_set_risks(scan_result, texture_folder_scan):
    risks = []
    if texture_folder_scan.get("requires_texture_set_selection"):
        risks.append({"id": "texture_set_selection_required", "severity": "error", "message": "Texture folder has multiple candidates and requires an explicit set token."})
    if texture_folder_scan.get("auto_selected_texture_sets"):
        risks.append({"id": "texture_set_auto_selected", "severity": "warning", "message": "Texture set was auto-selected; confirm it matches the current mesh/materials."})
    for item in texture_folder_scan.get("duplicate_matches", []) or []:
        risks.append({"id": "duplicate_texture_match", "severity": "warning", "usage": item.get("usage", ""), "matches": list(item.get("matches", [])), "message": "Multiple files match the same texture usage."})
    for item in texture_folder_scan.get("texture_sets", []) or []:
        if item.get("ambiguous_usages"):
            risks.append({"id": "ambiguous_texture_set_usage", "severity": "warning", "texture_set": item.get("set_name", ""), "usages": list(item.get("ambiguous_usages", [])), "message": "One texture set has duplicate files for the same usage."})

    binding_risks = scan_result.get("material_texture_binding_risks", []) or []
    if binding_risks:
        risks.extend(binding_risks)
    else:
        risks.extend(_material_binding_risks(scan_result))
        risks.extend(_shared_texture_set_risks(scan_result))
        risks.extend(_shared_texture_file_risks(scan_result))
    return {"risk_count": len(risks), "items": risks}


def _shared_texture_set_risks(scan_result):
    by_set = {}
    for item in scan_result.get("material_texture_sets", []) or []:
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
                "message": "One texture set is bound to multiple materials; confirm this is intentional sharing.",
            }
        )
    return risks


def _material_binding_risks(scan_result):
    risks = []
    for item in scan_result.get("material_texture_sets", []) or []:
        status = item.get("status", "")
        if status == "bound":
            continue
        risks.append(
            {
                "id": status or "material_texture_set_unresolved",
                "severity": "warning",
                "material_name": item.get("material_name", ""),
                "texture_set": item.get("texture_set", ""),
                "texture_count": item.get("texture_count", 0),
                "message": "Material and texture set binding needs review before export.",
            }
        )
    return risks


def _shared_texture_file_risks(scan_result):
    by_path = {}
    for material in scan_result.get("materials", []) or []:
        material_name = material.get("name", "")
        for texture in material.get("textures", []) or []:
            path = texture.get("source_path") or texture.get("path", "")
            if not path:
                continue
            by_path.setdefault(path, set()).add(material_name)

    risks = []
    for path, materials in sorted(by_path.items()):
        if len(materials) <= 1:
            continue
        risks.append(
            {
                "id": "shared_texture_file",
                "severity": "warning",
                "path": path,
                "materials": sorted(materials),
                "message": "One texture file is referenced by multiple materials; confirm shared material intent.",
            }
        )
    return risks


def _next_action(validation_result, errors, warnings, texture_risks, suggestions):
    if errors or not validation_result.get("can_export", False):
        return "Resolve blocking checks, then run Maya preflight again."
    if texture_risks.get("risk_count", 0):
        return "Review texture set risks before export."
    if warnings or suggestions:
        return "Review warnings and optional fixes before export."
    return "Ready to export."
