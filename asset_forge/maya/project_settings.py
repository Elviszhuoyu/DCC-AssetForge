# -*- coding: utf-8 -*-
"""Project-level DCC settings for DCC AssetForge."""

from __future__ import absolute_import, unicode_literals

import io
import json
import os
import re
from datetime import datetime

from asset_forge.shared.constants import ASSET_TYPE_STATIC_PROP, TARGET_PLATFORM_PC
from asset_forge.shared.package_naming import PACKAGE_VERSION_MODE_OVERWRITE, normalize_package_version_mode
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.rules_schema import get_project_rules
from asset_forge.shared.python_compat import to_text, write_utf8_json
from asset_forge.shared.unreal_path import sanitize_unreal_package_path


PROJECT_SETTINGS_VERSION = "0.3"
NORMAL_FORMAT_LABELS = {"directx": "DirectX（UE 默认）", "opengl": "OpenGL"}
SETTING_VALUE_LABELS = {
    "project_default": "跟随项目默认", "overwrite": "覆盖现有包体", "auto_increment": "自动递增版本",
    "enable": "启用", "disable": "禁用", "report_only": "仅记录",
    "import_existing": "导入现有 LOD", "ignore_lods": "忽略 LOD",
    "force_on": "强制开启", "force_off": "强制关闭", "auto": "自动",
    "streaming": "流送", "never_stream": "不流送",
}

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
    "texture_set_token": ("贴图名筛选词", "dcc.texture_set_token"),
    "triangle_budget": ("三角面最大上限", "asset_forge.validation.triangle_budget"),
    "material_slot_budget": ("材质槽最大上限", "asset_forge.validation.material_slot_budget"),
    "normal_format": ("法线坐标格式", "ue.texture.normal_format"),
    "mesh_prefix": ("模型前缀", "asset_forge.naming.mesh_prefix"),
    "texture_prefix": ("贴图前缀", "asset_forge.naming.texture_prefix"),
    "ue_target_path": ("UE 目标路径", "ue.target_path"),
    "target_engine_version": ("目标 UE 版本", "ue.target_engine_version"),
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
    "target_engine_version",
    "export_root",
    "package_name_override",
    "package_version_mode",
    "package_version_padding",
    "target_platform",
    "material_profile",
    "triangle_budget",
    "material_slot_budget",
    "normal_format",
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
    "material_slot_budget": None,
    "normal_format": "directx",
    "mesh_prefix": "SM_",
    "texture_prefix": "T_",
    "texture_set_token": "",
    "package_name_override": "",
    "asset_name_override": "",
    "package_version_mode": PACKAGE_VERSION_MODE_OVERWRITE,
    "package_version_padding": 3,
    "package_version_start": 1,
    "ue_target_path": "/Game/Props",
    "target_engine_version": "",
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


def normalize_normal_format(value):
    return "opengl" if to_text(value or "").strip().lower() == "opengl" else "directx"


def apply_rule_settings(rules, platform, name_prefix, triangle_budget=0, material_slot_budget=0):
    result = dict(rules or {})
    static = dict(result.get(ASSET_TYPE_STATIC_PROP, {}))
    for key, limit in (("max_triangles", triangle_budget), ("max_material_slots", material_slot_budget)):
        budgets = dict(static.get(key, {}))
        if limit > 0:
            budgets[platform] = limit
        static[key] = budgets
    static["name_prefix"] = name_prefix
    result[ASSET_TYPE_STATIC_PROP] = static
    return result


def normalize_project_settings(data):
    result = default_project_settings()
    result.update(data or {})
    result["schema"] = "asset_forge_project_preset"
    result["version"] = to_text(result.get("version") or PROJECT_SETTINGS_VERSION)
    result["preset_name"] = to_text(result.get("preset_name") or "AssetForge_Default_StaticProp")
    result["preset_version"] = to_text(result.get("preset_version") or "1")
    result["updated_at"] = to_text(result.get("updated_at") or "")
    result["export_root"] = normalize_path(result.get("export_root", ""))
    result["texture_root"] = normalize_path(result.get("texture_root", ""))
    result["triangle_budget"] = int(result.get("triangle_budget") or 0)
    result["mesh_prefix"] = to_text(result.get("mesh_prefix") or "SM_")
    result["texture_prefix"] = to_text(result.get("texture_prefix") or "T_")
    result["texture_set_token"] = to_text(result.get("texture_set_token") or result.get("texture_set_selection") or "")
    package_name = to_text(
        result.get("package_name_override")
        or result.get("package_name")
        or result.get("asset_name_override")
        or result.get("export_asset_name")
        or ""
    )
    result["package_name_override"] = package_name
    # Old presets sometimes used asset_name_override as the package/folder name.
    # Keep it as a migration input above, but do not let a package name rename meshes.
    result["asset_name_override"] = to_text(result.get("asset_name_override") or "")
    result["package_version_mode"] = normalize_package_version_mode(result.get("package_version_mode"))
    result["package_version_padding"] = _positive_int(result.get("package_version_padding"), 3)
    result["package_version_start"] = _positive_int(result.get("package_version_start"), 1)
    result["ue_target_path"] = sanitize_unreal_package_path(result.get("ue_target_path") or "/Game/Props")
    engine_version = to_text(result.get("target_engine_version") or "").strip()
    if engine_version and not re.match(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?\Z", engine_version):
        raise ValueError("目标 UE 版本应为数字版本号，例如 5.6 或 5.8。")
    result["target_engine_version"] = engine_version
    result["target_platform"] = to_text(result.get("target_platform") or TARGET_PLATFORM_PC)
    limit = result.get("material_slot_budget")
    if limit is None:
        budgets = get_project_rules()[ASSET_TYPE_STATIC_PROP].get("max_material_slots", {})
        limit = budgets.get(result["target_platform"], 0)
    result["material_slot_budget"] = max(0, int(limit))
    result["normal_format"] = normalize_normal_format(result.get("normal_format"))
    result["material_profile"] = to_text(result.get("material_profile") or "Props_Opaque_PainterUE_ARM")
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
    result["texture_group"] = to_text(result.get("texture_group") or "project_default")
    result["nanite_policy"] = _choice(
        result.get("nanite_policy"),
        ["project_default", "enable", "disable", "report_only"],
        "project_default",
    )
    result["static_mesh_lod_group"] = to_text(result.get("static_mesh_lod_group") or "project_default")
    result["static_mesh_lod_import_policy"] = _choice(
        result.get("static_mesh_lod_import_policy"),
        ["project_default", "import_existing", "ignore_lods", "report_only"],
        "import_existing",
    )
    result["build_reversed_index_buffer"] = to_text(result.get("build_reversed_index_buffer") or "report_only")
    result["generate_lightmap_uvs"] = to_text(result.get("generate_lightmap_uvs") or "report_only")
    result["collision_complexity"] = to_text(result.get("collision_complexity") or "report_only")
    return result


def _choice(value, allowed, default):
    value = to_text(value or default)
    return value if value in allowed else default


def _positive_int(value, default):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    return max(1, number)


def load_project_settings(path):
    with io.open(path, "r", encoding="utf-8") as stream:
        data = json.load(stream)
    if to_text(path).lower().endswith(".assetforge.json"):
        if not isinstance(data, dict) or data.get("schema") != "asset_forge_project_preset":
            raise ValueError("场景预设缺少 asset_forge_project_preset 标识")
        for key in ("texture_root", "export_root"):
            if data.get(key):
                data[key] = os.path.join(os.path.dirname(os.path.abspath(path)), data[key])
    return normalize_project_settings(data)


def save_project_settings(path, settings):
    path = normalize_project_settings_path(path)
    active = normalize_project_settings(settings)
    active["updated_at"] = datetime.now().replace(microsecond=0).isoformat()
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    write_utf8_json(path, active, indent=2, sort_keys=True)
    return normalize_path(path)


def project_settings_rows(settings, include_all=False):
    """Return table-like preset rows for DCC UI status blocks."""
    active = normalize_project_settings(settings)
    rows = []
    keys = PROJECT_SETTINGS_EXPORT_KEYS if include_all else [
        "preset_name",
        "preset_version",
        "ue_target_path",
        "target_engine_version",
        "export_root",
        "package_name_override",
        "package_version_mode",
        "package_version_padding",
        "target_platform",
        "material_profile",
        "triangle_budget",
        "material_slot_budget",
        "normal_format",
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
    rows = project_settings_rows(active)
    priority = ("mesh_prefix", "texture_prefix", "triangle_budget", "material_slot_budget")
    by_key = {row["key"]: row for row in rows}
    rows = [by_key[key] for key in priority] + [row for row in rows if row["key"] not in priority]
    for row in rows[: int(max_rows or 10)]:
        value = row.get("value", "")
        if row["key"] == "normal_format":
            value = NORMAL_FORMAT_LABELS.get(value, value)
        if row["key"] in ("package_version_mode", "nanite_policy", "virtual_texture_policy", "texture_group",
                          "static_mesh_lod_group", "static_mesh_lod_import_policy", "texture_streaming_policy"):
            value = SETTING_VALUE_LABELS.get(value, value)
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
