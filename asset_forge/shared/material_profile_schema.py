# -*- coding: utf-8 -*-
"""Project Material Profile schema for texture and material standards."""

from __future__ import absolute_import, unicode_literals

import io
import json
import re

from asset_forge.shared.python_compat import text_type, write_utf8_json
import os

from asset_forge.shared.constants import (
    ASSET_TYPE_CHARACTER,
    ASSET_TYPE_ENVIRONMENT,
    ASSET_TYPE_FX,
    ASSET_TYPE_PROPS,
    RENDER_MODE_ADDITIVE,
    RENDER_MODE_MASKED,
    RENDER_MODE_OPAQUE,
    RENDER_MODE_TRANSLUCENT,
)


MATERIAL_PROFILE_VERSION = "0.1"
DEFAULT_MATERIAL_PROFILE_NAME = "Props_Opaque_PainterUE_ARM"
PROPS_PAINTER_OPAQUE_MASTER = "/AssetForge/Materials/M_AF_Props_Opaque_Master"
_LEGACY_PROPS_MASTER = "/AssetForge/Materials/M_AF_Props_Master"
NORMAL_TEXTURE_FORMATS = ("directx", "opengl")

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
        "vector_parameters": kwargs.get("vector_parameters", {}),
        "supports": kwargs.get("supports", {}),
        "master_family": kwargs.get("master_family", ""),
        "material_variants": kwargs.get("material_variants", {}),
        "material_slot_variants": kwargs.get("material_slot_variants", []),
        "enabled_material_variants": kwargs.get("enabled_material_variants", []),
        "default_import_profile": kwargs.get("default_import_profile", True),
        "require_complete_texture_sets": kwargs.get("require_complete_texture_sets", False),
        "expose_packed_channel_scalars": kwargs.get("expose_packed_channel_scalars", True),
        "allow_external_master_material": kwargs.get("allow_external_master_material", False),
        "parameter_api_mapping": kwargs.get("parameter_api_mapping", {}),
        "texture_import_policy": kwargs.get(
            "texture_import_policy",
            {"virtual_texture_policy": "project_default", "texture_streaming_policy": "project_default", "texture_group": "project_default"},
        ),
        "static_mesh_import_policy": kwargs.get(
            "static_mesh_import_policy",
            {"lod_group": "project_default", "import_lod_policy": "import_existing"},
        ),
        "material_network_status": kwargs.get("material_network_status", "generated_pbr"),
        "material_network_message": kwargs.get(
            "material_network_message",
            "UE Python bootstrap 可生成参数化 PBR 母材质网络；真实验收仍需在 UE 现场确认节点连接。",
        ),
        "packed_texture_semantics": kwargs.get("packed_texture_semantics", {"R": "ambient_occlusion", "G": "roughness", "B": "metallic"}),
    }


def material_slot_variant_map(profile):
    """Read exact source-material routes, rejecting malformed project declarations."""
    entries = profile.get("material_slot_variants", [])
    if not isinstance(entries, list):
        raise ValueError("material_slot_variants must be a list")
    variants = profile.get("material_variants", {})
    routes = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each material_slot_variants entry needs a material and a variant")
        material, key = entry.get("material"), entry.get("variant")
        if not all(isinstance(v, (str, text_type)) and v and v == v.strip() for v in (material, key)):
            raise ValueError("Material slot routes need exact, non-empty material and variant names")
        if material in routes:
            raise ValueError("Duplicate material slot variant route: {0}".format(material))
        if not isinstance(variants, dict) or key not in variants:
            raise ValueError("Undeclared material variant {0} for source material {1}".format(key, material))
        parent = variants[key]
        # Accept a long package name or its top-level Unreal object path.
        if not isinstance(parent, (str, text_type)) or not re.match(r"^/(?:[\w-]+/)+([\w-]+)(?:\.\1)?\Z", parent, re.UNICODE):
            raise ValueError("Invalid parent path for material variant {0}: {1}".format(key, parent))
        if not parent.startswith("/AssetForge/") and profile.get("allow_external_master_material") is not True:
            raise ValueError("External parent for material variant {0} requires allow_external_master_material=true".format(key))
        routes[material] = key
    return routes


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

    try:
        material_slot_variant_map(profile)
    except ValueError as exc:
        issues.append(str(exc))

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
            _props_opaque_pbr_profile(),
            _props_masked_profile(),
            _props_translucent_profile(),
            _environment_opaque_profile(),
            _environment_masked_profile(),
            _character_basic_profile(),
            _emissive_surface_profile(),
        ],
    }


def get_default_material_profile(name):
    for profile in get_default_material_profiles()["profiles"]:
        if profile["name"] == name:
            return profile
    return None


def default_material_profiles_path():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(repo_root, "config", "material_profiles.json")


def get_project_material_profiles(path=None):
    profile_path = path or default_material_profiles_path()
    if profile_path and os.path.exists(profile_path):
        return read_material_profiles(profile_path)
    return get_default_material_profiles()


def get_material_profile(name, profiles=None):
    active = profiles or get_project_material_profiles()
    for profile in active.get("profiles", []):
        if profile.get("name") == name:
            return profile
    return None


def material_profile_names(profiles=None):
    active = profiles or get_project_material_profiles()
    return [profile.get("name", "") for profile in active.get("profiles", []) if profile.get("name")]


def resolve_material_profile(profile=None, profiles=None):
    """Return a profile dict from a dict, name, or default Props Opaque fallback."""
    if isinstance(profile, dict):
        return _apply_legacy_painter_arm_coverage(profile)
    if profile:
        found = get_material_profile(profile, profiles)
        if found:
            return _apply_legacy_painter_arm_coverage(found)
    return _apply_legacy_painter_arm_coverage(
        get_material_profile(DEFAULT_MATERIAL_PROFILE_NAME, profiles) or get_default_material_profile(DEFAULT_MATERIAL_PROFILE_NAME)
    )


def _apply_legacy_painter_arm_coverage(profile):
    # Keep historical parents and project settings on published packages.
    if (
        profile.get("name") != DEFAULT_MATERIAL_PROFILE_NAME
        or profile.get("master_material") != _LEGACY_PROPS_MASTER
        or profile.get("render_mode") != RENDER_MODE_OPAQUE
    ):
        return profile
    legacy_rule = next(rule for rule in _common_props_texture_rules() if rule["usage"] == "packed_arm")
    rules = profile.get("texture_rules", [])
    if legacy_rule not in rules:
        return profile
    return dict(profile, texture_rules=[
        _require_packed_arm(rule) if rule == legacy_rule else rule for rule in rules
    ])


def _require_packed_arm(rule):
    return dict(rule, required=True, missing_severity="warning")


def write_material_profiles(path, profiles, pretty=True):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent)
    indent = 2 if pretty else None
    write_utf8_json(path, profiles, indent=indent)
    return path


def read_material_profiles(path):
    with io.open(path, "r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def validate_material_profiles_report(profiles):
    """Return a Chinese report for project Material Profile schema checks."""
    issues = validate_material_profiles(profiles)
    checks = [
        {
            "id": "material_profile_schema",
            "status": "error",
            "message": _localize_profile_issue(issue),
            "raw": issue,
        }
        for issue in issues
    ]
    if not checks:
        checks.append(
            {
                "id": "material_profile_schema",
                "status": "pass",
                "message": "Material Profile 配置结构有效",
            }
        )
    return {
        "status": "error" if issues else "pass",
        "can_use": not issues,
        "profile_count": len(profiles.get("profiles", [])) if isinstance(profiles, dict) else 0,
        "checks": checks,
        "issues": [_localize_profile_issue(issue) for issue in issues],
    }


def export_material_profiles_config(destination_path, profiles=None):
    """Export active Material Profiles to a distributable JSON file."""
    active_profiles = profiles or get_project_material_profiles()
    validation = validate_material_profiles_report(active_profiles)
    if not validation.get("can_use", False):
        return {
            "status": "error",
            "message": "Material Profile 配置存在错误，未导出",
            "path": destination_path,
            "validation": validation,
        }
    write_material_profiles(destination_path, active_profiles)
    return {
        "status": "success",
        "message": "Material Profile 配置已导出",
        "path": os.path.abspath(destination_path).replace("\\", "/"),
        "profile_count": validation.get("profile_count", 0),
        "validation": validation,
    }


def import_material_profiles_config(source_path, target_path=None):
    """Validate and import a project Material Profile JSON file."""
    profiles = read_material_profiles(source_path)
    validation = validate_material_profiles_report(profiles)
    active_target = target_path or default_material_profiles_path()
    if not validation.get("can_use", False):
        return {
            "status": "error",
            "message": "Material Profile 配置存在错误，未导入",
            "source_path": os.path.abspath(source_path).replace("\\", "/"),
            "target_path": os.path.abspath(active_target).replace("\\", "/"),
            "validation": validation,
        }
    write_material_profiles(active_target, profiles)
    return {
        "status": "success",
        "message": "Material Profile 配置已导入",
        "source_path": os.path.abspath(source_path).replace("\\", "/"),
        "target_path": os.path.abspath(active_target).replace("\\", "/"),
        "profile_count": validation.get("profile_count", 0),
        "validation": validation,
    }


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

    if rule.get("missing_severity", "error") not in ("warning", "error"):
        issues.append("texture_rules[{0}] missing_severity must be warning or error".format(index))
    if rule.get("normal_format", "directx") not in NORMAL_TEXTURE_FORMATS:
        issues.append("texture_rules[{0}] normal_format must be directx or opengl".format(index))

    return issues


def _localize_profile_issue(issue):
    if issue == "material profiles must be a dict":
        return "Material Profile 集合必须是字典结构"
    if issue == "profiles must be a list":
        return "profiles 必须是列表"
    if issue == "material profile must be a dict":
        return "单个 Material Profile 必须是字典结构"
    if issue.startswith("duplicate profile name:"):
        return "Material Profile 名称重复：{0}".format(issue.split(":", 1)[1].strip())
    if "missing field:" in issue:
        return "缺少字段：{0}".format(issue.split("missing field:", 1)[1].strip())
    if "texture_rules must be a list" in issue:
        return "texture_rules 必须是列表"
    if "scalar_parameters must be a dict" in issue:
        return "scalar_parameters 必须是字典"
    if "suffixes must be a list" in issue:
        return "贴图规则 suffixes 必须是列表：{0}".format(issue)
    if "channels must be a dict" in issue:
        return "贴图规则 channels 必须是字典：{0}".format(issue)
    if "texture_rules" in issue and "missing field:" in issue:
        return "贴图规则缺少字段：{0}".format(issue)
    return issue


def _common_props_texture_rules():
    return [
        {
            "usage": "base_color",
            "parameter": "BaseColor",
            "suffixes": ["_BaseColor", "_Base Color", "_Base_Color", "_BC", "_B", "_Color", "_Albedo", "_Diffuse"],
            "srgb": True,
            "compression": "default",
            "required": True,
        },
        {
            "usage": "normal",
            "parameter": "Normal",
            "suffixes": ["_Normal", "_NormalMap", "_N"],
            "srgb": False,
            "compression": "normalmap",
            "normal_format": "directx",
            "required": True,
        },
        {
            "usage": "packed_arm",
            "parameter": "ARM",
            "suffixes": ["_ARM", "_ORM", "_OcclusionRoughnessMetallic", "_Occlusion_Roughness_Metallic"],
            "srgb": False,
            "compression": "masks",
            "required": False,
            "channels": {"r": "ao", "g": "roughness", "b": "metallic"},
        },
        {
            "usage": "imperfection_mask",
            "parameter": "ImperfectionMask",
            "suffixes": ["_Imperfection", "_Imperfections", "_Dirty", "_Dirt", "_Grime", "_Wear", "_EdgeWear", "_Scratches"],
            "srgb": False,
            "compression": "masks",
            "required": False,
            "channels": {"r": "dust_or_grime", "g": "edge_wear", "b": "scratches", "a": "stain"},
        },
        {
            "usage": "emissive",
            "parameter": "Emissive",
            "suffixes": ["_Emissive", "_Emission", "_Emit", "_Glow"],
            "srgb": True,
            "compression": "default",
            "required": False,
        },
        {
            "usage": "height",
            "parameter": "Height",
            "suffixes": ["_Height", "_HeightMap", "_Displacement", "_Disp", "_POM"],
            "srgb": False,
            "compression": "masks",
            "required": False,
        },
    ]


def _props_opaque_profile():
    rules = [
        _require_packed_arm(rule) if rule["usage"] == "packed_arm" else rule
        for rule in _common_props_texture_rules()
    ]
    variants = _hard_surface_variants()
    for variant in ("opaque", "opaque_vt", "emissive", "emissive_vt", "dirty_wear", "dirty_wear_vt"):
        variants[variant] = PROPS_PAINTER_OPAQUE_MASTER
    return create_material_profile(
        DEFAULT_MATERIAL_PROFILE_NAME,
        ASSET_TYPE_PROPS,
        RENDER_MODE_OPAQUE,
        PROPS_PAINTER_OPAQUE_MASTER,
        rules,
        display_name="Props Opaque - Painter UE ARM",
        supports={"emissive": True, "opacity_mask": False, "translucency": False, "imperfection_mask": True, "height": True, "pom": False},
        master_family="MM_Surface_PBR",
        material_variants=variants,
        parameter_api_mapping=_hard_surface_parameter_api_mapping(),
        scalar_parameters={
            "UVTiling": 1.0,
            "BaseColorIntensity": 1.0,
            "AOIntensity": 1.0,
            "RoughnessIntensity": 1.0,
            "RoughnessMin": 0.05,
            "RoughnessMax": 0.95,
            "MetallicIntensity": 1.0,
            "Specular": 0.5,
            "NormalStrength": 1.0,
            "ImperfectionIntensity": 0.0,
            "EdgeWearIntensity": 0.0,
        },
        vector_parameters={"BaseColorTint": [1.0, 1.0, 1.0, 1.0]},
    )


def _props_opaque_pbr_profile():
    rules = [rule for rule in _common_props_texture_rules() if rule["usage"] in ("base_color", "normal", "packed_arm")]
    for rule in rules:
        rule["required"] = True
    return create_material_profile(
        "Props_Opaque_PBR",
        ASSET_TYPE_PROPS,
        RENDER_MODE_OPAQUE,
        "/AssetForge/Materials/M_AF_Opaque_PBR",
        rules,
        display_name="Opaque PBR - Base Color, Normal, ORM",
        require_complete_texture_sets=True,
        expose_packed_channel_scalars=False,
        master_family="MM_Surface_PBR",
        scalar_parameters={
            "UVTiling": 1.0, "BaseColorIntensity": 1.0, "NormalStrength": 1.0,
            "AOIntensity": 1.0, "RoughnessIntensity": 1.0, "MetallicIntensity": 1.0, "Specular": 0.5,
        },
        vector_parameters={"BaseColorTint": [1.0, 1.0, 1.0, 1.0]},
    )


def _props_masked_profile():
    rules = _common_props_texture_rules() + [
        {
            "usage": "opacity_mask",
            "parameter": "OpacityMask",
            "suffixes": ["_Mask", "_Opacity", "_OpacityMask"],
            "srgb": False,
            "compression": "masks",
            "required": False,
        }
    ]
    return create_material_profile(
        "Props_Masked_PainterUE_ARM",
        ASSET_TYPE_PROPS,
        RENDER_MODE_MASKED,
        "/AssetForge/Materials/M_AF_Props_Master",
        rules,
        display_name="Props Masked - Painter UE ARM",
        supports={"emissive": True, "opacity_mask": True, "translucency": False, "imperfection_mask": True, "height": True, "pom": False},
        master_family="MM_Surface_PBR",
        material_variants=_hard_surface_variants(),
        parameter_api_mapping=_hard_surface_parameter_api_mapping(),
        scalar_parameters={
            "UVTiling": 1.0,
            "BaseColorIntensity": 1.0,
            "AOIntensity": 1.0,
            "RoughnessIntensity": 1.0,
            "RoughnessMin": 0.05,
            "RoughnessMax": 0.95,
            "MetallicIntensity": 1.0,
            "Specular": 0.5,
            "NormalStrength": 1.0,
            "OpacityClipValue": 0.333,
            "ImperfectionIntensity": 0.0,
            "EdgeWearIntensity": 0.0,
        },
        vector_parameters={"BaseColorTint": [1.0, 1.0, 1.0, 1.0]},
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
        "/AssetForge/Materials/M_AF_Props_Master",
        rules,
        display_name="Props Translucent - Painter UE ARM",
        supports={"emissive": True, "opacity_mask": False, "translucency": True, "imperfection_mask": True},
        master_family="MM_Surface_PBR",
        material_variants=_hard_surface_variants(),
        parameter_api_mapping=_hard_surface_parameter_api_mapping(),
        enabled_material_variants=["glass", "translucent"],
        default_import_profile=False,
        scalar_parameters={
            "UVTiling": 1.0,
            "BaseColorIntensity": 1.0,
            "AOIntensity": 1.0,
            "RoughnessIntensity": 1.0,
            "RoughnessMin": 0.05,
            "RoughnessMax": 0.95,
            "MetallicIntensity": 1.0,
            "Specular": 0.5,
            "NormalStrength": 1.0,
            "OpacityIntensity": 1.0,
            "ImperfectionIntensity": 0.0,
            "EdgeWearIntensity": 0.0,
        },
        vector_parameters={"BaseColorTint": [1.0, 1.0, 1.0, 1.0]},
    )


def _environment_opaque_profile():
    return create_material_profile(
        "Environment_Opaque_PainterUE_ARM",
        ASSET_TYPE_ENVIRONMENT,
        RENDER_MODE_OPAQUE,
        "/AssetForge/Materials/M_AF_Environment_Master",
        _common_props_texture_rules(),
        display_name="Environment Opaque - Painter UE ARM",
        supports={"emissive": True, "opacity_mask": False, "translucency": False, "imperfection_mask": True, "height": True, "pom": False},
        master_family="MM_Surface_PBR",
        material_variants=_hard_surface_variants(),
        parameter_api_mapping=_hard_surface_parameter_api_mapping(),
        scalar_parameters=_surface_scalar_defaults(),
        vector_parameters={"BaseColorTint": [1.0, 1.0, 1.0, 1.0]},
    )


def _environment_masked_profile():
    rules = _common_props_texture_rules() + [
        {
            "usage": "opacity_mask",
            "parameter": "OpacityMask",
            "suffixes": ["_Mask", "_Opacity", "_OpacityMask", "_Alpha"],
            "srgb": False,
            "compression": "masks",
            "required": False,
        }
    ]
    return create_material_profile(
        "Environment_Masked_PainterUE_ARM",
        ASSET_TYPE_ENVIRONMENT,
        RENDER_MODE_MASKED,
        "/AssetForge/Materials/M_AF_Environment_Master",
        rules,
        display_name="Environment Masked - Painter UE ARM",
        supports={"emissive": True, "opacity_mask": True, "translucency": False, "imperfection_mask": True, "height": True, "pom": False},
        master_family="MM_Surface_PBR",
        material_variants=_hard_surface_variants(),
        parameter_api_mapping=_hard_surface_parameter_api_mapping(),
        scalar_parameters=dict(_surface_scalar_defaults(), OpacityClipValue=0.333),
        vector_parameters={"BaseColorTint": [1.0, 1.0, 1.0, 1.0]},
    )


def _character_basic_profile():
    return create_material_profile(
        "Character_Basic_PainterUE_ARM",
        ASSET_TYPE_CHARACTER,
        RENDER_MODE_OPAQUE,
        "/AssetForge/Materials/M_AF_Character_Master",
        _common_props_texture_rules(),
        display_name="Character Basic - Painter UE ARM",
        supports={"emissive": False, "opacity_mask": True, "translucency": False, "imperfection_mask": False, "height": False, "pom": False},
        master_family="MM_Surface_PBR",
        material_variants=_hard_surface_variants(),
        parameter_api_mapping=_hard_surface_parameter_api_mapping(),
        scalar_parameters=dict(_surface_scalar_defaults(), SubsurfaceIntensity=0.25),
        vector_parameters={"BaseColorTint": [1.0, 1.0, 1.0, 1.0], "SubsurfaceTint": [1.0, 0.78, 0.65, 1.0]},
    )


def _emissive_surface_profile():
    rules = [
        {
            "usage": "base_color",
            "parameter": "BaseColor",
            "suffixes": ["_BaseColor", "_Color", "_Albedo", "_Diffuse"],
            "srgb": True,
            "compression": "default",
            "required": False,
        },
        {
            "usage": "emissive",
            "parameter": "Emissive",
            "suffixes": ["_Emissive", "_Emission", "_Emit", "_Glow"],
            "srgb": True,
            "compression": "default",
            "required": True,
        },
        {
            "usage": "opacity",
            "parameter": "Opacity",
            "suffixes": ["_Opacity", "_Alpha", "_Mask"],
            "srgb": False,
            "compression": "masks",
            "required": False,
        },
    ]
    return create_material_profile(
        "Emissive_Surface_PainterUE",
        ASSET_TYPE_FX,
        RENDER_MODE_ADDITIVE,
        "/AssetForge/Materials/M_AF_Props_Master",
        rules,
        display_name="Emissive Surface - Painter UE",
        supports={"emissive": True, "opacity_mask": False, "translucency": True, "imperfection_mask": False, "height": False, "pom": False},
        master_family="MM_Emissive_Effect",
        material_variants=_hard_surface_variants(),
        parameter_api_mapping=_hard_surface_parameter_api_mapping(),
        scalar_parameters={"UVTiling": 1.0, "BaseColorIntensity": 1.0, "OpacityIntensity": 1.0, "EmissiveIntensity": 2.0},
        vector_parameters={"BaseColorTint": [1.0, 1.0, 1.0, 1.0], "EmissiveTint": [1.0, 1.0, 1.0, 1.0]},
    )


def _hard_surface_variants():
    return {
        "opaque": "/AssetForge/Materials/M_AF_Props_Master",
        "opaque_vt": "/AssetForge/Materials/M_AF_Props_Master",
        "masked": "/AssetForge/Materials/M_AF_Props_Master",
        "masked_vt": "/AssetForge/Materials/M_AF_Props_Master",
        "emissive": "/AssetForge/Materials/M_AF_Props_Master",
        "emissive_vt": "/AssetForge/Materials/M_AF_Props_Master",
        "dirty_wear": "/AssetForge/Materials/M_AF_Props_Master",
        "dirty_wear_vt": "/AssetForge/Materials/M_AF_Props_Master",
        "world_aligned": "/AssetForge/Materials/M_AF_Environment_Master",
        "pom": "/AssetForge/Materials/M_AF_Environment_Master",
        "decal": "/AssetForge/Materials/M_AF_Props_Master",
        "glass": "/AssetForge/Materials/M_AF_Props_Master",
        "translucent": "/AssetForge/Materials/M_AF_Props_Master",
        "translucent_vt": "/AssetForge/Materials/M_AF_Props_Master",
        "environment": "/AssetForge/Materials/M_AF_Environment_Master",
        "environment_vt": "/AssetForge/Materials/M_AF_Environment_Master",
        "environment_masked": "/AssetForge/Materials/M_AF_Environment_Master",
        "environment_masked_vt": "/AssetForge/Materials/M_AF_Environment_Master",
        "environment_emissive": "/AssetForge/Materials/M_AF_Environment_Master",
        "environment_emissive_vt": "/AssetForge/Materials/M_AF_Environment_Master",
        "character_basic": "/AssetForge/Materials/M_AF_Character_Master",
        "character_basic_vt": "/AssetForge/Materials/M_AF_Character_Master",
        "character_masked": "/AssetForge/Materials/M_AF_Character_Master",
        "character_masked_vt": "/AssetForge/Materials/M_AF_Character_Master",
        "emissive_surface": "/AssetForge/Materials/M_AF_Props_Master",
        "emissive_surface_vt": "/AssetForge/Materials/M_AF_Props_Master",
    }


def _hard_surface_parameter_api_mapping():
    return {
        "BaseColor": "Base Color",
        "Normal": "Normal Map",
        "ARM": "Pack Map",
        "ImperfectionMask": "Imperfection Mask",
        "Emissive": "Emissive Map",
        "Opacity": "Opacity Map",
        "OpacityMask": "Opacity Map",
        "Height": "Height Map",
        "UVTiling": "UV Tile",
        "WorldAlignedScale": "World Aligned Scale",
        "ProjectionBlendSharpness": "Projection Blend Sharpness",
        "HeightScale": "Height Scale",
        "POMMinSteps": "POM Min Steps",
        "POMMaxSteps": "POM Max Steps",
        "POMTemporalAAStepMultiplier": "POM Temporal AA Step Multiplier",
        "DecalAlphaSharpness": "Decal Alpha Sharpness",
        "RefractionDepthBias": "Refraction Depth Bias",
        "SubsurfaceTint": "Subsurface Tint",
        "SubsurfaceIntensity": "Subsurface Intensity",
        "EmissiveTint": "Emissive Tint",
        "EmissiveIntensity": "Emissive Intensity",
        "OpacityIntensity": "Opacity Intensity",
        "BaseColorTint": "Tint",
        "NormalStrength": "Normal Intensity",
        "RoughnessMin": "Roughness Min",
        "RoughnessMax": "Roughness Max",
        "ImperfectionIntensity": "Imperfection Intensity",
        "EdgeWearIntensity": "Edge Wear Intensity",
    }


def _surface_scalar_defaults():
    return {
        "UVTiling": 1.0,
        "BaseColorIntensity": 1.0,
        "AOIntensity": 1.0,
        "RoughnessIntensity": 1.0,
        "RoughnessMin": 0.05,
        "RoughnessMax": 0.95,
        "MetallicIntensity": 1.0,
        "Specular": 0.5,
        "NormalStrength": 1.0,
        "ImperfectionIntensity": 0.0,
        "EdgeWearIntensity": 0.0,
    }
