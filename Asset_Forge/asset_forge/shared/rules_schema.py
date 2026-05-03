"""Default executable rule schema for Asset Forge v0.1."""

from __future__ import absolute_import

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
        "checks": [
            {
                "id": "name_prefix",
                "label": "命名规范",
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

