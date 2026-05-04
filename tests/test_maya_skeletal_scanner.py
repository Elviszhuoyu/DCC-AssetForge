from __future__ import absolute_import

import unittest

from asset_forge.maya.skeletal_scanner import MayaSkeletalScanner
from asset_forge.shared.skeletal_scan_schema import validate_skeletal_scan_result


class MayaSkeletalScannerTest(unittest.TestCase):
    def test_scanner_outputs_shared_skeletal_scan_schema(self):
        scan = MayaSkeletalScanner(FakeSkeletalCmds()).scan("|SK_Mannequin")

        self.assertEqual(validate_skeletal_scan_result(scan), [])
        self.assertEqual(scan["asset_name"], "SK_Mannequin")
        self.assertEqual(scan["root_joint"], "|SK_Mannequin|root")
        self.assertEqual(scan["joint_count"], 3)
        self.assertEqual(scan["skin_cluster_count"], 1)
        self.assertEqual(scan["max_influences"], 4)
        self.assertEqual(scan["lods"][0]["name"], "LOD0")
        self.assertEqual(scan["materials"], [{"name": "M_Body"}])

    def test_missing_skin_data_stays_in_schema_and_reports_issues(self):
        cmds = FakeSkeletalCmds()
        cmds.connections["|SK_Mannequin|geo|bodyShape"] = []

        scan = MayaSkeletalScanner(cmds).scan("|SK_Mannequin")

        self.assertEqual(scan["skin_cluster_count"], 0)
        self.assertIn("skin_cluster_count must be greater than 0", validate_skeletal_scan_result(scan))

    def test_scanner_reports_unavailable_outside_maya(self):
        scanner = MayaSkeletalScanner(cmds_module=None)
        scanner.cmds = None

        self.assertFalse(scanner.is_available())
        with self.assertRaises(RuntimeError):
            scanner.scan("|SK_Mannequin")


class FakeSkeletalCmds(object):
    def __init__(self):
        self.types = {
            "|SK_Mannequin": "transform",
            "|SK_Mannequin|root": "joint",
            "|SK_Mannequin|root|pelvis": "joint",
            "|SK_Mannequin|root|pelvis|spine_01": "joint",
            "|SK_Mannequin|geo": "transform",
            "|SK_Mannequin|geo|bodyShape": "mesh",
            "|SK_Mannequin|LOD0": "transform",
            "skinCluster1": "skinCluster",
            "initialShadingGroup": "shadingEngine",
            "M_Body": "lambert",
        }
        self.children = {
            "|SK_Mannequin": [
                "|SK_Mannequin|root",
                "|SK_Mannequin|root|pelvis",
                "|SK_Mannequin|root|pelvis|spine_01",
                "|SK_Mannequin|geo",
                "|SK_Mannequin|geo|bodyShape",
                "|SK_Mannequin|LOD0",
            ]
        }
        self.connections = {
            "|SK_Mannequin|geo|bodyShape": ["skinCluster1", "initialShadingGroup"],
            "initialShadingGroup.surfaceShader": ["M_Body"],
        }

    def listRelatives(self, node, allDescendents=False, fullPath=False):
        return self.children.get(node, [])

    def nodeType(self, node):
        return self.types[node]

    def listConnections(self, node, type=None):
        values = self.connections.get(node, [])
        if type == "skinCluster":
            return [item for item in values if self.types.get(item) == "skinCluster"]
        if type == "shadingEngine":
            return [item for item in values if self.types.get(item) == "shadingEngine"]
        return values

    def skinCluster(self, cluster, query=False, maximumInfluences=False, influence=False):
        if maximumInfluences:
            return 4
        if influence:
            return ["|SK_Mannequin|root", "|SK_Mannequin|root|pelvis"]
        return None


if __name__ == "__main__":
    unittest.main()
