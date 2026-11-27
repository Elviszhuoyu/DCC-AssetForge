from __future__ import absolute_import

import json
import os
import sys
import tempfile
import unittest

import asset_forge.blender.provider_asset_forge as provider_module
from asset_forge.blender.provider_asset_forge import BlenderAssetForgeProvider, _write_png_rgba
from asset_forge.blender.scanner import BlenderStaticPropScanner
from asset_forge.shared.manifest_schema import read_manifest
from asset_forge.shared.rule_validator import StaticPropRuleValidator
from integrations.blender.asset_forge_extension import bridge
from integrations.blender_mcp.client import BlenderBridgeClient
from integrations.blender_mcp.protocol import ALL_ACTIONS
from integrations.blender_mcp_runtime.ports import allocate_port


class FakeMaterial(object):
    def __init__(self, name, textures=None):
        self.name = name
        self.diffuse_color = (0.72, 0.72, 0.72, 1.0)
        self.use_nodes = bool(textures)
        self.node_tree = FakeNodeTree(textures or [])


class FakeMaterialSlot(object):
    def __init__(self, material):
        if isinstance(material, FakeMaterial):
            self.material = material
            self.name = material.name
        else:
            self.material = FakeMaterial(material)
            self.name = material


class FakeColorspaceSettings(object):
    def __init__(self, name):
        self.name = name


class FakeImage(object):
    def __init__(self, filepath, name="", colorspace="sRGB"):
        self.filepath = filepath
        self.name = name or os.path.basename(filepath)
        self.colorspace_settings = FakeColorspaceSettings(colorspace)
        self.library = None


class FakeSocket(object):
    def __init__(self, name):
        self.name = name
        self.links = []


class FakeLink(object):
    def __init__(self, to_node, to_socket):
        self.to_node = to_node
        self.to_socket = to_socket


class FakeNode(object):
    def __init__(self, node_type, name, image=None):
        self.type = node_type
        self.name = name
        self.image = image
        self.outputs = [FakeSocket("Color")]


class FakeNodeTree(object):
    def __init__(self, textures):
        self.nodes = []
        principled = FakeNode("BSDF_PRINCIPLED", "Principled BSDF")
        normal_map = FakeNode("NORMAL_MAP", "Normal Map")
        for item in textures:
            path, target = item[0], item[1]
            image = FakeImage(path, colorspace="Non-Color" if target in ("normal", "packed_arm") else "sRGB")
            tex_node = FakeNode("TEX_IMAGE", "Image Texture " + target, image=image)
            if target == "base_color":
                tex_node.outputs[0].links.append(FakeLink(principled, FakeSocket("Base Color")))
            elif target == "normal":
                tex_node.outputs[0].links.append(FakeLink(normal_map, FakeSocket("Color")))
            self.nodes.append(tex_node)
        self.nodes.extend([principled, normal_map])


class FakeUvLayer(object):
    def __init__(self, name):
        self.name = name
        self.uv = [(0.0, 0.0)] * 6


class FakePolygon(object):
    def __init__(self, vertices):
        self.vertices = vertices


class FakeMeshData(object):
    def __init__(self, vertex_count=8, polygons=None, uv_names=None):
        self.vertices = list(range(vertex_count))
        self.polygons = [FakePolygon(item) for item in (polygons or [(0, 1, 2), (0, 2, 3)])]
        self.loop_triangles = list(range(len(self.polygons)))
        self.uv_layers = [FakeUvLayer(name) for name in (uv_names or ["UVMap", "LightmapUV"])]


class FakeObject(object):
    def __init__(self, name, object_type="MESH", data=None, children=None, materials=None):
        self.name = name
        self.type = object_type
        self.data = data or FakeMeshData()
        self.children = children or []
        self.parent = None
        for child in self.children:
            child.parent = self
        self.material_slots = [FakeMaterialSlot(item) for item in (materials or ["M_Body"])]
        self.location = (0.0, 0.0, 0.0)
        self.rotation_euler = (0.0, 0.0, 0.0)
        self.scale = (1.0, 1.0, 1.0)
        self.hide_viewport = False
        self.library = None

    def hide_get(self):
        return self.hide_viewport


class FakeActiveContainer(object):
    def __init__(self, active):
        self.active = active


class FakeViewLayer(object):
    def __init__(self, active):
        self.objects = FakeActiveContainer(active)


class FakeContext(object):
    def __init__(self, selected, active):
        self.selected_objects = selected
        self.active_object = active
        self.view_layer = FakeViewLayer(active)


class FakeData(object):
    def __init__(self, filepath, objects):
        self.filepath = filepath
        self.objects = objects


class FakeBpy(object):
    def __init__(self, selected=None, active=None, objects=None, root_name="SM_BlenderCrate"):
        mesh = FakeObject(root_name, materials=["M_Body", "M_Trim"])
        self.objects = objects if objects is not None else [mesh]
        self.data = FakeData("E:/Scenes/ProviderTest.blend", self.objects)
        active_object = self.objects[0] if self.objects else None
        if active is not None or active is None and objects is not None:
            active_object = active
        self.context = FakeContext(selected if selected is not None else [mesh], active_object)


class FakeExporter(object):
    def __init__(self):
        self.called = False

    def export_objects(self, asset_roots, fbx_path, rename_map=None):
        self.called = True
        raise AssertionError("export_objects should not run for blocked preflight")


class BlenderAssetForgeProviderTest(unittest.TestCase):
    def setUp(self):
        bridge.stop_bridge()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: os.path.isdir(self.temp_dir) and __import__("shutil").rmtree(self.temp_dir))
        self.addCleanup(bridge.stop_bridge)

    def test_provider_hot_reload_refreshes_package_naming_dependencies(self):
        calls = []
        original_reload = provider_module.importlib.reload

        def fake_reload(module):
            calls.append(module.__name__)
            return module

        provider_module.importlib.reload = fake_reload
        self.addCleanup(lambda: setattr(provider_module.importlib, "reload", original_reload))

        provider_module._refresh_shared_texture_modules_for_hot_reload()

        if "asset_forge.maya.export_package" in sys.modules:
            self.assertIn("asset_forge.maya.export_package", calls)
        if "asset_forge.shared.manifest_schema" in sys.modules:
            self.assertIn("asset_forge.shared.manifest_schema", calls)
        if "asset_forge.shared.package_naming" in sys.modules:
            self.assertIn("asset_forge.shared.package_naming", calls)

    def test_scanner_reads_static_prop_fields_from_selection(self):
        scanner = BlenderStaticPropScanner(bpy_module=FakeBpy())

        scan = scanner.scan_selection()

        self.assertEqual(scan["asset_name"], "SM_BlenderCrate")
        self.assertEqual(scan["source_dcc"], "blender")
        self.assertEqual(scan["mesh_count"], 1)
        self.assertEqual(scan["triangles"], 2)
        self.assertEqual(scan["vertices"], 8)
        self.assertEqual(scan["material_slots"], 2)
        self.assertEqual(scan["material_slot_details"][0]["name"], "M_Body")
        self.assertTrue(scan["has_uv0"])
        self.assertTrue(scan["has_lightmap_uv"])
        self.assertTrue(scan["frozen_transform"])

    def test_missing_and_empty_uv_layers_report_the_render_mesh(self):
        body = FakeObject("Body")
        trim = FakeObject("Trim")
        collider = FakeObject("UCX_SM_Prop_00")
        collider.data.uv_layers = []
        root = FakeObject("SM_Prop", object_type="EMPTY", children=[body, trim, collider])
        scanner = BlenderStaticPropScanner(bpy_module=FakeBpy(selected=[root], objects=[root, body, trim, collider]))
        validator = StaticPropRuleValidator()

        for layers in ([], [FakeUvLayer("UVMap"), FakeUvLayer("Lightmap")]):
            trim.data.uv_layers = layers
            if layers:
                layers[0].uv = []
            scan = scanner.scan_selection()
            validation = validator.validate(scan)
            checks = {item["id"]: item for item in validation["checks"]}
            self.assertFalse(scan["has_uv0"])
            self.assertFalse(validation["can_export"])
            self.assertEqual(checks["uv0"]["affected_meshes"], ["Trim"])
            self.assertEqual(scan["has_lightmap_uv"], bool(layers))
        trim.data.uv_layers[0].uv = [(0.0, 0.0)] * 6
        self.assertTrue(validator.validate(scanner.scan_selection())["can_export"])

    def test_edit_mode_uv_coverage_reads_live_bmesh(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        mesh = FakeObject("SM_Prop")
        mesh.data.is_editmode = True
        mesh.data.uv_layers = []
        bmesh = SimpleNamespace(
            loops=SimpleNamespace(layers=SimpleNamespace(uv={"UVMap": 0, "Lightmap": 1})),
            faces=[SimpleNamespace(verts=(0, 1, 2))],
        )
        scanner = BlenderStaticPropScanner(bpy_module=FakeBpy(selected=[mesh], objects=[mesh]))
        with patch.dict(sys.modules, {"bmesh": SimpleNamespace(from_edit_mesh=lambda data: bmesh)}):
            scan = scanner.scan_selection()
        self.assertEqual(scan["uv_coordinate_counts"][mesh.name], [3, 3])
        self.assertTrue(scan["has_lightmap_uv"])

    def test_scanner_reads_image_texture_nodes_from_blender_materials(self):
        base_color = os.path.join(self.temp_dir, "T_Body_BaseColor.png")
        normal = os.path.join(self.temp_dir, "T_Body_Normal.png")
        packed = os.path.join(self.temp_dir, "T_Body_ARM.png")
        material = FakeMaterial("M_Body", textures=[(base_color, "base_color"), (normal, "normal"), (packed, "packed_arm")])
        mesh = FakeObject("B", materials=[material])
        scanner = BlenderStaticPropScanner(bpy_module=FakeBpy(selected=[mesh], objects=[mesh]))

        scan = scanner.scan_selection()
        textures_by_usage = dict((item["usage"], item) for item in scan["materials"][0]["textures"])

        self.assertEqual(textures_by_usage["base_color"]["source_type"], "blender_image_node")
        self.assertEqual(textures_by_usage["base_color"]["parameter"], "BaseColor")
        self.assertTrue(textures_by_usage["base_color"]["srgb"])
        self.assertEqual(textures_by_usage["normal"]["compression"], "normalmap")
        self.assertEqual(textures_by_usage["packed_arm"]["channels"]["g"], "roughness")

    def test_scanner_does_not_block_on_container_transform_when_meshes_are_frozen(self):
        mesh = FakeObject("B_a", materials=["M_Body"])
        container = FakeObject("B", object_type="EMPTY", children=[mesh], data=None, materials=[])
        container.location = (12.0, 0.0, -3.0)
        container.rotation_euler = (0.0, 0.0, 0.0)
        container.scale = (1.0, 1.0, 1.0)
        scanner = BlenderStaticPropScanner(bpy_module=FakeBpy(selected=[container], objects=[container, mesh]))

        scan = scanner.scan_selection()

        self.assertTrue(scan["frozen_transform"])
        self.assertFalse(scan["container_frozen_transform"])
        self.assertEqual(scan["asset_name"], "SM_B")

    def test_scanner_auto_prefixes_non_sm_source_name_without_renaming_scene(self):
        scanner = BlenderStaticPropScanner(bpy_module=FakeBpy(root_name="B"))

        scan = scanner.scan_selection()

        self.assertEqual(scan["asset_name"], "SM_B")
        self.assertEqual(scan["source_asset_name"], "B")
        self.assertEqual(scan["asset_name_source_name"], "B")
        self.assertIn("B", scan["asset_name_candidates"])

    def test_scanner_uses_active_child_when_selection_collection_is_empty(self):
        child = FakeObject("B_a", materials=["M_Body"])
        root = FakeObject("B", object_type="EMPTY", data=None, children=[child], materials=[])
        group = FakeObject("group1", object_type="EMPTY", data=None, children=[root], materials=[])
        scanner = BlenderStaticPropScanner(bpy_module=FakeBpy(selected=[], active=child, objects=[group, root, child]))

        scan = scanner.scan_selection()

        self.assertEqual(scan["asset_root"], "B")
        self.assertEqual(scan["asset_name"], "SM_B")
        self.assertEqual(scan["meshes"], ["B_a"])

    def test_scanner_promotes_organization_root_selection_to_real_asset_root(self):
        child = FakeObject("B_a", materials=["M_Body"])
        root = FakeObject("B", object_type="EMPTY", data=None, children=[child], materials=[])
        group = FakeObject("group1", object_type="EMPTY", data=None, children=[root], materials=[])
        scanner = BlenderStaticPropScanner(bpy_module=FakeBpy(selected=[group], objects=[group, root, child]))

        scan = scanner.scan_selection()

        self.assertEqual(scan["asset_root"], "B")
        self.assertEqual(scan["asset_name"], "SM_B")

    def test_preflight_allows_non_sm_source_name_after_auto_prefix(self):
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(root_name="B"))

        result = provider.preflight_static_prop({})

        self.assertEqual(result["scan"]["asset_name"], "SM_B")
        self.assertTrue(result["can_export"])
        self.assertEqual(result["validation"]["summary"]["errors"], 0)

    def test_preflight_uses_blender_ui_prefix_and_triangle_budget(self):
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(root_name="B"))

        result = provider.preflight_static_prop({"mesh_prefix": "AF_", "triangle_budget": 1})
        checks = dict((item["id"], item) for item in result["validation"]["checks"])

        self.assertEqual(result["scan"]["asset_name"], "AF_B")
        self.assertEqual(result["scan"]["asset_name_prefix"], "AF_")
        self.assertEqual(result["validation"]["asset_name"], "AF_B")
        self.assertEqual(checks["name_prefix"]["status"], "pass")
        self.assertEqual(checks["name_prefix"]["limit"], "AF_")
        self.assertEqual(checks["triangle_budget"]["status"], "warning")
        self.assertEqual(checks["triangle_budget"]["limit"], 1)
        self.assertTrue(result["can_export"])

    def test_blender_transform_warning_does_not_block_export(self):
        mesh = FakeObject("B")
        mesh.scale = (0.01, 0.01, 0.01)
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(selected=[mesh], objects=[mesh]))

        result = provider.preflight_static_prop({})
        checks = dict((item["id"], item) for item in result["validation"]["checks"])

        self.assertTrue(result["can_export"])
        self.assertEqual(result["validation"]["summary"]["errors"], 0)
        self.assertEqual(checks["frozen_transform"]["status"], "warning")

    def test_preflight_uses_shared_static_prop_rules(self):
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy())

        result = provider.preflight_static_prop({})

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["can_export"])
        self.assertEqual(result["validation"]["asset_name"], "SM_BlenderCrate")
        self.assertEqual(result["validation"]["summary"]["errors"], 0)

    def test_package_contract_writes_blender_manifest_without_claiming_ue_ready(self):
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(root_name="B"))

        result = provider.build_static_prop_package_contract(
            {
                "export_root": self.temp_dir,
                "target_path": "/Game/Props/Blender",
                "material_profile": "Props_Opaque_PainterUE_ARM",
                "texture_import_policy": {"virtual_texture_policy": "force_off", "texture_streaming_policy": "streaming", "texture_group": "project_default"},
                "static_mesh_import_policy": {"nanite_policy": "disable", "lod_group": "SmallProp", "import_lod_policy": "import_existing"},
            }
        )
        manifest = read_manifest(result["manifest_path"])
        with open(result["export_report_path"], "r", encoding="utf-8") as stream:
            report = json.load(stream)

        self.assertEqual(result["fbx_export_status"], "planned")
        self.assertFalse(result["can_continue_to_ue"])
        self.assertEqual(manifest["source_dcc"], "blender")
        self.assertEqual(manifest["asset_name"], "SM_B")
        self.assertEqual(manifest["target_path"], "/Game/Props/Blender")
        self.assertEqual(manifest["texture_import_policy"]["virtual_texture_policy"], "force_off")
        self.assertEqual(manifest["static_mesh_import_policy"]["nanite_policy"], "disable")
        self.assertEqual(manifest["static_mesh_import_policy"]["lod_group"], "SmallProp")
        self.assertEqual(len(manifest["textures"]), 6)
        self.assertEqual(manifest["textures"][0]["source_type"], "blender_placeholder")
        self.assertEqual(len(manifest["material_texture_bindings"]), 2)
        self.assertEqual(manifest["material_texture_bindings"][0]["texture_usages"], ["base_color", "normal", "packed_arm"])
        self.assertEqual(manifest["fbx_export_status"], "planned")
        self.assertFalse(manifest["can_continue_to_ue"])
        self.assertEqual(report["package_contract_status"], "draft")
        self.assertFalse(os.path.exists(manifest["fbx_path"]))

    def test_package_contract_uses_custom_prefix_for_asset_identity(self):
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(root_name="B"))

        result = provider.build_static_prop_package_contract({"export_root": self.temp_dir, "mesh_prefix": "AF_", "triangle_budget": 1})
        manifest = read_manifest(result["manifest_path"])
        checks = dict((item["id"], item) for item in result["validation"]["checks"])

        self.assertEqual(manifest["asset_name"], "AF_B")
        self.assertEqual(checks["name_prefix"]["limit"], "AF_")
        self.assertEqual(checks["triangle_budget"]["limit"], 1)

    def test_package_contract_sanitizes_blender_material_names_for_unreal_slots(self):
        mesh = FakeObject("B", materials=["B_b1.001"])
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(selected=[mesh], objects=[mesh]))

        result = provider.build_static_prop_package_contract({"export_root": self.temp_dir, "target_path": "/Game/Props/Blender"})
        manifest = read_manifest(result["manifest_path"])

        self.assertEqual(manifest["materials"][0]["material_name"], "B_b1_001")
        self.assertEqual(manifest["materials"][0]["source_material_name"], "B_b1.001")
        self.assertEqual(manifest["material_slots"][0]["name"], "B_b1_001")
        self.assertEqual(manifest["material_slots"][0]["source_slot_name"], "B_b1.001")
        self.assertEqual(manifest["material_texture_bindings"][0]["material_name"], "B_b1_001")
        self.assertEqual(manifest["material_texture_bindings"][0]["ue_material_instance_path"], "/Game/Props/Blender/Materials/MI_B_b1_001")

    def test_package_contract_copies_blender_image_node_textures(self):
        source = os.path.join(self.temp_dir, "source", "T_Body_BaseColor.png")
        _write_png_rgba(source, 2, 1, [(255, 0, 0, 255), (0, 255, 0, 255)])
        material = FakeMaterial("M_Body", textures=[(source, "base_color")])
        mesh = FakeObject("B", materials=[material])
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(selected=[mesh], objects=[mesh]))

        result = provider.build_static_prop_package_contract({"export_root": self.temp_dir, "target_path": "/Game/Props/Blender"})
        manifest = read_manifest(result["manifest_path"])
        textures_by_usage = dict((item["usage"], item) for item in manifest["materials"][0]["textures"])

        self.assertEqual(textures_by_usage["base_color"]["source_type"], "blender_image_node")
        self.assertTrue(textures_by_usage["base_color"]["copied"])
        self.assertTrue(os.path.exists(textures_by_usage["base_color"]["package_path"]))
        self.assertNotEqual(textures_by_usage["base_color"]["source_path"], textures_by_usage["base_color"]["package_path"])
        self.assertEqual(textures_by_usage["base_color"]["width"], 2)
        self.assertEqual(textures_by_usage["normal"]["source_type"], "blender_placeholder")
        self.assertEqual(manifest["material_texture_sets"][0]["binding_source"], "blender_image_node")

    def test_package_contract_uses_texture_folder_to_complete_blender_node_materials(self):
        node_source = os.path.join(self.temp_dir, "source", "T_Node_BaseColor.png")
        _write_png_rgba(node_source, 2, 1, [(255, 0, 0, 255), (0, 255, 0, 255)])
        texture_root = os.path.join(self.temp_dir, "textures")
        for name in [
            "T_HK416_D_B_a1_BaseColor.png",
            "T_HK416_D_B_a1_Normal.png",
            "T_HK416_D_B_a1_OcclusionRoughnessMetallic.png",
            "T_HK416_D_B_b1_BaseColor.png",
            "T_HK416_D_B_b1_Normal.png",
            "T_HK416_D_B_b1_OcclusionRoughnessMetallic.png",
        ]:
            _write_png_rgba(os.path.join(texture_root, name), 1, 1, [(128, 128, 128, 255)])
        material = FakeMaterial("B_a1", textures=[(node_source, "base_color")])
        mesh = FakeObject("B", materials=[material])
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(selected=[mesh], objects=[mesh]))

        result = provider.build_static_prop_package_contract(
            {
                "export_root": self.temp_dir,
                "target_path": "/Game/Props/Blender",
                "texture_folder": texture_root,
            }
        )
        manifest = read_manifest(result["manifest_path"])
        textures_by_usage = dict((item["usage"], item) for item in manifest["materials"][0]["textures"])

        self.assertEqual(manifest["texture_folder_scan"]["auto_material_texture_set_token"], "a1")
        self.assertEqual(textures_by_usage["base_color"]["source_type"], "texture_folder")
        self.assertEqual(textures_by_usage["normal"]["source_type"], "texture_folder")
        self.assertEqual(textures_by_usage["packed_arm"]["source_type"], "texture_folder")
        self.assertEqual(manifest["material_texture_sets"][0]["binding_source"], "blender_image_node+texture_folder")
        self.assertEqual(manifest["material_texture_bindings"][0]["texture_usages"], ["base_color", "normal", "packed_arm"])

    def test_preflight_uses_texture_folder_to_complete_blender_node_materials(self):
        node_source = os.path.join(self.temp_dir, "source", "T_Node_BaseColor.png")
        _write_png_rgba(node_source, 1, 1, [(255, 0, 0, 255)])
        texture_root = os.path.join(self.temp_dir, "textures")
        for name in [
            "T_HK416_D_B_a1_BaseColor.png",
            "T_HK416_D_B_a1_Normal.png",
            "T_HK416_D_B_a1_OcclusionRoughnessMetallic.png",
            "T_HK416_D_B_b1_BaseColor.png",
            "T_HK416_D_B_b1_Normal.png",
            "T_HK416_D_B_b1_OcclusionRoughnessMetallic.png",
        ]:
            _write_png_rgba(os.path.join(texture_root, name), 1, 1, [(128, 128, 128, 255)])
        material = FakeMaterial("B_a1", textures=[(node_source, "base_color")])
        mesh = FakeObject("B", materials=[material])
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(selected=[mesh], objects=[mesh]))

        result = provider.preflight_static_prop({"texture_folder": texture_root, "target_path": "/Game/Props/Blender"})
        textures_by_usage = dict((item["usage"], item) for item in result["scan"]["materials"][0]["textures"])

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["can_export"])
        self.assertEqual(result["texture_folder_scan"]["auto_material_texture_set_token"], "a1")
        self.assertEqual(textures_by_usage["base_color"]["source_type"], "texture_folder")
        self.assertEqual(textures_by_usage["normal"]["source_type"], "texture_folder")
        self.assertEqual(textures_by_usage["packed_arm"]["source_type"], "texture_folder")
        self.assertEqual(result["scan"]["material_texture_bindings"][0]["texture_usages"], ["base_color", "normal", "packed_arm"])

    def test_package_name_override_does_not_rename_blender_asset(self):
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(root_name="B"))

        result = provider.build_static_prop_package_contract(
            {
                "export_root": self.temp_dir,
                "target_path": "/Game/Props/Blender",
                "source_name_suffix": "Blender",
                "package_name_override": "Client Preview",
            }
        )
        manifest = read_manifest(result["manifest_path"])

        self.assertEqual(manifest["asset_name"], "SM_B_Blender")
        self.assertEqual(manifest["target_path"], "/Game/Props/Blender")
        self.assertEqual(manifest["package_naming"]["package_name"], "Client_Preview")
        self.assertTrue(result["package_dir"].endswith("/Client_Preview"))
        self.assertEqual(manifest["fbx_export_status"], "planned")

    def test_auto_increment_package_version_drives_blender_package_folder(self):
        os.makedirs(os.path.join(self.temp_dir, "SM_B_Blender_v001"))
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(root_name="B"))

        result = provider.build_static_prop_package_contract(
            {
                "export_root": self.temp_dir,
                "source_name_suffix": "Blender",
                "package_version_mode": "auto_increment",
                "project_preset": {"preset_name": "Team", "preset_version": "0.3", "target_engine_version": "5.8"},
            }
        )
        manifest = read_manifest(result["manifest_path"])

        self.assertEqual(manifest["asset_name"], "SM_B_Blender")
        self.assertEqual(manifest["package_naming"]["package_name"], "SM_B_Blender_v002")
        self.assertEqual(manifest["package_naming"]["version_mode"], "auto_increment")
        self.assertEqual(manifest["project_preset"]["preset_name"], "Team")
        self.assertEqual(manifest["target_engine_version"], "5.8")
        self.assertTrue(result["package_dir"].endswith("/SM_B_Blender_v002"))

    def test_export_result_includes_scan_for_ui_status_counts(self):
        class WritingExporter(object):
            def export_objects(self, _asset_roots, fbx_path, rename_map=None):
                parent = os.path.dirname(fbx_path)
                if parent and not os.path.isdir(parent):
                    os.makedirs(parent)
                with open(fbx_path, "wb") as stream:
                    stream.write(b"fbx")
                return fbx_path

        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(root_name="B"), exporter=WritingExporter())

        result = provider.export_static_prop_package({"export_root": self.temp_dir, "target_path": "/Game/Props/Blender"})

        self.assertEqual(result["status"], "success")
        self.assertIn("scan", result)
        self.assertTrue(result["scan"]["materials"])
        self.assertTrue(result["scan"]["textures"])
        self.assertEqual(len(result["scan"]["textures"]), len(result["manifest"]["textures"]))

    def test_source_name_suffix_drives_blender_default_publish_identity(self):
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(root_name="B"))

        result = provider.build_static_prop_package_contract(
            {
                "export_root": self.temp_dir,
                "source_name_suffix": "Blender",
            }
        )
        manifest = read_manifest(result["manifest_path"])

        self.assertEqual(manifest["asset_name"], "SM_B_Blender")
        self.assertTrue(result["package_dir"].endswith("/SM_B_Blender"))
        self.assertEqual(provider._static_mesh_export_name("SM_B_Blender", "B_a", "SM_", "B"), "SM_B_a_Blender")
        self.assertEqual(provider._static_mesh_export_name("SM_B_Blender", "SM_B_a", "SM_", "B"), "SM_B_a_Blender")

    def test_preflight_texture_family_token_binds_blender_duplicate_material_suffixes(self):
        texture_root = os.path.join(self.temp_dir, "textures")
        for set_name in ["a1", "b1", "d1"]:
            for suffix in ["BaseColor", "Normal", "OcclusionRoughnessMetallic"]:
                _write_png_rgba(os.path.join(texture_root, "T_HK416_D_B_{0}_{1}.png".format(set_name, suffix)), 1, 1, [(128, 128, 128, 255)])
        for suffix in ["BaseColor", "Normal", "OcclusionRoughnessMetallic"]:
            _write_png_rgba(os.path.join(texture_root, "T_HK416_D_H_a_{0}.png".format(suffix)), 1, 1, [(128, 128, 128, 255)])
        mesh = FakeObject("B", materials=["B_a1", "B_b1.001", "B_d1.002", "B_d1.001"])
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(selected=[mesh], objects=[mesh]))

        result = provider.preflight_static_prop(
            {
                "texture_folder": texture_root,
                "texture_set_token": "B",
                "target_path": "/Game/Props/Blender",
            }
        )

        bindings = dict((item["material_name"], item) for item in result["scan"]["material_texture_bindings"])
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["can_export"])
        self.assertEqual(result["texture_folder_scan"]["selected_texture_set_short_names"], ["a1", "b1", "d1"])
        self.assertEqual(bindings["B_a1"]["texture_set_short_name"], "a1")
        self.assertEqual(bindings["B_b1_001"]["texture_set_short_name"], "b1")
        self.assertEqual(bindings["B_d1_002"]["texture_set_short_name"], "d1")
        self.assertEqual(bindings["B_d1_001"]["texture_set_short_name"], "d1")
        self.assertFalse([item for item in result["scan"]["material_texture_binding_risks"] if item.get("id") == "unmatched_material"])

    def test_preflight_blocks_ambiguous_texture_folder_without_material_token(self):
        texture_root = os.path.join(self.temp_dir, "textures")
        for name in [
            "T_HK416_D_B_a1_BaseColor.png",
            "T_HK416_D_B_a1_Normal.png",
            "T_HK416_D_B_a1_OcclusionRoughnessMetallic.png",
            "T_HK416_D_B_b1_BaseColor.png",
            "T_HK416_D_B_b1_Normal.png",
            "T_HK416_D_B_b1_OcclusionRoughnessMetallic.png",
        ]:
            _write_png_rgba(os.path.join(texture_root, name), 1, 1, [(128, 128, 128, 255)])
        mesh = FakeObject("B", materials=["M_Body"])
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(selected=[mesh], objects=[mesh]))

        result = provider.preflight_static_prop({"texture_folder": texture_root, "target_path": "/Game/Props/Blender"})
        checks = dict((item["id"], item) for item in result["validation"]["checks"])

        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["can_export"])
        self.assertTrue(result["texture_folder_scan"]["requires_texture_set_selection"])
        self.assertIn("texture_set_selection", checks)
        self.assertEqual(checks["texture_set_selection"]["status"], "error")

    def test_export_blocks_generic_slot_with_two_selected_painter_sets(self):
        texture_root = os.path.join(self.temp_dir, "Painter")
        for name in ("Body", "Trim"):
            for suffix in ("BaseColor", "Normal", "ORM"):
                path = os.path.join(texture_root, "Prop_{0}_{1}.png".format(name, suffix))
                _write_png_rgba(path, 1, 1, [(128, 128, 128, 255)])
        mesh = FakeObject("SM_Panel", materials=["M_Generic"])
        exporter = FakeExporter()
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(selected=[mesh], objects=[mesh]), exporter=exporter)
        params = {"export_root": self.temp_dir, "texture_folder": texture_root}
        for token in ("Body,Trim", "Trim,Body"):
            result = provider.export_static_prop_package(dict(params, texture_set_token=token))
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["can_continue_to_ue"])
            self.assertFalse(exporter.called)
            risk = next(item for item in result["scan"]["material_texture_binding_risks"]
                        if item["id"] == "ambiguous_material_texture_set")
            self.assertEqual(risk["candidates"], ["Prop_Body", "Prop_Trim"])
        selected = provider.preflight_static_prop(dict(params, texture_set_token="Trim"))
        self.assertTrue(selected["can_export"])
        binding = selected["scan"]["material_texture_bindings"][0]
        self.assertEqual(binding["texture_set"], "Prop_Trim")
        self.assertEqual(binding["texture_count"], 3)

    def test_export_blocks_ambiguous_texture_folder_before_fbx_export(self):
        texture_root = os.path.join(self.temp_dir, "textures")
        for name in [
            "T_HK416_D_B_a1_BaseColor.png",
            "T_HK416_D_B_a1_Normal.png",
            "T_HK416_D_B_a1_OcclusionRoughnessMetallic.png",
            "T_HK416_D_B_b1_BaseColor.png",
            "T_HK416_D_B_b1_Normal.png",
            "T_HK416_D_B_b1_OcclusionRoughnessMetallic.png",
        ]:
            _write_png_rgba(os.path.join(texture_root, name), 1, 1, [(128, 128, 128, 255)])
        mesh = FakeObject("B", materials=["M_Body"])
        exporter = FakeExporter()
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(selected=[mesh], objects=[mesh]), exporter=exporter)

        result = provider.export_static_prop_package(
            {
                "export_root": self.temp_dir,
                "target_path": "/Game/Props/Blender",
                "texture_folder": texture_root,
            }
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["fbx_export_status"], "blocked")
        self.assertFalse(result["can_continue_to_ue"])
        self.assertFalse(exporter.called)

    def test_package_contract_allows_blender_duplicate_materials_to_share_texture_set(self):
        texture_root = os.path.join(self.temp_dir, "textures")
        for name in [
            "T_HK416_D_B_d1_BaseColor.png",
            "T_HK416_D_B_d1_Normal.png",
            "T_HK416_D_B_d1_OcclusionRoughnessMetallic.png",
        ]:
            _write_png_rgba(os.path.join(texture_root, name), 1, 1, [(128, 128, 128, 255)])
        mesh = FakeObject("B", materials=["B_d1.001", "B_d1.002"])
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(selected=[mesh], objects=[mesh]))

        result = provider.build_static_prop_package_contract(
            {
                "export_root": self.temp_dir,
                "target_path": "/Game/Props/Blender",
                "texture_folder": texture_root,
            }
        )
        manifest = read_manifest(result["manifest_path"])

        for material in manifest["materials"]:
            self.assertEqual(dict((item["usage"], item["source_type"]) for item in material["textures"])["normal"], "texture_folder")
            self.assertEqual(material["texture_set"], "HK416_D_B_d1")
        self.assertTrue(any(item["id"] == "shared_texture_set" for item in manifest["material_texture_binding_risks"]))

    def test_empty_selection_without_active_object_returns_readable_bridge_error(self):
        port = allocate_port("127.0.0.1", 8900, 8999)
        registered = bridge.start_bridge(port=port, token="secret", bpy_module=FakeBpy(selected=[], active=None, objects=[]), repo_root=self.temp_dir, registry_path=os.path.join(self.temp_dir, "instances.json"))
        client = BlenderBridgeClient.from_instance(registered)

        with self.assertRaises(RuntimeError) as caught:
            client.call("blender_scan_static_prop", {})

        self.assertIn("没有选中资产", str(caught.exception))

    def test_bridge_socket_runs_provider_actions(self):
        port = allocate_port("127.0.0.1", 8900, 8999)
        registered = bridge.start_bridge(port=port, token="secret", bpy_module=FakeBpy(), repo_root=self.temp_dir, registry_path=os.path.join(self.temp_dir, "instances.json"))
        client = BlenderBridgeClient.from_instance(registered)

        scan = client.call("blender_scan_static_prop", {})
        preflight = client.call("blender_preflight_static_prop", {})
        package = client.call("blender_build_static_prop_package_contract", {"export_root": self.temp_dir})

        self.assertEqual(scan["scan"]["asset_name"], "SM_BlenderCrate")
        self.assertTrue(preflight["can_export"])
        self.assertEqual(package["fbx_export_status"], "planned")
        self.assertFalse(package["can_continue_to_ue"])

    def test_blender_tool_whitelist_has_provider_actions_but_no_exec(self):
        self.assertIn("blender_scan_static_prop", ALL_ACTIONS)
        self.assertIn("blender_preflight_static_prop", ALL_ACTIONS)
        self.assertIn("blender_build_static_prop_package_contract", ALL_ACTIONS)
        self.assertNotIn("blender_run_python", ALL_ACTIONS)
        self.assertFalse(any("exec" in name or "eval" in name for name in ALL_ACTIONS))


if __name__ == "__main__":
    unittest.main()
