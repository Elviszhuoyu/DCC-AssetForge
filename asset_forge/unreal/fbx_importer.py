"""Unreal Static Mesh FBX importer."""

from __future__ import absolute_import

from asset_forge.unreal.property_utils import (
    get_unreal_property,
    set_first_available_property,
    set_unreal_property,
)
from asset_forge.unreal.unreal_bridge import get_unreal


MESH_STRATEGY_OVERWRITE = "overwrite"
MESH_STRATEGY_REUSE = "reuse"
MESH_STRATEGY_SKIP = "skip"
MESH_STRATEGY_ERROR = "error"


class UnrealStaticMeshFbxImporter(object):
    """Import Static Mesh FBX files using Unreal Python."""

    def __init__(self, unreal_module=None):
        self.unreal = unreal_module or get_unreal()
        self.last_import_policy_report = self._empty_policy_report()

    def is_available(self):
        return self.unreal is not None

    def import_static_mesh(self, manifest, preset):
        if not self.is_available():
            raise RuntimeError("当前环境不可用 Unreal Python 模块")

        target_asset_path = self._target_asset_path(manifest)
        strategy = manifest.get("existing_mesh_strategy", MESH_STRATEGY_OVERWRITE)
        self.last_import_policy_report = self._empty_policy_report(strategy)
        if self._asset_exists(target_asset_path):
            if strategy == MESH_STRATEGY_SKIP:
                self._record_policy(target_asset_path, strategy, "skipped", "同名 Static Mesh 已存在，按策略跳过")
                return [target_asset_path]
            if strategy == MESH_STRATEGY_REUSE:
                self._record_policy(target_asset_path, strategy, "reused", "复用已有 Static Mesh")
                return [target_asset_path]
            if strategy == MESH_STRATEGY_ERROR:
                raise RuntimeError("同名 Static Mesh 已存在：{0}".format(target_asset_path))

        unreal = self.unreal
        task = unreal.AssetImportTask()
        set_unreal_property(task, "filename", manifest["fbx_path"])
        set_unreal_property(task, "destination_path", manifest["target_path"])
        set_unreal_property(task, "automated", True)
        set_unreal_property(task, "replace_existing", strategy == MESH_STRATEGY_OVERWRITE)
        set_unreal_property(task, "save", True)
        set_unreal_property(task, "options", self._build_fbx_import_ui(preset))

        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        imported = list(get_unreal_property(task, "imported_object_paths", []) or [])
        self._record_policy(target_asset_path, strategy, "imported", "Static Mesh 已执行 FBX 导入")
        return imported

    def _target_asset_path(self, manifest):
        return "{0}/{1}".format(manifest.get("target_path", "").rstrip("/"), manifest.get("asset_name", ""))

    def _asset_exists(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "does_asset_exist"):
            return bool(library.does_asset_exist(asset_path))
        if library and hasattr(library, "load_asset"):
            return bool(library.load_asset(asset_path))
        return False

    def _record_policy(self, target_asset_path, strategy, action, message):
        self.last_import_policy_report["actions"].append(
            {
                "target_asset_path": target_asset_path,
                "strategy": strategy,
                "action": action,
                "message": message,
            }
        )
        self.last_import_policy_report["status"] = "success"

    def _empty_policy_report(self, strategy="overwrite"):
        return {
            "status": "skipped",
            "existing_mesh_strategy": strategy,
            "actions": [],
            "issues": [],
        }

    def _build_fbx_import_ui(self, preset):
        unreal = self.unreal
        options = unreal.FbxImportUI()
        set_unreal_property(options, "import_mesh", bool(preset.get("import_mesh", True)))
        set_unreal_property(options, "import_materials", bool(preset.get("import_materials", False)))
        set_unreal_property(options, "import_textures", bool(preset.get("import_textures", False)))
        set_unreal_property(options, "import_as_skeletal", False)

        static_mesh_data = get_unreal_property(options, "static_mesh_import_data")
        set_unreal_property(static_mesh_data, "combine_meshes", bool(preset.get("combine_meshes", False)))
        set_first_available_property(
            static_mesh_data,
            ["generate_lightmap_u_vs", "generate_lightmap_uvs"],
            bool(preset.get("generate_lightmap_uvs", True)),
        )
        set_unreal_property(
            static_mesh_data,
            "auto_generate_collision",
            bool(preset.get("generate_missing_collision", False)),
        )
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
            set_unreal_property(static_mesh_data, "normal_import_method", enum_value)
