# -*- coding: utf-8 -*-
"""Project-level Maya settings for Asset Forge."""

from __future__ import absolute_import

import io
import json
import os

from asset_forge.shared.constants import TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.unreal_path import sanitize_unreal_package_path


PROJECT_SETTINGS_VERSION = "0.1"

DEFAULT_PROJECT_SETTINGS = {
    "version": PROJECT_SETTINGS_VERSION,
    "export_root": os.path.expanduser("~/AssetForge/Exports"),
    "texture_root": "",
    "triangle_budget": 50000,
    "mesh_prefix": "SM_",
    "texture_prefix": "T_",
    "texture_set_token": "",
    "asset_name_override": "",
    "ue_target_path": "/Game/Props",
    "target_platform": TARGET_PLATFORM_HIGH_END_MOBILE,
    "material_profile": "Props_Opaque_PainterUE_ARM",
    "virtual_texture_policy": "project_default",
    "texture_streaming_policy": "project_default",
    "texture_group": "project_default",
    "nanite_policy": "project_default",
    "static_mesh_lod_group": "project_default",
    "static_mesh_lod_import_policy": "import_existing",
    "build_reversed_index_buffer": "report_only",
    "generate_lightmap_uvs": "report_only",
    "collision_complexity": "report_only",
}


def default_project_settings():
    return dict(DEFAULT_PROJECT_SETTINGS)


def normalize_project_settings(data):
    result = default_project_settings()
    result.update(data or {})
    result["version"] = str(result.get("version") or PROJECT_SETTINGS_VERSION)
    result["export_root"] = normalize_path(result.get("export_root", ""))
    result["texture_root"] = normalize_path(result.get("texture_root", ""))
    result["triangle_budget"] = int(result.get("triangle_budget") or 0)
    result["mesh_prefix"] = str(result.get("mesh_prefix") or "SM_")
    result["texture_prefix"] = str(result.get("texture_prefix") or "T_")
    result["texture_set_token"] = str(result.get("texture_set_token") or result.get("texture_set_selection") or "")
    result["asset_name_override"] = str(result.get("asset_name_override") or result.get("export_asset_name") or "")
    result["ue_target_path"] = sanitize_unreal_package_path(result.get("ue_target_path") or "/Game/Props")
    result["target_platform"] = str(result.get("target_platform") or TARGET_PLATFORM_HIGH_END_MOBILE)
    result["material_profile"] = str(result.get("material_profile") or "Props_Opaque_PainterUE_ARM")
    result["virtual_texture_policy"] = _choice(
        result.get("virtual_texture_policy"),
        ["project_default", "auto", "force_on", "force_off"],
        "project_default",
    )
    result["texture_streaming_policy"] = _choice(
        result.get("texture_streaming_policy"),
        ["project_default", "streaming", "never_stream"],
        "project_default",
    )
    result["texture_group"] = str(result.get("texture_group") or "project_default")
    result["nanite_policy"] = _choice(
        result.get("nanite_policy"),
        ["project_default", "enable", "disable", "report_only"],
        "project_default",
    )
    result["static_mesh_lod_group"] = str(result.get("static_mesh_lod_group") or "project_default")
    result["static_mesh_lod_import_policy"] = _choice(
        result.get("static_mesh_lod_import_policy"),
        ["project_default", "import_existing", "ignore_lods", "report_only"],
        "import_existing",
    )
    result["build_reversed_index_buffer"] = str(result.get("build_reversed_index_buffer") or "report_only")
    result["generate_lightmap_uvs"] = str(result.get("generate_lightmap_uvs") or "report_only")
    result["collision_complexity"] = str(result.get("collision_complexity") or "report_only")
    return result


def _choice(value, allowed, default):
    value = str(value or default)
    return value if value in allowed else default


def load_project_settings(path):
    with io.open(path, "r", encoding="utf-8") as stream:
        return normalize_project_settings(json.load(stream))


def save_project_settings(path, settings):
    path = normalize_project_settings_path(path)
    active = normalize_project_settings(settings)
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with io.open(path, "w", encoding="utf-8") as stream:
        json.dump(active, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return normalize_path(path)


def normalize_project_settings_path(path):
    active = (path or "").strip()
    root, extension = os.path.splitext(active)
    if extension == ".*":
        return root + ".json"
    if extension.lower() != ".json":
        return active + ".json"
    return active
