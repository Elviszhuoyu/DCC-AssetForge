from __future__ import absolute_import

import unittest

from asset_forge.shared.constants import CHECK_STATUS_ERROR, CHECK_STATUS_PASS, CHECK_STATUS_WARNING
from asset_forge.shared.skeletal_rule_validator import SkeletalMeshRuleValidator
from asset_forge.shared.skeletal_scan_schema import create_skeletal_scan_result


class SkeletalRuleValidatorTest(unittest.TestCase):
    def test_valid_skeletal_scan_passes(self):
        scan = create_skeletal_scan_result(
            "SK_Mannequin",
            root_joint="root",
            joints=["root", "pelvis"],
            skin_clusters=[{"name": "skinCluster1", "max_influences": 4}],
            lods=[{"name": "LOD0"}, {"name": "LOD1"}],
            materials=[{"name": "M_Body"}],
        )

        validation = SkeletalMeshRuleValidator().validate(scan)

        self.assertEqual(validation["status"], CHECK_STATUS_PASS)
        self.assertTrue(validation["can_export"])
        self.assertEqual(validation["score"], 100)

    def test_missing_root_and_skin_cluster_blocks_export(self):
        scan = create_skeletal_scan_result("Broken_Character")

        validation = SkeletalMeshRuleValidator().validate(scan)
        checks = dict((item["id"], item) for item in validation["checks"])

        self.assertEqual(validation["status"], CHECK_STATUS_ERROR)
        self.assertFalse(validation["can_export"])
        self.assertEqual(checks["sk_prefix"]["status"], CHECK_STATUS_ERROR)
        self.assertEqual(checks["has_root_joint"]["status"], CHECK_STATUS_ERROR)
        self.assertEqual(checks["has_skin_cluster"]["status"], CHECK_STATUS_ERROR)

    def test_high_influence_count_is_warning_only(self):
        scan = create_skeletal_scan_result(
            "SK_Heavy",
            root_joint="root",
            joints=["root"],
            skin_clusters=[{"name": "skinCluster1", "max_influences": 8}],
            lods=[{"name": "LOD0"}],
            materials=[{"name": "M_Body"}],
        )

        validation = SkeletalMeshRuleValidator().validate(scan)
        checks = dict((item["id"], item) for item in validation["checks"])

        self.assertEqual(validation["status"], CHECK_STATUS_WARNING)
        self.assertTrue(validation["can_export"])
        self.assertEqual(checks["max_influences"]["status"], CHECK_STATUS_WARNING)

    def test_bad_lod_order_is_warning(self):
        scan = create_skeletal_scan_result(
            "SK_BadLod",
            root_joint="root",
            joints=["root"],
            skin_clusters=[{"name": "skinCluster1", "max_influences": 4}],
            lods=[{"name": "LOD0"}, {"name": "LOD2"}],
            materials=[{"name": "M_Body"}],
        )

        validation = SkeletalMeshRuleValidator().validate(scan)
        checks = dict((item["id"], item) for item in validation["checks"])

        self.assertEqual(checks["lod_order"]["status"], CHECK_STATUS_WARNING)


if __name__ == "__main__":
    unittest.main()
