"""Validation helpers for Material Profile texture coverage."""

from __future__ import absolute_import

from asset_forge.shared.constants import CHECK_STATUS_PASS, CHECK_STATUS_WARNING
from asset_forge.shared.material_profile_schema import resolve_material_profile


def validate_material_texture_coverage(material_profile, textures):
    """Return warnings when required profile texture usages are not present."""
    profile = resolve_material_profile(material_profile)
    usages = set(texture.get("usage", "") for texture in (textures or []))
    checks = []
    for rule in profile.get("texture_rules", []):
        if not rule.get("required", False):
            continue
        usage = rule.get("usage", "")
        passed = usage in usages
        checks.append(
            {
                "id": "required_texture",
                "label": "必需贴图",
                "status": CHECK_STATUS_PASS if passed else CHECK_STATUS_WARNING,
                "usage": usage,
                "parameter": rule.get("parameter", ""),
                "message": "已找到必需贴图：{0}".format(usage) if passed else "缺少必需贴图：{0}".format(usage),
            }
        )
    warnings = [item for item in checks if item.get("status") == CHECK_STATUS_WARNING]
    return {
        "status": CHECK_STATUS_WARNING if warnings else CHECK_STATUS_PASS,
        "profile": profile.get("name", ""),
        "checks": checks,
        "missing_usages": [item["usage"] for item in warnings],
    }
