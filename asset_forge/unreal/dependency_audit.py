"""Offline release dependency audit for Unreal Asset Forge reports."""

from __future__ import absolute_import

import re


ASSET_FORGE_ROOT = "/AssetForge"

STATUS_PASS = "pass"
STATUS_WARNING = "warning"
STATUS_BLOCKED_PLUGIN_DEPENDENCY = "blocked_plugin_dependency"
STATUS_PROJECT_MATERIAL_PROFILE_READY = "project_material_profile_ready"

_ASSET_FORGE_PATH_RE = re.compile(r"/AssetForge(?:/[A-Za-z0-9_.-]+)*")


def audit_unreal_dependencies(report, project_material_parent_mapping=None, allow_plugin_dependencies=False):
    """Return a dry-run release dependency audit for a manifest/report-like dict.

    The audit is intentionally pure Python. It only reads the supplied structure,
    finds `/AssetForge` Unreal asset paths, and prepares reparent actions when a
    project material parent mapping is supplied.
    """
    mapping = dict(project_material_parent_mapping or {})
    dependencies = _scan_dependencies(report)
    reparent_actions = []
    missing_mappings = []

    for dependency in dependencies:
        source_path = dependency["path"]
        target_path = mapping.get(source_path, "")
        if _can_reparent(dependency):
            if target_path:
                dependency["reparent_available"] = True
                dependency["replacement_path"] = target_path
                reparent_actions.append(_reparent_action(dependency, target_path))
            elif not allow_plugin_dependencies:
                missing_mappings.append(source_path)

    missing_mappings = sorted(set(missing_mappings))
    unmapped_blockers = [
        item
        for item in dependencies
        if not allow_plugin_dependencies and not _has_reparent_mapping(item, mapping)
    ]
    blocked = bool(unmapped_blockers)
    status = _status(dependencies, blocked, allow_plugin_dependencies, reparent_actions)
    messages = _messages(status, dependencies, missing_mappings, allow_plugin_dependencies)

    return {
        "version": "0.1",
        "stage": "unreal_dependency_audit",
        "status": status,
        "can_release": status in (STATUS_PASS, STATUS_PROJECT_MATERIAL_PROFILE_READY, STATUS_WARNING),
        "allow_plugin_dependencies": bool(allow_plugin_dependencies),
        "asset_forge_dependency_count": len(dependencies),
        "plugin_dependencies": dependencies,
        "blocked_dependencies": unmapped_blockers if blocked else [],
        "reparent_plan": {
            "status": _reparent_plan_status(dependencies, reparent_actions, missing_mappings, allow_plugin_dependencies),
            "dry_run": True,
            "action_count": len(reparent_actions),
            "actions": reparent_actions,
            "missing_mappings": missing_mappings,
        },
        "messages": messages,
        "next_action": _next_action(status, missing_mappings, allow_plugin_dependencies),
    }


def _scan_dependencies(value):
    dependencies = []
    seen = set()
    for field_path, key, text in _walk_strings(value):
        for asset_path in _asset_forge_paths(text):
            marker = (field_path, asset_path)
            if marker in seen:
                continue
            seen.add(marker)
            dependencies.append(_dependency(field_path, key, asset_path))
    return dependencies


def _walk_strings(value, field_path="", key=""):
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            child_path = "{0}.{1}".format(field_path, item_key) if field_path else str(item_key)
            for item in _walk_strings(item_value, child_path, str(item_key)):
                yield item
    elif isinstance(value, (list, tuple)):
        for index, item_value in enumerate(value):
            child_path = "{0}[{1}]".format(field_path, index) if field_path else "[{0}]".format(index)
            for item in _walk_strings(item_value, child_path, key):
                yield item
    elif isinstance(value, str):
        yield field_path, key, value


def _asset_forge_paths(text):
    paths = []
    for match in _ASSET_FORGE_PATH_RE.finditer(text or ""):
        path = match.group(0).rstrip(".,;:)")
        if path:
            paths.append(_strip_object_suffix(path))
    return paths


def _strip_object_suffix(path):
    last_segment = path.rsplit("/", 1)[-1]
    object_suffix = ".{0}".format(last_segment)
    if path.endswith(object_suffix):
        return path[: -len(object_suffix)]
    return path


def _dependency(field_path, key, asset_path):
    asset_type = _asset_type(asset_path)
    reference_role = _reference_role(key, field_path)
    return {
        "path": asset_path,
        "field_path": field_path,
        "asset_type": asset_type,
        "reference_role": reference_role,
        "reparent_candidate": reference_role in ("parent_material", "master_material") and asset_type == "material",
        "reparent_available": False,
        "replacement_path": "",
    }


def _asset_type(path):
    lowered = (path or "").lower()
    if "/materialinstances/" in lowered:
        return "material_instance"
    if "/materialfunctions/" in lowered:
        return "material_function"
    if "/parametercollections/" in lowered:
        return "material_parameter_collection"
    if "/textures/" in lowered:
        return "texture"
    if "/materials/" in lowered:
        return "material"
    if "/meshes/" in lowered or "/staticmeshes/" in lowered or "/static_meshes/" in lowered:
        return "static_mesh"
    return "asset"


def _reference_role(key, field_path):
    text = "{0}.{1}".format(field_path or "", key or "").lower()
    if "parent_material" in text:
        return "parent_material"
    if "master_material" in text or "material_variants" in text:
        return "master_material"
    if "texture" in text:
        return "texture"
    if "function" in text:
        return "material_function"
    if "parametercollection" in text or "parameter_collection" in text or "mpc" in text:
        return "material_parameter_collection"
    if "static_mesh" in text or "mesh" in text:
        return "static_mesh"
    return "asset_reference"


def _can_reparent(dependency):
    return bool(dependency.get("reparent_candidate"))


def _has_reparent_mapping(dependency, mapping):
    return _can_reparent(dependency) and dependency.get("path") in mapping


def _reparent_action(dependency, target_path):
    return {
        "action": "reparent_material_instance",
        "dry_run": True,
        "source_parent_material": dependency.get("path", ""),
        "target_parent_material": target_path,
        "field_path": dependency.get("field_path", ""),
        "message": "Dry-run only: replace Material Instance parent with project material.",
    }


def _reparent_plan_status(dependencies, reparent_actions, missing_mappings, allow_plugin_dependencies):
    if reparent_actions:
        return "ready"
    if allow_plugin_dependencies and dependencies:
        return "allowed_plugin_dependency"
    if missing_mappings:
        return "missing_mapping"
    return "not_required"


def _status(dependencies, blocked, allow_plugin_dependencies, reparent_actions):
    if not dependencies:
        return STATUS_PASS
    if allow_plugin_dependencies:
        return STATUS_WARNING
    if blocked:
        return STATUS_BLOCKED_PLUGIN_DEPENDENCY
    if reparent_actions:
        return STATUS_PROJECT_MATERIAL_PROFILE_READY
    return STATUS_PASS


def _messages(status, dependencies, missing_mappings, allow_plugin_dependencies):
    if status == STATUS_PASS:
        return ["No /AssetForge release dependencies found."]
    if allow_plugin_dependencies:
        return ["Project explicitly allows /AssetForge plugin dependencies; release should record this as a known plugin runtime dependency."]
    if missing_mappings:
        return ["Missing project material parent mapping for: {0}".format(", ".join(missing_mappings))]
    if dependencies:
        return ["Project material parent mapping is ready; reparent plan is dry-run only."]
    return []


def _next_action(status, missing_mappings, allow_plugin_dependencies):
    if status == STATUS_PASS:
        return "Release package has no AssetForge plugin dependency."
    if allow_plugin_dependencies:
        return "Keep AssetForge plugin enabled in the target project and record the dependency in release notes."
    if missing_mappings:
        return "Provide project material parent mapping before release handoff."
    if status == STATUS_PROJECT_MATERIAL_PROFILE_READY:
        return "Review the dry-run reparent plan, then apply it in a real UE-controlled step if desired."
    return "Review plugin dependencies before release."
