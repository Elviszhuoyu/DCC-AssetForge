from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.constants import (
    IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
    TARGET_PLATFORM_HIGH_END_MOBILE,
    UNREAL_IMPORT_STATUS_FAILED,
    UNREAL_IMPORT_STATUS_SUCCESS,
)
from asset_forge.shared.manifest_schema import create_manifest, write_manifest
from asset_forge.unreal.fbx_importer import UnrealStaticMeshFbxImporter
from asset_forge.unreal.import_presets import UnrealImportPresetManager
from asset_forge.unreal.manifest_reader import prepare_manifest_for_import
from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline


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
        )
        write_manifest(self.manifest_path, self.manifest)

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

    def test_unknown_preset_raises(self):
        manager = UnrealImportPresetManager()
        with self.assertRaises(KeyError):
            manager.get_preset("MissingPreset")


if __name__ == "__main__":
    unittest.main()
