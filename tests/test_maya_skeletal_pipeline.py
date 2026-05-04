from __future__ import absolute_import

import unittest

from asset_forge.maya.skeletal_pipeline import MayaSkeletalPipeline
from asset_forge.maya.skeletal_scanner import MayaSkeletalScanner
from asset_forge.shared.constants import ASSET_TYPE_SKELETAL_MESH
from asset_forge.shared.manifest_schema import validate_manifest
from tests.test_maya_skeletal_scanner import FakeSkeletalCmds


class MayaSkeletalPipelineTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
