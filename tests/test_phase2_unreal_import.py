from __future__ import absolute_import

import os
import json
import shutil
import tempfile
import unittest

from asset_forge.unreal import operation_logger as unreal_operation_logger
from asset_forge.shared.constants import (
    IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
    TARGET_PLATFORM_HIGH_END_MOBILE,
    UNREAL_IMPORT_STATUS_FAILED,
    UNREAL_IMPORT_STATUS_SKIPPED,
    UNREAL_IMPORT_STATUS_SUCCESS,
)
from asset_forge.shared.manifest_schema import create_manifest, write_manifest
from asset_forge.shared.report_schema import read_report, summarize_pipeline, write_report
from scripts.unreal_import_manifest import import_all_manifests as script_import_all_manifests
from scripts.unreal_import_manifest import import_asset_forge_package as script_import_asset_forge_package
from scripts.unreal_import_manifest import import_manifest as script_import_manifest
from asset_forge.unreal.fbx_importer import UnrealStaticMeshFbxImporter
from asset_forge.unreal.import_presets import UnrealImportPresetManager
from asset_forge.unreal.manifest_reader import prepare_manifest_for_import
from asset_forge.unreal.material_instance_creator import UnrealMaterialInstanceCreator
from asset_forge.unreal.material_slot_assigner import UnrealMaterialSlotAssigner
from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline, import_asset_forge_package, import_latest_manifest
from asset_forge.unreal.texture_importer import UnrealTextureImporter


class FakeImporter(object):
    def import_static_mesh(self, manifest, preset):
        return [manifest["target_path"] + "/" + manifest["asset_name"]]

    def plan_fbx_import_options(self, manifest, preset):
        return UnrealStaticMeshFbxImporter(FakeUnreal()).plan_fbx_import_options(manifest, preset)


class TrackingFakeImporter(FakeImporter):
    def __init__(self):
        self.called = False
        self.last_manifest = None
        self.last_preset = None
        self.last_fbx_import_options_report = {}

    def import_static_mesh(self, manifest, preset):
        self.called = True
        self.last_manifest = dict(manifest)
        self.last_preset = dict(preset)
        self.last_fbx_import_options_report = {
            "status": "ready",
            "options": {
                "normal_import_method": preset.get("normal_import_method", ""),
                "normal_generation_method": preset.get("normal_generation_method", ""),
                "vertex_color_import_option": preset.get("vertex_color_import_option", ""),
            },
            "applied_options": [
                {"property": "normal_import_method", "value": preset.get("normal_import_method", ""), "readback": "compute"},
                {"property": "vertex_color_import_option", "value": preset.get("vertex_color_import_option", ""), "readback": "override_enum"},
            ],
            "ignored_options": [
                {"property": "normal_generation_method", "value": preset.get("normal_generation_method", ""), "reason": "test ignored"}
            ],
            "warnings": [],
        }
        return super(TrackingFakeImporter, self).import_static_mesh(manifest, preset)


class BlockingEngineVersionPreflight(object):
    def check(self, manifest):
        return {
            "status": "error",
            "can_write_assets": False,
            "errors": [{"message": "Manifest target_engine_version is 5.6, but current UE runtime is 5.5."}],
            "warnings": [],
        }


class FakeEditorObject(object):
    def set_editor_property(self, name, value):
        setattr(self, name, value)

    def get_editor_property(self, name):
        return getattr(self, name)


class FakeAssetImportTask(FakeEditorObject):
    def __init__(self):
        self.imported_object_paths = []


class FakeStaticMeshImportData(FakeEditorObject):
    pass


class FakeStaticMeshImportDataWithLodAlias(FakeEditorObject):
    def __setattr__(self, name, value):
        if name == "import_mesh_lods":
            raise AttributeError("import_mesh_lods is not exposed by this fake UE version")
        super(FakeStaticMeshImportDataWithLodAlias, self).__setattr__(name, value)

    def set_editor_property(self, name, value):
        if name == "import_mesh_lods":
            raise AttributeError("import_mesh_lods is not exposed by this fake UE version")
        setattr(self, name, value)


class FakeFbxImportUI(FakeEditorObject):
    def __init__(self):
        self.static_mesh_import_data = FakeStaticMeshImportData()


class FakeFbxImportUIWithLodAlias(FakeEditorObject):
    def __init__(self):
        self.static_mesh_import_data = FakeStaticMeshImportDataWithLodAlias()


class FakeAssetTools(object):
    def __init__(self):
        self.tasks = []
        self.assets = []

    def import_asset_tasks(self, tasks):
        self.tasks.extend(tasks)
        for task in tasks:
            name = getattr(task, "destination_name", "SM_Crate_01")
            task.imported_object_paths = [task.destination_path + "/" + name]
            FakeUnreal.EditorAssetLibrary.assets[task.destination_path + "/" + name] = FakeTexture()

    def create_asset(self, asset_name, package_path, asset_class, factory):
        asset = FakeMaterialInstance()
        asset.asset_name = asset_name
        asset.package_path = package_path
        asset.asset_class = asset_class
        asset.factory = factory
        self.assets.append(asset)
        return asset


class FakeAssetToolsWithoutImportedPaths(FakeAssetTools):
    def import_asset_tasks(self, tasks):
        self.tasks.extend(tasks)
        for task in tasks:
            asset_path = task.destination_path + "/" + task.destination_name
            task.imported_object_paths = []
            FakeUnreal.EditorAssetLibrary.assets[asset_path] = FakeStaticMesh()


class FakeAssetToolsHelpers(object):
    asset_tools = FakeAssetTools()

    @classmethod
    def get_asset_tools(cls):
        return cls.asset_tools


class FakeNormalImportMethod(object):
    FBXNIM_IMPORT_NORMALS_AND_TANGENTS = "normals_and_tangents"
    FBXNIM_IMPORT_NORMALS = "normals"
    FBXNIM_COMPUTE_NORMALS = "compute"


class FakeNormalGenerationMethod(object):
    MIKK_T_SPACE = "mikk_enum"
    BUILT_IN = "built_in_enum"


class FakeFBXImportType(object):
    FBXIT_STATIC_MESH = "static_mesh"


class FakeVertexColorImportOption(object):
    Replace = "replace_enum"
    Ignore = "ignore_enum"
    Override = "override_enum"


class FakeUnreal(object):
    AssetImportTask = FakeAssetImportTask
    FbxImportUI = FakeFbxImportUI
    AssetToolsHelpers = FakeAssetToolsHelpers
    FBXImportType = FakeFBXImportType
    FBXNormalImportMethod = FakeNormalImportMethod
    FBXNormalGenerationMethod = FakeNormalGenerationMethod
    EVertexColorImportOption = FakeVertexColorImportOption
    MaterialInstanceConstant = "MaterialInstanceConstant"

    class Color(object):
        def __init__(self, r, g, b, a=255):
            self.r = r
            self.g = g
            self.b = b
            self.a = a

    class Vector(object):
        def __init__(self, x, y, z):
            self.x = x
            self.y = y
            self.z = z

    class Rotator(object):
        def __init__(self, pitch, yaw, roll):
            self.pitch = pitch
            self.yaw = yaw
            self.roll = roll

    class LinearColor(object):
        def __init__(self, r, g, b, a=1.0):
            self.r = r
            self.g = g
            self.b = b
            self.a = a

    class MaterialInstanceConstantFactoryNew(object):
        pass

    class EditorAssetLibrary(object):
        loaded = []
        assets = {}
        saved = []

        @classmethod
        def load_asset(cls, asset_path):
            cls.loaded.append(asset_path)
            if asset_path in cls.assets:
                return cls.assets[asset_path]
            return "asset:" + asset_path

        @classmethod
        def does_asset_exist(cls, asset_path):
            return asset_path in cls.assets

        @classmethod
        def delete_asset(cls, asset_path):
            if asset_path in cls.assets:
                del cls.assets[asset_path]
                return True
            return False

        @classmethod
        def save_asset(cls, asset_path):
            cls.saved.append(asset_path)

    class TextureCompressionSettings(object):
        TC_DEFAULT = "default"
        TC_NORMALMAP = "normalmap"
        TC_MASKS = "masks"

    class TextureGroup(object):
        TEXTUREGROUP_World = "TEXTUREGROUP_World"
        TEXTUREGROUP_WorldNormalMap = "TEXTUREGROUP_WorldNormalMap"

    class MaterialEditingLibrary(object):
        texture_calls = []
        scalar_calls = []
        vector_calls = []
        static_switch_calls = []

        @classmethod
        def set_material_instance_parent(cls, material_instance, parent):
            material_instance.parent = parent
            return True

        @classmethod
        def set_material_instance_texture_parameter_value(cls, material_instance, name, texture_asset):
            cls.texture_calls.append((material_instance, name, texture_asset))
            return True

        @classmethod
        def set_material_instance_scalar_parameter_value(cls, material_instance, name, value):
            cls.scalar_calls.append((material_instance, name, value))
            return True

        @classmethod
        def set_material_instance_vector_parameter_value(cls, material_instance, name, value):
            if not isinstance(value, FakeUnreal.LinearColor):
                return False
            cls.vector_calls.append((material_instance, name, value))
            return True

        @classmethod
        def set_material_instance_static_switch_parameter_value(cls, material_instance, name, value):
            cls.static_switch_calls.append((material_instance, name, value))
            return True


class FakeUnrealWithLodAlias(FakeUnreal):
    FbxImportUI = FakeFbxImportUIWithLodAlias


class FakeMaterialInstance(FakeEditorObject):
    pass


class FakeNaniteSettings(FakeEditorObject):
    pass


class FakeTexture(FakeEditorObject):
    def __init__(self):
        self.nanite_settings = FakeNaniteSettings()


class FakeStaticMaterial(FakeEditorObject):
    def __init__(self, slot_name):
        self.material_slot_name = slot_name


class FakeStaticMesh(FakeEditorObject):
    def __init__(self, slot_names=None):
        self.static_materials = [FakeStaticMaterial(slot_name) for slot_name in (slot_names or [])]
        self.assigned_materials = {}

    def set_material(self, index, material):
        self.assigned_materials[index] = material


class Phase2UnrealImportTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fbx_path = os.path.join(self.temp_dir, "SM_Crate_01.fbx")
        with open(self.fbx_path, "wb") as stream:
            stream.write(b"fake fbx")

        self.manifest_path = os.path.join(self.temp_dir, "SM_Crate_01_manifest.json")
        self.manifest = create_manifest(
            "SM_Crate_01",
            self.fbx_path.replace("\\", "/"),
            "/Game/Props",
            checks={},
            score=92,
            target_platform=TARGET_PLATFORM_HIGH_END_MOBILE,
            import_preset=IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
            materials=[{"name": "M_Crate", "textures": []}],
            textures=[{"node": "file_basecolor", "path": self.fbx_path.replace(".fbx", ".png"), "usage": "base_color"}],
        )
        write_manifest(self.manifest_path, self.manifest)
        export_report = {
            "version": "0.1",
            "stage": "maya_export",
            "asset_name": "SM_Crate_01",
            "validation": {"status": "warning", "score": 92},
        }
        write_report(os.path.join(self.temp_dir, "SM_Crate_01_export_report.json"), export_report)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_prepare_manifest_resolves_preset(self):
        prepared = prepare_manifest_for_import(self.manifest_path)

        self.assertTrue(prepared["can_import"])
        self.assertEqual(prepared["issues"], [])
        self.assertEqual(prepared["preset"]["name"], IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE)
        self.assertTrue(prepared["preset"]["generate_lightmap_uvs"])
        self.assertTrue(prepared["preset"]["import_materials"])
        self.assertTrue(prepared["preset"]["import_textures"])
        self.assertFalse(prepared["preset"]["fbx_import_materials"])
        self.assertFalse(prepared["preset"]["fbx_import_textures"])

    def test_pipeline_applies_gate_import_options_override(self):
        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            import_options={
                "import_materials": True,
                "import_textures": True,
                "combine_meshes": True,
                "auto_generate_collision": True,
                "generate_lightmap_uvs": False,
                "build_nanite": False,
                "build_reversed_index_buffer": True,
                "import_mesh_lods": False,
                "one_convex_hull_per_ucx": False,
                "remove_degenerates": False,
                "compute_weighted_normals": True,
                "convert_scene": False,
                "force_front_x_axis": True,
                "convert_scene_unit": False,
                "transform_vertex_to_absolute": False,
                "bake_pivot_in_vertex": True,
                "import_translation": [10.0, 20.0, 30.0],
                "import_rotation": [5.0, 15.0, 25.0],
                "import_uniform_scale": 2.0,
                "normal_import_method": "import_normals",
                "normal_generation_method": "built_in",
                "static_mesh_lod_group": "SmallProp",
                "vertex_color_import_option": "override",
                "vertex_override_color": [0.25, 0.5, 0.75],
            },
        ).dry_run_manifest(self.manifest_path)

        options_report = report["fbx_import_options_report"]
        self.assertEqual(report["gate_import_options_override"]["combine_meshes"], True)
        self.assertFalse(options_report["options"]["import_materials"])
        self.assertFalse(options_report["options"]["import_textures"])
        self.assertTrue(report["import_policy_summary"]["content_import_policy"]["import_materials"]["enabled"])
        self.assertTrue(report["import_policy_summary"]["content_import_policy"]["import_textures"]["enabled"])
        self.assertEqual(report["import_policy_summary"]["content_import_policy"]["import_materials"]["source"], "gate_override")
        self.assertEqual(report["import_policy_summary"]["content_import_policy"]["import_textures"]["source"], "gate_override")
        self.assertTrue(options_report["options"]["combine_meshes"])
        self.assertTrue(options_report["options"]["auto_generate_collision"])
        self.assertFalse(options_report["options"]["generate_lightmap_uvs"])
        self.assertFalse(options_report["options"]["build_nanite"])
        self.assertTrue(options_report["options"]["build_reversed_index_buffer"])
        self.assertFalse(options_report["options"]["import_mesh_lods"])
        self.assertFalse(options_report["options"]["one_convex_hull_per_ucx"])
        self.assertFalse(options_report["options"]["remove_degenerates"])
        self.assertTrue(options_report["options"]["compute_weighted_normals"])
        self.assertFalse(options_report["options"]["convert_scene"])
        self.assertTrue(options_report["options"]["force_front_x_axis"])
        self.assertFalse(options_report["options"]["convert_scene_unit"])
        self.assertFalse(options_report["options"]["transform_vertex_to_absolute"])
        self.assertTrue(options_report["options"]["bake_pivot_in_vertex"])
        self.assertEqual(options_report["options"]["import_translation"], [10.0, 20.0, 30.0])
        self.assertEqual(options_report["options"]["import_rotation"], [5.0, 15.0, 25.0])
        self.assertEqual(options_report["options"]["import_uniform_scale"], 2.0)
        self.assertEqual(options_report["options"]["normal_import_method"], "import_normals")
        self.assertEqual(options_report["options"]["normal_generation_method"], "built_in")
        self.assertEqual(options_report["options"]["static_mesh_lod_group"], "SmallProp")
        self.assertEqual(options_report["options"]["vertex_color_import_option"], "override")
        self.assertEqual(options_report["options"]["vertex_override_color"], [0.25, 0.5, 0.75])
        self.assertEqual(options_report["policy"]["nanite_policy"], "disable")
        self.assertEqual(options_report["policy"]["import_lod_policy"], "ignore_lods")
        self.assertEqual(options_report["policy"]["build_reversed_index_buffer"], "enable")

    def test_fbx_importer_coerces_string_bool_options(self):
        prepared = prepare_manifest_for_import(self.manifest_path)
        preset = dict(prepared["preset"])
        preset["fbx_import_materials"] = "true"
        preset["fbx_import_textures"] = "1"
        preset["import_materials"] = "false"
        preset["import_textures"] = "0"
        preset["combine_meshes"] = "no"
        preset["convert_scene"] = "off"
        preset["force_front_x_axis"] = "true"

        report = UnrealStaticMeshFbxImporter(FakeUnreal()).plan_fbx_import_options(prepared["manifest"], preset)

        self.assertTrue(report["options"]["import_materials"])
        self.assertTrue(report["options"]["import_textures"])
        self.assertFalse(report["options"]["combine_meshes"])
        self.assertFalse(report["options"]["convert_scene"])
        self.assertTrue(report["options"]["force_front_x_axis"])

    def test_import_branch_passes_gate_import_options_to_importer(self):
        importer = TrackingFakeImporter()
        report = UnrealStaticMeshImportPipeline(
            importer=importer,
            import_options={
                "import_materials": True,
                "import_textures": True,
                "combine_meshes": True,
                "generate_lightmap_uvs": False,
                "normal_import_method": "compute_normals",
                "static_mesh_lod_group": "LargeProp",
                "one_convex_hull_per_ucx": False,
                "remove_degenerates": False,
                "compute_weighted_normals": True,
                "convert_scene": False,
                "force_front_x_axis": True,
                "convert_scene_unit": False,
                "transform_vertex_to_absolute": False,
                "bake_pivot_in_vertex": True,
                "import_translation": [1.0, 2.0, 3.0],
                "import_rotation": [4.0, 5.0, 6.0],
                "import_uniform_scale": 1.5,
                "normal_generation_method": "built_in",
                "vertex_color_import_option": "override",
                "vertex_override_color": [0.1, 0.2, 0.3],
            },
        ).import_from_manifest(self.manifest_path)

        self.assertTrue(importer.called)
        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertTrue(importer.last_preset["import_materials"])
        self.assertTrue(importer.last_preset["import_textures"])
        self.assertTrue(importer.last_preset["combine_meshes"])
        self.assertFalse(importer.last_preset["generate_lightmap_uvs"])
        self.assertEqual(importer.last_preset["normal_import_method"], "compute_normals")
        self.assertFalse(importer.last_preset["one_convex_hull_per_ucx"])
        self.assertFalse(importer.last_preset["remove_degenerates"])
        self.assertTrue(importer.last_preset["compute_weighted_normals"])
        self.assertFalse(importer.last_preset["convert_scene"])
        self.assertTrue(importer.last_preset["force_front_x_axis"])
        self.assertFalse(importer.last_preset["convert_scene_unit"])
        self.assertFalse(importer.last_preset["transform_vertex_to_absolute"])
        self.assertTrue(importer.last_preset["bake_pivot_in_vertex"])
        self.assertEqual(importer.last_preset["import_translation"], [1.0, 2.0, 3.0])
        self.assertEqual(importer.last_preset["import_rotation"], [4.0, 5.0, 6.0])
        self.assertEqual(importer.last_preset["import_uniform_scale"], 1.5)
        self.assertEqual(importer.last_preset["normal_generation_method"], "built_in")
        self.assertEqual(importer.last_preset["vertex_color_import_option"], "override")
        self.assertEqual(importer.last_preset["vertex_override_color"], [0.1, 0.2, 0.3])
        self.assertEqual(importer.last_manifest["static_mesh_import_policy"]["lod_group"], "LargeProp")
        options_report = report["fbx_import_options_report"]
        self.assertIn("applied_options", options_report)
        self.assertIn("ignored_options", options_report)
        self.assertEqual(options_report["applied_options"][0]["readback"], "compute")
        self.assertEqual(options_report["ignored_options"][0]["property"], "normal_generation_method")

    def test_import_branch_writes_real_fbx_options_report_to_log(self):
        importer = TrackingFakeImporter()
        log_path = os.path.join(self.temp_dir, "import_report.json")

        UnrealStaticMeshImportPipeline(
            importer=importer,
            import_options={
                "normal_import_method": "compute_normals",
                "normal_generation_method": "built_in",
                "vertex_color_import_option": "override",
            },
        ).import_from_manifest(self.manifest_path, log_path)

        written = read_report(log_path)
        self.assertEqual(written["fbx_import_options_report"]["applied_options"][0]["readback"], "compute")
        self.assertEqual(written["fbx_import_options_report"]["ignored_options"][0]["reason"], "test ignored")

    def test_pipeline_returns_success_report(self):
        pipeline = UnrealStaticMeshImportPipeline(importer=FakeImporter())
        log_path = os.path.join(self.temp_dir, "import_report.json")
        report = pipeline.import_from_manifest(self.manifest_path, log_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["imported_assets"], ["/Game/Props/SM_Crate_01"])
        self.assertTrue(os.path.exists(log_path))
        self.assertEqual(report["target_platform"], TARGET_PLATFORM_HIGH_END_MOBILE)
        self.assertEqual(report["resolved_preset"]["name"], IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE)
        self.assertNotIn("\\", report["fbx_path"])
        self.assertEqual(report["materials"][0]["name"], "M_Crate")
        self.assertEqual(report["textures"][0]["usage"], "base_color")
        self.assertEqual(report["package_validation"]["status"], "pass")
        self.assertEqual(report["plugin_content_validation"]["content_mount"], "/AssetForge")
        self.assertIn("/AssetForge/Materials/M_AF_Props_Master", report["plugin_content_validation"]["missing_assets"])
        self.assertEqual(report["texture_import_plan"]["target_dir"], "/Game/Props/Textures")
        self.assertEqual(report["texture_import_plan"]["profile"], "Props_Opaque_PainterUE_ARM")
        self.assertEqual(report["material_profile_validation"]["status"], "warning")
        self.assertIn("normal", report["material_profile_validation"]["missing_usages"])
        self.assertEqual(report["material_binding_plan"]["target_dir"], "/Game/Props/Materials")
        self.assertEqual(report["material_binding_plan"]["master_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertEqual(report["material_binding_plan"]["materials"][0]["target_asset_path"], "/Game/Props/Materials/MI_M_Crate")
        self.assertEqual(report["imported_textures"], [])
        self.assertEqual(report["texture_import_issues"], [])
        self.assertEqual(report["created_material_instances"], [])
        self.assertEqual(report["material_instance_issues"], [])
        self.assertEqual(report["material_asset_bootstrap_report"]["status"], "skipped")
        self.assertEqual(report["material_assignment_report"]["status"], "skipped")
        self.assertEqual(report["material_graph_evidence_report"]["status"], "warning")
        self.assertEqual(report["material_graph_evidence_report"]["real_ue_evidence"], "not_provided")
        self.assertEqual(report["post_import_validation"]["status"], "pass")

    def test_engine_version_preflight_blocks_asset_writes(self):
        importer = TrackingFakeImporter()
        pipeline = UnrealStaticMeshImportPipeline(
            importer=importer,
            engine_version_preflight=BlockingEngineVersionPreflight(),
        )

        report = pipeline.import_from_manifest(self.manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_FAILED)
        self.assertFalse(importer.called)
        self.assertEqual(report["engine_version_preflight"]["status"], "error")
        self.assertIn("5.6", report["issues"][0])

    def test_pipeline_writes_default_import_and_end_to_end_reports(self):
        pipeline = UnrealStaticMeshImportPipeline(importer=FakeImporter())

        report = pipeline.import_from_manifest(self.manifest_path)

        import_report_path = os.path.join(self.temp_dir, "SM_Crate_01_import_report.json")
        end_to_end_path = os.path.join(self.temp_dir, "SM_Crate_01_end_to_end_report.json")
        self.assertTrue(os.path.exists(import_report_path))
        self.assertTrue(os.path.exists(end_to_end_path))
        self.assertEqual(read_report(import_report_path)["status"], report["status"])
        end_to_end_report = read_report(end_to_end_path)
        self.assertEqual(end_to_end_report["stage"], "end_to_end")
        self.assertEqual(end_to_end_report["pipeline_summary"]["import_status"], report["status"])
        self.assertEqual(end_to_end_report["pipeline_summary"]["plugin_content_status"], "warning")
        self.assertEqual(end_to_end_report["pipeline_summary"]["material_assignment_status"], "skipped")
        self.assertTrue(end_to_end_report["pipeline_summary"]["can_accept"])
        self.assertEqual(end_to_end_report["pipeline_summary"]["blocking_error_count"], 0)

    def test_dry_run_returns_skipped_report(self):
        pipeline = UnrealStaticMeshImportPipeline(importer=FakeImporter())
        log_path = os.path.join(self.temp_dir, "dry_run_report.json")
        report = pipeline.dry_run_manifest(self.manifest_path, log_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SKIPPED)
        self.assertEqual(report["message"], "预检查通过，未执行导入")
        self.assertEqual(report["imported_assets"], [])
        self.assertEqual(report["resolved_preset"]["name"], IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE)
        self.assertTrue(os.path.exists(log_path))
        self.assertNotIn("\\", report["fbx_path"])
        self.assertEqual(report["package_validation"]["textures"]["total"], 1)
        self.assertEqual(report["texture_import_plan"]["count"], 0)
        self.assertIn("fbx_import_options_report", report)
        self.assertEqual(report["fbx_import_options_report"]["options"]["fbx_import_type"], "FBXIT_STATIC_MESH")
        self.assertIn("unreal.FbxStaticMeshImportData", report["fbx_import_options_report"]["api"]["static_mesh_import_data"])
        self.assertEqual(report["import_policy_summary"]["status"], "manual_validation_required")
        self.assertIn("static_mesh_import_policy", report["import_policy_summary"])
        self.assertIn("texture_import_policy", report["import_policy_summary"])
        self.assertEqual(report["material_network_summary"]["material_network_status"], "generated_pbr")
        self.assertEqual(report["material_graph_evidence_report"]["real_ue_evidence"], "not_provided")
        self.assertTrue(report["manual_validation_required"])

    def test_texture_import_plan_includes_packaged_texture(self):
        texture_dir = os.path.join(self.temp_dir, "Textures")
        os.makedirs(texture_dir)
        texture_path = os.path.join(texture_dir, "T_Crate_BaseColor.png")
        with open(texture_path, "wb") as stream:
            stream.write(b"fake texture")
        textured_manifest_path = os.path.join(self.temp_dir, "textured_manifest.json")
        textured_manifest = dict(self.manifest)
        textured_manifest["textures"] = [
            {
                "node": "file_basecolor",
                "path": self.fbx_path.replace(".fbx", ".png"),
                "package_path": texture_path,
                "copied": True,
                "source_type": "texture_folder",
                "usage": "base_color",
            }
        ]
        textured_manifest["materials"] = [{"name": "M_Crate", "textures": textured_manifest["textures"]}]
        write_manifest(textured_manifest_path, textured_manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(textured_manifest_path)

        self.assertEqual(report["texture_import_plan"]["count"], 1)
        self.assertEqual(report["texture_import_plan"]["target_dir"], "/Game/Props/Textures")
        self.assertEqual(report["texture_import_plan"]["textures"][0]["parameter"], "BaseColor")
        self.assertTrue(report["texture_import_plan"]["textures"][0]["srgb"])
        self.assertEqual(report["texture_import_plan"]["textures"][0]["source_type"], "texture_folder")
        self.assertEqual(
            report["texture_import_plan"]["textures"][0]["target_asset_path"],
            "/Game/Props/Textures/T_Crate_BaseColor",
        )
        self.assertEqual(
            report["material_binding_plan"]["materials"][0]["slots"]["base_color"],
            "/Game/Props/Textures/T_Crate_BaseColor",
        )
        self.assertEqual(
            report["material_binding_plan"]["materials"][0]["texture_parameters"]["BaseColor"],
            "/Game/Props/Textures/T_Crate_BaseColor",
        )
        self.assertEqual(report["texture_import_plan"]["textures"][0]["channels"], {})

    def test_dry_run_includes_offline_texture_policy_preview(self):
        texture_path = self._write_packaged_texture()
        manifest_path = self._write_textured_manifest(
            texture_path,
            texture_import_policy={
                "virtual_texture_policy": "auto",
                "texture_streaming_policy": "never_stream",
                "texture_group": "project_default",
            },
        )

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(manifest_path)
        policy_report = report["texture_import_policy_report"]["actions"][0]["policy_report"]

        self.assertEqual(report["texture_import_policy_report"]["mode"], "offline_preview")
        self.assertEqual(policy_report["resolved_virtual_texture_policy"], "auto_resolved_force_off")
        self.assertIn({"property": "virtual_texture_streaming", "value": False}, policy_report["applied"])
        self.assertIn({"property": "never_stream", "value": True}, policy_report["applied"])
        self.assertFalse(policy_report["actual_policy"]["effective_virtual_texture"])
        self.assertTrue(policy_report["actual_policy"]["never_stream"])
        self.assertIn("VT=auto", policy_report["user_message"])

    def test_dry_run_logs_offline_texture_policy_preview(self):
        old_log_root = os.environ.get("ASSET_FORGE_LOG_ROOT")
        os.environ["ASSET_FORGE_LOG_ROOT"] = self.temp_dir
        try:
            texture_path = self._write_packaged_texture()
            manifest_path = self._write_textured_manifest(
                texture_path,
                texture_import_policy={
                    "virtual_texture_policy": "auto",
                    "texture_streaming_policy": "never_stream",
                    "texture_group": "project_default",
                },
            )

            UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(manifest_path)

            entries = unreal_operation_logger.read_latest_log_tail(self.temp_dir, 20)
            preview_entries = [entry for entry in entries if entry.get("operation") == "unreal_texture_policy_preview"]
            self.assertTrue(preview_entries)
            outputs = preview_entries[0]["outputs"]
            self.assertEqual(outputs["resolved_virtual_texture_policy"], "auto_resolved_force_off")
            self.assertEqual(outputs["actual_policy_source"], "offline_expected_from_requested_policy")
            self.assertIn("actual_policy", outputs)
            self.assertIn("user_message", outputs)
        finally:
            if old_log_root is None:
                os.environ.pop("ASSET_FORGE_LOG_ROOT", None)
            else:
                os.environ["ASSET_FORGE_LOG_ROOT"] = old_log_root

    def test_texture_import_plan_deduplicates_target_asset_names(self):
        texture_dir = os.path.join(self.temp_dir, "Textures")
        os.makedirs(texture_dir)
        first = os.path.join(texture_dir, "T_Crate_BaseColor.png")
        second_dir = os.path.join(texture_dir, "Nested")
        os.makedirs(second_dir)
        second = os.path.join(second_dir, "T_Crate_BaseColor.png")
        for path in [first, second]:
            with open(path, "wb") as stream:
                stream.write(b"fake texture")
        manifest = dict(self.manifest)
        manifest["textures"] = [
            {"node": "base_a", "path": first, "package_path": first, "copied": True, "usage": "base_color"},
            {"node": "base_b", "path": second, "package_path": second, "copied": True, "usage": "base_color"},
        ]
        manifest["materials"] = [{"name": "M_Crate", "textures": manifest["textures"]}]
        manifest_path = os.path.join(self.temp_dir, "duplicate_texture_manifest.json")
        write_manifest(manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(manifest_path)

        names = [texture["asset_name"] for texture in report["texture_import_plan"]["textures"]]
        self.assertEqual(names, ["T_Crate_BaseColor", "T_Crate_BaseColor_2"])

    def test_binding_plan_carries_packed_texture_channels_and_existing_strategy(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        manifest = dict(self.manifest)
        manifest["existing_material_strategy"] = "skip"
        manifest["textures"] = [
            {
                "node": "file_arm",
                "path": texture_path,
                "package_path": texture_path,
                "copied": True,
                "usage": "packed_arm",
            }
        ]
        manifest["materials"] = [{"name": "M_Crate", "textures": manifest["textures"]}]
        write_manifest(textured_manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(textured_manifest_path)

        self.assertEqual(report["material_binding_plan"]["existing_material_strategy"], "skip")
        self.assertEqual(report["texture_import_plan"]["textures"][0]["channels"]["r"], "ao")
        self.assertEqual(report["material_binding_plan"]["materials"][0]["channel_mappings"]["packed_arm"]["g"], "roughness")
        self.assertEqual(report["material_binding_plan"]["materials"][0]["scalar_parameters"]["packed_arm_R_ao"], 1.0)

    def test_binding_plan_declares_real_switches_for_masked_base_alpha(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        manifest = dict(self.manifest)
        manifest["material_profile"] = "Props_Masked_PainterUE_ARM"
        manifest["textures"] = [
            {
                "node": "file_basecolor",
                "path": texture_path,
                "package_path": texture_path,
                "copied": True,
                "usage": "base_color",
            }
        ]
        manifest["materials"] = [{"name": "M_Crate", "textures": manifest["textures"]}]
        write_manifest(textured_manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(textured_manifest_path)
        material = report["material_binding_plan"]["materials"][0]

        self.assertTrue(material["static_switch_parameters"]["UseOpacityMask"])
        self.assertFalse(material["static_switch_parameters"]["UseSeparateOpacityMask"])
        self.assertEqual(material["binding_contract"]["opacity_source"], "base_color_alpha")

    def test_binding_plan_declares_separate_mask_and_emissive_contracts(self):
        texture_path = self._write_packaged_texture()
        mask_path = os.path.join(self.temp_dir, "Textures", "T_Crate_OpacityMask.png")
        emissive_path = os.path.join(self.temp_dir, "Textures", "T_Crate_Emissive.png")
        for path in [mask_path, emissive_path]:
            with open(path, "wb") as stream:
                stream.write(b"fake texture")
        textured_manifest_path = self._write_textured_manifest(texture_path)
        manifest = dict(self.manifest)
        manifest["material_profile"] = "Props_Masked_PainterUE_ARM"
        manifest["textures"] = [
            {"node": "file_basecolor", "path": texture_path, "package_path": texture_path, "copied": True, "usage": "base_color"},
            {"node": "file_mask", "path": mask_path, "package_path": mask_path, "copied": True, "usage": "opacity_mask"},
            {"node": "file_emissive", "path": emissive_path, "package_path": emissive_path, "copied": True, "usage": "emissive"},
        ]
        manifest["materials"] = [{"name": "M_Crate", "textures": manifest["textures"]}]
        write_manifest(textured_manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(textured_manifest_path)
        material = report["material_binding_plan"]["materials"][0]

        self.assertTrue(material["static_switch_parameters"]["UseOpacityMask"])
        self.assertTrue(material["static_switch_parameters"]["UseSeparateOpacityMask"])
        self.assertTrue(material["static_switch_parameters"]["UseEmissive"])
        self.assertEqual(material["binding_contract"]["opacity_source"], "separate_opacity_mask")
        self.assertFalse(material["texture_contracts"]["OpacityMask"]["srgb"])
        self.assertEqual(material["texture_contracts"]["OpacityMask"]["compression"], "masks")
        self.assertTrue(material["texture_contracts"]["Emissive"]["srgb"])

    def test_binding_plan_splits_multi_texture_sets_by_material_name(self):
        texture_dir = os.path.join(self.temp_dir, "Textures")
        if not os.path.exists(texture_dir):
            os.makedirs(texture_dir)
        manifest = dict(self.manifest)
        manifest["textures"] = []
        for set_name in ["a1", "d1"]:
            for usage, suffix in [("base_color", "BaseColor"), ("normal", "Normal"), ("packed_arm", "OcclusionRoughnessMetallic")]:
                path = os.path.join(texture_dir, "T_HK416_D_B_{0}_{1}.png".format(set_name, suffix))
                with open(path, "wb") as stream:
                    stream.write(b"fake texture")
                manifest["textures"].append(
                    {
                        "path": path,
                        "package_path": path,
                        "copied": True,
                        "source_type": "texture_folder",
                        "usage": usage,
                        "selected_texture_set": "HK416_D_B_{0}".format(set_name),
                    }
                )
        manifest["materials"] = [{"name": "B_a1", "textures": []}, {"name": "B_d1", "textures": []}]
        manifest_path = os.path.join(self.temp_dir, "multi_texture_set_manifest.json")
        write_manifest(manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(manifest_path)
        by_name = dict((item["material_name"], item) for item in report["material_binding_plan"]["materials"])

        self.assertEqual(by_name["B_a1"]["texture_set"], "a1")
        self.assertIn("T_HK416_D_B_a1_BaseColor", by_name["B_a1"]["texture_parameters"]["BaseColor"])
        self.assertIn("T_HK416_D_B_a1_Normal", by_name["B_a1"]["texture_parameters"]["Normal"])
        self.assertIn("T_HK416_D_B_a1_OcclusionRoughnessMetallic", by_name["B_a1"]["texture_parameters"]["ARM"])
        self.assertIn("T_HK416_D_B_d1_BaseColor", by_name["B_d1"]["texture_parameters"]["BaseColor"])
        self.assertFalse(by_name["B_a1"]["binding_warnings"])

    def test_binding_plan_reuses_material_instance_for_identical_texture_signature(self):
        texture_path = self._write_packaged_texture()
        manifest = dict(self.manifest)
        shared_textures = [
            {
                "node": "file_basecolor",
                "path": texture_path,
                "package_path": texture_path,
                "copied": True,
                "usage": "base_color",
            }
        ]
        manifest["textures"] = list(shared_textures)
        manifest["materials"] = [
            {"name": "B_a1", "textures": list(shared_textures)},
            {"name": "B_attachment", "textures": list(shared_textures)},
        ]
        manifest_path = os.path.join(self.temp_dir, "shared_texture_material_manifest.json")
        write_manifest(manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(manifest_path)
        plan = report["material_binding_plan"]
        by_name = dict((item["material_name"], item) for item in plan["materials"])

        self.assertEqual(plan["count"], 2)
        self.assertEqual(plan["unique_material_instance_count"], 1)
        self.assertEqual(plan["material_instance_reuse_count"], 1)
        self.assertEqual(by_name["B_attachment"]["target_asset_path"], by_name["B_a1"]["target_asset_path"])
        self.assertEqual(by_name["B_attachment"]["material_instance_reuse_role"], "alias")
        self.assertEqual(by_name["B_attachment"]["material_instance_reuse_source"], "B_a1")

    def test_material_profile_selects_masked_parent_and_parameters(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        manifest = dict(self.manifest)
        manifest["material_profile"] = "Props_Masked_PainterUE_ARM"
        manifest["textures"] = [
            {
                "node": "file_basecolor",
                "path": self.fbx_path.replace(".fbx", ".png"),
                "package_path": texture_path,
                "copied": True,
                "usage": "base_color",
            }
        ]
        manifest["materials"] = [{"name": "M_Crate", "textures": manifest["textures"]}]
        write_manifest(textured_manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(textured_manifest_path)

        self.assertEqual(report["material_binding_plan"]["profile"], "Props_Masked_PainterUE_ARM")
        self.assertEqual(report["material_binding_plan"]["master_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertEqual(report["material_binding_plan"]["render_mode"], "masked")
        self.assertEqual(report["material_binding_plan"]["materials"][0]["scalar_parameters"]["OpacityClipValue"], 0.333)

    def test_material_and_texture_target_names_are_sanitized(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        manifest = dict(self.manifest)
        manifest["textures"] = [
            {
                "node": "file_basecolor",
                "path": self.fbx_path.replace(".fbx", ".png"),
                "package_path": os.path.join(self.temp_dir, "Textures", "T Crate.BaseColor.png"),
                "copied": True,
                "usage": "base_color",
            }
        ]
        with open(manifest["textures"][0]["package_path"], "wb") as stream:
            stream.write(b"fake")
        manifest["materials"] = [{"name": "Wood Crate.Material", "textures": manifest["textures"]}]
        write_manifest(textured_manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(textured_manifest_path)

        self.assertEqual(report["texture_import_plan"]["textures"][0]["asset_name"], "T_Crate_BaseColor")
        self.assertEqual(report["material_binding_plan"]["materials"][0]["target_asset_name"], "MI_Wood_Crate_Material")
        self.assertEqual(report["material_binding_plan"]["materials"][0]["target_asset_path"], "/Game/Props/Materials/MI_Wood_Crate_Material")

    def test_pipeline_imports_planned_textures_without_blocking_mesh(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        texture_importer = FakeTextureImporter(["/Game/Props/Textures/T_Crate_BaseColor.T_Crate_BaseColor"])
        texture_importer.last_configuration_report = {"status": "success", "configured": [{"asset_path": "/Game/Props/Textures/T_Crate_BaseColor"}], "issues": []}

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=texture_importer,
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["imported_textures"], ["/Game/Props/Textures/T_Crate_BaseColor.T_Crate_BaseColor"])
        self.assertEqual(texture_importer.plans[0]["count"], 1)
        self.assertEqual(report["texture_configuration_report"]["status"], "success")
        self.assertEqual(report["texture_import_policy_report"]["status"], "success")
        self.assertTrue(report["import_policy_summary"]["content_import_policy"]["import_textures"]["enabled"])

    def test_pipeline_respects_import_textures_gate_option(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        texture_importer = FakeTextureImporter(["/Game/Props/Textures/T_Crate_BaseColor.T_Crate_BaseColor"])

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=texture_importer,
            import_options={"import_textures": False},
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(texture_importer.plans, [])
        self.assertEqual(report["imported_textures"], [])
        self.assertEqual(report["texture_import_policy_report"]["status"], "skipped")
        self.assertIn("import_textures=false", report["texture_import_policy_report"]["skip_reason"])
        self.assertFalse(report["import_policy_summary"]["content_import_policy"]["import_textures"]["enabled"])
        self.assertEqual(report["import_policy_summary"]["content_import_policy"]["import_textures"]["source"], "gate_override")

    def test_pipeline_keeps_fbx_texture_option_independent_from_af_texture_import(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        texture_importer = FakeTextureImporter(["/Game/Props/Textures/T_Crate_BaseColor.T_Crate_BaseColor"])

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=texture_importer,
            import_options={"import_textures": False, "fbx_import_textures": True},
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertTrue(report["fbx_import_options_report"]["options"]["import_textures"])
        self.assertEqual(texture_importer.plans, [])
        self.assertEqual(report["imported_textures"], [])
        self.assertFalse(report["import_policy_summary"]["content_import_policy"]["import_textures"]["enabled"])

    def test_pipeline_keeps_af_texture_import_independent_from_fbx_texture_option(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        texture_importer = FakeTextureImporter(["/Game/Props/Textures/T_Crate_BaseColor.T_Crate_BaseColor"])

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=texture_importer,
            import_options={"import_textures": True, "fbx_import_textures": False},
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertFalse(report["fbx_import_options_report"]["options"]["import_textures"])
        self.assertEqual(texture_importer.plans[0]["count"], 1)
        self.assertEqual(report["imported_textures"], ["/Game/Props/Textures/T_Crate_BaseColor.T_Crate_BaseColor"])
        self.assertTrue(report["import_policy_summary"]["content_import_policy"]["import_textures"]["enabled"])

    def test_pipeline_creates_material_instances_without_blocking_mesh(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        material_creator = FakeMaterialInstanceCreator(["/Game/Props/Materials/MI_M_Crate"])

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=FakeTextureImporter([]),
            material_instance_creator=material_creator,
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["created_material_instances"], ["/Game/Props/Materials/MI_M_Crate"])
        material = material_creator.plans[0]["materials"][0]
        self.assertEqual(material["parent_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertEqual(material["selected_material_variant"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertIn("base_color", material["detected_features"])
        self.assertEqual(material["parameter_api_mapping"]["BaseColor"], "Base Color")

    def test_pipeline_respects_import_materials_gate_option(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        material_creator = FakeMaterialInstanceCreator(["/Game/Props/Materials/MI_M_Crate"])
        material_assigner = FakeMaterialSlotAssigner()

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=FakeTextureImporter([]),
            material_instance_creator=material_creator,
            material_slot_assigner=material_assigner,
            import_options={"import_materials": False},
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(material_creator.plans, [])
        self.assertEqual(material_assigner.reports, [])
        self.assertEqual(report["created_material_instances"], [])
        self.assertEqual(report["material_instance_policy_report"]["status"], "skipped")
        self.assertIn("import_materials=false", report["material_instance_policy_report"]["skip_reason"])
        self.assertIn("import_materials=false", report["material_assignment_report"]["issues"][0])
        self.assertFalse(report["import_policy_summary"]["content_import_policy"]["import_materials"]["enabled"])
        self.assertEqual(report["import_policy_summary"]["content_import_policy"]["import_materials"]["source"], "gate_override")

    def test_pipeline_keeps_standard_parent_for_project_default_vt_textures(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        texture_importer = FakeTextureImporter(["/Game/Props/Textures/T_Crate_BaseColor.T_Crate_BaseColor"])
        texture_importer.last_configuration_report = {
            "status": "success",
            "configured": [
                {
                    "asset_path": "/Game/Props/Textures/T_Crate_BaseColor",
                    "policy_report": {
                        "requested_policy": {"virtual_texture_policy": "project_default"},
                        "actual_policy": {"effective_virtual_texture": True},
                    },
                }
            ],
            "issues": [],
        }
        material_creator = FakeMaterialInstanceCreator(["/Game/Props/Materials/MI_M_Crate"])

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=texture_importer,
            material_instance_creator=material_creator,
        ).import_from_manifest(textured_manifest_path)
        material = material_creator.plans[0]["materials"][0]

        self.assertEqual(material["parent_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertFalse(material["uses_virtual_texture_sampling"])
        self.assertEqual(report["material_variant_selection"]["status"], "standard_variant_selected")
        self.assertEqual(report["material_sampler_policy_validation"]["status"], "warning")

    def test_pipeline_assigns_created_material_instances_to_static_mesh_slots(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        material_creator = FakeMaterialInstanceCreator(["/Game/Props/Materials/MI_M_Crate"])
        material_assigner = FakeMaterialSlotAssigner()

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=FakeTextureImporter([]),
            material_instance_creator=material_creator,
            material_slot_assigner=material_assigner,
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["material_assignment_report"]["status"], "success")
        self.assertEqual(report["material_graph_evidence_report"]["status"], "warning")
        self.assertTrue(any(item.get("id") == "slot_binding" and item.get("status") == "pass" for item in report["material_graph_evidence_report"]["checks"]))
        self.assertEqual(report["material_assignment_report"]["assigned"][0]["slot_index"], 0)
        self.assertEqual(
            report["material_assignment_report"]["assigned"][0]["material_instance"],
            "/Game/Props/Materials/MI_M_Crate",
        )

    def test_pipeline_attaches_real_material_graph_evidence_when_collected(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=FakeTextureImporter([]),
            material_instance_creator=FakeMaterialInstanceCreator(["/Game/Props/Materials/MI_M_Crate"]),
            material_slot_assigner=FakeMaterialSlotAssigner(),
            material_evidence_collector=FakeMaterialEvidenceCollector(),
        ).import_from_manifest(textured_manifest_path)

        evidence = report["material_graph_evidence_report"]
        self.assertEqual(evidence["real_ue_evidence"], "provided")
        self.assertTrue(any(item.get("id") == "compile_log_evidence" and item.get("status") == "pass" for item in evidence["checks"]))
        self.assertTrue(any(item.get("id") == "real_ue_material_graph" and item.get("status") == "pass" for item in evidence["checks"]))
        self.assertFalse(any(item.get("id") == "compile_log_evidence" and item.get("status") == "warning" for item in evidence["checks"]))
        self.assertFalse(any(item.get("id") == "real_ue_material_graph" and item.get("status") == "warning" for item in evidence["checks"]))

    def test_material_assignment_warning_does_not_fail_static_mesh_import(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=FakeTextureImporter([]),
            material_instance_creator=FakeMaterialInstanceCreator(["/Game/Props/Materials/MI_M_Crate"]),
            material_slot_assigner=FailingMaterialSlotAssigner(),
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["material_assignment_report"]["status"], "warning")
        self.assertTrue(report["material_assignment_report"]["issues"])

        summary = summarize_pipeline(import_report=report)
        self.assertEqual(summary["material_assignment_status"], "warning")
        self.assertGreater(summary["warning_count"], 0)
        self.assertEqual(summary["error_count"], 0)

    def test_summary_includes_texture_configuration_warnings(self):
        summary = summarize_pipeline(
            import_report={
                "status": UNREAL_IMPORT_STATUS_SUCCESS,
                "texture_configuration_report": {
                    "status": "warning",
                    "configured": [{"asset_path": "/Game/Props/Textures/T_Crate_BaseColor"}],
                    "issues": ["无法加载导入后的贴图资产：/Game/Props/Textures/T_Crate_Normal"],
                },
            }
        )

        self.assertEqual(summary["texture_configuration_status"], "warning")
        self.assertEqual(summary["configured_texture_count"], 1)
        self.assertEqual(summary["warning_count"], 1)
        self.assertEqual(summary["warnings"][0]["source"], "texture_configuration")

    def test_summary_includes_vt_sampler_mismatch_warning(self):
        summary = summarize_pipeline(
            import_report={
                "status": UNREAL_IMPORT_STATUS_SUCCESS,
                "material_sampler_policy_validation": {
                    "status": "warning",
                    "checks": [
                        {
                            "id": "vt_sampler_mismatch",
                            "status": "warning",
                            "message": "有效贴图为 Virtual Texture，但当前母材质计划仍使用普通 TextureSampleParameter2D。",
                        }
                    ],
                },
            }
        )

        self.assertEqual(summary["material_sampler_policy_status"], "warning")
        self.assertEqual(summary["warning_count"], 1)
        self.assertEqual(summary["warnings"][0]["source"], "material_sampler_policy")

    def test_pipeline_logs_texture_policy_and_sampler_validation_events(self):
        old_log_root = os.environ.get("ASSET_FORGE_LOG_ROOT")
        os.environ["ASSET_FORGE_LOG_ROOT"] = self.temp_dir
        try:
            texture_path = self._write_packaged_texture()
            manifest_path = self._write_textured_manifest(
                texture_path,
                texture_import_policy={"virtual_texture_policy": "auto", "texture_streaming_policy": "never_stream", "texture_group": "project_default"},
            )

            report = UnrealStaticMeshImportPipeline(
                importer=FakeImporter(),
                texture_importer=UnrealTextureImporter(FakeUnreal()),
                material_instance_creator=FakeMaterialInstanceCreator([]),
            ).import_from_manifest(manifest_path)

            self.assertEqual(report["material_sampler_policy_validation"]["status"], "pass")
            configured = report["texture_configuration_report"]["configured"][0]
            policy_report = configured["policy_report"]
            self.assertEqual(policy_report["resolved_virtual_texture_policy"], "auto_resolved_force_off")
            self.assertFalse(policy_report["actual_policy"]["effective_virtual_texture"])

            entries = unreal_operation_logger.read_latest_log_tail(self.temp_dir, 20)
            operations = [entry.get("operation") for entry in entries]
            self.assertIn("unreal_import_entry", operations)
            self.assertIn("unreal_texture_policy_application", operations)
            self.assertIn("unreal_material_sampler_policy_validation", operations)
            policy_entries = [entry for entry in entries if entry.get("operation") == "unreal_texture_policy_application"]
            self.assertTrue(any(item.get("outputs", {}).get("resolved_virtual_texture_policy") == "auto_resolved_force_off" for item in policy_entries))
        finally:
            if old_log_root is None:
                os.environ.pop("ASSET_FORGE_LOG_ROOT", None)
            else:
                os.environ["ASSET_FORGE_LOG_ROOT"] = old_log_root

    def test_pipeline_keeps_standard_parent_for_project_default_real_texture_policy(self):
        texture_path = self._write_packaged_texture()
        manifest_path = self._write_textured_manifest(
            texture_path,
            texture_import_policy={"virtual_texture_policy": "project_default", "texture_streaming_policy": "streaming", "texture_group": "project_default"},
        )
        material_creator = FakeMaterialInstanceCreator(["/Game/Props/Materials/MI_M_Crate"])

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=FakeVTTextureImporter("/Game/Props/Textures/T_Crate_BaseColor"),
            material_instance_creator=material_creator,
        ).import_from_manifest(manifest_path)

        material = report["material_binding_plan"]["materials"][0]
        self.assertEqual(material["parent_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertFalse(material["uses_virtual_texture_sampling"])
        self.assertEqual(report["material_variant_selection"]["status"], "standard_variant_selected")
        self.assertEqual(report["material_sampler_policy_validation"]["status"], "warning")
        self.assertEqual(material_creator.plans[0]["materials"][0]["parent_material"], "/AssetForge/Materials/M_AF_Props_Master")

    def test_pipeline_blocks_force_on_vt_when_verified_vt_parent_is_unavailable(self):
        texture_path = self._write_packaged_texture()
        manifest_path = self._write_textured_manifest(
            texture_path,
            texture_import_policy={"virtual_texture_policy": "force_on", "texture_streaming_policy": "streaming", "texture_group": "project_default"},
        )
        material_creator = FakeMaterialInstanceCreator(["/Game/Props/Materials/MI_M_Crate"])

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=UnrealTextureImporter(FakeUnreal()),
            material_instance_creator=material_creator,
        ).import_from_manifest(manifest_path)

        material = report["material_binding_plan"]["materials"][0]
        self.assertEqual(report["material_variant_selection"]["status"], "vt_sampler_required_unavailable")
        self.assertTrue(material["requires_virtual_texture_sampling"])
        self.assertFalse(material["uses_virtual_texture_sampling"])
        self.assertEqual(material["parent_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertEqual(report["created_material_instances"], [])
        self.assertTrue(report["material_instance_issues"])
        self.assertEqual(material_creator.plans, [])

    def test_material_instance_error_does_not_fail_static_mesh_import(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=FakeTextureImporter([]),
            material_instance_creator=FailingMaterialInstanceCreator(),
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["created_material_instances"], [])
        self.assertTrue(report["material_instance_issues"])

    def test_missing_plugin_parent_skips_material_instance_creation(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        material_creator = AvailableMaterialInstanceCreator()

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=FakeTextureImporter([]),
            material_instance_creator=material_creator,
            plugin_content_bootstrap=MissingPluginContentBootstrap(),
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["created_material_instances"], [])
        self.assertFalse(material_creator.called)
        self.assertTrue(report["material_instance_issues"])
        self.assertEqual(report["parent_material_validation"]["status"], "warning")
        self.assertTrue(report["summary"]["can_accept"])
        self.assertEqual(report["material_assignment_report"]["status"], "skipped")

    def test_auto_material_bootstrap_refreshes_plugin_validation_before_instances(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        plugin_bootstrap = RefreshingPluginContentBootstrap()
        material_creator = FakeMaterialInstanceCreator(["/Game/Props/Materials/MI_M_Crate"])

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=FakeTextureImporter([]),
            material_instance_creator=material_creator,
            plugin_content_bootstrap=plugin_bootstrap,
            material_asset_bootstrap=FakeMaterialAssetBootstrap(),
            auto_bootstrap_material_assets=True,
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["material_asset_bootstrap_report"]["status"], "success")
        self.assertEqual(report["plugin_content_validation"]["status"], "pass")
        self.assertEqual(report["created_material_instances"], ["/Game/Props/Materials/MI_M_Crate"])
        self.assertEqual(plugin_bootstrap.calls, 2)

    def test_material_instance_creator_configures_unreal_asset(self):
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        fake_unreal.EditorAssetLibrary.loaded = []
        fake_unreal.MaterialEditingLibrary.texture_calls = []
        fake_unreal.MaterialEditingLibrary.scalar_calls = []
        fake_unreal.MaterialEditingLibrary.vector_calls = []
        fake_unreal.MaterialEditingLibrary.static_switch_calls = []
        plan = {
            "materials": [
                {
                    "material_name": "M_Crate",
                    "parent_material": "/AssetForge/Materials/M_AF_Props_Opaque",
                    "target_asset_path": "/Game/Props/Materials/M_Crate",
                    "texture_parameters": {"BaseColor": "/Game/Props/Textures/T_Crate_BaseColor"},
                    "scalar_parameters": {"EmissiveIntensity": 1.0},
                    "vector_parameters": {"BaseColorTint": [1.0, 0.9, 0.8, 1.0]},
                    "static_switch_parameters": {"UseEmissive": True},
                }
            ]
        }

        created = UnrealMaterialInstanceCreator(fake_unreal).create_from_plan(plan)

        asset = fake_unreal.AssetToolsHelpers.asset_tools.assets[0]
        self.assertEqual(created, ["/Game/Props/Materials/M_Crate"])
        self.assertEqual(asset.asset_name, "M_Crate")
        self.assertEqual(asset.package_path, "/Game/Props/Materials")
        self.assertEqual(asset.parent, "asset:/AssetForge/Materials/M_AF_Props_Opaque")
        self.assertEqual(fake_unreal.MaterialEditingLibrary.texture_calls[0][1], "BaseColor")
        self.assertEqual(fake_unreal.MaterialEditingLibrary.scalar_calls[0][1], "EmissiveIntensity")
        self.assertEqual(fake_unreal.MaterialEditingLibrary.vector_calls[0][1], "BaseColorTint")
        self.assertIsInstance(fake_unreal.MaterialEditingLibrary.vector_calls[0][2], fake_unreal.LinearColor)
        self.assertEqual(fake_unreal.MaterialEditingLibrary.static_switch_calls[0][1], "UseEmissive")
        self.assertEqual(UnrealMaterialInstanceCreator(fake_unreal).last_parameter_report["status"], "skipped")

    def test_material_instance_creator_skips_duplicate_target_paths_in_plan(self):
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        fake_unreal.EditorAssetLibrary.assets = {}
        plan = {
            "materials": [
                {
                    "material_name": "B_a1",
                    "parent_material": "/AssetForge/Materials/M_AF_Props_Opaque",
                    "target_asset_path": "/Game/Props/Materials/MI_B_a1",
                },
                {
                    "material_name": "B_attachment",
                    "parent_material": "/AssetForge/Materials/M_AF_Props_Opaque",
                    "target_asset_path": "/Game/Props/Materials/MI_B_a1",
                },
            ]
        }
        creator = UnrealMaterialInstanceCreator(fake_unreal)

        created = creator.create_from_plan(plan)

        self.assertEqual(created, ["/Game/Props/Materials/MI_B_a1"])
        self.assertEqual(len(fake_unreal.AssetToolsHelpers.asset_tools.assets), 1)
        self.assertEqual(creator.last_creation_report["actions"][-1]["action"], "reused_in_plan")

    def test_material_instance_creator_records_parameter_report(self):
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        fake_unreal.MaterialEditingLibrary.texture_calls = []
        fake_unreal.MaterialEditingLibrary.scalar_calls = []
        fake_unreal.MaterialEditingLibrary.static_switch_calls = []
        creator = UnrealMaterialInstanceCreator(fake_unreal)
        plan = {
            "materials": [
                {
                    "material_name": "M_Crate",
                    "parent_material": "/AssetForge/Materials/M_AF_Props_Opaque",
                    "target_asset_path": "/Game/Props/Materials/M_Crate",
                    "texture_parameters": {"BaseColor": "/Game/Props/Textures/T_Crate_BaseColor"},
                    "scalar_parameters": {"EmissiveIntensity": 2.0},
                    "static_switch_parameters": {"UseEmissive": True},
                }
            ]
        }

        creator.create_from_plan(plan)

        self.assertEqual(creator.last_parameter_report["texture_parameters"][0]["name"], "BaseColor")
        self.assertEqual(creator.last_parameter_report["scalar_parameters"][0]["value"], 2.0)
        self.assertEqual(creator.last_parameter_report["static_switch_parameters"][0]["name"], "UseEmissive")

    def test_material_instance_creator_reports_missing_texture_setter_without_crashing(self):
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        original_setter = fake_unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value
        delattr(fake_unreal.MaterialEditingLibrary, "set_material_instance_texture_parameter_value")
        try:
            creator = UnrealMaterialInstanceCreator(fake_unreal)
            creator.create_from_plan(
                {
                    "materials": [
                        {
                            "material_name": "M_Crate",
                            "parent_material": "/AssetForge/Materials/M_AF_Props_Opaque",
                            "target_asset_path": "/Game/Props/Materials/M_Crate_MissingTextureSetter",
                            "texture_parameters": {"BaseColor": "/Game/Props/Textures/T_Crate_BaseColor"},
                        }
                    ]
                }
            )
        finally:
            fake_unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value = original_setter

        texture_report = creator.last_parameter_report["texture_parameters"][0]
        self.assertFalse(texture_report["applied"])
        self.assertEqual(texture_report["reason"], "texture parameter setter unavailable")

    def test_material_instance_creator_marks_texture_parameter_false_as_failed(self):
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        original_setter = fake_unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value

        def _return_false(material_instance, name, texture_asset):
            return False

        fake_unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value = staticmethod(_return_false)
        try:
            creator = UnrealMaterialInstanceCreator(fake_unreal)
            creator.create_from_plan(
                {
                    "materials": [
                        {
                            "material_name": "M_Crate",
                            "parent_material": "/AssetForge/Materials/M_AF_Props_Opaque",
                            "target_asset_path": "/Game/Props/Materials/M_Crate",
                            "texture_parameters": {"BaseColor": "/Game/Props/Textures/T_Crate_BaseColor"},
                        }
                    ]
                }
            )
        finally:
            fake_unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value = original_setter

        texture_report = creator.last_parameter_report["texture_parameters"][0]
        self.assertFalse(texture_report["applied"])
        self.assertIn("parameter slot", texture_report["reason"])

    def test_material_instance_creator_requires_readback_when_setter_returns_none(self):
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        original_setter = fake_unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value

        def _return_none(material_instance, name, texture_asset):
            return None

        fake_unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value = staticmethod(_return_none)
        try:
            creator = UnrealMaterialInstanceCreator(fake_unreal)
            creator.create_from_plan(
                {
                    "materials": [
                        {
                            "material_name": "M_Crate",
                            "parent_material": "/AssetForge/Materials/M_AF_Props_Opaque",
                            "target_asset_path": "/Game/Props/Materials/M_Crate_NoneReturn",
                            "texture_parameters": {"BaseColor": "/Game/Props/Textures/T_Crate_BaseColor"},
                        }
                    ]
                }
            )
        finally:
            fake_unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value = original_setter

        texture_report = creator.last_parameter_report["texture_parameters"][0]
        self.assertFalse(texture_report["applied"])
        self.assertEqual(creator.last_parameter_report["failed_count"], 1)

    def test_material_instance_creator_reuses_existing_asset_by_default(self):
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        existing = FakeMaterialInstance()
        fake_unreal.EditorAssetLibrary.assets = {
            "/AssetForge/Materials/M_AF_Props_Opaque": "parent",
            "/Game/Props/Materials/M_Crate": existing,
        }
        creator = UnrealMaterialInstanceCreator(fake_unreal)

        created = creator.create_from_plan(
            {
                "materials": [
                    {
                        "material_name": "M_Crate",
                        "parent_material": "/AssetForge/Materials/M_AF_Props_Opaque",
                        "target_asset_path": "/Game/Props/Materials/M_Crate",
                    }
                ]
            }
        )

        self.assertEqual(created, ["/Game/Props/Materials/M_Crate"])
        self.assertEqual(creator.last_creation_report["actions"][0]["action"], "reused")
        self.assertEqual(fake_unreal.AssetToolsHelpers.asset_tools.assets, [])

    def test_material_instance_creator_skips_existing_asset_when_requested(self):
        fake_unreal = FakeUnreal()
        existing = FakeMaterialInstance()
        fake_unreal.EditorAssetLibrary.assets = {
            "/AssetForge/Materials/M_AF_Props_Opaque": "parent",
            "/Game/Props/Materials/M_Crate": existing,
        }
        creator = UnrealMaterialInstanceCreator(fake_unreal)

        created = creator.create_from_plan(
            {
                "existing_material_strategy": "skip",
                "materials": [
                    {
                        "material_name": "M_Crate",
                        "parent_material": "/AssetForge/Materials/M_AF_Props_Opaque",
                        "target_asset_path": "/Game/Props/Materials/M_Crate",
                    }
                ],
            }
        )

        self.assertEqual(created, [])
        self.assertEqual(creator.last_creation_report["actions"][0]["action"], "skipped")

    def test_summary_includes_export_texture_and_profile_warnings(self):
        summary = summarize_pipeline(
            export_report={
                "validation": {"status": "pass"},
                "texture_folder_scan": {"issues": [{"message": "缺少必需贴图类型：normal"}]},
                "material_profile_validation": {
                    "status": "warning",
                    "checks": [
                        {
                            "id": "required_texture",
                            "status": "warning",
                            "message": "缺少必需贴图：normal",
                        }
                    ],
                },
            },
            import_report={"status": UNREAL_IMPORT_STATUS_SUCCESS},
        )

        self.assertEqual(summary["export_material_profile_status"], "warning")
        self.assertEqual(summary["warning_count"], 2)

    def test_material_slot_assigner_configures_unreal_static_mesh(self):
        fake_unreal = FakeUnreal()
        static_mesh = FakeStaticMesh(["M_Crate"])
        material_instance = FakeMaterialInstance()
        fake_unreal.EditorAssetLibrary.assets = {
            "/Game/Props/SM_Crate_01": static_mesh,
            "/Game/Props/Materials/M_Crate": material_instance,
        }
        report = {
            "imported_assets": ["/Game/Props/SM_Crate_01"],
            "created_material_instances": ["/Game/Props/Materials/M_Crate"],
            "material_binding_plan": {
                "materials": [
                    {
                        "material_name": "M_Crate",
                        "target_asset_path": "/Game/Props/Materials/M_Crate",
                    }
                ]
            },
        }

        result = UnrealMaterialSlotAssigner(fake_unreal).assign_from_report(report)

        self.assertEqual(result["status"], "success")
        self.assertEqual(static_mesh.assigned_materials[0], material_instance)
        self.assertEqual(result["assigned"][0]["material_name"], "M_Crate")
        self.assertEqual(result["planned_count"], 1)
        self.assertEqual(result["assigned_count"], 1)
        self.assertEqual(result["unassigned_materials"], [])

    def test_material_slot_assigner_binds_reused_material_instances(self):
        fake_unreal = FakeUnreal()
        static_mesh = FakeStaticMesh(["M_Crate"])
        material_instance = FakeMaterialInstance()
        fake_unreal.EditorAssetLibrary.assets = {
            "/Game/Props/SM_Crate_01": static_mesh,
            "/Game/Props/Materials/M_Crate": material_instance,
        }
        report = {
            "imported_assets": ["/Game/Props/SM_Crate_01"],
            "created_material_instances": [],
            "material_binding_plan": {
                "materials": [
                    {
                        "material_name": "M_Crate",
                        "target_asset_path": "/Game/Props/Materials/M_Crate",
                    }
                ]
            },
        }

        result = UnrealMaterialSlotAssigner(fake_unreal).assign_from_report(report)

        self.assertEqual(result["status"], "success")
        self.assertEqual(static_mesh.assigned_materials[0], material_instance)
        self.assertEqual(result["assigned_count"], 1)
        self.assertEqual(result["unassigned_materials"], [])

    def test_material_slot_assigner_binds_only_matching_slots_per_mesh(self):
        fake_unreal = FakeUnreal()
        mesh_body = FakeStaticMesh(["M_Body"])
        mesh_trim = FakeStaticMesh(["M_Trim"])
        body_instance = FakeMaterialInstance()
        trim_instance = FakeMaterialInstance()
        fake_unreal.EditorAssetLibrary.assets = {
            "/Game/Props/SM_Body": mesh_body,
            "/Game/Props/SM_Trim": mesh_trim,
            "/Game/Props/Materials/M_Body": body_instance,
            "/Game/Props/Materials/M_Trim": trim_instance,
        }
        report = {
            "imported_assets": ["/Game/Props/SM_Body", "/Game/Props/SM_Trim"],
            "created_material_instances": ["/Game/Props/Materials/M_Body", "/Game/Props/Materials/M_Trim"],
            "material_binding_plan": {
                "materials": [
                    {
                        "material_name": "M_Body",
                        "target_asset_path": "/Game/Props/Materials/M_Body",
                    },
                    {
                        "material_name": "M_Trim",
                        "target_asset_path": "/Game/Props/Materials/M_Trim",
                    },
                ]
            },
        }

        result = UnrealMaterialSlotAssigner(fake_unreal).assign_from_report(report)

        self.assertEqual(result["status"], "success")
        self.assertEqual(mesh_body.assigned_materials, {0: body_instance})
        self.assertEqual(mesh_trim.assigned_materials, {0: trim_instance})
        self.assertEqual(result["assigned_count"], 2)
        self.assertEqual(result["unassigned_materials"], [])

    def test_material_slot_assigner_reports_unassigned_planned_materials(self):
        fake_unreal = FakeUnreal()
        static_mesh = FakeStaticMesh(["M_Crate", "M_Trim"])
        material_instance = FakeMaterialInstance()
        fake_unreal.EditorAssetLibrary.assets = {
            "/Game/Props/SM_Crate_01": static_mesh,
            "/Game/Props/Materials/M_Crate": material_instance,
        }
        report = {
            "imported_assets": ["/Game/Props/SM_Crate_01"],
            "created_material_instances": ["/Game/Props/Materials/M_Crate"],
            "material_binding_plan": {
                "materials": [
                    {
                        "material_name": "M_Crate",
                        "target_asset_path": "/Game/Props/Materials/M_Crate",
                    },
                    {
                        "material_name": "M_Trim",
                        "target_asset_path": "/Game/Props/Materials/M_Trim",
                    },
                ]
            },
        }

        result = UnrealMaterialSlotAssigner(fake_unreal).assign_from_report(report)

        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["planned_count"], 2)
        self.assertEqual(result["assigned_count"], 1)
        self.assertEqual(result["unassigned_materials"], ["/Game/Props/Materials/M_Trim"])

    def test_texture_importer_configures_unreal_tasks(self):
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        fake_unreal.EditorAssetLibrary.assets = {}
        fake_unreal.EditorAssetLibrary.saved = []
        plan = {
            "textures": [
                {
                    "source_path": "C:/Exports/SM_Crate_01/Textures/T_Crate_BaseColor.png",
                    "target_dir": "/Game/Props/Textures",
                    "asset_name": "T_Crate_BaseColor",
                    "target_asset_path": "/Game/Props/Textures/T_Crate_BaseColor",
                    "usage": "base_color",
                    "srgb": True,
                    "compression": "default",
                }
            ]
        }

        importer = UnrealTextureImporter(fake_unreal)
        imported = importer.import_textures(plan)

        task = fake_unreal.AssetToolsHelpers.asset_tools.tasks[0]
        texture = fake_unreal.EditorAssetLibrary.assets["/Game/Props/Textures/T_Crate_BaseColor"]
        self.assertEqual(imported, ["/Game/Props/Textures/T_Crate_BaseColor"])
        self.assertEqual(task.filename, "C:/Exports/SM_Crate_01/Textures/T_Crate_BaseColor.png")
        self.assertEqual(task.destination_path, "/Game/Props/Textures")
        self.assertEqual(task.destination_name, "T_Crate_BaseColor")
        self.assertTrue(task.automated)
        self.assertTrue(texture.srgb)
        self.assertEqual(texture.compression_settings, "default")
        self.assertEqual(importer.last_configuration_report["status"], "success")
        self.assertEqual(importer.last_configuration_report["configured"][0]["usage"], "base_color")
        self.assertEqual(importer.last_import_policy_report["actions"][0]["action"], "queued")
        self.assertIn("/Game/Props/Textures/T_Crate_BaseColor", fake_unreal.EditorAssetLibrary.saved)

    def test_texture_importer_reuses_existing_texture_when_requested(self):
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        existing = FakeTexture()
        fake_unreal.EditorAssetLibrary.assets = {"/Game/Props/Textures/T_Crate_BaseColor": existing}
        fake_unreal.EditorAssetLibrary.saved = []
        plan = {
            "existing_texture_strategy": "reuse",
            "textures": [
                {
                    "source_path": "C:/Exports/SM_Crate_01/Textures/T_Crate_BaseColor.png",
                    "target_dir": "/Game/Props/Textures",
                    "asset_name": "T_Crate_BaseColor",
                    "target_asset_path": "/Game/Props/Textures/T_Crate_BaseColor",
                    "existing_texture_strategy": "reuse",
                    "usage": "base_color",
                    "srgb": True,
                    "compression": "default",
                }
            ],
        }
        importer = UnrealTextureImporter(fake_unreal)

        imported = importer.import_textures(plan)

        self.assertEqual(imported, ["/Game/Props/Textures/T_Crate_BaseColor"])
        self.assertEqual(fake_unreal.AssetToolsHelpers.asset_tools.tasks, [])
        self.assertTrue(existing.srgb)
        self.assertEqual(importer.last_import_policy_report["actions"][0]["action"], "reused")

    def test_texture_import_error_does_not_fail_static_mesh_import(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=FailingTextureImporter(),
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["imported_textures"], [])
        self.assertTrue(report["texture_import_issues"])

    def test_package_validation_warns_for_missing_packaged_texture(self):
        bad_texture_manifest_path = os.path.join(self.temp_dir, "bad_texture_manifest.json")
        bad_texture_manifest = dict(self.manifest)
        bad_texture_manifest["textures"] = [
            {
                "node": "file_basecolor",
                "path": self.fbx_path.replace(".fbx", ".png"),
                "package_path": os.path.join(self.temp_dir, "Textures", "Missing.png"),
                "copied": True,
                "usage": "base_color",
            }
        ]
        write_manifest(bad_texture_manifest_path, bad_texture_manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(bad_texture_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SKIPPED)
        self.assertEqual(report["package_validation"]["status"], "warning")
        self.assertEqual(len(report["package_validation"]["textures"]["missing_package_paths"]), 1)

    def test_fbx_importer_configures_unreal_task(self):
        prepared = prepare_manifest_for_import(self.manifest_path)
        preset = dict(prepared["preset"])
        preset["import_materials"] = True
        preset["import_textures"] = True
        preset["fbx_import_materials"] = False
        preset["fbx_import_textures"] = False
        preset["convert_scene"] = False
        preset["force_front_x_axis"] = True
        preset["convert_scene_unit"] = False
        preset["transform_vertex_to_absolute"] = False
        preset["bake_pivot_in_vertex"] = True
        preset["one_convex_hull_per_ucx"] = False
        preset["remove_degenerates"] = False
        preset["compute_weighted_normals"] = True
        preset["auto_generate_collision"] = True
        preset["import_translation"] = [10.0, 20.0, 30.0]
        preset["import_rotation"] = [5.0, 15.0, 25.0]
        preset["import_uniform_scale"] = 2.0
        preset["normal_import_method"] = "import_normals"
        preset["normal_generation_method"] = "built_in"
        preset["vertex_color_import_option"] = "override"
        preset["vertex_override_color"] = [0.25, 0.5, 0.75]
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()

        fbx_importer = UnrealStaticMeshFbxImporter(fake_unreal)
        imported = fbx_importer.import_static_mesh(
            prepared["manifest"],
            preset,
        )

        self.assertEqual(imported, ["/Game/Props/SM_Crate_01"])
        task = fake_unreal.AssetToolsHelpers.asset_tools.tasks[-1]
        static_mesh_data = task.options.static_mesh_import_data
        self.assertEqual(static_mesh_data.normal_import_method, "normals")
        self.assertEqual(static_mesh_data.normal_generation_method, "built_in_enum")
        self.assertEqual(static_mesh_data.vertex_color_import_option, "override_enum")
        self.assertEqual(static_mesh_data.vertex_override_color.r, 64)
        self.assertEqual(static_mesh_data.vertex_override_color.g, 128)
        self.assertEqual(static_mesh_data.vertex_override_color.b, 191)
        self.assertEqual(static_mesh_data.vertex_override_color.a, 255)
        applied_properties = {item["property"] for item in fbx_importer.last_fbx_import_options_report["applied_options"]}
        self.assertIn("generate_lightmap_u_vs", applied_properties)
        self.assertIn("force_front_x_axis", applied_properties)
        self.assertIn("import_translation", applied_properties)
        self.assertIn("import_rotation", applied_properties)
        self.assertIn("import_uniform_scale", applied_properties)
        self.assertIn("normal_import_method", applied_properties)
        self.assertIn("normal_generation_method", applied_properties)
        self.assertIn("vertex_color_import_option", applied_properties)
        self.assertIn("vertex_override_color", applied_properties)
        task = fake_unreal.AssetToolsHelpers.asset_tools.tasks[0]
        self.assertEqual(task.filename, self.fbx_path.replace("\\", "/"))
        self.assertEqual(task.destination_path, "/Game/Props")
        self.assertEqual(task.destination_name, "SM_Crate_01")
        self.assertTrue(task.options.import_mesh)
        self.assertFalse(task.options.import_materials)
        self.assertFalse(task.options.import_textures)
        self.assertFalse(task.options.import_as_skeletal)
        self.assertEqual(task.options.mesh_type_to_import, "static_mesh")
        self.assertTrue(task.options.static_mesh_import_data.generate_lightmap_u_vs)
        self.assertFalse(static_mesh_data.convert_scene)
        self.assertTrue(static_mesh_data.force_front_x_axis)
        self.assertFalse(static_mesh_data.convert_scene_unit)
        self.assertFalse(static_mesh_data.transform_vertex_to_absolute)
        self.assertTrue(static_mesh_data.bake_pivot_in_vertex)
        self.assertEqual(static_mesh_data.import_translation.x, 10.0)
        self.assertEqual(static_mesh_data.import_translation.y, 20.0)
        self.assertEqual(static_mesh_data.import_translation.z, 30.0)
        self.assertEqual(static_mesh_data.import_rotation.pitch, 5.0)
        self.assertEqual(static_mesh_data.import_rotation.yaw, 15.0)
        self.assertEqual(static_mesh_data.import_rotation.roll, 25.0)
        self.assertEqual(static_mesh_data.import_uniform_scale, 2.0)
        self.assertFalse(static_mesh_data.one_convex_hull_per_ucx)
        self.assertFalse(static_mesh_data.remove_degenerates)
        self.assertTrue(static_mesh_data.compute_weighted_normals)
        self.assertTrue(static_mesh_data.auto_generate_collision)
        self.assertEqual(
            task.options.static_mesh_import_data.normal_import_method,
            "normals",
        )
        applied_by_property = {
            item["property"]: item for item in fbx_importer.last_fbx_import_options_report["applied_options"]
        }
        self.assertEqual(applied_by_property["import_translation"]["readback"], [10.0, 20.0, 30.0])
        self.assertEqual(applied_by_property["import_rotation"]["readback"], [5.0, 15.0, 25.0])
        self.assertEqual(applied_by_property["import_uniform_scale"]["readback"], 2.0)
        self.assertEqual(applied_by_property["normal_import_method"]["readback"], "normals")
        self.assertEqual(applied_by_property["normal_generation_method"]["readback"], "built_in_enum")
        self.assertEqual(applied_by_property["vertex_override_color"]["readback"], [64, 128, 191, 255])

    def test_fbx_importer_can_enable_unreal_native_material_texture_import(self):
        prepared = prepare_manifest_for_import(self.manifest_path)
        preset = dict(prepared["preset"])
        preset["import_materials"] = False
        preset["import_textures"] = False
        preset["fbx_import_materials"] = True
        preset["fbx_import_textures"] = True
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()

        UnrealStaticMeshFbxImporter(fake_unreal).import_static_mesh(
            prepared["manifest"],
            preset,
        )

        task = fake_unreal.AssetToolsHelpers.asset_tools.tasks[0]
        self.assertTrue(task.options.import_materials)
        self.assertTrue(task.options.import_textures)

    def test_fbx_importer_uses_lod_alias_when_ue_exposes_split_lod_property(self):
        prepared = prepare_manifest_for_import(self.manifest_path)
        manifest = dict(prepared["manifest"])
        manifest["static_mesh_import_policy"] = {
            "import_lod_policy": "import_existing",
        }
        fake_unreal = FakeUnrealWithLodAlias()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()

        importer = UnrealStaticMeshFbxImporter(fake_unreal)
        importer.import_static_mesh(manifest, prepared["preset"])

        static_mesh_data = fake_unreal.AssetToolsHelpers.asset_tools.tasks[-1].options.static_mesh_import_data
        self.assertFalse(hasattr(static_mesh_data, "import_mesh_lods"))
        self.assertTrue(static_mesh_data.import_mesh_lo_ds)
        applied = importer.last_fbx_import_options_report["applied_options"]
        lod_entry = [item for item in applied if item.get("option") == "import_mesh_lods"][0]
        self.assertEqual(lod_entry["property"], "import_mesh_lo_ds")
        self.assertTrue(lod_entry["readback"])

    def test_fbx_importer_skips_normal_generation_when_source_tangents_are_imported(self):
        prepared = prepare_manifest_for_import(self.manifest_path)
        preset = dict(prepared["preset"])
        preset["normal_import_method"] = "import_normals_and_tangents"
        preset["normal_generation_method"] = "built_in"
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()

        importer = UnrealStaticMeshFbxImporter(fake_unreal)
        importer.import_static_mesh(prepared["manifest"], preset)

        static_mesh_data = fake_unreal.AssetToolsHelpers.asset_tools.tasks[-1].options.static_mesh_import_data
        self.assertEqual(static_mesh_data.normal_import_method, "normals_and_tangents")
        self.assertFalse(hasattr(static_mesh_data, "normal_generation_method"))
        applied_properties = {item["property"] for item in importer.last_fbx_import_options_report["applied_options"]}
        self.assertNotIn("normal_generation_method", applied_properties)
        ignored = importer.last_fbx_import_options_report["ignored_options"]
        self.assertEqual(ignored[0]["property"], "normal_generation_method")
        self.assertIn("source normals and tangents", ignored[0]["reason"])

    def test_fbx_importer_only_sets_vertex_override_color_in_override_mode(self):
        prepared = prepare_manifest_for_import(self.manifest_path)
        preset = dict(prepared["preset"])
        preset["vertex_color_import_option"] = "ignore"
        preset["vertex_override_color"] = [1.0, 0.0, 0.0]
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()

        importer = UnrealStaticMeshFbxImporter(fake_unreal)
        importer.import_static_mesh(prepared["manifest"], preset)

        static_mesh_data = fake_unreal.AssetToolsHelpers.asset_tools.tasks[-1].options.static_mesh_import_data
        self.assertEqual(static_mesh_data.vertex_color_import_option, "ignore_enum")
        self.assertFalse(hasattr(static_mesh_data, "vertex_override_color"))
        applied_properties = {item["property"] for item in importer.last_fbx_import_options_report["applied_options"]}
        self.assertNotIn("vertex_override_color", applied_properties)
        self.assertNotIn("vertex_override_color", importer.last_fbx_import_options_report["options"])

    def test_fbx_importer_defaults_vertex_override_color_to_white_in_override_mode(self):
        prepared = prepare_manifest_for_import(self.manifest_path)
        preset = dict(prepared["preset"])
        preset["vertex_color_import_option"] = "OVERRIDE"
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()

        importer = UnrealStaticMeshFbxImporter(fake_unreal)
        importer.import_static_mesh(prepared["manifest"], preset)

        static_mesh_data = fake_unreal.AssetToolsHelpers.asset_tools.tasks[-1].options.static_mesh_import_data
        self.assertEqual(static_mesh_data.vertex_color_import_option, "override_enum")
        self.assertEqual(static_mesh_data.vertex_override_color.r, 255)
        self.assertEqual(static_mesh_data.vertex_override_color.g, 255)
        self.assertEqual(static_mesh_data.vertex_override_color.b, 255)
        self.assertEqual(importer.last_fbx_import_options_report["options"]["vertex_color_import_option"], "override")
        self.assertEqual(importer.last_fbx_import_options_report["options"]["vertex_override_color"], [1.0, 1.0, 1.0])

    def test_fbx_import_options_report_is_json_serializable_after_readback(self):
        prepared = prepare_manifest_for_import(self.manifest_path)
        preset = dict(prepared["preset"])
        preset["normal_import_method"] = "import_normals"
        preset["normal_generation_method"] = "built_in"
        preset["vertex_color_import_option"] = "override"
        preset["vertex_override_color"] = [0.25, 0.5, 0.75]
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()

        importer = UnrealStaticMeshFbxImporter(fake_unreal)
        importer.import_static_mesh(prepared["manifest"], preset)

        dumped = json.dumps(importer.last_fbx_import_options_report, ensure_ascii=False)
        self.assertIn("readback", dumped)
        self.assertIn("built_in_enum", dumped)
        self.assertIn("[64, 128, 191, 255]", dumped)

    def test_fbx_importer_falls_back_to_target_asset_when_unreal_returns_empty_imported_paths(self):
        prepared = prepare_manifest_for_import(self.manifest_path)
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetToolsWithoutImportedPaths()

        imported = UnrealStaticMeshFbxImporter(fake_unreal).import_static_mesh(
            prepared["manifest"],
            prepared["preset"],
        )

        self.assertEqual(imported, ["/Game/Props/SM_Crate_01"])

    def test_fbx_importer_reports_nanite_and_lod_policy(self):
        manifest = dict(prepare_manifest_for_import(self.manifest_path)["manifest"])
        manifest["static_mesh_import_policy"] = {
            "nanite_policy": "enable",
            "lod_group": "SmallProp",
            "import_lod_policy": "report_only",
        }
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        importer = UnrealStaticMeshFbxImporter(fake_unreal)

        importer.import_static_mesh(manifest, prepare_manifest_for_import(self.manifest_path)["preset"])

        report = importer.last_import_policy_report["static_mesh_policy_report"]
        self.assertIn("Nanite 是虚拟化几何系统", report["message"])
        self.assertEqual(report["policy"]["nanite_policy"], "enable")
        self.assertTrue(any(item["property"] == "nanite_settings.enabled" for item in report["applied"]))
        self.assertTrue(any(item["property"] == "lod_group" for item in report["applied"]))

    def test_fbx_importer_reports_official_static_mesh_import_options(self):
        manifest = dict(prepare_manifest_for_import(self.manifest_path)["manifest"])
        manifest["static_mesh_import_policy"] = {
            "nanite_policy": "enable",
            "lod_group": "SmallProp",
            "import_lod_policy": "import_existing",
            "build_reversed_index_buffer": "enable",
        }
        prepared = prepare_manifest_for_import(self.manifest_path)

        report = UnrealStaticMeshFbxImporter(FakeUnreal()).plan_fbx_import_options(manifest, prepared["preset"])

        self.assertEqual(report["api"]["import_type"], "unreal.FBXImportType.FBXIT_STATIC_MESH")
        self.assertEqual(report["options"]["fbx_import_type"], "FBXIT_STATIC_MESH")
        self.assertTrue(report["options"]["build_nanite"])
        self.assertTrue(report["options"]["build_reversed_index_buffer"])
        self.assertTrue(report["options"]["import_mesh_lods"])

    def test_fbx_importer_reuses_existing_mesh_when_requested(self):
        prepared = prepare_manifest_for_import(self.manifest_path)
        manifest = dict(prepared["manifest"])
        manifest["existing_mesh_strategy"] = "reuse"
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        fake_unreal.EditorAssetLibrary.assets = {"/Game/Props/SM_Crate_01": FakeStaticMesh()}

        imported = UnrealStaticMeshFbxImporter(fake_unreal).import_static_mesh(manifest, prepared["preset"])

        self.assertEqual(imported, ["/Game/Props/SM_Crate_01"])
        self.assertEqual(fake_unreal.AssetToolsHelpers.asset_tools.tasks, [])

    def test_invalid_target_path_blocks_import(self):
        bad_manifest_path = os.path.join(self.temp_dir, "bad_manifest.json")
        bad_manifest = dict(self.manifest)
        bad_manifest["target_path"] = "Content/Props"
        write_manifest(bad_manifest_path, bad_manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).import_from_manifest(bad_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_FAILED)
        self.assertTrue(report["issues"])

    def test_target_path_trailing_newline_is_stripped_before_planning(self):
        manifest_path = os.path.join(self.temp_dir, "newline_target_manifest.json")
        manifest = dict(self.manifest)
        manifest["target_path"] = "/Game/Props/Test01\n"
        write_manifest(manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(manifest_path)

        self.assertEqual(report["target_path"], "/Game/Props/Test01")
        self.assertEqual(report["texture_import_plan"]["target_dir"], "/Game/Props/Test01/Textures")
        self.assertEqual(report["material_binding_plan"]["target_dir"], "/Game/Props/Test01/Materials")
        self.assertNotIn("\n", report["material_binding_plan"]["materials"][0]["target_asset_path"])

    def test_target_path_internal_control_character_blocks_import(self):
        manifest_path = os.path.join(self.temp_dir, "bad_control_target_manifest.json")
        manifest = dict(self.manifest)
        manifest["target_path"] = "/Game/Props/Te\nst"
        write_manifest(manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_FAILED)
        self.assertTrue(any("控制字符" in issue for issue in report["issues"]))

    def test_material_instance_names_use_mi_prefix(self):
        manifest_path = os.path.join(self.temp_dir, "material_name_manifest.json")
        manifest = dict(self.manifest)
        manifest["materials"] = [{"name": "B_d1", "textures": []}]
        write_manifest(manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).dry_run_manifest(manifest_path)

        self.assertEqual(report["material_binding_plan"]["materials"][0]["target_asset_name"], "MI_B_d1")
        self.assertEqual(report["material_binding_plan"]["materials"][0]["target_asset_path"], "/Game/Props/Materials/MI_B_d1")

    def test_post_import_validation_blocks_wrong_target_path(self):
        class WrongPathImporter(object):
            def import_static_mesh(self, manifest, preset):
                return ["/Game/Wrong/SM_Crate_01"]

        report = UnrealStaticMeshImportPipeline(importer=WrongPathImporter()).import_from_manifest(self.manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_FAILED)
        self.assertEqual(report["post_import_validation"]["status"], "error")
        self.assertTrue(report["issues"])

    def test_post_import_validation_accepts_unreal_object_path(self):
        class ObjectPathImporter(object):
            def import_static_mesh(self, manifest, preset):
                return ["/Game/Props/SM_Crate_01.SM_Crate_01"]

        report = UnrealStaticMeshImportPipeline(importer=ObjectPathImporter()).import_from_manifest(self.manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["post_import_validation"]["status"], "pass")

    def test_post_import_validation_accepts_multi_meshes_under_target_dir(self):
        class MultiMeshImporter(object):
            def import_static_mesh(self, manifest, preset):
                return ["/Game/Props/SM_B_a.SM_B_a", "/Game/Props/SM_B_e.SM_B_e"]

        manifest_path = os.path.join(self.temp_dir, "multi_mesh_manifest.json")
        manifest = dict(self.manifest)
        manifest["asset_name"] = "SM_zuti"
        manifest["checks"] = dict(manifest.get("checks", {}))
        manifest["checks"]["mesh_exists"] = {"status": "pass", "value": 2}
        write_manifest(manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(importer=MultiMeshImporter()).import_from_manifest(manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["post_import_validation"]["status"], "pass")
        self.assertEqual(report["post_import_validation"]["expected_static_mesh_count"], 2)
        self.assertEqual(report["post_import_validation"]["imported_static_mesh_count"], 2)

    def test_post_import_validation_counts_combined_mesh_as_one_static_mesh(self):
        class CombinedMeshImporter(FakeImporter):
            def import_static_mesh(self, manifest, preset):
                return ["/Game/Props/SM_zuti.SM_zuti"]

        manifest_path = os.path.join(self.temp_dir, "combined_mesh_manifest.json")
        manifest = dict(self.manifest)
        manifest["asset_name"] = "SM_zuti"
        manifest["checks"] = dict(manifest.get("checks", {}))
        manifest["checks"]["mesh_exists"] = {"status": "pass", "value": 3}
        write_manifest(manifest_path, manifest)

        report = UnrealStaticMeshImportPipeline(
            importer=CombinedMeshImporter(),
            import_options={"combine_meshes": True},
        ).import_from_manifest(manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["post_import_validation"]["status"], "pass")
        self.assertEqual(report["post_import_validation"]["expected_static_mesh_count"], 1)
        self.assertEqual(report["post_import_validation"]["imported_static_mesh_count"], 1)

    def test_post_import_validation_blocks_unprefixed_runtime_multi_mesh_result(self):
        class MultiMeshImporter(object):
            def import_static_mesh(self, manifest, preset):
                return ["/Game/Props/B_d.B_d", "/Game/Props/B_c.B_c", "/Game/Props/B_b.B_b"]

        report = UnrealStaticMeshImportPipeline(importer=MultiMeshImporter()).import_from_manifest(self.manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_FAILED)
        self.assertEqual(report["post_import_validation"]["status"], "error")
        self.assertIn("未规范化命名", report["post_import_validation"]["checks"][1]["message"])

    def test_mixed_slash_fbx_path_is_normalized(self):
        mixed_manifest_path = os.path.join(self.temp_dir, "mixed_manifest.json")
        mixed_manifest = dict(self.manifest)
        mixed_manifest["fbx_path"] = self.fbx_path.replace("\\", "/").replace("/", "\\", 1)
        write_manifest(mixed_manifest_path, mixed_manifest)

        prepared = prepare_manifest_for_import(mixed_manifest_path)

        self.assertTrue(prepared["can_import"])
        self.assertNotIn("\\", prepared["manifest"]["fbx_path"])

    def test_unknown_preset_raises(self):
        manager = UnrealImportPresetManager()
        with self.assertRaises(KeyError):
            manager.get_preset("MissingPreset")

    def test_script_entrypoint_supports_dry_run(self):
        report = script_import_manifest(self.manifest_path, dry_run=True)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SKIPPED)
        self.assertEqual(report["asset_name"], "SM_Crate_01")

    def test_import_latest_manifest_supports_dry_run(self):
        report = import_latest_manifest(self.temp_dir, dry_run=True)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SKIPPED)
        self.assertEqual(report["asset_name"], "SM_Crate_01")

    def test_import_asset_forge_package_supports_dry_run_and_default_report_path(self):
        report = import_asset_forge_package(self.temp_dir, dry_run=True)
        report_path = os.path.join(self.temp_dir, "package_import_report.json")

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SKIPPED)
        self.assertEqual(report["asset_name"], "SM_Crate_01")
        self.assertTrue(os.path.exists(report_path))
        self.assertEqual(read_report(report_path)["asset_name"], "SM_Crate_01")

    def test_script_entrypoint_supports_package_dry_run(self):
        report = script_import_asset_forge_package(self.temp_dir, dry_run=True)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SKIPPED)
        self.assertIn("plugin_content_validation", report)

    def test_script_entrypoint_supports_batch_dry_run(self):
        report = script_import_all_manifests(self.temp_dir, dry_run=True)

        self.assertEqual(report["stage"], "batch_import")
        self.assertEqual(report["counts"]["skipped"], 1)

    def _write_packaged_texture(self):
        texture_dir = os.path.join(self.temp_dir, "Textures")
        if not os.path.exists(texture_dir):
            os.makedirs(texture_dir)
        texture_path = os.path.join(texture_dir, "T_Crate_BaseColor.png")
        with open(texture_path, "wb") as stream:
            stream.write(b"fake texture")
        return texture_path

    def _write_textured_manifest(self, texture_path, texture_import_policy=None):
        manifest_path = os.path.join(self.temp_dir, "textured_import_manifest.json")
        manifest = dict(self.manifest)
        manifest["textures"] = [
            {
                "node": "file_basecolor",
                "path": self.fbx_path.replace(".fbx", ".png"),
                "package_path": texture_path,
                "copied": True,
                "usage": "base_color",
            }
        ]
        manifest["materials"] = [{"name": "M_Crate", "textures": manifest["textures"]}]
        if texture_import_policy is not None:
            manifest["texture_import_policy"] = texture_import_policy
        write_manifest(manifest_path, manifest)
        return manifest_path


class FakeTextureImporter(object):
    def __init__(self, imported):
        self.imported = imported
        self.plans = []
        self.last_import_policy_report = {"status": "success", "existing_texture_strategy": "overwrite", "actions": [], "issues": []}

    def import_textures(self, texture_import_plan):
        self.plans.append(texture_import_plan)
        return self.imported


class FakeVTTextureImporter(FakeTextureImporter):
    def __init__(self, imported_path):
        super(FakeVTTextureImporter, self).__init__([imported_path])
        self.imported_path = imported_path

    def import_textures(self, texture_import_plan):
        self.plans.append(texture_import_plan)
        self.last_configuration_report = {
            "status": "success",
            "configured": [
                {
                    "asset_path": self.imported_path,
                    "usage": "base_color",
                    "policy_report": {
                        "requested_policy": {"virtual_texture_policy": "project_default"},
                        "actual_policy": {"effective_virtual_texture": True},
                        "resolved_virtual_texture_policy": "project_default",
                        "applied": [],
                        "warnings": [],
                    },
                }
            ],
            "issues": [],
        }
        return list(self.imported)


class FailingTextureImporter(object):
    def import_textures(self, texture_import_plan):
        raise RuntimeError("texture import failed")


class FakeMaterialInstanceCreator(object):
    def __init__(self, created):
        self.created = created
        self.plans = []

    def create_from_plan(self, material_binding_plan):
        self.plans.append(material_binding_plan)
        return self.created


class FailingMaterialInstanceCreator(object):
    def create_from_plan(self, material_binding_plan):
        raise RuntimeError("material instance creation failed")


class AvailableMaterialInstanceCreator(object):
    def __init__(self):
        self.called = False

    def is_available(self):
        return True

    def create_from_plan(self, material_binding_plan):
        self.called = True
        raise RuntimeError("不应在缺少母材质时创建材质实例")


class MissingPluginContentBootstrap(object):
    def validate(self):
        return {
            "status": "warning",
            "missing_assets": [
                "/AssetForge/Materials/M_AF_HardSurface_Master",
                "/AssetForge/Materials/M_AF_Props_Opaque",
            ],
            "checks": [
                {
                    "id": "asset_exists",
                    "status": "warning",
                    "path": "/AssetForge/Materials/M_AF_HardSurface_Master",
                    "message": "缺少插件资产",
                },
                {
                    "id": "asset_exists",
                    "status": "warning",
                    "path": "/AssetForge/Materials/M_AF_Props_Opaque",
                    "message": "缺少插件资产",
                }
            ],
        }


class RefreshingPluginContentBootstrap(object):
    def __init__(self):
        self.calls = 0

    def validate(self):
        self.calls += 1
        if self.calls == 1:
            return MissingPluginContentBootstrap().validate()
        return {"status": "pass", "missing_assets": [], "checks": []}


class FakeMaterialAssetBootstrap(object):
    def bootstrap(self, dry_run=False):
        return {
            "status": "success",
            "message": "默认材质资产 Bootstrap 完成",
            "created_assets": [
                "/AssetForge/Materials/M_AF_HardSurface_Master",
                "/AssetForge/Materials/M_AF_Props_Opaque",
            ],
            "existing_assets": [],
            "issues": [],
        }


class FakeMaterialSlotAssigner(object):
    def __init__(self):
        self.reports = []

    def assign_from_report(self, report):
        self.reports.append(report)
        material = report["material_binding_plan"]["materials"][0]
        return {
            "status": "success",
            "assigned": [
                {
                    "static_mesh": report["imported_assets"][0],
                    "slot_index": 0,
                    "material_name": material["material_name"],
                    "material_instance": material["target_asset_path"],
                }
            ],
            "issues": [],
        }


class FakeMaterialEvidenceCollector(object):
    def is_available(self):
        return True

    def collect(self, report):
        return {
            "material_compile_log_evidence": {
                "status": "pass",
                "source": "fake collector",
                "material_paths": [report["material_binding_plan"]["master_material"]],
                "recompiled_materials": [report["material_binding_plan"]["master_material"]],
                "error_count": 0,
                "warning_count": 0,
                "messages": [],
            },
            "real_ue_material_graph": {
                "status": "pass",
                "source": "fake collector",
                "materials": [
                    {
                        "material_path": report["material_binding_plan"]["master_material"],
                        "exists": True,
                        "required_parameters": {"BaseColor": {}, "Normal": {}, "ARM": {}},
                    }
                ],
                "issues": [],
            },
        }


class FailingMaterialSlotAssigner(object):
    def assign_from_report(self, report):
        raise RuntimeError("material assignment failed")


if __name__ == "__main__":
    unittest.main()
