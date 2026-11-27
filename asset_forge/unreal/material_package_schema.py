"""Default DCC AssetForge material package planning schema for Unreal."""

from __future__ import absolute_import

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
from asset_forge.shared.material_profile_schema import PROPS_PAINTER_OPAQUE_MASTER, get_default_material_profiles
from asset_forge.unreal.material_library import (
    AF_CHARACTER_BASIC,
    AF_ENVIRONMENT_MASTER,
    AF_PROPS_MASTER,
    PARAMETER_API_MAPPING,
    SURFACE_PBR_FAMILY,
)


MATERIAL_PACKAGE_VERSION = "0.1"

DEFAULT_PACKAGE_ROOT = "/AssetForge"


DEFAULT_TEXTURE_PATHS = {
    "base_color": "/AssetForge/Textures/T_AF_Default_BaseColor",
    "normal": "/AssetForge/Textures/T_AF_Default_Normal",
    "packed_arm": "/AssetForge/Textures/T_AF_Default_ARM",
    "opacity_mask": "/AssetForge/Textures/T_AF_Default_OpacityMask",
    "imperfection_mask": "/AssetForge/Textures/T_AF_Default_ImperfectionMask",
    "emissive": "/AssetForge/Textures/T_AF_Default_Emissive",
}


def get_default_material_package_plan():
    """Return the planned UE plugin content layout for DCC AssetForge materials."""
    return {
        "version": MATERIAL_PACKAGE_VERSION,
        "root": DEFAULT_PACKAGE_ROOT,
        "content_mount": DEFAULT_PACKAGE_ROOT,
        "disk_content_root": "Plugins/AssetForge/Content",
        "directories": [
            "/AssetForge/Materials",
            "/AssetForge/MaterialInstances",
            "/AssetForge/MaterialFunctions",
            "/AssetForge/Textures",
            "/AssetForge/ParameterCollections",
            "/AssetForge/Showcase",
        ],
        "placeholder_textures": [
            _placeholder_texture("T_AF_Default_BaseColor", DEFAULT_TEXTURE_PATHS["base_color"], "base_color", [128, 128, 128, 255], True, "default"),
            _placeholder_texture("T_AF_Default_Normal", DEFAULT_TEXTURE_PATHS["normal"], "normal", [128, 128, 255, 255], False, "normal"),
            _placeholder_texture("T_AF_Default_ARM", DEFAULT_TEXTURE_PATHS["packed_arm"], "packed_arm", [255, 128, 0, 255], False, "masks"),
            _placeholder_texture("T_AF_Default_OpacityMask", DEFAULT_TEXTURE_PATHS["opacity_mask"], "opacity_mask", [255, 255, 255, 255], False, "masks"),
            _placeholder_texture("T_AF_Default_ImperfectionMask", DEFAULT_TEXTURE_PATHS["imperfection_mask"], "imperfection_mask", [0, 0, 0, 255], False, "masks"),
            _placeholder_texture("T_AF_Default_Emissive", DEFAULT_TEXTURE_PATHS["emissive"], "emissive", [0, 0, 0, 255], True, "default"),
            _placeholder_texture("T_AF_Preview_BaseColor_AlphaGrid", "/AssetForge/Textures/T_AF_Preview_BaseColor_AlphaGrid", "base_color", [148, 162, 178, 255], True, "default", "alpha_grid"),
            _placeholder_texture("T_AF_Preview_OpacityMask_Stripes", "/AssetForge/Textures/T_AF_Preview_OpacityMask_Stripes", "opacity_mask", [255, 255, 255, 255], False, "masks", "mask_stripes"),
            _placeholder_texture("T_AF_Preview_Emissive_Panels", "/AssetForge/Textures/T_AF_Preview_Emissive_Panels", "emissive", [0, 0, 0, 255], True, "default", "emissive_panels"),
            _placeholder_texture("T_AF_Preview_Imperfection_Wear", "/AssetForge/Textures/T_AF_Preview_Imperfection_Wear", "imperfection_mask", [0, 0, 0, 255], False, "masks", "imperfection_wear"),
            _placeholder_texture("T_AF_Preview_BaseColor_MetalPanel", "/AssetForge/Textures/T_AF_Preview_BaseColor_MetalPanel", "base_color", [132, 142, 150, 255], True, "default", "metal_panel"),
            _placeholder_texture("T_AF_Preview_BaseColor_Rubber", "/AssetForge/Textures/T_AF_Preview_BaseColor_Rubber", "base_color", [24, 28, 31, 255], True, "default", "rubber"),
            _placeholder_texture("T_AF_Preview_BaseColor_TileFloor", "/AssetForge/Textures/T_AF_Preview_BaseColor_TileFloor", "base_color", [116, 122, 118, 255], True, "default", "tile_floor"),
            _placeholder_texture("T_AF_Preview_BaseColor_SkinWarm", "/AssetForge/Textures/T_AF_Preview_BaseColor_SkinWarm", "base_color", [205, 150, 120, 255], True, "default", "skin_warm"),
            _placeholder_texture("T_AF_Preview_ARM_Metal", "/AssetForge/Textures/T_AF_Preview_ARM_Metal", "packed_arm", [255, 82, 255, 255], False, "masks", "solid"),
            _placeholder_texture("T_AF_Preview_ARM_Rough", "/AssetForge/Textures/T_AF_Preview_ARM_Rough", "packed_arm", [255, 220, 0, 255], False, "masks", "solid"),
        ],
        "materials": [
            _category_material(
                "M_AF_Props_Master",
                AF_PROPS_MASTER,
                ASSET_TYPE_PROPS,
                RENDER_MODE_MASKED,
                ["BaseColor", "Normal", "ARM", "OpacityMask", "Emissive", "ImperfectionMask"],
                ["OpacityClipValue", "MaskContrast", "EmissiveIntensity", "ImperfectionIntensity"],
                {"BaseColorTint": [1.0, 1.0, 1.0, 1.0], "EmissiveTint": [1.0, 1.0, 1.0, 1.0]},
                {"UseOpacityMask": False, "UseSeparateOpacityMask": False, "UseEmissive": False},
            ),
            _category_material(
                "M_AF_Props_Opaque_Master",
                PROPS_PAINTER_OPAQUE_MASTER,
                ASSET_TYPE_PROPS,
                RENDER_MODE_OPAQUE,
                ["BaseColor", "Normal", "ARM", "Emissive", "ImperfectionMask"],
                ["EmissiveIntensity", "ImperfectionIntensity"],
                {"EmissiveTint": [1.0, 1.0, 1.0, 1.0]},
                {"UseEmissive": False},
            ),
            _category_material(
                "M_AF_Environment_Master",
                AF_ENVIRONMENT_MASTER,
                ASSET_TYPE_ENVIRONMENT,
                RENDER_MODE_MASKED,
                ["BaseColor", "Normal", "ARM", "OpacityMask", "Emissive", "ImperfectionMask"],
                [
                    "OpacityClipValue",
                    "MaskContrast",
                    "EmissiveIntensity",
                    "ImperfectionIntensity",
                ],
                {"BaseColorTint": [1.0, 1.0, 1.0, 1.0], "EmissiveTint": [1.0, 1.0, 1.0, 1.0]},
                {"UseOpacityMask": False, "UseSeparateOpacityMask": False, "UseEmissive": False},
            ),
            _category_material(
                "M_AF_Character_Master",
                AF_CHARACTER_BASIC,
                ASSET_TYPE_CHARACTER,
                RENDER_MODE_OPAQUE,
                ["BaseColor", "Normal", "ARM"],
                ["SubsurfaceIntensity"],
                {"BaseColorTint": [1.0, 1.0, 1.0, 1.0], "SubsurfaceTint": [1.0, 0.78, 0.65, 1.0]},
                {"UseSubsurface": True},
            ),
            _category_material(
                "M_AF_Opaque_PBR", "/AssetForge/Materials/M_AF_Opaque_PBR", ASSET_TYPE_PROPS,
                RENDER_MODE_OPAQUE, ["BaseColor", "Normal", "ARM"],
            ),
        ],
        "material_instances": [
            _material_instance("MI_AF_Props_Default", "/AssetForge/MaterialInstances/MI_AF_Props_Default", AF_PROPS_MASTER),
            _material_instance("MI_AF_Props_Masked", "/AssetForge/MaterialInstances/MI_AF_Props_Masked", AF_PROPS_MASTER, scalar_overrides={"OpacityClipValue": 0.333, "MaskContrast": 1.0}, static_switch_overrides={"UseOpacityMask": True}, texture_overrides={"BaseColor": "/AssetForge/Textures/T_AF_Preview_BaseColor_AlphaGrid"}),
            _material_instance("MI_AF_Props_Masked_SeparateMask", "/AssetForge/MaterialInstances/MI_AF_Props_Masked_SeparateMask", AF_PROPS_MASTER, scalar_overrides={"OpacityClipValue": 0.333, "MaskContrast": 1.0}, static_switch_overrides={"UseOpacityMask": True, "UseSeparateOpacityMask": True}, texture_overrides={"BaseColor": "/AssetForge/Textures/T_AF_Preview_BaseColor_AlphaGrid", "OpacityMask": "/AssetForge/Textures/T_AF_Preview_OpacityMask_Stripes"}),
            _material_instance("MI_AF_Props_Emissive", "/AssetForge/MaterialInstances/MI_AF_Props_Emissive", AF_PROPS_MASTER, scalar_overrides={"EmissiveIntensity": 6.0}, vector_overrides={"EmissiveTint": [1.0, 0.55, 0.12, 1.0]}, static_switch_overrides={"UseEmissive": True}, texture_overrides={"BaseColor": "/AssetForge/Textures/T_AF_Preview_BaseColor_AlphaGrid", "Emissive": "/AssetForge/Textures/T_AF_Preview_Emissive_Panels"}),
            _material_instance("MI_AF_Props_DirtyWear", "/AssetForge/MaterialInstances/MI_AF_Props_DirtyWear", AF_PROPS_MASTER, scalar_overrides={"ImperfectionIntensity": 0.75, "RoughnessIntensity": 1.25}, texture_overrides={"BaseColor": "/AssetForge/Textures/T_AF_Preview_BaseColor_AlphaGrid", "ImperfectionMask": "/AssetForge/Textures/T_AF_Preview_Imperfection_Wear"}),
            _material_instance("MI_AF_Props_MetalPanel", "/AssetForge/MaterialInstances/MI_AF_Props_MetalPanel", AF_PROPS_MASTER, scalar_overrides={"RoughnessIntensity": 0.85, "MetallicIntensity": 1.0}, texture_overrides={"BaseColor": "/AssetForge/Textures/T_AF_Preview_BaseColor_MetalPanel", "ARM": "/AssetForge/Textures/T_AF_Preview_ARM_Metal"}),
            _material_instance("MI_AF_Props_RubberMatte", "/AssetForge/MaterialInstances/MI_AF_Props_RubberMatte", AF_PROPS_MASTER, scalar_overrides={"RoughnessIntensity": 1.35, "MetallicIntensity": 0.0, "Specular": 0.35}, texture_overrides={"BaseColor": "/AssetForge/Textures/T_AF_Preview_BaseColor_Rubber", "ARM": "/AssetForge/Textures/T_AF_Preview_ARM_Rough"}),
            _material_instance("MI_AF_Environment_Default", "/AssetForge/MaterialInstances/MI_AF_Environment_Default", AF_ENVIRONMENT_MASTER),
            _material_instance("MI_AF_Environment_Masked", "/AssetForge/MaterialInstances/MI_AF_Environment_Masked", AF_ENVIRONMENT_MASTER, scalar_overrides={"OpacityClipValue": 0.333, "MaskContrast": 1.0}, static_switch_overrides={"UseOpacityMask": True}, texture_overrides={"BaseColor": "/AssetForge/Textures/T_AF_Preview_BaseColor_AlphaGrid"}),
            _material_instance("MI_AF_Environment_Masked_SeparateMask", "/AssetForge/MaterialInstances/MI_AF_Environment_Masked_SeparateMask", AF_ENVIRONMENT_MASTER, scalar_overrides={"OpacityClipValue": 0.333, "MaskContrast": 1.0}, static_switch_overrides={"UseOpacityMask": True, "UseSeparateOpacityMask": True}, texture_overrides={"BaseColor": "/AssetForge/Textures/T_AF_Preview_BaseColor_AlphaGrid", "OpacityMask": "/AssetForge/Textures/T_AF_Preview_OpacityMask_Stripes"}),
            _material_instance("MI_AF_Environment_Emissive", "/AssetForge/MaterialInstances/MI_AF_Environment_Emissive", AF_ENVIRONMENT_MASTER, scalar_overrides={"EmissiveIntensity": 6.0}, vector_overrides={"EmissiveTint": [0.25, 0.85, 1.0, 1.0]}, static_switch_overrides={"UseEmissive": True}, texture_overrides={"BaseColor": "/AssetForge/Textures/T_AF_Preview_BaseColor_AlphaGrid", "Emissive": "/AssetForge/Textures/T_AF_Preview_Emissive_Panels"}),
            _material_instance("MI_AF_Environment_TileFloor", "/AssetForge/MaterialInstances/MI_AF_Environment_TileFloor", AF_ENVIRONMENT_MASTER, scalar_overrides={"UVTiling": 4.0, "RoughnessIntensity": 1.1}, texture_overrides={"BaseColor": "/AssetForge/Textures/T_AF_Preview_BaseColor_TileFloor", "ARM": "/AssetForge/Textures/T_AF_Preview_ARM_Rough"}),
            _material_instance("MI_AF_Environment_WornWall", "/AssetForge/MaterialInstances/MI_AF_Environment_WornWall", AF_ENVIRONMENT_MASTER, scalar_overrides={"UVTiling": 2.0, "ImperfectionIntensity": 0.65, "RoughnessIntensity": 1.2}, texture_overrides={"BaseColor": "/AssetForge/Textures/T_AF_Preview_BaseColor_TileFloor", "ImperfectionMask": "/AssetForge/Textures/T_AF_Preview_Imperfection_Wear", "ARM": "/AssetForge/Textures/T_AF_Preview_ARM_Rough"}),
            _material_instance("MI_AF_Character_Default", "/AssetForge/MaterialInstances/MI_AF_Character_Default", AF_CHARACTER_BASIC, scalar_overrides={"SubsurfaceIntensity": 0.25}),
            _material_instance("MI_AF_Character_SkinPreview", "/AssetForge/MaterialInstances/MI_AF_Character_SkinPreview", AF_CHARACTER_BASIC, scalar_overrides={"SubsurfaceIntensity": 0.45, "RoughnessIntensity": 1.15}, vector_overrides={"SubsurfaceTint": [1.0, 0.62, 0.45, 1.0]}, texture_overrides={"BaseColor": "/AssetForge/Textures/T_AF_Preview_BaseColor_SkinWarm", "ARM": "/AssetForge/Textures/T_AF_Preview_ARM_Rough"}),
        ],
        "reserved_materials": [
            _reserved_material("M_AF_Character_Skin", ASSET_TYPE_CHARACTER, "skin"),
            _reserved_material("M_AF_FX_Translucent", ASSET_TYPE_FX, RENDER_MODE_TRANSLUCENT),
        ],
        "functions": [],
        "parameter_collections": [],
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

    for index, material_instance in enumerate(plan.get("material_instances", [])):
        for field in ["name", "path", "parent_material"]:
            if field not in material_instance:
                issues.append("material_instances[{0}] missing field: {1}".format(index, field))
        parent_material = material_instance.get("parent_material", "")
        if parent_material and parent_material not in material_paths:
            issues.append("material_instances[{0}] references missing parent material: {1}".format(index, parent_material))

    return issues


def material_package_paths(plan=None):
    """Return the material asset paths that should exist in UE."""
    active_plan = plan or get_default_material_package_plan()
    return [material["path"] for material in active_plan.get("materials", [])]


def material_instance_package_paths(plan=None):
    """Return the default Material Instance preset paths that should exist in UE."""
    active_plan = plan or get_default_material_package_plan()
    return [material_instance["path"] for material_instance in active_plan.get("material_instances", [])]


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


def _material(name, path, asset_family, render_mode, texture_parameters, scalar_parameters, supports_virtual_texture_sampling=False, required_for_import=True):
    return {
        "name": name,
        "path": path,
        "asset_family": asset_family,
        "render_mode": render_mode,
        "master_family": "",
        "texture_parameters": texture_parameters,
        "scalar_parameters": scalar_parameters,
        "vector_parameters": {
            "BaseColorTint": [1.0, 1.0, 1.0, 1.0],
        },
        "parameter_api_mapping": dict((parameter, PARAMETER_API_MAPPING.get(parameter, parameter)) for parameter in texture_parameters + scalar_parameters),
        "material_network_status": "generated_pbr",
        "packed_texture_semantics": {"R": "ambient_occlusion", "G": "roughness", "B": "metallic"},
        "supports_virtual_texture_sampling": bool(supports_virtual_texture_sampling),
        "required_for_import": bool(required_for_import),
        "compatibility_role": "" if required_for_import else "legacy_props_compatibility",
    }


def _hard_surface_material(
    name,
    path,
    render_mode,
    texture_parameters,
    extra_scalar_parameters=None,
    extra_vector_parameters=None,
    supports_virtual_texture_sampling=False,
    static_switches=None,
    performance_notes=None,
    required_for_import=True,
):
    scalar_parameters = [
        "UVTiling",
        "BaseColorIntensity",
        "AOIntensity",
        "RoughnessIntensity",
        "MetallicIntensity",
        "Specular",
        "NormalStrength",
    ] + list(extra_scalar_parameters or [])
    vector_parameters = {"BaseColorTint": [1.0, 1.0, 1.0, 1.0]}
    vector_parameters.update(extra_vector_parameters or {})
    material = _material(
        name,
        path,
        ASSET_TYPE_PROPS,
        render_mode,
        texture_parameters,
        scalar_parameters,
        supports_virtual_texture_sampling=supports_virtual_texture_sampling,
        required_for_import=required_for_import,
    )
    material["master_family"] = SURFACE_PBR_FAMILY
    material["vector_parameters"] = vector_parameters
    material["parameter_api_mapping"].update(dict((name, PARAMETER_API_MAPPING.get(name, name)) for name in vector_parameters))
    default_switches = {
        "UseImperfections": False,
        "UseWear": False,
        "UseTriplanar": False,
        "UsePOM": False,
    }
    default_switches.update(static_switches or {})
    material["static_switches"] = default_switches
    material["performance_notes"] = performance_notes or [
        "POM, triplanar, dirty and wear branches are opt-in; do not enable them for default static props.",
    ]
    return material


def _surface_material(
    name,
    path,
    asset_family,
    render_mode,
    texture_parameters,
    extra_scalar_parameters=None,
    extra_vector_parameters=None,
    supports_virtual_texture_sampling=False,
):
    scalar_parameters = [
        "UVTiling",
        "BaseColorIntensity",
        "AOIntensity",
        "RoughnessIntensity",
        "MetallicIntensity",
        "Specular",
        "NormalStrength",
    ]
    if "Opacity" in texture_parameters:
        scalar_parameters.append("OpacityIntensity")
    scalar_parameters.extend(extra_scalar_parameters or [])
    vector_parameters = {"BaseColorTint": [1.0, 1.0, 1.0, 1.0]}
    vector_parameters.update(extra_vector_parameters or {})
    material = _material(
        name,
        path,
        asset_family,
        render_mode,
        texture_parameters,
        scalar_parameters,
        supports_virtual_texture_sampling=supports_virtual_texture_sampling,
    )
    material["master_family"] = SURFACE_PBR_FAMILY if asset_family != ASSET_TYPE_FX else "MM_Emissive_Effect"
    material["vector_parameters"] = vector_parameters
    material["parameter_api_mapping"].update(dict((name, PARAMETER_API_MAPPING.get(name, name)) for name in vector_parameters))
    material["static_switches"] = {
        "UseEmissive": "Emissive" in texture_parameters,
        "UseOpacity": "Opacity" in texture_parameters or "OpacityMask" in texture_parameters,
        "UseSubsurface": asset_family == ASSET_TYPE_CHARACTER,
    }
    return material


def _category_material(
    name,
    path,
    asset_family,
    render_mode,
    texture_parameters,
    extra_scalar_parameters=None,
    extra_vector_parameters=None,
    static_switches=None,
):
    scalar_parameters = [
        "UVTiling",
        "BaseColorIntensity",
        "AOIntensity",
        "RoughnessIntensity",
        "MetallicIntensity",
        "Specular",
        "NormalStrength",
    ]
    scalar_parameters.extend(extra_scalar_parameters or [])
    vector_parameters = {"BaseColorTint": [1.0, 1.0, 1.0, 1.0]}
    vector_parameters.update(extra_vector_parameters or {})
    material = _material(
        name,
        path,
        asset_family,
        render_mode,
        texture_parameters,
        scalar_parameters,
    )
    material["master_family"] = SURFACE_PBR_FAMILY
    material["vector_parameters"] = vector_parameters
    material["parameter_api_mapping"].update(dict((name, PARAMETER_API_MAPPING.get(name, name)) for name in vector_parameters))
    material["parameter_api_mapping"].update(dict((name, PARAMETER_API_MAPPING.get(name, name)) for name in static_switches or {}))
    material["static_switches"] = dict(static_switches or {})
    material["performance_notes"] = [
        "Blend modes use separate parents. Share material instance parameters for looks using the same blend mode.",
        "Virtual texture inputs are detected at import time; UE sampler-type support must use verified VT sample branches before enabling VT-specific assets.",
    ]
    return material


def _material_function(name, path, purpose, inputs, outputs, required_for_import=True):
    return {
        "name": name,
        "path": path,
        "purpose": purpose,
        "inputs": list(inputs),
        "outputs": list(outputs),
        "required_for_import": bool(required_for_import),
        "material_function_interface_status": "generated_interface",
    }


def _placeholder_texture(name, path, usage, rgba, srgb, compression, pattern="solid"):
    return {
        "name": name,
        "path": path,
        "usage": usage,
        "rgba": list(rgba),
        "srgb": bool(srgb),
        "compression": compression,
        "pattern": pattern,
        "required_for_import": True,
    }


def _material_instance(name, path, parent_material, scalar_overrides=None, vector_overrides=None, static_switch_overrides=None, texture_overrides=None):
    return {
        "name": name,
        "path": path,
        "parent_material": parent_material,
        "scalar_overrides": scalar_overrides or {},
        "vector_overrides": vector_overrides or {},
        "static_switch_overrides": static_switch_overrides or {},
        "texture_overrides": texture_overrides or {},
        "purpose": "Default DCC AssetForge material preset for common hard-surface/prop workflows.",
    }


def _reserved_material(name, asset_family, render_mode):
    return {
        "name": name,
        "asset_family": asset_family,
        "render_mode": render_mode,
        "status": "reserved",
    }
