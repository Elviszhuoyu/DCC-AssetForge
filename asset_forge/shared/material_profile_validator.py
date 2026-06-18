"""Validation helpers for Material Profile texture coverage."""

from __future__ import absolute_import

import os

from asset_forge.shared.constants import CHECK_STATUS_INFO, CHECK_STATUS_PASS, CHECK_STATUS_WARNING
from asset_forge.shared.material_profile_schema import resolve_material_profile


SUPPORTED_TEXTURE_EXTENSIONS = set([".png", ".tga", ".tif", ".tiff", ".exr"])
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
        "dust_or_grime",
        "edge_wear",
        "scratches",
        "stain",
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


def validate_material_texture_quality(material_profile, textures):
    """Validate texture quality metadata from manifest/profile without heavy image deps."""
    profile = resolve_material_profile(material_profile)
    textures = list(textures or [])
    rule_lookup = dict((rule.get("usage", ""), rule) for rule in profile.get("texture_rules", []))
    checks = []
    checks.extend(_texture_count_checks(profile, textures))
    for texture in textures:
        rule = rule_lookup.get(texture.get("usage", ""))
        checks.extend(_texture_file_checks(texture, rule))
        checks.extend(_texture_dimension_checks(texture))
        checks.extend(_texture_profile_expectation_checks(texture, rule))

    if not checks:
        checks.append(
            {
                "id": "texture_quality",
                "label": "贴图质量",
                "status": CHECK_STATUS_INFO,
                "message": "manifest 中没有可检查的贴图条目",
            }
        )

    warnings = [item for item in checks if item.get("status") == CHECK_STATUS_WARNING]
    return {
        "status": CHECK_STATUS_WARNING if warnings else CHECK_STATUS_PASS,
        "profile": profile.get("name", ""),
        "check_count": len(checks),
        "checks": checks,
        "warning_count": len(warnings),
        "warning_usages": [item.get("usage", "") for item in warnings if item.get("usage")],
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


def _texture_count_checks(profile, textures):
    checks = []
    grouped_textures = _texture_count_groups(textures)

    for group_name, group_textures in grouped_textures:
        usage_counts = {}
        for texture in group_textures:
            usage = texture.get("usage", "unknown")
            usage_counts[usage] = usage_counts.get(usage, 0) + 1

        for rule in profile.get("texture_rules", []):
            usage = rule.get("usage", "")
            count = usage_counts.get(usage, 0)
            if rule.get("required", False) and count == 0:
                checks.append(_texture_check("texture_count", CHECK_STATUS_WARNING, usage, "", "缺少必需贴图数量：{0}".format(usage), count=count, texture_set=group_name))
            elif count > 1:
                checks.append(_texture_check("texture_count", CHECK_STATUS_WARNING, usage, "", "同一 usage 匹配到多张贴图：{0}".format(usage), count=count, texture_set=group_name))
            elif count == 1:
                checks.append(_texture_check("texture_count", CHECK_STATUS_PASS, usage, "", "贴图数量符合 profile：{0}".format(usage), count=count, texture_set=group_name))
    return checks


def _texture_count_groups(textures):
    groups = {}
    unnamed = []
    for texture in textures or []:
        group = texture.get("selected_texture_set", "") or texture.get("texture_set", "")
        if group:
            groups.setdefault(group, []).append(texture)
        else:
            unnamed.append(texture)
    if groups:
        for texture in unnamed:
            groups.setdefault("__unbound__", []).append(texture)
        return sorted(groups.items(), key=lambda item: item[0])
    return [("", list(textures or []))]


def _texture_file_checks(texture, rule):
    path = _texture_path(texture)
    usage = texture.get("usage", "unknown")
    checks = []
    extension = os.path.splitext(path)[1].lower()
    if not path:
        checks.append(_texture_check("texture_format", CHECK_STATUS_WARNING, usage, path, "贴图路径为空，无法检查格式"))
        return checks
    if extension in SUPPORTED_TEXTURE_EXTENSIONS:
        checks.append(_texture_check("texture_format", CHECK_STATUS_PASS, usage, path, "贴图格式可用于 UE 导入：{0}".format(extension)))
    else:
        checks.append(_texture_check("texture_format", CHECK_STATUS_WARNING, usage, path, "贴图格式不在推荐列表：{0}".format(extension or "无扩展名")))

    suffixes = [suffix.lower() for suffix in (rule or {}).get("suffixes", [])]
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    if not suffixes:
        checks.append(_texture_check("texture_naming", CHECK_STATUS_INFO, usage, path, "profile 未配置命名后缀，跳过命名检查"))
    elif any(stem.endswith(suffix.lower()) for suffix in suffixes):
        checks.append(_texture_check("texture_naming", CHECK_STATUS_PASS, usage, path, "贴图命名后缀符合 profile：{0}".format(usage)))
    else:
        checks.append(_texture_check("texture_naming", CHECK_STATUS_WARNING, usage, path, "贴图命名后缀不符合 profile：{0}".format(usage)))
    return checks


def _texture_dimension_checks(texture):
    path = _texture_path(texture)
    usage = texture.get("usage", "unknown")
    width, height = _texture_dimensions(texture)
    if not width or not height:
        return [_texture_check("texture_dimensions", CHECK_STATUS_INFO, usage, path, "manifest 未记录贴图尺寸，跳过尺寸检查")]
    if width <= 0 or height <= 0:
        return [_texture_check("texture_dimensions", CHECK_STATUS_WARNING, usage, path, "贴图尺寸无效：{0}x{1}".format(width, height), width=width, height=height)]
    if not _is_power_of_two(width) or not _is_power_of_two(height):
        return [_texture_check("texture_dimensions", CHECK_STATUS_WARNING, usage, path, "贴图尺寸建议使用 2 的幂：{0}x{1}".format(width, height), width=width, height=height)]
    return [_texture_check("texture_dimensions", CHECK_STATUS_PASS, usage, path, "贴图尺寸为 2 的幂：{0}x{1}".format(width, height), width=width, height=height)]


def _texture_profile_expectation_checks(texture, rule):
    if not rule:
        return [
            _texture_check(
                "texture_profile_rule",
                CHECK_STATUS_WARNING,
                texture.get("usage", "unknown"),
                _texture_path(texture),
                "Material Profile 未定义此贴图 usage：{0}".format(texture.get("usage", "unknown")),
            )
        ]

    checks = []
    path = _texture_path(texture)
    usage = texture.get("usage", "unknown")
    for key, label in [("srgb", "sRGB"), ("compression", "Compression")]:
        expected = rule.get(key)
        actual = texture.get(key)
        if actual is None or actual == "":
            checks.append(_texture_check("texture_" + key, CHECK_STATUS_INFO, usage, path, "manifest 未记录 {0}，导入时将使用 profile 预期值".format(label), expected=expected))
        elif actual == expected:
            checks.append(_texture_check("texture_" + key, CHECK_STATUS_PASS, usage, path, "{0} 与 profile 一致".format(label), expected=expected, actual=actual))
        else:
            checks.append(_texture_check("texture_" + key, CHECK_STATUS_WARNING, usage, path, "{0} 与 profile 不一致：预期 {1}，实际 {2}".format(label, expected, actual), expected=expected, actual=actual))
    return checks


def _texture_path(texture):
    return (texture.get("package_path") or texture.get("source_path") or texture.get("path") or "").replace("\\", "/")


def _texture_dimensions(texture):
    if texture.get("width") and texture.get("height"):
        return int(texture.get("width")), int(texture.get("height"))
    dimensions = texture.get("dimensions") or texture.get("size")
    if isinstance(dimensions, (list, tuple)) and len(dimensions) >= 2:
        return int(dimensions[0]), int(dimensions[1])
    if isinstance(dimensions, dict):
        return int(dimensions.get("width", 0)), int(dimensions.get("height", 0))
    return 0, 0


def _is_power_of_two(value):
    return value > 0 and (value & (value - 1)) == 0


def _texture_check(check_id, status, usage, path, message, **extra):
    data = {
        "id": check_id,
        "label": "贴图质量",
        "status": status,
        "usage": usage,
        "path": path,
        "message": message,
    }
    data.update(extra)
    return data
