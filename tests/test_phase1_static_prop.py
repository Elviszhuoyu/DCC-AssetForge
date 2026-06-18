from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.maya.adapter import MayaAdapter
from asset_forge.maya.fbx_exporter import DEFAULT_FBX_EXPORT_PRESET, MayaFbxExporter
from asset_forge.maya.package_opener import open_directory
from asset_forge.maya.pipeline import ExportValidationError, MayaStaticPropPipeline
from asset_forge.maya.manifest_writer import MayaManifestWriter
from asset_forge.maya.scanner import MayaAssetScanner
from asset_forge.maya.texture_packager import MayaTexturePackager
from asset_forge.shared.material_texture_bindings import create_material_texture_bindings
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


class EmptySelectionSingleAssemblyCmds(FakeCmds):
    def __init__(self):
        super(EmptySelectionSingleAssemblyCmds, self).__init__()
        self.types.update({"|persp": "transform", "|persp|perspShape": "camera"})
        self.children["|persp"] = ["|persp|perspShape"]

    def ls(self, selection=False, long=False, assemblies=False):
        if selection:
            return []
        if assemblies:
            return ["|persp", "|SM_Crate_01"]
        return []


class EmptySelectionMultipleAssemblyCmds(EmptySelectionSingleAssemblyCmds):
    def __init__(self):
        super(EmptySelectionMultipleAssemblyCmds, self).__init__()
        self.types.update({"|SM_Second": "transform", "|SM_Second|meshShape": "mesh"})
        self.children["|SM_Second"] = ["|SM_Second|meshShape"]

    def ls(self, selection=False, long=False, assemblies=False):
        if selection:
            return []
        if assemblies:
            return ["|persp", "|SM_Crate_01", "|SM_Second"]
        return []


class EmptySelectionGroupedSingleAssetCmds(EmptySelectionSingleAssemblyCmds):
    def __init__(self):
        super(EmptySelectionGroupedSingleAssetCmds, self).__init__()
        self.types = {
            "|group1": "transform",
            "|group1|SM_B": "transform",
            "|group1|SM_B|meshShape": "mesh",
            "|persp": "transform",
            "|persp|perspShape": "camera",
        }
        self.children = {
            "|group1": ["|group1|SM_B"],
            "|group1|SM_B": ["|group1|SM_B|meshShape"],
            "|persp": ["|persp|perspShape"],
        }

    def ls(self, selection=False, long=False, assemblies=False):
        if selection:
            return []
        if assemblies:
            return ["|persp", "|group1"]
        return []

    def listRelatives(self, node, allDescendents=False, fullPath=False, parent=False, children=False):
        if parent:
            return []
        if children:
            return self.children.get(node, [])
        if allDescendents and node == "|group1":
            return ["|group1|SM_B", "|group1|SM_B|meshShape"]
        return self.children.get(node, [])


class RenameMeshTransformCmds(object):
    def __init__(self):
        self.types = {
            "|SM_B": "transform",
            "|SM_B|zuti": "transform",
            "|SM_B|zuti|B_a": "transform",
            "|SM_B|zuti|B_a|B_aShape": "mesh",
            "|SM_B|zuti|B_b": "transform",
            "|SM_B|zuti|B_b|B_bShape": "mesh",
        }
        self.parents = {
            "|SM_B|zuti|B_a|B_aShape": ["|SM_B|zuti|B_a"],
            "|SM_B|zuti|B_b|B_bShape": ["|SM_B|zuti|B_b"],
        }
        self.renamed = []

    def nodeType(self, node):
        return self.types[node]

    def listRelatives(self, node, allDescendents=False, fullPath=False, parent=False):
        if parent:
            return self.parents.get(node, [])
        if node == "|SM_B":
            return [
                "|SM_B|zuti",
                "|SM_B|zuti|B_a",
                "|SM_B|zuti|B_a|B_aShape",
                "|SM_B|zuti|B_b",
                "|SM_B|zuti|B_b|B_bShape",
            ]
        return []

    def rename(self, node, new_short_name):
        parent = node.rsplit("|", 1)[0]
        renamed = parent + "|" + new_short_name
        self.renamed.append((node, new_short_name))
        return renamed

    def polyEvaluate(self, mesh, triangle=False, vertex=False, face=False):
        return 1

    def listConnections(self, *args, **kwargs):
        return []

    def polyUVSet(self, *args, **kwargs):
        return ["map1"]

    def getAttr(self, attr):
        if attr.endswith(".visibility"):
            return True
        return [(0.0, 0.0, 0.0)] if attr.endswith((".translate", ".rotate")) else [(1.0, 1.0, 1.0)]

    def listHistory(self, *args, **kwargs):
        return []


class Phase1StaticPropTest(unittest.TestCase):
    def test_scanner_falls_back_to_single_mesh_assembly_when_selection_empty(self):
        selection = MayaAssetScanner(EmptySelectionSingleAssemblyCmds()).get_current_selection()

        self.assertEqual(selection, ["|SM_Crate_01"])

    def test_scanner_does_not_guess_when_multiple_mesh_assemblies_exist(self):
        selection = MayaAssetScanner(EmptySelectionMultipleAssemblyCmds()).get_current_selection()

        self.assertEqual(selection, [])

    def test_scanner_prefers_single_mesh_child_under_generic_group(self):
        selection = MayaAssetScanner(EmptySelectionGroupedSingleAssetCmds()).get_current_selection()

        self.assertEqual(selection, ["|group1|SM_B"])

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
            self.assertEqual(loaded["material_profile"], "")
        finally:
            shutil.rmtree(temp_dir)

    def test_manifest_writer_strips_target_path_trailing_newline(self):
        scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
        validation = StaticPropRuleValidator().validate(scan, TARGET_PLATFORM_HIGH_END_MOBILE)

        manifest = MayaManifestWriter().build(scan, validation, r"C:\Exports\SM_Crate_01.fbx", "/Game/Props/Test01\n")

        self.assertEqual(manifest["target_path"], "/Game/Props/Test01")

    def test_manifest_writer_rejects_internal_target_path_control_character(self):
        scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
        validation = StaticPropRuleValidator().validate(scan, TARGET_PLATFORM_HIGH_END_MOBILE)

        with self.assertRaises(ValueError):
            MayaManifestWriter().build(scan, validation, r"C:\Exports\SM_Crate_01.fbx", "/Game/Props/Te\nst")

    def test_scanner_renames_export_mesh_transforms_with_sm_prefix(self):
        cmds = RenameMeshTransformCmds()

        renamed = MayaAssetScanner(cmds).rename_mesh_transforms_with_prefix(["|SM_B"], "SM_")

        self.assertEqual(renamed, ["|SM_B|zuti|SM_B_a", "|SM_B|zuti|SM_B_b"])
        self.assertEqual(cmds.renamed, [("|SM_B|zuti|B_a", "SM_B_a"), ("|SM_B|zuti|B_b", "SM_B_b")])

    def test_pipeline_writes_export_report(self):
        temp_dir = tempfile.mkdtemp()
        try:
            scanner = MayaAssetScanner(FakeCmds())
            adapter = MayaAdapter(scanner=scanner, exporter=FakeExporter())
            pipeline = MayaStaticPropPipeline(adapter=adapter, exporter=FakeExporter())

            result = pipeline.export_asset("|SM_Crate_01", temp_dir, target_platform="pc")

            self.assertTrue(result["export_report_path"].endswith("/SM_Crate_01_export_report.json"))
            self.assertEqual(result["manifest"]["material_profile"], "Props_Opaque_PainterUE_ARM")
            self.assertTrue(result["manifest"]["material_profiles_snapshot_path"].endswith("/material_profiles_snapshot.json"))
            self.assertTrue(os.path.exists(result["manifest"]["material_profiles_snapshot_path"]))
            report = read_report(result["export_report_path"])
            self.assertEqual(report["stage"], "maya_export")
            self.assertEqual(report["asset_name"], "SM_Crate_01")
            self.assertEqual(report["validation"]["score"], result["validation"]["score"])
            self.assertTrue(report["material_profiles_snapshot_path"].endswith("/material_profiles_snapshot.json"))
            self.assertEqual(report["portfolio_capture_hint"], result["portfolio_capture_hint"])
            self.assertIn("录制前看这里：资产 SM_Crate_01 已可导出", report["portfolio_capture_hint"])
            self.assertIn("下一步在 UE Gate 选择该 Package，做预检、导入预演、批准导入", report["portfolio_capture_hint"])
        finally:
            shutil.rmtree(temp_dir)

    def test_pipeline_manifest_and_export_report_keep_chinese_utf8(self):
        temp_dir = tempfile.mkdtemp()
        try:
            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["asset_name"] = "SM_测试"
            scan["textures"] = []
            scan["materials"][0]["textures"] = []
            pipeline = MayaStaticPropPipeline(adapter=FakeScanAdapter(scan), exporter=FakeExporter())

            result = pipeline.export_asset("|SM_测试", os.path.join(temp_dir, "Exports"), target_platform="pc", target_path="/Game/Props/测试")

            with open(result["manifest_path"], "r", encoding="utf-8") as stream:
                manifest_raw = stream.read()
            with open(result["export_report_path"], "r", encoding="utf-8") as stream:
                report_raw = stream.read()

            self.assertIn("测试", manifest_raw)
            self.assertIn("测试", report_raw)
            mojibake = chr(0x5A34) + chr(0x5B2D) + chr(0x762F)
            self.assertNotIn(mojibake, manifest_raw)
            self.assertNotIn(mojibake, report_raw)
            self.assertEqual(result["manifest"]["asset_name"], "SM_测试")
        finally:
            shutil.rmtree(temp_dir)

    def test_pipeline_manifest_can_select_material_profile(self):
        temp_dir = tempfile.mkdtemp()
        try:
            pipeline = MayaStaticPropPipeline(
                adapter=FakeScanAdapter(MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")),
                exporter=FakeExporter(),
            )

            result = pipeline.export_asset(
                "|SM_Crate_01",
                temp_dir,
                target_platform="pc",
                material_profile="Props_Masked_PainterUE_ARM",
            )

            self.assertEqual(result["manifest"]["material_profile"], "Props_Masked_PainterUE_ARM")
        finally:
            shutil.rmtree(temp_dir)

    def test_pipeline_can_package_textures_from_external_folder(self):
        temp_dir = tempfile.mkdtemp()
        try:
            texture_folder = os.path.join(temp_dir, "Painter")
            os.makedirs(texture_folder)
            base_color = os.path.join(texture_folder, "SM_Crate_01_BaseColor.png")
            normal = os.path.join(texture_folder, "SM_Crate_01_Normal.png")
            with open(base_color, "wb") as stream:
                stream.write(b"fake base color")
            with open(normal, "wb") as stream:
                stream.write(b"fake normal")
            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["textures"] = []
            scan["materials"][0]["textures"] = []
            pipeline = MayaStaticPropPipeline(
                adapter=FakeScanAdapter(scan),
                exporter=FakeExporter(),
            )

            result = pipeline.export_asset(
                "|SM_Crate_01",
                os.path.join(temp_dir, "Exports"),
                target_platform="pc",
                texture_folder=texture_folder,
            )

            usages = [texture["usage"] for texture in result["manifest"]["textures"]]
            self.assertEqual(usages, ["base_color", "normal"])
            self.assertEqual(result["scan"]["texture_folder_scan"]["issues"], [])
            self.assertEqual(result["scan"]["texture_folder_scan"]["directory_status"], "valid")
            self.assertEqual(result["scan"]["texture_folder_scan"]["matched_count"], 2)
            self.assertEqual(result["scan"]["texture_folder_scan"]["texture_naming_validation"]["status"], "warning")
            self.assertTrue(result["export_report"]["texture_folder_scan"]["rename_suggestions"])
            self.assertEqual(result["scan"]["material_profile_validation"]["status"], "pass")
            self.assertTrue(result["manifest"]["textures"][0]["copied"])
            self.assertEqual(result["manifest"]["materials"][0]["textures"][0]["source_type"], "texture_folder")
        finally:
            shutil.rmtree(temp_dir)

    def test_pipeline_texture_folder_token_prioritizes_user_texture_set(self):
        temp_dir = tempfile.mkdtemp()
        try:
            texture_folder = os.path.join(temp_dir, "Painter")
            os.makedirs(texture_folder)
            for name in [
                "HK416_D_B_a1_BaseColor.png",
                "HK416_D_B_a1_Normal.png",
                "HK416_D_B_a1_OcclusionRoughnessMetallic.png",
                "HK416_D_B_d1_BaseColor.png",
                "HK416_D_B_d1_Normal.png",
                "HK416_D_B_d1_OcclusionRoughnessMetallic.png",
            ]:
                with open(os.path.join(texture_folder, name), "wb") as stream:
                    stream.write(b"fake texture")
            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["asset_name"] = "SM_B_e"
            scan["textures"] = [{"node": "maya_file", "path": "C:/Old/T_Only_BaseColor.png", "usage": "base_color"}]
            scan["materials"][0]["name"] = "B_d1"
            scan["materials"][0]["textures"] = list(scan["textures"])
            pipeline = MayaStaticPropPipeline(adapter=FakeScanAdapter(scan), exporter=FakeExporter())

            result = pipeline.export_asset(
                "|SM_B_e",
                os.path.join(temp_dir, "Exports"),
                target_platform="pc",
                texture_folder=texture_folder,
                texture_set_token="d1",
            )

            names = [os.path.basename(texture["source_path"]) for texture in result["manifest"]["textures"]]
            self.assertEqual(names, ["HK416_D_B_d1_BaseColor.png", "HK416_D_B_d1_Normal.png", "HK416_D_B_d1_OcclusionRoughnessMetallic.png"])
            self.assertEqual(result["scan"]["texture_folder_scan"]["texture_set_token"], "d1")
            self.assertTrue(all(texture["source_type"] == "texture_folder" for texture in result["manifest"]["textures"]))
            self.assertTrue(all("T_Only_BaseColor" not in texture.get("path", "") for texture in result["manifest"]["textures"]))
        finally:
            shutil.rmtree(temp_dir)

    def test_pipeline_maps_texture_sets_to_matching_material_names(self):
        temp_dir = tempfile.mkdtemp()
        try:
            texture_folder = os.path.join(temp_dir, "Painter")
            os.makedirs(texture_folder)
            for name in [
                "HK416_D_B_a1_BaseColor.png",
                "HK416_D_B_a1_Normal.png",
                "HK416_D_B_a1_OcclusionRoughnessMetallic.png",
                "HK416_D_B_d1_BaseColor.png",
                "HK416_D_B_d1_Normal.png",
                "HK416_D_B_d1_OcclusionRoughnessMetallic.png",
            ]:
                with open(os.path.join(texture_folder, name), "wb") as stream:
                    stream.write(b"fake texture")

            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["asset_name"] = "SM_zuti"
            scan["textures"] = []
            scan["materials"] = [
                {"name": "B_d1", "shading_group": "B_eSG", "type": "phong", "textures": []},
                {"name": "B_a1", "shading_group": "B_aSG", "type": "phong", "textures": []},
            ]
            pipeline = MayaStaticPropPipeline(adapter=FakeScanAdapter(scan), exporter=FakeExporter())

            result = pipeline.export_asset(
                "|SM_zuti",
                os.path.join(temp_dir, "Exports"),
                target_platform="pc",
                texture_folder=texture_folder,
                texture_set_token="a1,d1",
            )

            materials = dict((material["name"], material) for material in result["manifest"]["materials"])
            self.assertEqual(len(materials["B_d1"]["textures"]), 3)
            self.assertEqual(len(materials["B_a1"]["textures"]), 3)
            self.assertTrue(all(texture["selected_texture_set"] == "HK416_D_B_d1" for texture in materials["B_d1"]["textures"]))
            self.assertTrue(all(texture["selected_texture_set"] == "HK416_D_B_a1" for texture in materials["B_a1"]["textures"]))
            self.assertEqual(materials["B_d1"]["texture_set_short_name"], "d1")
            self.assertEqual(materials["B_a1"]["texture_set_short_name"], "a1")

            mapping = result["manifest"]["material_texture_sets"]
            self.assertEqual([(item["material_name"], item["texture_set_short_name"], item["texture_count"]) for item in mapping], [("B_d1", "d1", 3), ("B_a1", "a1", 3)])
            self.assertEqual([slot["name"] for slot in result["manifest"]["material_slots"]], ["B_d1", "B_a1"])
            self.assertEqual(result["export_report"]["material_texture_sets"][0]["binding_source"], "material_name_short_token")
            self.assertEqual(result["manifest"]["texture_folder_scan"]["material_texture_sets"][1]["material_name"], "B_a1")
            bindings = dict((item["material_name"], item) for item in result["manifest"]["material_texture_bindings"])
            self.assertEqual(bindings["B_d1"]["texture_set_short_name"], "d1")
            self.assertEqual(bindings["B_d1"]["texture_usages"], ["base_color", "normal", "packed_arm"])
            self.assertEqual(bindings["B_d1"]["slot_index"], 0)
            self.assertEqual(bindings["B_a1"]["slot_index"], 1)
            self.assertEqual(bindings["B_a1"]["ue_material_instance_name"], "MI_B_a1")
            self.assertEqual(bindings["B_a1"]["ue_material_instance_path"], "/Game/Props/Materials/MI_B_a1")
            self.assertEqual(bindings["B_d1"]["textures_by_usage"]["base_color"][0]["selected_texture_set"], "HK416_D_B_d1")
            self.assertEqual(result["export_report"]["material_texture_bindings"][1]["material_name"], "B_a1")
        finally:
            shutil.rmtree(temp_dir)

    def test_pipeline_auto_selects_texture_sets_from_material_names_when_token_empty(self):
        temp_dir = tempfile.mkdtemp()
        try:
            texture_folder = os.path.join(temp_dir, "Painter")
            os.makedirs(texture_folder)
            for set_name in ["a1", "b1", "d1"]:
                for suffix in ["BaseColor", "Normal", "OcclusionRoughnessMetallic"]:
                    with open(os.path.join(texture_folder, "T_HK416_D_B_{0}_{1}.png".format(set_name, suffix)), "wb") as stream:
                        stream.write(b"fake texture")

            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["asset_name"] = "SM_B"
            scan["textures"] = []
            scan["materials"] = [
                {"name": "B_d1", "shading_group": "B_eSG", "type": "phong", "textures": []},
                {"name": "B_a1", "shading_group": "B_aSG", "type": "phong", "textures": []},
                {"name": "B_b1", "shading_group": "B_bSG", "type": "phong", "textures": []},
            ]
            pipeline = MayaStaticPropPipeline(adapter=FakeScanAdapter(scan), exporter=FakeExporter())

            result = pipeline.export_asset(
                "|SM_B",
                os.path.join(temp_dir, "Exports"),
                target_platform="pc",
                texture_folder=texture_folder,
                texture_set_token="",
            )

            materials = dict((material["name"], material) for material in result["manifest"]["materials"])
            self.assertEqual(result["manifest"]["texture_folder_scan"]["auto_material_texture_set_token"], "d1,a1,b1")
            self.assertEqual(materials["B_d1"]["texture_set_short_name"], "d1")
            self.assertEqual(materials["B_a1"]["texture_set_short_name"], "a1")
            self.assertEqual(materials["B_b1"]["texture_set_short_name"], "b1")
            self.assertEqual(len(materials["B_d1"]["textures"]), 3)
            self.assertEqual(len(materials["B_a1"]["textures"]), 3)
            self.assertEqual(len(materials["B_b1"]["textures"]), 3)
            self.assertFalse(result["manifest"]["material_texture_binding_risks"])
        finally:
            shutil.rmtree(temp_dir)

    def test_pipeline_blocks_export_when_material_texture_set_is_missing(self):
        temp_dir = tempfile.mkdtemp()
        try:
            texture_folder = os.path.join(temp_dir, "Painter")
            os.makedirs(texture_folder)
            for set_name in ["b1", "d1"]:
                for suffix in ["BaseColor", "Normal", "OcclusionRoughnessMetallic"]:
                    with open(os.path.join(texture_folder, "T_HK416_D_B_{0}_{1}.png".format(set_name, suffix)), "wb") as stream:
                        stream.write(b"fake texture")

            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["asset_name"] = "SM_B"
            scan["textures"] = []
            scan["materials"] = [
                {"name": "B_d1", "shading_group": "B_eSG", "type": "phong", "textures": []},
                {"name": "B_a1", "shading_group": "B_aSG", "type": "phong", "textures": []},
                {"name": "B_b1", "shading_group": "B_bSG", "type": "phong", "textures": []},
            ]
            pipeline = MayaStaticPropPipeline(adapter=FakeScanAdapter(scan), exporter=FakeExporter())

            with self.assertRaises(ExportValidationError) as caught:
                pipeline.export_asset(
                    "|SM_B",
                    os.path.join(temp_dir, "Exports"),
                    target_platform="pc",
                    texture_folder=texture_folder,
                    texture_set_token="",
                )

            self.assertFalse(caught.exception.validation.get("can_export"))
            self.assertTrue(any(item.get("id") == "unmatched_material" and item.get("object") == "B_a1" for item in caught.exception.validation.get("checks", [])))
            self.assertTrue(any(item.get("id") == "unmatched_material" for item in caught.exception.scan.get("material_texture_binding_risks", [])))
        finally:
            shutil.rmtree(temp_dir)

    def test_material_texture_bindings_warn_shared_set_and_unmatched_material(self):
        scan = {
            "materials": [{"name": "B_a1"}, {"name": "B_copy_a1"}, {"name": "B_missing"}],
            "material_texture_sets": [
                {
                    "status": "bound",
                    "material_name": "B_a1",
                    "texture_set": "HK416_D_B_a1",
                    "texture_set_short_name": "a1",
                    "binding_source": "material_name_short_token",
                    "textures": [{"usage": "base_color", "source_path": "D:/Tex/T_B_a1_BaseColor.png"}],
                },
                {
                    "status": "bound",
                    "material_name": "B_copy_a1",
                    "texture_set": "HK416_D_B_a1",
                    "texture_set_short_name": "a1",
                    "binding_source": "manual_override",
                    "textures": [{"usage": "base_color", "source_path": "D:/Tex/T_B_a1_BaseColor.png"}],
                },
                {
                    "status": "unmatched_material",
                    "material_name": "B_missing",
                    "texture_set": "",
                    "texture_set_short_name": "",
                    "binding_source": "unmatched_material",
                    "textures": [],
                },
            ],
        }

        report = create_material_texture_bindings(scan, "/Game/Props")
        risk_ids = [item["id"] for item in report["risks"]]

        self.assertIn("shared_texture_set", risk_ids)
        self.assertIn("shared_texture_file", risk_ids)
        self.assertIn("unmatched_material", risk_ids)
        self.assertEqual(report["bindings"][0]["static_mesh_slot"]["index"], 0)
        self.assertEqual(report["bindings"][0]["ue_material_instance"]["path"], "/Game/Props/Materials/MI_B_a1")

    def test_material_texture_bindings_warn_unassigned_texture_set(self):
        scan = {
            "materials": [{"name": "B_a1"}],
            "material_texture_sets": [
                {
                    "status": "unassigned_texture_set",
                    "material_name": "",
                    "texture_set": "HK416_D_B_d1",
                    "texture_set_short_name": "d1",
                    "binding_source": "no_matching_material",
                    "textures": [{"usage": "normal", "source_path": "D:/Tex/T_B_d1_Normal.png"}],
                }
            ],
        }

        report = create_material_texture_bindings(scan, "/Game/Props")

        self.assertEqual(report["bindings"][0]["texture_set_short_name"], "d1")
        self.assertEqual(report["bindings"][0]["texture_count"], 1)
        self.assertTrue(any(item["id"] == "unassigned_texture_set" for item in report["risks"]))

    def test_preflight_attaches_asset_health_report_without_exporting(self):
        temp_dir = tempfile.mkdtemp()
        try:
            texture_folder = os.path.join(temp_dir, "Painter")
            os.makedirs(texture_folder)
            for name in [
                "HK416_D_B_a1_BaseColor.png",
                "HK416_D_B_a1_Normal.png",
                "HK416_D_B_d1_BaseColor.png",
                "HK416_D_B_d1_Normal.png",
            ]:
                with open(os.path.join(texture_folder, name), "wb") as stream:
                    stream.write(b"fake texture")

            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["asset_name"] = "SM_zuti"
            scan["materials"] = [
                {"name": "B_a1", "shading_group": "B_aSG", "type": "phong", "textures": []},
                {"name": "B_copy_a1", "shading_group": "B_copySG", "type": "phong", "textures": []},
            ]
            pipeline = MayaStaticPropPipeline(adapter=FakeScanAdapter(scan), exporter=FakeExporter())

            result = pipeline.preflight_assets(
                ["|SM_zuti"],
                target_platform="pc",
                texture_folder=texture_folder,
                texture_set_token="a1",
            )

            report = result["asset_health_report"]
            self.assertIn(report["status"], ["ready", "review"])
            self.assertIn("grade", report)
            self.assertFalse(os.path.exists(os.path.join(temp_dir, "Exports")))
            self.assertTrue(any(item["id"] == "unmatched_material" for item in report["texture_set_risks"]["items"]))
            self.assertEqual(result["scan"]["asset_health_report"]["score"], report["score"])
            self.assertEqual(result["validation"]["asset_health_report"]["score"], report["score"])
        finally:
            shutil.rmtree(temp_dir)

    def test_pipeline_blocked_export_writes_debug_report(self):
        temp_dir = tempfile.mkdtemp()
        try:
            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["asset_name"] = "Crate_01"
            pipeline = MayaStaticPropPipeline(adapter=FakeScanAdapter(scan), exporter=FakeExporter())

            with self.assertRaises(ExportValidationError) as caught:
                pipeline.export_asset("|Crate_01", os.path.join(temp_dir, "Exports"), target_platform="pc")

            self.assertTrue(caught.exception.debug_report_path.endswith("_export_blocked_report.json"))
            self.assertTrue(os.path.exists(caught.exception.debug_report_path))
            report = read_report(caught.exception.debug_report_path)
            self.assertEqual(report["schema_version"], "0.2")
            self.assertEqual(report["asset_forge_schema_version"], "0.2")
            self.assertEqual(report["source_dcc"], "maya")
            self.assertEqual(report["stage"], "maya_export_blocked")
            self.assertFalse(report["can_accept"])
            self.assertEqual(report["errors"][0]["id"], "name_prefix")
            self.assertEqual(report["asset_health_report"]["status"], "blocked")
            self.assertTrue(report["asset_health_report"]["auto_fix_suggestions"])
            self.assertEqual(report["summary"]["repair_action_count"], 1)
            self.assertEqual(report["repair_actions"][0]["id"], "fix_asset_name_prefix")
            self.assertEqual(report["repair_actions"][0]["label"], "修复资产名前缀")
            self.assertEqual(report["repair_actions"][0]["button_label"], "修复资产名前缀")
            self.assertEqual(report["repair_actions"][0]["target_label"], "修复资产名前缀按钮")
            self.assertEqual(report["repair_actions"][0]["ui_callback"], "_rename_prefix")
            self.assertEqual(report["repair_actions"][0]["problem"], "导出资产名缺少 SM_ 前缀")
            self.assertIn("next_action", report["repair_actions"][0])
            self.assertIn("next_step", report["repair_actions"][0])
            self.assertEqual(report["repair_actions"][0]["report_path"], caught.exception.debug_report_path.replace("\\", "/"))
            self.assertEqual(report["report_path"], caught.exception.debug_report_path.replace("\\", "/"))
            self.assertIn("录制前看这里：资产 Crate_01 还不能导出", report["portfolio_capture_hint"])
            self.assertIn("下一步点对应入口后重新检查", report["portfolio_capture_hint"])
        finally:
            shutil.rmtree(temp_dir)

    def test_pipeline_can_export_with_non_destructive_asset_name_override(self):
        temp_dir = tempfile.mkdtemp()
        try:
            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["asset_name"] = "B"
            pipeline = MayaStaticPropPipeline(adapter=FakeScanAdapter(scan), exporter=FakeExporter())

            result = pipeline.export_asset("|group1|B", os.path.join(temp_dir, "Exports"), target_platform="pc", asset_name_override="SM_B")

            self.assertEqual(result["scan"]["asset_name"], "SM_B")
            self.assertEqual(result["scan"]["asset_name_original"], "B")
            self.assertEqual(result["manifest"]["asset_name"], "SM_B")
            self.assertTrue(result["fbx_path"].endswith("/SM_B.fbx"))
        finally:
            shutil.rmtree(temp_dir)

    def test_blocked_export_report_keeps_chinese_utf8(self):
        temp_dir = tempfile.mkdtemp()
        try:
            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["asset_name"] = "Crate_01"
            mojibake_path = "E:/" + chr(0x5A34) + chr(0x5B2D) + chr(0x762F) + "/Test01"
            scan["source_path"] = mojibake_path
            pipeline = MayaStaticPropPipeline(adapter=FakeScanAdapter(scan), exporter=FakeExporter())

            with self.assertRaises(ExportValidationError) as caught:
                pipeline.export_asset("|Crate_01", os.path.join(temp_dir, "Exports"), target_platform="pc", target_path="/Game/Props/测试")

            with open(caught.exception.debug_report_path, "r", encoding="utf-8") as stream:
                raw = stream.read()
            report = read_report(caught.exception.debug_report_path)

            self.assertIn("测试", raw)
            mojibake = chr(0x5A34) + chr(0x5B2D) + chr(0x762F)
            self.assertNotIn(mojibake, raw)
            self.assertEqual(report["target_path"], "/Game/Props/测试")
            self.assertEqual(report["scan"]["source_path"], "E:/测试/Test01")
        finally:
            shutil.rmtree(temp_dir)

    def test_rename_asset_root_with_prefix_targets_identity_source_only(self):
        scan = {
            "asset_root": "|zuti|SM_B_a",
            "asset_roots": ["|zuti|SM_B_a", "|zuti|SM_B_e"],
            "asset_name": "zuti",
            "asset_name_source": "common_parent",
            "asset_name_source_path": "|zuti",
        }
        adapter = RenameRootAdapter(scan)
        pipeline = MayaStaticPropPipeline(adapter=adapter, exporter=FakeExporter())

        renamed = pipeline.rename_asset_root_with_prefix("SM_")

        self.assertEqual(adapter.renamed_roots, ["|zuti"])
        self.assertEqual(renamed, ["|SM_zuti"])

    def test_pipeline_exports_multiple_selected_roots_to_one_package_without_nested_asset_folder(self):
        temp_dir = tempfile.mkdtemp()
        try:
            output_package_dir = os.path.join(temp_dir, "SM_B_a")
            scan = {
                "asset_root": "|SM_B_a",
                "asset_roots": ["|SM_B_a", "|SM_B_e"],
                "asset_name": "SM_B_a",
                "mesh_count": 2,
                "meshes": ["|SM_B_a|meshShape", "|SM_B_e|meshShape"],
                "transform_count": 2,
                "transforms": ["|SM_B_a", "|SM_B_e"],
                "transform_data": {},
                "triangles": 100,
                "vertices": 50,
                "faces": 25,
                "material_slots": 1,
                "materials": [{"name": "B_d1", "textures": []}],
                "textures": [],
                "uv_sets": {"mesh": ["map1", "lightmap"]},
                "has_uv0": True,
                "has_lightmap_uv": True,
                "frozen_transform": True,
                "empty_meshes": [],
                "collision_nodes": [],
                "invalid_collision_nodes": [],
                "hidden_objects": [],
                "history_nodes": [],
                "illegal_scale": False,
            }
            exporter = MultiFakeExporter()
            pipeline = MayaStaticPropPipeline(adapter=MultiScanAdapter(scan), exporter=exporter)

            result = pipeline.export_assets(["|SM_B_a", "|SM_B_e"], output_package_dir, target_platform="pc")

            self.assertEqual(exporter.exported_roots, ["|SM_B_a", "|SM_B_e"])
            self.assertEqual(result["package_dir"], output_package_dir.replace("\\", "/"))
            self.assertTrue(result["fbx_path"].endswith("/SM_B_a.fbx"))
            self.assertNotIn("/SM_B_a/SM_B_a/", result["fbx_path"])
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

    def test_texture_packager_repeated_export_preserves_existing_texture_dir_files(self):
        temp_dir = tempfile.mkdtemp()
        try:
            texture_path = os.path.join(temp_dir, "T_Crate_BaseColor.png")
            with open(texture_path, "wb") as stream:
                stream.write(b"fake texture")
            old_path = os.path.join(temp_dir, "Textures", "Old_Texture.png")
            os.makedirs(os.path.dirname(old_path))
            with open(old_path, "wb") as stream:
                stream.write(b"old")
            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["textures"][0]["path"] = texture_path

            MayaTexturePackager().package_scan_textures(scan, temp_dir)

            self.assertTrue(os.path.exists(old_path))
            self.assertEqual(sorted(os.listdir(os.path.join(temp_dir, "Textures"))), ["Old_Texture.png", "T_Crate_BaseColor.png"])
        finally:
            shutil.rmtree(temp_dir)

    def test_texture_packager_repeated_export_overwrites_same_texture_name_without_suffix(self):
        temp_dir = tempfile.mkdtemp()
        try:
            texture_path = os.path.join(temp_dir, "T_Crate_BaseColor.png")
            with open(texture_path, "wb") as stream:
                stream.write(b"new texture")
            texture_dir = os.path.join(temp_dir, "Textures")
            os.makedirs(texture_dir)
            existing_path = os.path.join(texture_dir, "T_Crate_BaseColor.png")
            with open(existing_path, "wb") as stream:
                stream.write(b"old texture")
            scan = MayaAssetScanner(FakeCmds()).scan("|SM_Crate_01")
            scan["textures"][0]["path"] = texture_path

            MayaTexturePackager().package_scan_textures(scan, temp_dir)

            self.assertEqual(sorted(os.listdir(texture_dir)), ["T_Crate_BaseColor.png"])
            self.assertTrue(scan["textures"][0]["package_path"].endswith("/Textures/T_Crate_BaseColor.png"))
            with open(existing_path, "rb") as stream:
                self.assertEqual(stream.read(), b"new texture")
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


class MultiScanAdapter(FakeScanAdapter):
    def scan_assets(self, asset_roots, rules):
        result = dict(self.scan_result)
        result["asset_roots"] = list(asset_roots)
        return result


class RenameRootAdapter(FakeScanAdapter):
    def __init__(self, scan_result):
        FakeScanAdapter.__init__(self, scan_result)
        self.renamed_roots = []

    def get_current_selection(self):
        return list(self.scan_result.get("asset_roots", []))

    def scan_assets(self, asset_roots, rules):
        return dict(self.scan_result)

    def rename_with_prefix(self, asset_roots, prefix="SM_"):
        self.renamed_roots = list(asset_roots)
        return ["|{0}{1}".format(prefix, root.split("|")[-1]) for root in asset_roots]


class MultiFakeExporter(FakeExporter):
    def __init__(self):
        self.exported_roots = []

    def export_assets(self, asset_roots, output_path, preset=None):
        self.exported_roots = list(asset_roots)
        with open(output_path, "wb") as stream:
            stream.write(b"fake multi fbx")
        return output_path


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
