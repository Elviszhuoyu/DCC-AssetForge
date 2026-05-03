"""Manifest helpers for Asset Forge v0.1."""

from __future__ import absolute_import

import io
import json

from asset_forge.shared.constants import (
    ASSET_TYPE_STATIC_PROP,
    SOURCE_DCC_MAYA,
    TARGET_ENGINE_UNREAL,
    TARGET_PLATFORM_HIGH_END_MOBILE,
)

MANIFEST_VERSION = "0.1"

REQUIRED_MANIFEST_FIELDS = [
    "version",
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
    return {
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
        "materials": kwargs.get("materials", []),
        "textures": kwargs.get("textures", []),
        "checks": checks or {},
        "score": score,
    }


def validate_manifest(manifest):
    """Return a list of missing or invalid manifest fields."""
    issues = []

    if not isinstance(manifest, dict):
        return ["manifest must be a dict"]

    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            issues.append("missing field: {0}".format(field))

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
