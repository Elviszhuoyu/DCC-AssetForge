from __future__ import absolute_import

import os
import shutil
import tempfile
import time
import unittest

from asset_forge.maya.export_package import build_export_package
from asset_forge.shared.manifest_schema import create_manifest, write_manifest
from asset_forge.unreal.manifest_finder import find_latest_manifest, find_manifest_files
from asset_forge.unreal.pipeline import import_latest_manifest


class FakeLatestImporter(object):
    def import_static_mesh(self, manifest, preset):
        return [manifest["target_path"] + "/" + manifest["asset_name"]]


class ExportPackageAndLatestManifestTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_export_package_paths_use_asset_folder(self):
        package = build_export_package(self.temp_dir, "SM_Crate_01")

        self.assertTrue(package["package_dir"].endswith("/SM_Crate_01"))
        self.assertTrue(package["fbx_path"].endswith("/SM_Crate_01/SM_Crate_01.fbx"))
        self.assertTrue(package["manifest_path"].endswith("/SM_Crate_01/SM_Crate_01_manifest.json"))
        self.assertNotIn("\\", package["fbx_path"])

    def test_find_latest_manifest_recurses_package_dirs(self):
        old_dir = build_export_package(self.temp_dir, "SM_Old")
        new_dir = build_export_package(self.temp_dir, "SM_New")

        old_manifest = create_manifest(
            "SM_Old",
            old_dir["fbx_path"],
            "/Game/Props",
            package_dir=old_dir["package_dir"],
        )
        new_manifest = create_manifest(
            "SM_New",
            new_dir["fbx_path"],
            "/Game/Props",
            package_dir=new_dir["package_dir"],
        )

        with open(old_dir["fbx_path"], "wb") as stream:
            stream.write(b"old")
        with open(new_dir["fbx_path"], "wb") as stream:
            stream.write(b"new")
        write_manifest(old_dir["manifest_path"], old_manifest)
        time.sleep(0.01)
        write_manifest(new_dir["manifest_path"], new_manifest)

        manifests = find_manifest_files(self.temp_dir)
        latest = find_latest_manifest(self.temp_dir)

        self.assertEqual(len(manifests), 2)
        self.assertTrue(latest.endswith("/SM_New/SM_New_manifest.json"))


if __name__ == "__main__":
    unittest.main()
