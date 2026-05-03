"""Default Unreal Asset Forge material package planning schema."""

from __future__ import absolute_import

from asset_forge.shared.constants import (
    ASSET_TYPE_CHARACTER,
    ASSET_TYPE_FX,
    ASSET_TYPE_PROPS,
    RENDER_MODE_MASKED,
    RENDER_MODE_OPAQUE,
    RENDER_MODE_TRANSLUCENT,
)
from asset_forge.shared.material_profile_schema import get_default_material_profiles


MATERIAL_PACKAGE_VERSION = "0.1"

DEFAULT_PACKAGE_ROOT = "/Game/AssetForge"


def get_default_material_package_plan():
    """Return the planned UE plugin content layout for Asset Forge materials."""
    return {
        "version": MATERIAL_PACKAGE_VERSION,
        "root": DEFAULT_PACKAGE_ROOT,
        "directories": [
            "/Game/AssetForge/Materials",
            "/Game/AssetForge/MaterialFunctions",
            "/Game/AssetForge/ParameterCollections",
        ],
        "materials": [
            _material(
                "M_AF_Props_Opaque",
                "/Game/AssetForge/Materials/M_AF_Props_Opaque",
                ASSET_TYPE_PROPS,
                RENDER_MODE_OPAQUE,
                ["BaseColor", "Normal", "ARM", "Emissive"],
                ["RoughnessIntensity", "MetallicIntensity", "EmissiveIntensity"],
            ),
            _material(
                "M_AF_Props_Masked",
                "/Game/AssetForge/Materials/M_AF_Props_Masked",
                ASSET_TYPE_PROPS,
                RENDER_MODE_MASKED,
                ["BaseColor", "Normal", "ARM", "Emissive", "OpacityMask"],
                ["OpacityClipValue", "EmissiveIntensity"],
            ),
            _material(
                "M_AF_Props_Translucent",
                "/Game/AssetForge/Materials/M_AF_Props_Translucent",
                ASSET_TYPE_PROPS,
                RENDER_MODE_TRANSLUCENT,
                ["BaseColor", "Normal", "ARM", "Emissive", "Opacity"],
                ["OpacityIntensity", "EmissiveIntensity"],
            ),
        ],
        "reserved_materials": [
            _reserved_material("M_AF_Character_Skin", ASSET_TYPE_CHARACTER, "skin"),
            _reserved_material("M_AF_FX_Translucent", ASSET_TYPE_FX, RENDER_MODE_TRANSLUCENT),
        ],
        "functions": [
            {
                "name": "MF_AF_UnpackARM",
                "path": "/Game/AssetForge/MaterialFunctions/MF_AF_UnpackARM",
                "purpose": "Unpack AO, Roughness, and Metallic channels from ARM or ORM textures.",
            },
            {
                "name": "MF_AF_ApplyEmissive",
                "path": "/Game/AssetForge/MaterialFunctions/MF_AF_ApplyEmissive",
                "purpose": "Apply emissive texture and intensity controls.",
            },
        ],
        "parameter_collections": [
            {
                "name": "MPC_AF_Global",
                "path": "/Game/AssetForge/ParameterCollections/MPC_AF_Global",
                "purpose": "Global project-wide controls only; per-asset textures stay on Material Instances.",
                "parameters": ["GlobalEmissiveScale"],
            }
        ],
    }


def validate_material_package_plan(plan):
    """Return structural issues for a material package plan."""
    issues = []
    if not isinstance(plan, dict):
        return ["material package plan must be a dict"]

    for field in ["version", "root", "directories", "materials", "functions", "parameter_collections"]:
        if field not in plan:
            issues.append("missing field: {0}".format(field))

    material_paths = set()
    for index, material in enumerate(plan.get("materials", [])):
        for field in ["name", "path", "asset_family", "render_mode", "texture_parameters", "scalar_parameters"]:
            if field not in material:
                issues.append("materials[{0}] missing field: {1}".format(index, field))
        path = material.get("path")
        if path in material_paths:
            issues.append("duplicate material path: {0}".format(path))
        elif path:
            material_paths.add(path)

    return issues


def material_package_paths(plan=None):
    """Return the material asset paths that should exist in UE."""
    active_plan = plan or get_default_material_package_plan()
    return [material["path"] for material in active_plan.get("materials", [])]


def profile_master_material_issues(profiles=None, plan=None):
    """Return issues when profile master materials are not in the package plan."""
    active_profiles = profiles or get_default_material_profiles()
    planned_paths = set(material_package_paths(plan))
    issues = []
    for profile in active_profiles.get("profiles", []):
        master_material = profile.get("master_material", "")
        if master_material not in planned_paths:
            issues.append(
                "profile {0} references missing master material: {1}".format(
                    profile.get("name", ""),
                    master_material,
                )
            )
    return issues


def _material(name, path, asset_family, render_mode, texture_parameters, scalar_parameters):
    return {
        "name": name,
        "path": path,
        "asset_family": asset_family,
        "render_mode": render_mode,
        "texture_parameters": texture_parameters,
        "scalar_parameters": scalar_parameters,
    }


def _reserved_material(name, asset_family, render_mode):
    return {
        "name": name,
        "asset_family": asset_family,
        "render_mode": render_mode,
        "status": "reserved",
    }
