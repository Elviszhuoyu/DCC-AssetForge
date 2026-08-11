"""Product-level acceptance checks for the DCC AssetForge material library."""

from __future__ import absolute_import

from asset_forge.unreal.material_package_schema import get_default_material_package_plan
from asset_forge.unreal.material_showcase import build_material_showcase_report


BLOCKED_DEFAULT_PARAMETERS = {
    "RoughnessMin",
    "RoughnessMax",
    "EdgeWearIntensity",
    "WorldAlignedScale",
    "ProjectionBlendSharpness",
    "MacroVariationScale",
    "MacroVariationIntensity",
    "SkinRoughnessBias",
    "MicroNormalStrength",
}

REQUIRED_PRESETS = {
    "MI_AF_Props_Default",
    "MI_AF_Props_Masked",
    "MI_AF_Props_Masked_SeparateMask",
    "MI_AF_Props_Emissive",
    "MI_AF_Props_DirtyWear",
    "MI_AF_Props_MetalPanel",
    "MI_AF_Props_RubberMatte",
    "MI_AF_Environment_Default",
    "MI_AF_Environment_Masked",
    "MI_AF_Environment_Masked_SeparateMask",
    "MI_AF_Environment_Emissive",
    "MI_AF_Environment_TileFloor",
    "MI_AF_Environment_WornWall",
    "MI_AF_Character_Default",
    "MI_AF_Character_SkinPreview",
}

REQUIRED_PREVIEW_TEXTURES = {
    "T_AF_Preview_BaseColor_AlphaGrid",
    "T_AF_Preview_OpacityMask_Stripes",
    "T_AF_Preview_Emissive_Panels",
    "T_AF_Preview_Imperfection_Wear",
    "T_AF_Preview_BaseColor_MetalPanel",
    "T_AF_Preview_BaseColor_Rubber",
    "T_AF_Preview_BaseColor_TileFloor",
    "T_AF_Preview_BaseColor_SkinWarm",
    "T_AF_Preview_ARM_Metal",
    "T_AF_Preview_ARM_Rough",
}


def validate_material_library_product_readiness(plan=None):
    """Return product-level issues that would make the material library feel unfinished."""
    active_plan = plan or get_default_material_package_plan()
    issues = []
    materials = {item["path"]: item for item in active_plan.get("materials", [])}
    instances = {item["name"]: item for item in active_plan.get("material_instances", [])}
    textures = {item["name"]: item for item in active_plan.get("placeholder_textures", [])}
    texture_paths = {item["path"] for item in active_plan.get("placeholder_textures", [])}

    if set(materials) != {
        "/AssetForge/Materials/M_AF_Props_Master",
        "/AssetForge/Materials/M_AF_Environment_Master",
        "/AssetForge/Materials/M_AF_Character_Master",
    }:
        issues.append("default material library must stay scoped to props, environment and character masters")

    if active_plan.get("functions"):
        issues.append("default material functions must not be generated until they are called by a master graph")

    missing_presets = sorted(REQUIRED_PRESETS.difference(instances))
    if missing_presets:
        issues.append("missing product material presets: {0}".format(", ".join(missing_presets)))

    missing_textures = sorted(REQUIRED_PREVIEW_TEXTURES.difference(textures))
    if missing_textures:
        issues.append("missing preview textures: {0}".format(", ".join(missing_textures)))

    for material in materials.values():
        blocked = sorted(BLOCKED_DEFAULT_PARAMETERS.intersection(material.get("scalar_parameters", [])))
        if blocked:
            issues.append("{0} exposes unfinished parameters: {1}".format(material.get("name", ""), ", ".join(blocked)))

    for instance in instances.values():
        parent = materials.get(instance.get("parent_material", ""))
        if not parent:
            issues.append("{0} references a missing parent material".format(instance.get("name", "")))
            continue
        for parameter in instance.get("scalar_overrides", {}):
            if parameter not in parent.get("scalar_parameters", []):
                issues.append("{0} overrides missing scalar parameter {1}".format(instance["name"], parameter))
        for parameter in instance.get("vector_overrides", {}):
            if parameter not in parent.get("vector_parameters", {}):
                issues.append("{0} overrides missing vector parameter {1}".format(instance["name"], parameter))
        for parameter in instance.get("static_switch_overrides", {}):
            if parameter not in parent.get("static_switches", {}):
                issues.append("{0} overrides missing static switch {1}".format(instance["name"], parameter))
        for parameter, texture_path in instance.get("texture_overrides", {}).items():
            if parameter not in parent.get("texture_parameters", []):
                issues.append("{0} overrides missing texture parameter {1}".format(instance["name"], parameter))
            if texture_path not in texture_paths:
                issues.append("{0} references missing preview texture {1}".format(instance["name"], texture_path))

    _validate_visible_preset(instances, issues, "MI_AF_Props_Emissive", "UseEmissive", "Emissive")
    _validate_visible_preset(instances, issues, "MI_AF_Environment_Emissive", "UseEmissive", "Emissive")
    _validate_visible_preset(instances, issues, "MI_AF_Props_Masked_SeparateMask", "UseSeparateOpacityMask", "OpacityMask")
    _validate_visible_preset(instances, issues, "MI_AF_Environment_Masked_SeparateMask", "UseSeparateOpacityMask", "OpacityMask")

    showcase_report = build_material_showcase_report(active_plan)
    if showcase_report.get("status") != "pass":
        issues.extend(showcase_report.get("issues", []))

    return {
        "status": "pass" if not issues else "error",
        "issue_count": len(issues),
        "issues": issues,
        "master_count": len(materials),
        "preset_count": len(instances),
        "preview_texture_count": len([name for name in textures if name.startswith("T_AF_Preview_")]),
        "showcase_level_path": showcase_report.get("level_path", ""),
        "showcase_entry_count": showcase_report.get("entry_count", 0),
        "showcase_category_count": showcase_report.get("category_count", 0),
    }


def _validate_visible_preset(instances, issues, name, switch_name, texture_parameter):
    instance = instances.get(name)
    if not instance:
        return
    if not instance.get("static_switch_overrides", {}).get(switch_name):
        issues.append("{0} must enable {1} to visibly demonstrate its feature".format(name, switch_name))
    if texture_parameter not in instance.get("texture_overrides", {}):
        issues.append("{0} must bind {1} preview texture".format(name, texture_parameter))
