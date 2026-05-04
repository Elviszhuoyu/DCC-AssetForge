"""Asset type schema placeholders for future pipeline expansion."""

from __future__ import absolute_import

from asset_forge.shared.constants import (
    ASSET_TYPE_ANIMATION,
    ASSET_TYPE_MORPH_TARGET,
    ASSET_TYPE_SKELETAL_MESH,
    ASSET_TYPE_STATIC_PROP,
    IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
    IMPORT_PRESET_STATIC_PROP_MOBILE,
    IMPORT_PRESET_STATIC_PROP_PC,
    SOURCE_DCC_BLENDER,
    SOURCE_DCC_MAYA,
    TARGET_ENGINE_UNREAL,
    TARGET_PLATFORM_HIGH_END_MOBILE,
    TARGET_PLATFORM_MOBILE,
    TARGET_PLATFORM_PC,
)


ASSET_TYPE_SCHEMAS = {
    ASSET_TYPE_STATIC_PROP: {
        "display_name": "Static Prop",
        "source_dcc": [SOURCE_DCC_MAYA, SOURCE_DCC_BLENDER],
        "target_engine": TARGET_ENGINE_UNREAL,
        "default_import_presets": {
            TARGET_PLATFORM_PC: IMPORT_PRESET_STATIC_PROP_PC,
            TARGET_PLATFORM_HIGH_END_MOBILE: IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
            TARGET_PLATFORM_MOBILE: IMPORT_PRESET_STATIC_PROP_MOBILE,
        },
        "manifest_fields": ["checks", "score", "fbx_path", "target_path", "import_preset"],
        "planned_checks": [
            "name_prefix",
            "mesh_exists",
            "frozen_transform",
            "triangle_budget",
            "material_slots",
            "uv0",
            "lightmap_uv",
            "history_nodes",
        ],
        "status": "implemented",
    },
    ASSET_TYPE_SKELETAL_MESH: {
        "display_name": "Skeletal Mesh",
        "source_dcc": [SOURCE_DCC_MAYA, SOURCE_DCC_BLENDER],
        "target_engine": TARGET_ENGINE_UNREAL,
        "default_import_presets": {},
        "manifest_fields": [
            "skeleton_path",
            "physics_asset_path",
            "import_morph_targets",
            "create_physics_asset",
        ],
        "planned_checks": [
            "sk_prefix",
            "has_skin_cluster",
            "has_root_joint",
            "joint_count_budget",
            "max_influences",
            "bind_pose_valid",
            "material_slots",
        ],
        "status": "planned",
    },
    ASSET_TYPE_ANIMATION: {
        "display_name": "Animation",
        "source_dcc": [SOURCE_DCC_MAYA, SOURCE_DCC_BLENDER],
        "target_engine": TARGET_ENGINE_UNREAL,
        "default_import_presets": {},
        "manifest_fields": ["skeleton_path", "frame_range", "sample_rate", "import_animations"],
        "planned_checks": [
            "animation_prefix",
            "has_keyframes",
            "frame_range_valid",
            "skeleton_compatible",
            "root_motion_policy",
        ],
        "status": "planned",
    },
    ASSET_TYPE_MORPH_TARGET: {
        "display_name": "Morph Target",
        "source_dcc": [SOURCE_DCC_MAYA, SOURCE_DCC_BLENDER],
        "target_engine": TARGET_ENGINE_UNREAL,
        "default_import_presets": {},
        "manifest_fields": ["base_mesh_path", "morph_target_names", "import_morph_targets"],
        "planned_checks": [
            "blendshape_exists",
            "target_vertex_count_matches",
            "target_names_valid",
            "no_topology_change",
        ],
        "status": "planned",
    },
}


def get_asset_type_schema(asset_type):
    schema = ASSET_TYPE_SCHEMAS.get(asset_type)
    return dict(schema) if schema else None


def list_asset_type_schemas():
    return dict(ASSET_TYPE_SCHEMAS)


def get_default_import_preset(asset_type, target_platform):
    schema = get_asset_type_schema(asset_type) or {}
    return schema.get("default_import_presets", {}).get(target_platform)
