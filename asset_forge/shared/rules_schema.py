# -*- coding: utf-8 -*-
"""Default executable rule schema for DCC AssetForge 0.1."""

from __future__ import absolute_import, unicode_literals

import io
import json
import os

from asset_forge.shared.constants import (
    ASSET_TYPE_STATIC_PROP,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    TARGET_PLATFORM_HIGH_END_MOBILE,
    TARGET_PLATFORM_MOBILE,
    TARGET_PLATFORM_PC,
)


DEFAULT_RULES = {
    ASSET_TYPE_STATIC_PROP: {
        "name_prefix": "SM_",
        "collision_prefixes": ["UCX_", "UBX_", "USP_", "UCP_"],
        "max_triangles": {
            TARGET_PLATFORM_PC: 50000,
            TARGET_PLATFORM_HIGH_END_MOBILE: 15000,
            TARGET_PLATFORM_MOBILE: 8000,
        },
        "max_material_slots": {
            TARGET_PLATFORM_PC: 5,
            TARGET_PLATFORM_HIGH_END_MOBILE: 3,
            TARGET_PLATFORM_MOBILE: 2,
        },
        "require_uv0": True,
        "require_lightmap_uv": True,
        "require_frozen_transform": True,
        "allow_warning_export": True,
        "block_export_on_error": True,
        "scoring": {
            "error_penalty": 20,
            "warning_penalty": 8,
            "min_score": 0,
        },
        "checks": [
            {
                "id": "name_prefix",
                "label": "命名规范",
                "severity": SEVERITY_ERROR,
                "enabled": True,
            },
            {
                "id": "mesh_exists",
                "label": "Mesh 存在",
                "severity": SEVERITY_ERROR,
                "enabled": True,
            },
            {"id": "zero_area_triangles", "label": "零面积三角形", "severity": SEVERITY_WARNING, "enabled": True},
            {"id": "zero_length_edges", "label": "零长度边", "severity": SEVERITY_WARNING, "enabled": True},
            {
                "id": "empty_mesh",
                "label": "空 Mesh",
                "severity": SEVERITY_ERROR,
                "enabled": True,
            },
            {
                "id": "frozen_transform",
                "label": "冻结变换",
                "severity": SEVERITY_ERROR,
                "enabled": True,
            },
            {
                "id": "illegal_scale",
                "label": "非法缩放",
                "severity": SEVERITY_ERROR,
                "enabled": True,
            },
            {
                "id": "triangle_budget",
                "label": "三角面预算",
                "severity": SEVERITY_WARNING,
                "enabled": True,
            },
            {
                "id": "material_slots",
                "label": "材质插槽",
                "severity": SEVERITY_WARNING,
                "enabled": True,
            },
            {
                "id": "uv0",
                "label": "UV0",
                "severity": SEVERITY_ERROR,
                "enabled": True,
            },
            {
                "id": "lightmap_uv",
                "label": "Lightmap UV",
                "severity": SEVERITY_WARNING,
                "enabled": True,
            },
            {
                "id": "hidden_objects",
                "label": "隐藏对象",
                "severity": SEVERITY_WARNING,
                "enabled": True,
            },
            {
                "id": "history_nodes",
                "label": "历史节点",
                "severity": SEVERITY_WARNING,
                "enabled": True,
            },
            {
                "id": "collision_naming",
                "label": "Collision naming",
                "severity": SEVERITY_WARNING,
                "enabled": True,
            },
        ],
    }
}


def get_default_rules():
    """Return a copy of the default rules."""
    rules = {}
    for asset_type, asset_rules in DEFAULT_RULES.items():
        copied = {}
        for key, value in asset_rules.items():
            if isinstance(value, dict):
                copied[key] = dict(value)
            elif isinstance(value, list):
                copied[key] = [dict(item) if isinstance(item, dict) else item for item in value]
            else:
                copied[key] = value
        rules[asset_type] = copied
    return rules


def get_project_rules(config_path=None):
    """Return project rules from config/project_rules.json when available."""
    path = config_path or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config", "project_rules.json"))
    if not os.path.exists(path):
        return get_default_rules()
    with io.open(path, "r", encoding="utf-8") as stream:
        data = json.load(stream)
    return _merge_rules(get_default_rules(), data)


def _merge_rules(default_rules, override_rules):
    result = get_default_rules()
    for asset_type, override in (override_rules or {}).items():
        base = result.setdefault(asset_type, {})
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                merged = dict(base[key])
                merged.update(value)
                base[key] = merged
            else:
                base[key] = value
    return result
