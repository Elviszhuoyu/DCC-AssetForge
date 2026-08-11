# -*- coding: utf-8 -*-
"""Project-level DCC settings for DCC AssetForge."""

from __future__ import absolute_import

import io
import json
import os
from datetime import datetime

from asset_forge.shared.constants import TARGET_PLATFORM_PC
from asset_forge.shared.package_naming import PACKAGE_VERSION_MODE_OVERWRITE, normalize_package_version_mode
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.unreal_path import sanitize_unreal_package_path


PROJECT_SETTINGS_VERSION = "0.3"

PROJECT_SETTINGS_LABELS = {
    "schema": ("配置类型", "asset_forge.preset.schema"),
    "version": ("配置格式版本", "asset_forge.preset.schema_version"),
    "preset_name": ("预设名称", "asset_forge.preset.name"),
    "preset_version": ("预设版本", "asset_forge.preset.version"),
    "updated_at": ("更新时间", "asset_forge.preset.updated_at"),
    "export_root": ("导出根目录", "dcc.export_root"),
    "package_name_override": ("包体/文件夹名", "dcc.package_name"),
    "package_version_mode": ("包体迭代模式", "dcc.package_version_mode"),
    "package_version_padding": ("版本号位数", "dcc.package_version_padding"),
    "package_version_start": ("起始版本号", "dcc.package_version_start"),
    "texture_root": ("贴图目录", "dcc.texture_root"),
    "texture_set_token": ("贴图集关键词", "dcc.texture_set_token"),
    "triangle_budget": ("三角面最大上限", "asset_forge.validation.triangle_budget"),
    "mesh_prefix": ("模型前缀", "asset_forge.naming.mesh_prefix"),
    "texture_prefix": ("贴图前缀", "asset_forge.naming.texture_prefix"),
    "ue_target_path": ("UE 目标路径", "ue.target_path"),
    "target_platform": ("目标平台", "ue.target_platform"),
    "material_profile": ("材质匹配规则", "ue.material_profile"),
    "virtual_texture_policy": ("Virtual Texture 策略", "ue.texture.virtual_texture_policy"),
    "texture_streaming_policy": ("Texture Streaming 策略", "ue.texture.streaming_policy"),
    "texture_group": ("Texture Group", "ue.texture.group"),
    "nanite_policy": ("Nanite 策略", "ue.static_mesh.nanite_policy"),
    "static_mesh_lod_group": ("Mesh LODGroup", "ue.static_mesh.lod_group"),
    "static_mesh_lod_import_policy": ("Mesh LOD 导入策略", "ue.static_mesh.lod_import_policy"),
    "build_reversed_index_buffer": ("反向索引缓冲", "ue.static_mesh.build_reversed_index_buffer"),
    "generate_lightmap_uvs": ("生成 Lightmap UV", "ue.static_mesh.generate_lightmap_uvs"),
    "collision_complexity": ("碰撞复杂度", "ue.static_mesh.collision_complexity"),
}

PROJECT_SETTINGS_EXPORT_KEYS = [
    "schema",
    "version",
    "preset_name",
    "preset_version",
    "ue_target_path",
    "export_root",
    "package_name_override",
    "package_version_mode",
    "package_version_padding",
    "target_platform",
    "material_profile",
    "triangle_budget",
    "mesh_prefix",
    "texture_root",
    "texture_set_token",
    "texture_prefix",
    "nanite_policy",
    "static_mesh_lod_group",
    "static_mesh_lod_import_policy",
    "virtual_texture_policy",
    "texture_streaming_policy",
    "texture_group",
    "updated_at",
    "package_version_start",
    "build_reversed_index_buffer",
    "generate_lightmap_uvs",
    "collision_complexity",
]

DEFAULT_PROJECT_SETTINGS = {
    "version": PROJECT_SETTINGS_VERSION,
    "schema": "asset_forge_project_preset",
    "preset_name": "AssetForge_Default_StaticProp",
    "preset_version": "1",
    "updated_at": "",
    "export_root": os.path.expanduser("~/AssetForge/Exports"),
    "texture_root": "",
    "triangle_budget": 50000,
    "mesh_prefix": "SM_",
    "texture_prefix": "T_",
    "texture_set_token": "",
    "package_name_override": "",
    "asset_name_override": "",
    "package_version_mode": PACKAGE_VERSION_MODE_OVERWRITE,
    "package_version_padding": 3,
    "package_version_start": 1,
    "ue_target_path": "/Game/Props",
    "target_platform": TARGET_PLATFORM_PC,
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
    result["schema"] = "asset_forge_project_preset"
    result["version"] = str(result.get("version") or PROJECT_SETTINGS_VERSION)
    result["preset_name"] = str(result.get("preset_name") or "AssetForge_Default_StaticProp")
    result["preset_version"] = str(result.get("preset_version") or "1")
    result["updated_at"] = str(result.get("updated_at") or "")
    result["export_root"] = normalize_path(result.get("export_root", ""))
    result["texture_root"] = normalize_path(result.get("texture_root", ""))
    result["triangle_budget"] = int(result.get("triangle_budget") or 0)
    result["mesh_prefix"] = str(result.get("mesh_prefix") or "SM_")
    result["texture_prefix"] = str(result.get("texture_prefix") or "T_")
    result["texture_set_token"] = str(result.get("texture_set_token") or result.get("texture_set_selection") or "")
    package_name = str(
        result.get("package_name_override")
        or result.get("package_name")
        or result.get("asset_name_override")
        or result.get("export_asset_name")
        or ""
    )
    result["package_name_override"] = package_name
    # Old presets sometimes used asset_name_override as the package/folder name.
    # Keep it as a migration input above, but do not let a package name rename meshes.
    result["asset_name_override"] = str(result.get("asset_name_override") or "")
    result["package_version_mode"] = normalize_package_version_mode(result.get("package_version_mode"))
    result["package_version_padding"] = _positive_int(result.get("package_version_padding"), 3)
    result["package_version_start"] = _positive_int(result.get("package_version_start"), 1)
    result["ue_target_path"] = sanitize_unreal_package_path(result.get("ue_target_path") or "/Game/Props")
    result["target_platform"] = str(result.get("target_platform") or TARGET_PLATFORM_PC)
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


def _positive_int(value, default):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    return max(1, number)


def load_project_settings(path):
    with io.open(path, "r", encoding="utf-8") as stream:
        return normalize_project_settings(json.load(stream))


def save_project_settings(path, settings):
    path = normalize_project_settings_path(path)
    active = normalize_project_settings(settings)
    active["updated_at"] = datetime.now().replace(microsecond=0).isoformat()
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with io.open(path, "w", encoding="utf-8") as stream:
        json.dump(active, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return normalize_path(path)


def project_settings_rows(settings, include_all=False):
    """Return table-like preset rows for DCC UI status blocks."""
    active = normalize_project_settings(settings)
    rows = []
    keys = PROJECT_SETTINGS_EXPORT_KEYS if include_all else [
        "preset_name",
        "preset_version",
        "ue_target_path",
        "export_root",
        "package_name_override",
        "package_version_mode",
        "package_version_padding",
        "target_platform",
        "material_profile",
        "triangle_budget",
        "mesh_prefix",
        "texture_root",
        "texture_set_token",
        "texture_prefix",
        "nanite_policy",
        "static_mesh_lod_group",
        "static_mesh_lod_import_policy",
        "virtual_texture_policy",
        "texture_streaming_policy",
        "texture_group",
    ]
    for key in keys:
        label, ue_interface = PROJECT_SETTINGS_LABELS.get(key, (key, ""))
        rows.append(
            {
                "key": key,
                "label": label,
                "value": active.get(key, ""),
                "ue_interface": ue_interface,
            }
        )
    return rows


def format_project_settings_summary(settings, max_rows=10):
    active = normalize_project_settings(settings)
    header = "项目预设：{0} | v{1} | {2}".format(
        active.get("preset_name", ""),
        active.get("preset_version", ""),
        active.get("updated_at") or "未保存",
    )
    lines = [header]
    for row in project_settings_rows(active)[: int(max_rows or 10)]:
        value = row.get("value", "")
        if value in (None, ""):
            value = "未设置"
        lines.append("{0}: {1}".format(row.get("label", ""), value))
    return "\n".join(lines)


def normalize_project_settings_path(path):
    active = (path or "").strip()
    root, extension = os.path.splitext(active)
    if extension == ".*":
        return root + ".json"
    if extension.lower() != ".json":
        return active + ".json"
    return active
