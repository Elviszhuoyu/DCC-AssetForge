"""Maya-side manifest writer."""

from __future__ import absolute_import

import os

from asset_forge.shared.constants import (
    IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
    IMPORT_PRESET_STATIC_PROP_MOBILE,
    IMPORT_PRESET_STATIC_PROP_PC,
    SOURCE_DCC_MAYA,
    TARGET_PLATFORM_HIGH_END_MOBILE,
    TARGET_PLATFORM_MOBILE,
    TARGET_PLATFORM_PC,
)
from asset_forge.shared.manifest_schema import create_manifest, write_manifest
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.rule_validator import checks_to_manifest_dict


IMPORT_PRESET_BY_PLATFORM = {
    TARGET_PLATFORM_PC: IMPORT_PRESET_STATIC_PROP_PC,
    TARGET_PLATFORM_HIGH_END_MOBILE: IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
    TARGET_PLATFORM_MOBILE: IMPORT_PRESET_STATIC_PROP_MOBILE,
}


class MayaManifestWriter(object):
    """Build and write manifest.json after Maya export."""

    def build(
        self,
        scan_result,
        validation_result,
        fbx_path,
        target_path,
        target_engine_version="",
        package_dir="",
        material_profile="",
        material_profiles_snapshot_path="",
    ):
        target_platform = validation_result.get("target_platform", TARGET_PLATFORM_HIGH_END_MOBILE)
        return create_manifest(
            scan_result.get("asset_name", ""),
            normalize_path(fbx_path),
            target_path,
            checks=checks_to_manifest_dict(validation_result),
            score=validation_result.get("score", 0),
            source_dcc=SOURCE_DCC_MAYA,
            target_platform=target_platform,
            target_engine_version=target_engine_version,
            import_preset=IMPORT_PRESET_BY_PLATFORM.get(target_platform, IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE),
            package_dir=normalize_path(package_dir) if package_dir else "",
            materials=scan_result.get("materials", []),
            textures=scan_result.get("textures", []),
            material_profile=material_profile,
            material_profiles_snapshot_path=normalize_path(material_profiles_snapshot_path) if material_profiles_snapshot_path else "",
        )

    def write(self, manifest_path, manifest):
        parent = os.path.dirname(os.path.abspath(manifest_path))
        if parent and not os.path.exists(parent):
            os.makedirs(parent)
        write_manifest(manifest_path, manifest, pretty=True)
        return manifest_path
