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
from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline, import_latest_manifest


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

    def import_asset_tasks(self, tasks):
        self.tasks.extend(tasks)
        for task in tasks:
            task.imported_object_paths = [task.destination_path + "/SM_Crate_01"]


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


if __name__ == "__main__":
    unittest.main()
