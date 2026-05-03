"""Project Material Profile schema for texture and material standards."""

from __future__ import absolute_import

import io
import json

from asset_forge.shared.constants import (
    ASSET_TYPE_PROPS,
    RENDER_MODE_MASKED,
    RENDER_MODE_OPAQUE,
    RENDER_MODE_TRANSLUCENT,
)


MATERIAL_PROFILE_VERSION = "0.1"

REQUIRED_PROFILE_FIELDS = [
    "version",
    "name",
    "asset_family",
    "render_mode",
    "master_material",
    "material_instance_dir",
    "texture_dir",
    "texture_rules",
    "scalar_parameters",
]

REQUIRED_TEXTURE_RULE_FIELDS = [
    "usage",
    "parameter",
    "suffixes",
    "srgb",
]


def create_material_profile(
    name,
    asset_family,
    render_mode,
    master_material,
    texture_rules,
    **kwargs
):
    """Create a serializable project material profile."""
    return {
        "version": kwargs.get("version", MATERIAL_PROFILE_VERSION),
        "name": name,
        "display_name": kwargs.get("display_name", name),
        "asset_family": asset_family,
        "render_mode": render_mode,
        "master_material": master_material,
        "material_instance_dir": kwargs.get("material_instance_dir", "{target_path}/Materials"),
        "texture_dir": kwargs.get("texture_dir", "{target_path}/Textures"),
        "texture_rules": texture_rules,
        "scalar_parameters": kwargs.get("scalar_parameters", {}),
        "supports": kwargs.get("supports", {}),
    }


def validate_material_profile(profile):
    """Return schema issues for one material profile."""
    issues = []
    if not isinstance(profile, dict):
        return ["material profile must be a dict"]

    for field in REQUIRED_PROFILE_FIELDS:
        if field not in profile:
            issues.append("missing field: {0}".format(field))

    if profile.get("texture_rules") is not None and not isinstance(profile.get("texture_rules"), list):
        issues.append("texture_rules must be a list")

    if profile.get("scalar_parameters") is not None and not isinstance(profile.get("scalar_parameters"), dict):
        issues.append("scalar_parameters must be a dict")

    for index, rule in enumerate(profile.get("texture_rules", [])):
        issues.extend(_validate_texture_rule(rule, index))

    return issues


def validate_material_profiles(profiles):
    """Return schema issues for a material profile collection."""
    issues = []
    if not isinstance(profiles, dict):
        return ["material profiles must be a dict"]

    profile_items = profiles.get("profiles")
    if not isinstance(profile_items, list):
        return ["profiles must be a list"]

    seen_names = set()
    for index, profile in enumerate(profile_items):
        for issue in validate_material_profile(profile):
            issues.append("profiles[{0}]: {1}".format(index, issue))
        name = profile.get("name") if isinstance(profile, dict) else ""
        if name in seen_names:
            issues.append("duplicate profile name: {0}".format(name))
        elif name:
            seen_names.add(name)

    return issues


def get_default_material_profiles():
    """Return built-in Material Profiles for the first UE Props pipeline."""
    return {
        "version": MATERIAL_PROFILE_VERSION,
        "profiles": [
            _props_opaque_profile(),
            _props_masked_profile(),
            _props_translucent_profile(),
        ],
    }


def get_default_material_profile(name):
    for profile in get_default_material_profiles()["profiles"]:
        if profile["name"] == name:
            return profile
    return None


def write_material_profiles(path, profiles, pretty=True):
    indent = 2 if pretty else None
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(profiles, ensure_ascii=False, indent=indent))
        stream.write("\n")
    return path


def read_material_profiles(path):
    with io.open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def _validate_texture_rule(rule, index):
    issues = []
    if not isinstance(rule, dict):
        return ["texture_rules[{0}] must be a dict".format(index)]

    for field in REQUIRED_TEXTURE_RULE_FIELDS:
        if field not in rule:
            issues.append("texture_rules[{0}] missing field: {1}".format(index, field))

    suffixes = rule.get("suffixes")
    if suffixes is not None and not isinstance(suffixes, list):
        issues.append("texture_rules[{0}] suffixes must be a list".format(index))

    channels = rule.get("channels")
    if channels is not None and not isinstance(channels, dict):
        issues.append("texture_rules[{0}] channels must be a dict".format(index))

    return issues


def _common_props_texture_rules():
    return [
        {
            "usage": "base_color",
            "parameter": "BaseColor",
            "suffixes": ["_BaseColor", "_BC", "_Albedo"],
            "srgb": True,
            "compression": "default",
            "required": True,
        },
        {
            "usage": "normal",
            "parameter": "Normal",
            "suffixes": ["_Normal", "_N"],
            "srgb": False,
            "compression": "normalmap",
            "required": True,
        },
        {
            "usage": "packed_arm",
            "parameter": "ARM",
            "suffixes": ["_ARM", "_ORM"],
            "srgb": False,
            "compression": "masks",
            "required": False,
            "channels": {"r": "ao", "g": "roughness", "b": "metallic"},
        },
        {
            "usage": "emissive",
            "parameter": "Emissive",
            "suffixes": ["_Emissive", "_E"],
            "srgb": True,
            "compression": "default",
            "required": False,
        },
    ]


def _props_opaque_profile():
    return create_material_profile(
        "Props_Opaque_PainterUE_ARM",
        ASSET_TYPE_PROPS,
        RENDER_MODE_OPAQUE,
        "/Game/AssetForge/Materials/M_AF_Props_Opaque",
        _common_props_texture_rules(),
        display_name="Props Opaque - Painter UE ARM",
        supports={"emissive": True, "opacity_mask": False, "translucency": False},
        scalar_parameters={
            "RoughnessIntensity": 1.0,
            "MetallicIntensity": 1.0,
            "EmissiveIntensity": 1.0,
        },
    )


def _props_masked_profile():
    rules = _common_props_texture_rules() + [
        {
            "usage": "opacity_mask",
            "parameter": "OpacityMask",
            "suffixes": ["_Mask", "_Opacity", "_OpacityMask"],
            "srgb": False,
            "compression": "masks",
            "required": True,
        }
    ]
    return create_material_profile(
        "Props_Masked_PainterUE_ARM",
        ASSET_TYPE_PROPS,
        RENDER_MODE_MASKED,
        "/Game/AssetForge/Materials/M_AF_Props_Masked",
        rules,
        display_name="Props Masked - Painter UE ARM",
        supports={"emissive": True, "opacity_mask": True, "translucency": False},
        scalar_parameters={"OpacityClipValue": 0.333, "EmissiveIntensity": 1.0},
    )


def _props_translucent_profile():
    rules = _common_props_texture_rules() + [
        {
            "usage": "opacity",
            "parameter": "Opacity",
            "suffixes": ["_Opacity", "_Alpha"],
            "srgb": False,
            "compression": "masks",
            "required": False,
        }
    ]
    return create_material_profile(
        "Props_Translucent_PainterUE_ARM",
        ASSET_TYPE_PROPS,
        RENDER_MODE_TRANSLUCENT,
        "/Game/AssetForge/Materials/M_AF_Props_Translucent",
        rules,
        display_name="Props Translucent - Painter UE ARM",
        supports={"emissive": True, "opacity_mask": False, "translucency": True},
        scalar_parameters={"OpacityIntensity": 1.0, "EmissiveIntensity": 1.0},
    )
