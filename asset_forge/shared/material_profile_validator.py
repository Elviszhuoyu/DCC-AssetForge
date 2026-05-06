"""Validation helpers for Material Profile texture coverage."""

from __future__ import absolute_import

from asset_forge.shared.constants import CHECK_STATUS_PASS, CHECK_STATUS_WARNING
from asset_forge.shared.material_profile_schema import resolve_material_profile


ALLOWED_CHANNEL_MEANINGS = set(
    [
        "ao",
        "ambient_occlusion",
        "roughness",
        "metallic",
        "opacity",
        "opacity_mask",
        "mask",
        "emissive",
    ]
)
PACKED_ARM_EXPECTED = {"r": "ao", "g": "roughness", "b": "metallic"}


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


def validate_packed_texture_channel_rules(material_profile):
    """Validate packed texture channel mapping rules such as ARM or ORM."""
    profile = resolve_material_profile(material_profile)
    checks = []
    for rule in profile.get("texture_rules", []):
        channels = rule.get("channels")
        if not channels:
            continue
        checks.extend(_channel_checks(rule, channels))
    if not checks:
        checks.append(
            {
                "id": "packed_channel_rules",
                "label": "通道规则",
                "status": CHECK_STATUS_PASS,
                "message": "未配置打包贴图通道规则，跳过校验",
            }
        )
    warnings = [item for item in checks if item.get("status") == CHECK_STATUS_WARNING]
    return {
        "status": CHECK_STATUS_WARNING if warnings else CHECK_STATUS_PASS,
        "profile": profile.get("name", ""),
        "checks": checks,
        "warning_usages": [item.get("usage", "") for item in warnings],
    }


def _channel_checks(rule, channels):
    checks = []
    usage = rule.get("usage", "")
    normalized = dict((str(key).lower(), str(value).lower()) for key, value in channels.items())
    for channel, meaning in normalized.items():
        if channel not in ("r", "g", "b", "a"):
            checks.append(_channel_check(rule, CHECK_STATUS_WARNING, "未知通道：{0}".format(channel)))
        elif meaning not in ALLOWED_CHANNEL_MEANINGS:
            checks.append(_channel_check(rule, CHECK_STATUS_WARNING, "未知通道语义：{0}={1}".format(channel.upper(), meaning)))

    if usage == "packed_arm":
        for channel, meaning in PACKED_ARM_EXPECTED.items():
            if normalized.get(channel) != meaning:
                checks.append(_channel_check(rule, CHECK_STATUS_WARNING, "ARM 通道建议为 R=AO、G=Roughness、B=Metallic"))
                break

    if not checks:
        checks.append(_channel_check(rule, CHECK_STATUS_PASS, "打包贴图通道规则有效"))
    return checks


def _channel_check(rule, status, message):
    return {
        "id": "packed_channel_rule",
        "label": "打包贴图通道",
        "status": status,
        "usage": rule.get("usage", ""),
        "parameter": rule.get("parameter", ""),
        "channels": dict(rule.get("channels", {})),
        "message": message,
    }
