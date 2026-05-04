"""Unreal Static Mesh import preset management."""

from __future__ import absolute_import

from asset_forge.shared.asset_type_schema import get_default_import_preset
from asset_forge.shared.constants import (
    IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
    IMPORT_PRESET_STATIC_PROP_MOBILE,
    IMPORT_PRESET_STATIC_PROP_PC,
)


STATIC_PROP_IMPORT_PRESETS = {
    IMPORT_PRESET_STATIC_PROP_PC: {
        "asset_type": "static_mesh",
        "import_mesh": True,
        "import_materials": False,
        "import_textures": False,
        "generate_missing_collision": False,
        "combine_meshes": False,
        "normal_import_method": "import_normals_and_tangents",
        "generate_lightmap_uvs": True,
        "build_nanite": False,
    },
    IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE: {
        "asset_type": "static_mesh",
        "import_mesh": True,
        "import_materials": False,
        "import_textures": False,
        "generate_missing_collision": False,
        "combine_meshes": False,
        "normal_import_method": "import_normals_and_tangents",
        "generate_lightmap_uvs": True,
        "build_nanite": False,
    },
    IMPORT_PRESET_STATIC_PROP_MOBILE: {
        "asset_type": "static_mesh",
        "import_mesh": True,
        "import_materials": False,
        "import_textures": False,
        "generate_missing_collision": False,
        "combine_meshes": False,
        "normal_import_method": "import_normals",
        "generate_lightmap_uvs": True,
        "build_nanite": False,
    },
}


class UnrealImportPresetManager(object):
    """Resolve import presets from manifest metadata."""

    def __init__(self, presets=None):
        self.presets = presets or STATIC_PROP_IMPORT_PRESETS

    def preset_name_for_manifest(self, manifest):
        asset_type = manifest.get("asset_type")
        target_platform = manifest.get("target_platform")
        explicit_name = manifest.get("import_preset")
        if explicit_name:
            return explicit_name
        return get_default_import_preset(asset_type, target_platform)

    def get_preset(self, preset_name):
        if preset_name not in self.presets:
            raise KeyError("Unknown Unreal import preset: {0}".format(preset_name))
        preset = dict(self.presets[preset_name])
        preset["name"] = preset_name
        return preset

    def get_for_manifest(self, manifest):
        return self.get_preset(self.preset_name_for_manifest(manifest))
