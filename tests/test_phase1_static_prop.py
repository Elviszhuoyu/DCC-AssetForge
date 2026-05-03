from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.maya.adapter import MayaAdapter
from asset_forge.maya.fbx_exporter import DEFAULT_FBX_EXPORT_PRESET, MayaFbxExporter
from asset_forge.maya.package_opener import open_directory
from asset_forge.maya.pipeline import MayaStaticPropPipeline
from asset_forge.maya.manifest_writer import MayaManifestWriter
from asset_forge.maya.scanner import MayaAssetScanner
from asset_forge.maya.texture_packager import MayaTexturePackager
from asset_forge.shared.report_schema import read_report
from asset_forge.shared.constants import TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.manifest_schema import read_manifest, validate_manifest
from asset_forge.shared.rule_validator import StaticPropRuleValidator
from asset_forge.shared.rules_schema import get_default_rules


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
        self.assertEqual(scan["textures"][0]["source_type"], "maya_file_node")

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

    def test_collision_naming_warns_for_loose_collision_prefix(self):
        cmds = FakeCmds()
        cmds.children["|SM_Crate_01"].append("|SM_Crate_01|COL_Crate")
        cmds.types["|SM_Crate_01|COL_Crate"] = "transform"

        scan = MayaAssetScanner(cmds).scan("|SM_Crate_01")
        validation = StaticPropRuleValidator().validate(scan, TARGET_PLATFORM_HIGH_END_MOBILE)
        checks = dict((item["id"], item) for item in validation["checks"])

        self.assertEqual(scan["invalid_collision_nodes"], ["|SM_Crate_01|COL_Crate"])
        self.assertEqual(checks["collision_naming"]["status"], "warning")
        self.assertTrue(validation["can_export"])

    def test_collision_naming_accepts_unreal_collision_prefix(self):
        cmds = FakeCmds()
        cmds.children["|SM_Crate_01"].append("|SM_Crate_01|UCX_SM_Crate_01_00")
        cmds.types["|SM_Crate_01|UCX_SM_Crate_01_00"] = "transform"

        scan = MayaAssetScanner(cmds).scan("|SM_Crate_01")
        validation = StaticPropRuleValidator().validate(scan, TARGET_PLATFORM_HIGH_END_MOBILE)
        checks = dict((item["id"], item) for item in validation["checks"])

        self.assertEqual(scan["collision_nodes"], ["|SM_Crate_01|UCX_SM_Crate_01_00"])
        self.assertEqual(checks["collision_naming"]["status"], "pass")

    def test_scoring_penalties_are_configurable(self):
        rules = get_default_rules()
        rules["static_prop"]["scoring"]["warning_penalty"] = 5
        scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")

        validation = StaticPropRuleValidator(rules).validate(scan, TARGET_PLATFORM_HIGH_END_MOBILE)

        self.assertEqual(validation["score"], 95)

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
            self.assertEqual(scan["textures"][0]["source_type"], "maya_file_node")
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

    def test_fbx_exporter_applies_static_prop_default_preset(self):
        temp_dir = tempfile.mkdtemp()
        try:
            cmds = FakeExportCmds()
            mel = FakeMel()
            output_path = os.path.join(temp_dir, "SM_Crate_01.fbx")

            MayaFbxExporter(cmds, mel).export_asset("|SM_Crate_01", output_path)

            self.assertEqual(cmds.selected, "|SM_Crate_01")
            self.assertTrue(cmds.loaded_plugin)
            self.assertIn("FBXResetExport", mel.commands)
            self.assertIn("FBXExportInAscii -v false", mel.commands)
            self.assertIn("FBXExportAnimationOnly -v false", mel.commands)
            self.assertIn("FBXExportBakeComplexAnimation -v false", mel.commands)
            self.assertIn("FBXExportSkins -v false", mel.commands)
            self.assertIn("FBXExportShapes -v false", mel.commands)
            self.assertIn("FBXExportSmoothingGroups -v true", mel.commands)
            self.assertIn("FBXExportTangents -v true", mel.commands)
            self.assertIn("FBXExportTriangulate -v false", mel.commands)
            self.assertIn("FBXExportConvertUnitString cm", mel.commands)
            self.assertTrue(mel.commands[-1].startswith('FBXExport -f "'))
        finally:
            shutil.rmtree(temp_dir)

    def test_fbx_export_preset_documents_static_prop_defaults(self):
        self.assertFalse(DEFAULT_FBX_EXPORT_PRESET["animation"])
        self.assertFalse(DEFAULT_FBX_EXPORT_PRESET["skins"])
        self.assertFalse(DEFAULT_FBX_EXPORT_PRESET["shapes"])
        self.assertTrue(DEFAULT_FBX_EXPORT_PRESET["smoothing_groups"])
        self.assertTrue(DEFAULT_FBX_EXPORT_PRESET["tangents_and_binormals"])
        self.assertFalse(DEFAULT_FBX_EXPORT_PRESET["triangulate"])
        self.assertEqual(DEFAULT_FBX_EXPORT_PRESET["units"], "cm")


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


class FakeExportCmds(object):
    def __init__(self):
        self.loaded_plugin = False
        self.selected = ""

    def pluginInfo(self, plugin, query=False, loaded=False):
        return self.loaded_plugin

    def loadPlugin(self, plugin):
        self.loaded_plugin = True

    def select(self, node, replace=False):
        self.selected = node

    def ls(self, selection=False, long=False):
        return [self.selected] if selection and self.selected else []


class FakeMel(object):
    def __init__(self):
        self.commands = []

    def eval(self, command):
        self.commands.append(command)


if __name__ == "__main__":
    unittest.main()
