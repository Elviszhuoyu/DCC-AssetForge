from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.maya.skeletal_pipeline import MayaSkeletalPipeline
from asset_forge.maya.skeletal_scanner import MayaSkeletalScanner
from asset_forge.shared.constants import ASSET_TYPE_SKELETAL_MESH
from asset_forge.shared.manifest_schema import validate_manifest
from asset_forge.shared.report_schema import read_report
from tests.test_maya_skeletal_scanner import FakeSkeletalCmds


class MayaSkeletalPipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_prepare_manifest_scans_validates_and_builds_skeletal_manifest(self):
        pipeline = MayaSkeletalPipeline(scanner=MayaSkeletalScanner(FakeSkeletalCmds()))

        result = pipeline.prepare_manifest(
            "|SK_Mannequin",
            r"C:\Exports\SK_Mannequin.fbx",
            "/Game/Characters",
            package_dir=r"C:\Exports\SK_Mannequin",
        )
        manifest = result["manifest"]

        self.assertEqual(result["validation"]["status"], "pass")
        self.assertEqual(manifest["asset_type"], ASSET_TYPE_SKELETAL_MESH)
        self.assertEqual(manifest["root_joint"], "|SK_Mannequin|root")
        self.assertEqual(manifest["joint_count"], 3)
        self.assertEqual(manifest["skin_cluster_count"], 1)
        self.assertEqual(manifest["max_influences"], 4)
        self.assertEqual(manifest["target_path"], "/Game/Characters")
        self.assertNotIn("\\", manifest["fbx_path"])
        self.assertNotIn("\\", manifest["package_dir"])
        self.assertEqual(validate_manifest(manifest), [])

    def test_blocking_validation_error_prevents_manifest_build(self):
        cmds = FakeSkeletalCmds()
        cmds.children["|SK_Mannequin"] = ["|SK_Mannequin|geo", "|SK_Mannequin|geo|bodyShape"]
        pipeline = MayaSkeletalPipeline(scanner=MayaSkeletalScanner(cmds))

        scan = pipeline.scan_asset("|SK_Mannequin")
        validation = pipeline.validate_scan(scan)

        with self.assertRaises(RuntimeError):
            pipeline.build_manifest(scan, validation, "C:/Exports/SK_Mannequin.fbx", "/Game/Characters")

    def test_prepare_package_metadata_writes_manifest_and_package_report(self):
        pipeline = MayaSkeletalPipeline(scanner=MayaSkeletalScanner(FakeSkeletalCmds()))

        result = pipeline.prepare_package_metadata("|SK_Mannequin", self.temp_dir, "/Game/Characters")

        self.assertTrue(os.path.exists(result["manifest_path"]))
        self.assertTrue(os.path.exists(result["package_report_path"]))
        self.assertTrue(result["package"]["skeleton_dir"].endswith("/SK_Mannequin/Skeleton"))
        self.assertEqual(result["manifest"]["asset_type"], ASSET_TYPE_SKELETAL_MESH)
        self.assertEqual(result["package_report"]["validation"]["status"], "pass")
        loaded_report = read_report(result["package_report_path"])
        self.assertEqual(loaded_report["stage"], "skeletal_package")

    def test_prepare_package_metadata_blocks_invalid_scan_before_writing(self):
        cmds = FakeSkeletalCmds()
        cmds.children["|SK_Mannequin"] = ["|SK_Mannequin|geo", "|SK_Mannequin|geo|bodyShape"]
        pipeline = MayaSkeletalPipeline(scanner=MayaSkeletalScanner(cmds))

        with self.assertRaises(RuntimeError):
            pipeline.prepare_package_metadata("|SK_Mannequin", self.temp_dir, "/Game/Characters")

        self.assertEqual(os.listdir(self.temp_dir), [])


if __name__ == "__main__":
    unittest.main()
