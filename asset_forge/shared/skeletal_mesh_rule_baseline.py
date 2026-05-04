"""Planned Skeletal Mesh rule baseline from official FBX pipeline docs."""

from __future__ import absolute_import


SKELETAL_MESH_RULE_BASELINE = {
    "asset_type": "skeletal_mesh",
    "status": "planned",
    "fbx_version": "2020.2",
    "official_sources": [
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-content-pipeline?application_version=5.6",
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/skeletal-mesh-assets-in-unreal-engine?application_version=5.6",
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-skeletal-mesh-pipeline?application_version=4.27",
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-morph-target-pipeline-in-unreal-engine?application_version=5.6",
        "https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Interoperability/files/GUID-FE8DBEAA-C2DD-43B3-9933-4BA4CDDEAA89.htm",
    ],
    "supported_fbx_features": [
        "materials",
        "animations",
        "morph_targets",
        "multiple_uv_sets",
        "smoothing_groups",
        "vertex_colors",
        "lods",
    ],
    "planned_manifest_fields": [
        "skeleton_path",
        "root_joint",
        "joint_count",
        "skin_cluster_count",
        "max_influences",
        "lods",
        "physics_asset_path",
        "import_morph_targets",
        "create_physics_asset",
    ],
    "planned_checks": [
        "sk_prefix",
        "has_root_joint",
        "has_skin_cluster",
        "joint_count_budget",
        "max_influences",
        "bind_pose_valid",
        "lod_order",
        "material_slots",
    ],
    "maya_export_baseline": {
        "skins": True,
        "smoothing_groups": True,
        "tangents_and_binormals": True,
        "animation_required_for_animation_assets": True,
        "deformed_models_required_for_morph_targets": True,
        "skeleton_definitions_optional": True,
    },
    "unreal_import_baseline": {
        "import_as_skeletal": True,
        "import_mesh": True,
        "import_materials": False,
        "import_textures": False,
        "import_morph_targets": "profile_driven",
        "import_animations": "asset_type_driven",
        "create_physics_asset": "profile_driven",
    },
}


def get_skeletal_mesh_rule_baseline():
    return dict(SKELETAL_MESH_RULE_BASELINE)
