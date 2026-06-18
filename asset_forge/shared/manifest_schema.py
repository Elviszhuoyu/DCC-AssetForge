"""Manifest helpers for Asset Forge v0.1."""

from __future__ import absolute_import

import io
import json

from asset_forge.shared.constants import (
    ASSET_TYPE_SKELETAL_MESH,
    ASSET_TYPE_STATIC_PROP,
    SOURCE_DCC_MAYA,
    TARGET_ENGINE_UNREAL,
    TARGET_PLATFORM_HIGH_END_MOBILE,
)

MANIFEST_VERSION = "0.1"
ASSET_FORGE_SCHEMA_VERSION = "0.2"
DEFAULT_TEXTURE_IMPORT_POLICY = {
    "virtual_texture_policy": "project_default",
    "texture_streaming_policy": "project_default",
    "texture_group": "project_default",
}
DEFAULT_STATIC_MESH_IMPORT_POLICY = {
    "nanite_policy": "project_default",
    "lod_group": "project_default",
    "import_lod_policy": "import_existing",
    "build_reversed_index_buffer": "report_only",
    "generate_lightmap_uvs": "report_only",
    "collision_complexity": "report_only",
}

REQUIRED_MANIFEST_FIELDS = [
    "asset_name",
    "asset_type",
    "source_dcc",
    "target_engine",
    "target_platform",
    "fbx_path",
    "target_path",
    "import_preset",
    "checks",
    "score",
]


def create_manifest(asset_name, fbx_path, target_path, checks=None, score=0, **kwargs):
    """Create a v0.1 manifest dictionary."""
    texture_import_policy = dict(DEFAULT_TEXTURE_IMPORT_POLICY)
    texture_import_policy.update(kwargs.get("texture_import_policy", {}) or {})
    static_mesh_import_policy = dict(DEFAULT_STATIC_MESH_IMPORT_POLICY)
    static_mesh_import_policy.update(kwargs.get("static_mesh_import_policy", {}) or {})
    return {
        "schema_version": ASSET_FORGE_SCHEMA_VERSION,
        "asset_forge_schema_version": ASSET_FORGE_SCHEMA_VERSION,
        "version": kwargs.get("version", MANIFEST_VERSION),
        "asset_name": asset_name,
        "asset_type": kwargs.get("asset_type", ASSET_TYPE_STATIC_PROP),
        "source_dcc": kwargs.get("source_dcc", SOURCE_DCC_MAYA),
        "target_engine": kwargs.get("target_engine", TARGET_ENGINE_UNREAL),
        "target_engine_version": kwargs.get("target_engine_version", ""),
        "target_platform": kwargs.get("target_platform", TARGET_PLATFORM_HIGH_END_MOBILE),
        "fbx_path": fbx_path,
        "target_path": target_path,
        "import_preset": kwargs.get("import_preset", "StaticProp_HighEndMobile"),
        "package_dir": kwargs.get("package_dir", ""),
        "material_profile": kwargs.get("material_profile", ""),
        "material_profiles_snapshot_path": kwargs.get("material_profiles_snapshot_path", ""),
        "materials": kwargs.get("materials", []),
        "material_texture_sets": kwargs.get("material_texture_sets", []),
        "material_texture_bindings": kwargs.get("material_texture_bindings", []),
        "material_texture_binding_risks": kwargs.get("material_texture_binding_risks", []),
        "material_feature_hints": kwargs.get("material_feature_hints", []),
        "variant_candidates": kwargs.get("variant_candidates", []),
        "asset_name_candidates": kwargs.get("asset_name_candidates", []),
        "material_slots": kwargs.get("material_slots", []),
        "textures": kwargs.get("textures", []),
        "texture_folder_scan": kwargs.get("texture_folder_scan", {}),
        "texture_import_policy": texture_import_policy,
        "static_mesh_import_policy": static_mesh_import_policy,
        "existing_mesh_strategy": kwargs.get("existing_mesh_strategy", "overwrite"),
        "existing_texture_strategy": kwargs.get("existing_texture_strategy", "overwrite"),
        "existing_material_strategy": kwargs.get("existing_material_strategy", "reuse"),
        "checks": checks or {},
        "score": score,
    }


def create_skeletal_mesh_manifest(asset_name, fbx_path, target_path, checks=None, score=0, **kwargs):
    """Create a planned Skeletal Mesh manifest without enabling import support yet."""
    manifest = create_manifest(
        asset_name,
        fbx_path,
        target_path,
        checks=checks,
        score=score,
        asset_type=ASSET_TYPE_SKELETAL_MESH,
        import_preset=kwargs.get("import_preset", ""),
        source_dcc=kwargs.get("source_dcc", SOURCE_DCC_MAYA),
        target_engine=kwargs.get("target_engine", TARGET_ENGINE_UNREAL),
        target_platform=kwargs.get("target_platform", TARGET_PLATFORM_HIGH_END_MOBILE),
        version=kwargs.get("version", MANIFEST_VERSION),
        package_dir=kwargs.get("package_dir", ""),
        material_profile=kwargs.get("material_profile", ""),
        material_profiles_snapshot_path=kwargs.get("material_profiles_snapshot_path", ""),
        materials=kwargs.get("materials", []),
        textures=kwargs.get("textures", []),
    )
    manifest.update(
        {
            "skeleton_path": kwargs.get("skeleton_path", ""),
            "root_joint": kwargs.get("root_joint", ""),
            "joint_count": kwargs.get("joint_count", 0),
            "skin_cluster_count": kwargs.get("skin_cluster_count", 0),
            "max_influences": kwargs.get("max_influences", 0),
            "lods": kwargs.get("lods", []),
            "physics_asset_path": kwargs.get("physics_asset_path", ""),
            "import_morph_targets": bool(kwargs.get("import_morph_targets", False)),
            "create_physics_asset": bool(kwargs.get("create_physics_asset", True)),
        }
    )
    return manifest


def validate_manifest(manifest):
    """Return a list of missing or invalid manifest fields."""
    issues = []

    if not isinstance(manifest, dict):
        return ["manifest must be a dict"]

    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            issues.append("missing field: {0}".format(field))

    if "version" not in manifest and "schema_version" not in manifest and "asset_forge_schema_version" not in manifest:
        # Old packages are allowed to load; interface_contract reports this as a warning.
        pass

    checks = manifest.get("checks")
    if checks is not None and not isinstance(checks, dict):
        issues.append("checks must be a dict")

    score = manifest.get("score")
    if score is not None and not isinstance(score, int):
        issues.append("score must be an int")

    return issues


def write_manifest(path, manifest, pretty=True):
    """Write a manifest JSON file using UTF-8."""
    indent = 2 if pretty else None
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=indent))
        stream.write("\n")


def read_manifest(path):
    """Read a manifest JSON file using UTF-8."""
    with io.open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)
