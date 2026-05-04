from __future__ import absolute_import

import unittest

from asset_forge.shared.constants import ASSET_TYPE_STATIC_PROP
from asset_forge.shared.manifest_schema import create_manifest, create_skeletal_mesh_manifest
from asset_forge.shared.skeletal_scan_schema import (
    create_skeletal_scan_result,
    skeletal_manifest_fields_from_scan,
    validate_skeletal_scan_result,
)


class SkeletalScanSchemaTest(unittest.TestCase):
    def test_skeletal_scan_result_summarizes_skeleton_skin_and_lods(self):
        scan = create_skeletal_scan_result(
            "SK_Mannequin",
            root_joint="root",
            joints=["root", "pelvis", "spine_01"],
            skin_clusters=[{"name": "skinCluster1", "max_influences": 4}],
            lods=[{"name": "LOD0"}, {"name": "LOD1"}],
            materials=[{"name": "M_Body"}],
        )

        self.assertEqual(validate_skeletal_scan_result(scan), [])
        self.assertEqual(scan["joint_count"], 3)
        self.assertEqual(scan["skin_cluster_count"], 1)
        self.assertEqual(scan["max_influences"], 4)
        self.assertEqual(scan["lod_count"], 2)
        self.assertEqual(scan["material_slots"], 1)

    def test_skeletal_scan_maps_to_manifest_fields(self):
        scan = create_skeletal_scan_result(
            "SK_Mannequin",
            root_joint="root",
            joints=["root"],
            skin_clusters=[{"name": "skinCluster1", "max_influences": 4}],
            lods=[{"name": "LOD0"}],
        )
        fields = skeletal_manifest_fields_from_scan(scan)
        manifest = create_skeletal_mesh_manifest(
            scan["asset_name"],
            "C:/Exports/SK_Mannequin.fbx",
            "/Game/Characters",
            **fields
        )

        self.assertEqual(manifest["root_joint"], "root")
        self.assertEqual(manifest["joint_count"], 1)
        self.assertEqual(manifest["skin_cluster_count"], 1)
        self.assertEqual(manifest["max_influences"], 4)
        self.assertEqual(manifest["lods"], [{"name": "LOD0"}])

    def test_static_prop_manifest_is_not_polluted_by_skeletal_scan_fields(self):
        manifest = create_manifest("SM_Crate_01", "C:/Exports/SM_Crate_01.fbx", "/Game/Props")

        self.assertEqual(manifest["asset_type"], ASSET_TYPE_STATIC_PROP)
        self.assertNotIn("root_joint", manifest)
        self.assertNotIn("skin_cluster_count", manifest)

    def test_invalid_skeletal_scan_reports_missing_core_data(self):
        scan = create_skeletal_scan_result("SK_Broken")

        issues = validate_skeletal_scan_result(scan)

        self.assertIn("missing root_joint", issues)
        self.assertIn("joint_count must be greater than 0", issues)
        self.assertIn("skin_cluster_count must be greater than 0", issues)


if __name__ == "__main__":
    unittest.main()
