"""Asset type schema placeholders for future pipeline expansion."""

from __future__ import absolute_import

from asset_forge.shared.constants import (
    ASSET_TYPE_ANIMATION,
    ASSET_TYPE_MORPH_TARGET,
    ASSET_TYPE_SKELETAL_MESH,
    ASSET_TYPE_STATIC_PROP,
)


ASSET_TYPE_SCHEMAS = {
    ASSET_TYPE_STATIC_PROP: {
        "display_name": "Static Prop",
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
    return ASSET_TYPE_SCHEMAS.get(asset_type)


def list_asset_type_schemas():
    return dict(ASSET_TYPE_SCHEMAS)
