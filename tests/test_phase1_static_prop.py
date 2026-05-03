from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.maya.adapter import MayaAdapter
from asset_forge.maya.fbx_exporter import MayaFbxExporter
from asset_forge.maya.package_opener import open_directory
from asset_forge.maya.pipeline import MayaStaticPropPipeline
from asset_forge.maya.manifest_writer import MayaManifestWriter
from asset_forge.maya.scanner import MayaAssetScanner
from asset_forge.maya.texture_packager import MayaTexturePackager
from asset_forge.shared.report_schema import read_report
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
            "initialShadingGroup": "shadingEngine",
            "M_Crate": "lambert",
            "file_basecolor": "file",
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
            "file_basecolor.fileTextureName": r"C:\Textures\T_Crate_BaseColor.png",
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

    def listConnections(self, node, type=None, source=True, destination=True, plugs=False):
        if type == "shadingEngine":
            return ["initialShadingGroup"]
        if node == "initialShadingGroup.surfaceShader":
            return ["M_Crate"]
        if node == "file_basecolor" and plugs:
            return ["M_Crate.color"]
        return []

    def polyUVSet(self, mesh, query=False, allUVSets=False):
        return ["map1", "lightmap"]

    def getAttr(self, attr):
        return self.attrs[attr]

    def listHistory(self, node, pruneDagObjects=False):
        if node == "M_Crate":
            return ["file_basecolor"]
        return ["polyBevel1"]


class Phase1StaticPropTest(unittest.TestCase):
    def test_scan_validate_and_manifest(self):
        scanner = MayaAssetScanner(FakeCmds())
        scan = scanner.scan("|SM_Crate_01")

        self.assertEqual(scan["asset_name"], "SM_Crate_01")
        self.assertEqual(scan["triangles"], 8240)
        self.assertTrue(scan["has_lightmap_uv"])
        self.assertEqual(scan["materials"][0]["name"], "M_Crate")
        self.assertEqual(scan["textures"][0]["usage"], "base_color")

        validation = StaticPropRuleValidator().validate(scan, TARGET_PLATFORM_HIGH_END_MOBILE)
        self.assertEqual(validation["status"], "warning")
        self.assertTrue(validation["can_export"])

        temp_dir = tempfile.mkdtemp()
        try:
            manifest_path = os.path.join(temp_dir, "manifest.json")
            writer = MayaManifestWriter()
            manifest = writer.build(scan, validation, r"<USER_HOME>/AssetForge/Exports\SM_Crate_01.fbx", "/Game/Props")
            writer.write(manifest_path, manifest)

            loaded = read_manifest(manifest_path)
            self.assertEqual(validate_manifest(loaded), [])
            self.assertEqual(loaded["asset_name"], "SM_Crate_01")
            self.assertNotIn("\\", loaded["fbx_path"])
            self.assertEqual(loaded["materials"][0]["name"], "M_Crate")
            self.assertTrue(loaded["textures"][0]["path"].endswith("/T_Crate_BaseColor.png"))
        finally:
            shutil.rmtree(temp_dir)

    def test_pipeline_writes_export_report(self):
        temp_dir = tempfile.mkdtemp()
        try:
            scanner = MayaAssetScanner(FakeCmds())
            adapter = MayaAdapter(scanner=scanner, exporter=FakeExporter())
            pipeline = MayaStaticPropPipeline(adapter=adapter, exporter=FakeExporter())

            result = pipeline.export_asset("|SM_Crate_01", temp_dir, target_platform="pc")

            self.assertTrue(result["export_report_path"].endswith("/SM_Crate_01_export_report.json"))
            report = read_report(result["export_report_path"])
            self.assertEqual(report["stage"], "maya_export")
            self.assertEqual(report["asset_name"], "SM_Crate_01")
            self.assertEqual(report["validation"]["score"], result["validation"]["score"])
        finally:
            shutil.rmtree(temp_dir)

    def test_texture_packager_copies_existing_texture(self):
        temp_dir = tempfile.mkdtemp()
        try:
            texture_path = os.path.join(temp_dir, "T_Crate_BaseColor.png")
            with open(texture_path, "wb") as stream:
                stream.write(b"fake texture")
            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["textures"][0]["path"] = texture_path

            MayaTexturePackager().package_scan_textures(scan, temp_dir)

            self.assertTrue(scan["textures"][0]["copied"])
            self.assertTrue(scan["textures"][0]["package_path"].endswith("/Textures/T_Crate_BaseColor.png"))
            self.assertTrue(os.path.exists(scan["textures"][0]["package_path"]))
            self.assertEqual(scan["materials"][0]["textures"][0]["package_path"], scan["textures"][0]["package_path"])
        finally:
            shutil.rmtree(temp_dir)

    def test_pipeline_manifest_includes_packaged_texture_path(self):
        temp_dir = tempfile.mkdtemp()
        try:
            texture_path = os.path.join(temp_dir, "T_Crate_BaseColor.png")
            with open(texture_path, "wb") as stream:
                stream.write(b"fake texture")
            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["textures"][0]["path"] = texture_path
            adapter = FakeScanAdapter(scan)
            pipeline = MayaStaticPropPipeline(adapter=adapter, exporter=FakeExporter())

            result = pipeline.export_asset("|SM_Crate_01", os.path.join(temp_dir, "Exports"), target_platform="pc")

            manifest_texture = result["manifest"]["textures"][0]
            self.assertTrue(manifest_texture["copied"])
            self.assertTrue(manifest_texture["package_path"].endswith("/Textures/T_Crate_BaseColor.png"))
            self.assertTrue(os.path.exists(manifest_texture["package_path"]))
        finally:
            shutil.rmtree(temp_dir)

    def test_open_directory_uses_injected_launcher(self):
        temp_dir = tempfile.mkdtemp()
        opened = []
        try:
            result = open_directory(temp_dir, launcher=opened.append)

            self.assertEqual(result.replace("\\", "/"), os.path.abspath(temp_dir).replace("\\", "/"))
            self.assertEqual(opened, [os.path.abspath(temp_dir)])
        finally:
            shutil.rmtree(temp_dir)


class FakeExporter(MayaFbxExporter):
    def __init__(self):
        pass

    def export_asset(self, asset_root, output_path, preset=None):
        with open(output_path, "wb") as stream:
            stream.write(b"fake fbx")
        return output_path


class FakeScanAdapter(object):
    def __init__(self, scan_result):
        self.scan_result = scan_result

    def scan_asset(self, asset_root, rules):
        return self.scan_result


if __name__ == "__main__":
    unittest.main()
