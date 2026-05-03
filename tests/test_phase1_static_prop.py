from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.maya.manifest_writer import MayaManifestWriter
from asset_forge.maya.scanner import MayaAssetScanner
from asset_forge.shared.constants import TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.manifest_schema import read_manifest, validate_manifest
from asset_forge.shared.rule_validator import StaticPropRuleValidator


class FakeCmds(object):
    def __init__(self):
        self.types = {
            "|SM_Crate_01": "transform",
            "|SM_Crate_01|meshTransform": "transform",
            "|SM_Crate_01|meshTransform|meshShape": "mesh",
            "polyBevel1": "polyBevel",
        }
        self.children = {
            "|SM_Crate_01": ["|SM_Crate_01|meshTransform", "|SM_Crate_01|meshTransform|meshShape"],
        }
        self.parents = {
            "|SM_Crate_01|meshTransform|meshShape": ["|SM_Crate_01|meshTransform"],
        }
        self.attrs = {
            "|SM_Crate_01.translate": [(0.0, 0.0, 0.0)],
            "|SM_Crate_01.rotate": [(0.0, 0.0, 0.0)],
            "|SM_Crate_01.scale": [(1.0, 1.0, 1.0)],
            "|SM_Crate_01.visibility": True,
            "|SM_Crate_01|meshTransform.translate": [(0.0, 0.0, 0.0)],
            "|SM_Crate_01|meshTransform.rotate": [(0.0, 0.0, 0.0)],
            "|SM_Crate_01|meshTransform.scale": [(1.0, 1.0, 1.0)],
            "|SM_Crate_01|meshTransform.visibility": True,
            "|SM_Crate_01|meshTransform|meshShape.visibility": True,
        }

    def ls(self, selection=False, long=False):
        return ["|SM_Crate_01"] if selection else []

    def nodeType(self, node):
        return self.types[node]

    def listRelatives(self, node, allDescendents=False, fullPath=False, parent=False):
        if parent:
            return self.parents.get(node, [])
        return self.children.get(node, [])

    def polyEvaluate(self, mesh, triangle=False, vertex=False, face=False):
        if triangle:
            return 8240
        if vertex:
            return 4200
        if face:
            return 4120
        return 0

    def listConnections(self, mesh, type=None):
        return ["initialShadingGroup", "M_Crate"]

    def polyUVSet(self, mesh, query=False, allUVSets=False):
        return ["map1", "lightmap"]

    def getAttr(self, attr):
        return self.attrs[attr]

    def listHistory(self, node, pruneDagObjects=False):
        return ["polyBevel1"]


class Phase1StaticPropTest(unittest.TestCase):
    def test_scan_validate_and_manifest(self):
        scanner = MayaAssetScanner(FakeCmds())
        scan = scanner.scan("|SM_Crate_01")

        self.assertEqual(scan["asset_name"], "SM_Crate_01")
        self.assertEqual(scan["triangles"], 8240)
        self.assertTrue(scan["has_lightmap_uv"])

        validation = StaticPropRuleValidator().validate(scan, TARGET_PLATFORM_HIGH_END_MOBILE)
        self.assertEqual(validation["status"], "warning")
        self.assertTrue(validation["can_export"])

        temp_dir = tempfile.mkdtemp()
        try:
            manifest_path = os.path.join(temp_dir, "manifest.json")
            writer = MayaManifestWriter()
            manifest = writer.build(scan, validation, "D:/AssetForge/Exports/SM_Crate_01.fbx", "/Game/Props")
            writer.write(manifest_path, manifest)

            loaded = read_manifest(manifest_path)
            self.assertEqual(validate_manifest(loaded), [])
            self.assertEqual(loaded["asset_name"], "SM_Crate_01")
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
