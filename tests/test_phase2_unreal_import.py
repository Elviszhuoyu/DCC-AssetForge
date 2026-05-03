from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.constants import (
    IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
    TARGET_PLATFORM_HIGH_END_MOBILE,
    UNREAL_IMPORT_STATUS_FAILED,
    UNREAL_IMPORT_STATUS_SKIPPED,
    UNREAL_IMPORT_STATUS_SUCCESS,
)
from asset_forge.shared.manifest_schema import create_manifest, write_manifest
from asset_forge.shared.report_schema import read_report, write_report
from scripts.unreal_import_manifest import import_all_manifests as script_import_all_manifests
from scripts.unreal_import_manifest import import_manifest as script_import_manifest
from asset_forge.unreal.fbx_importer import UnrealStaticMeshFbxImporter
from asset_forge.unreal.import_presets import UnrealImportPresetManager
from asset_forge.unreal.manifest_reader import prepare_manifest_for_import
from asset_forge.unreal.material_instance_creator import UnrealMaterialInstanceCreator
from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline, import_latest_manifest
from asset_forge.unreal.texture_importer import UnrealTextureImporter


class FakeImporter(object):
    def import_static_mesh(self, manifest, preset):
        return [manifest["target_path"] + "/" + manifest["asset_name"]]


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


class FakeFbxImportUI(FakeEditorObject):
    def __init__(self):
        self.static_mesh_import_data = FakeStaticMeshImportData()


class FakeAssetTools(object):
    def __init__(self):
        self.tasks = []
        self.assets = []

    def import_asset_tasks(self, tasks):
        self.tasks.extend(tasks)
        for task in tasks:
            name = getattr(task, "destination_name", "SM_Crate_01")
            task.imported_object_paths = [task.destination_path + "/" + name]

    def create_asset(self, asset_name, package_path, asset_class, factory):
        asset = FakeMaterialInstance()
        asset.asset_name = asset_name
        asset.package_path = package_path
        asset.asset_class = asset_class
        asset.factory = factory
        self.assets.append(asset)
        return asset


class FakeAssetToolsHelpers(object):
    asset_tools = FakeAssetTools()

    @classmethod
    def get_asset_tools(cls):
        return cls.asset_tools


class FakeNormalImportMethod(object):
    FBXNIM_IMPORT_NORMALS_AND_TANGENTS = "normals_and_tangents"
    FBXNIM_IMPORT_NORMALS = "normals"
    FBXNIM_COMPUTE_NORMALS = "compute"


class FakeUnreal(object):
    AssetImportTask = FakeAssetImportTask
    FbxImportUI = FakeFbxImportUI
    AssetToolsHelpers = FakeAssetToolsHelpers
    FBXNormalImportMethod = FakeNormalImportMethod
    MaterialInstanceConstant = "MaterialInstanceConstant"

    class MaterialInstanceConstantFactoryNew(object):
        pass

    class EditorAssetLibrary(object):
        loaded = []

        @classmethod
        def load_asset(cls, asset_path):
            cls.loaded.append(asset_path)
            return "asset:" + asset_path

    class MaterialEditingLibrary(object):
        texture_calls = []
        scalar_calls = []

        @classmethod
        def set_material_instance_texture_parameter_value(cls, material_instance, name, texture_asset):
            cls.texture_calls.append((material_instance, name, texture_asset))

        @classmethod
        def set_material_instance_scalar_parameter_value(cls, material_instance, name, value):
            cls.scalar_calls.append((material_instance, name, value))


class FakeMaterialInstance(FakeEditorObject):
    pass


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
        self.assertEqual(report["texture_import_plan"]["target_dir"], "/Game/Props/Textures")
        self.assertEqual(report["texture_import_plan"]["profile"], "Props_Opaque_PainterUE_ARM")
        self.assertEqual(report["material_binding_plan"]["target_dir"], "/Game/Props/Materials")
        self.assertEqual(report["material_binding_plan"]["master_material"], "/Game/AssetForge/Materials/M_AF_Props_Opaque")
        self.assertEqual(report["material_binding_plan"]["materials"][0]["target_asset_path"], "/Game/Props/Materials/M_Crate")
        self.assertEqual(report["imported_textures"], [])
        self.assertEqual(report["texture_import_issues"], [])
        self.assertEqual(report["created_material_instances"], [])
        self.assertEqual(report["material_instance_issues"], [])
        self.assertEqual(report["post_import_validation"]["status"], "pass")

    def test_pipeline_writes_default_import_and_end_to_end_reports(self):
        pipeline = UnrealStaticMeshImportPipeline(importer=FakeImporter())

        report = pipeline.import_from_manifest(self.manifest_path)

        import_report_path = os.path.join(self.temp_dir, "SM_Crate_01_import_report.json")
        end_to_end_path = os.path.join(self.temp_dir, "SM_Crate_01_end_to_end_report.json")
        self.assertTrue(os.path.exists(import_report_path))
        self.assertTrue(os.path.exists(end_to_end_path))
        self.assertEqual(read_report(import_report_path)["status"], report["status"])
        self.assertEqual(read_report(end_to_end_path)["stage"], "end_to_end")

    def test_dry_run_returns_skipped_report(self):
        pipeline = UnrealStaticMeshImportPipeline(importer=FakeImporter())
        log_path = os.path.join(self.temp_dir, "dry_run_report.json")
        report = pipeline.dry_run_manifest(self.manifest_path, log_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SKIPPED)
        self.assertEqual(report["message"], "Dry run passed")
        self.assertEqual(report["imported_assets"], [])
        self.assertEqual(report["resolved_preset"]["name"], IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE)
        self.assertTrue(os.path.exists(log_path))
        self.assertNotIn("\\", report["fbx_path"])
        self.assertEqual(report["package_validation"]["textures"]["total"], 1)
        self.assertEqual(report["texture_import_plan"]["count"], 0)

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
        self.assertEqual(report["material_binding_plan"]["master_material"], "/Game/AssetForge/Materials/M_AF_Props_Masked")
        self.assertEqual(report["material_binding_plan"]["render_mode"], "masked")
        self.assertEqual(report["material_binding_plan"]["materials"][0]["scalar_parameters"]["OpacityClipValue"], 0.333)

    def test_pipeline_imports_planned_textures_without_blocking_mesh(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        texture_importer = FakeTextureImporter(["/Game/Props/Textures/T_Crate_BaseColor.T_Crate_BaseColor"])

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=texture_importer,
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["imported_textures"], ["/Game/Props/Textures/T_Crate_BaseColor.T_Crate_BaseColor"])
        self.assertEqual(texture_importer.plans[0]["count"], 1)

    def test_pipeline_creates_material_instances_without_blocking_mesh(self):
        texture_path = self._write_packaged_texture()
        textured_manifest_path = self._write_textured_manifest(texture_path)
        material_creator = FakeMaterialInstanceCreator(["/Game/Props/Materials/M_Crate"])

        report = UnrealStaticMeshImportPipeline(
            importer=FakeImporter(),
            texture_importer=FakeTextureImporter([]),
            material_instance_creator=material_creator,
        ).import_from_manifest(textured_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_SUCCESS)
        self.assertEqual(report["created_material_instances"], ["/Game/Props/Materials/M_Crate"])
        self.assertEqual(material_creator.plans[0]["materials"][0]["parent_material"], "/Game/AssetForge/Materials/M_AF_Props_Opaque")

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

    def test_material_instance_creator_configures_unreal_asset(self):
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        fake_unreal.EditorAssetLibrary.loaded = []
        fake_unreal.MaterialEditingLibrary.texture_calls = []
        fake_unreal.MaterialEditingLibrary.scalar_calls = []
        plan = {
            "materials": [
                {
                    "material_name": "M_Crate",
                    "parent_material": "/Game/AssetForge/Materials/M_AF_Props_Opaque",
                    "target_asset_path": "/Game/Props/Materials/M_Crate",
                    "texture_parameters": {"BaseColor": "/Game/Props/Textures/T_Crate_BaseColor"},
                    "scalar_parameters": {"EmissiveIntensity": 1.0},
                }
            ]
        }

        created = UnrealMaterialInstanceCreator(fake_unreal).create_from_plan(plan)

        asset = fake_unreal.AssetToolsHelpers.asset_tools.assets[0]
        self.assertEqual(created, ["/Game/Props/Materials/M_Crate"])
        self.assertEqual(asset.asset_name, "M_Crate")
        self.assertEqual(asset.package_path, "/Game/Props/Materials")
        self.assertEqual(asset.parent, "asset:/Game/AssetForge/Materials/M_AF_Props_Opaque")
        self.assertEqual(fake_unreal.MaterialEditingLibrary.texture_calls[0][1], "BaseColor")
        self.assertEqual(fake_unreal.MaterialEditingLibrary.scalar_calls[0][1], "EmissiveIntensity")

    def test_texture_importer_configures_unreal_tasks(self):
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()
        plan = {
            "textures": [
                {
                    "source_path": "C:/Exports/SM_Crate_01/Textures/T_Crate_BaseColor.png",
                    "target_dir": "/Game/Props/Textures",
                    "asset_name": "T_Crate_BaseColor",
                }
            ]
        }

        imported = UnrealTextureImporter(fake_unreal).import_textures(plan)

        task = fake_unreal.AssetToolsHelpers.asset_tools.tasks[0]
        self.assertEqual(imported, ["/Game/Props/Textures/T_Crate_BaseColor"])
        self.assertEqual(task.filename, "C:/Exports/SM_Crate_01/Textures/T_Crate_BaseColor.png")
        self.assertEqual(task.destination_path, "/Game/Props/Textures")
        self.assertEqual(task.destination_name, "T_Crate_BaseColor")
        self.assertTrue(task.automated)

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
        fake_unreal = FakeUnreal()
        fake_unreal.AssetToolsHelpers.asset_tools = FakeAssetTools()

        imported = UnrealStaticMeshFbxImporter(fake_unreal).import_static_mesh(
            prepared["manifest"],
            prepared["preset"],
        )

        self.assertEqual(imported, ["/Game/Props/SM_Crate_01"])
        task = fake_unreal.AssetToolsHelpers.asset_tools.tasks[0]
        self.assertEqual(task.filename, self.fbx_path.replace("\\", "/"))
        self.assertEqual(task.destination_path, "/Game/Props")
        self.assertTrue(task.options.import_mesh)
        self.assertFalse(task.options.import_as_skeletal)
        self.assertTrue(task.options.static_mesh_import_data.generate_lightmap_u_vs)
        self.assertEqual(
            task.options.static_mesh_import_data.normal_import_method,
            "normals_and_tangents",
        )

    def test_invalid_target_path_blocks_import(self):
        bad_manifest_path = os.path.join(self.temp_dir, "bad_manifest.json")
        bad_manifest = dict(self.manifest)
        bad_manifest["target_path"] = "Content/Props"
        write_manifest(bad_manifest_path, bad_manifest)

        report = UnrealStaticMeshImportPipeline(importer=FakeImporter()).import_from_manifest(bad_manifest_path)

        self.assertEqual(report["status"], UNREAL_IMPORT_STATUS_FAILED)
        self.assertTrue(report["issues"])

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

    def _write_textured_manifest(self, texture_path):
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
        write_manifest(manifest_path, manifest)
        return manifest_path


class FakeTextureImporter(object):
    def __init__(self, imported):
        self.imported = imported
        self.plans = []

    def import_textures(self, texture_import_plan):
        self.plans.append(texture_import_plan)
        return self.imported


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


if __name__ == "__main__":
    unittest.main()
