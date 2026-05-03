"""Unreal Static Mesh FBX importer."""

from __future__ import absolute_import

from asset_forge.unreal.unreal_bridge import get_unreal


class UnrealStaticMeshFbxImporter(object):
    """Import Static Mesh FBX files using Unreal Python."""

    def __init__(self, unreal_module=None):
        self.unreal = unreal_module or get_unreal()

    def is_available(self):
        return self.unreal is not None

    def import_static_mesh(self, manifest, preset):
        if not self.is_available():
            raise RuntimeError("unreal module is not available")

        unreal = self.unreal
        task = unreal.AssetImportTask()
        task.filename = manifest["fbx_path"]
        task.destination_path = manifest["target_path"]
        task.automated = True
        task.replace_existing = True
        task.save = True
        task.options = self._build_fbx_import_ui(preset)

        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        return list(getattr(task, "imported_object_paths", []) or [])

    def _build_fbx_import_ui(self, preset):
        unreal = self.unreal
        options = unreal.FbxImportUI()
        options.import_mesh = bool(preset.get("import_mesh", True))
        options.import_materials = bool(preset.get("import_materials", False))
        options.import_textures = bool(preset.get("import_textures", False))
        options.import_as_skeletal = False

        static_mesh_data = options.static_mesh_import_data
        static_mesh_data.combine_meshes = bool(preset.get("combine_meshes", False))
        static_mesh_data.generate_lightmap_u_vs = bool(preset.get("generate_lightmap_uvs", True))
        static_mesh_data.auto_generate_collision = bool(preset.get("generate_missing_collision", False))
        self._apply_normal_import_method(static_mesh_data, preset.get("normal_import_method"))
        return options

    def _apply_normal_import_method(self, static_mesh_data, method_name):
        unreal = self.unreal
        if not method_name or not hasattr(unreal, "FBXNormalImportMethod"):
            return

        normal_enum = unreal.FBXNormalImportMethod
        enum_value = None
        if method_name == "import_normals_and_tangents":
            enum_value = getattr(normal_enum, "FBXNIM_IMPORT_NORMALS_AND_TANGENTS", None)
        elif method_name == "import_normals":
            enum_value = getattr(normal_enum, "FBXNIM_IMPORT_NORMALS", None)
        elif method_name == "compute_normals":
            enum_value = getattr(normal_enum, "FBXNIM_COMPUTE_NORMALS", None)

        if enum_value is not None:
            static_mesh_data.normal_import_method = enum_value
