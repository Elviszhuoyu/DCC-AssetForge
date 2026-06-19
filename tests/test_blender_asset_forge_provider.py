from __future__ import absolute_import

import json
import os
import tempfile
import unittest

from asset_forge.blender.provider_asset_forge import BlenderAssetForgeProvider
from asset_forge.blender.scanner import BlenderStaticPropScanner
from asset_forge.shared.manifest_schema import read_manifest
from integrations.blender.asset_forge_extension import bridge
from integrations.blender_mcp.client import BlenderBridgeClient
from integrations.blender_mcp.protocol import ALL_ACTIONS
from integrations.blender_mcp_runtime.ports import allocate_port


class FakeMaterial(object):
    def __init__(self, name):
        self.name = name


class FakeMaterialSlot(object):
    def __init__(self, name):
        self.material = FakeMaterial(name)
        self.name = name


class FakeUvLayer(object):
    def __init__(self, name):
        self.name = name


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
        self.material_slots = [FakeMaterialSlot(name) for name in (materials or ["M_Body"])]
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
    def __init__(self, selected=None, objects=None, root_name="SM_BlenderCrate"):
        mesh = FakeObject(root_name, materials=["M_Body", "M_Trim"])
        self.objects = objects or [mesh]
        self.data = FakeData("E:/Scenes/ProviderTest.blend", self.objects)
        self.context = FakeContext(selected if selected is not None else [mesh], self.objects[0] if self.objects else None)


class BlenderAssetForgeProviderTest(unittest.TestCase):
    def setUp(self):
        bridge.stop_bridge()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: os.path.isdir(self.temp_dir) and __import__("shutil").rmtree(self.temp_dir))
        self.addCleanup(bridge.stop_bridge)

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


    def test_scanner_auto_prefixes_non_sm_source_name_without_renaming_scene(self):
        scanner = BlenderStaticPropScanner(bpy_module=FakeBpy(root_name="B"))

        scan = scanner.scan_selection()

        self.assertEqual(scan["asset_name"], "SM_B")
        self.assertEqual(scan["source_asset_name"], "B")
        self.assertEqual(scan["asset_name_source_name"], "B")
        self.assertIn("B", scan["asset_name_candidates"])

    def test_preflight_allows_non_sm_source_name_after_auto_prefix(self):
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(root_name="B"))

        result = provider.preflight_static_prop({})

        self.assertEqual(result["scan"]["asset_name"], "SM_B")
        self.assertTrue(result["can_export"])
        self.assertEqual(result["validation"]["summary"]["errors"], 0)
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
        self.assertEqual(len(manifest["textures"]), 6)
        self.assertEqual(manifest["textures"][0]["source_type"], "blender_placeholder")
        self.assertEqual(len(manifest["material_texture_bindings"]), 2)
        self.assertEqual(manifest["material_texture_bindings"][0]["texture_usages"], ["base_color", "normal", "packed_arm"])
        self.assertEqual(manifest["fbx_export_status"], "planned")
        self.assertFalse(manifest["can_continue_to_ue"])
        self.assertEqual(report["package_contract_status"], "draft")
        self.assertFalse(os.path.exists(manifest["fbx_path"]))

    def test_empty_selection_returns_readable_bridge_error(self):
        port = allocate_port("127.0.0.1", 8900, 8999)
        registered = bridge.start_bridge(port=port, token="secret", bpy_module=FakeBpy(selected=[]), repo_root=self.temp_dir, registry_path=os.path.join(self.temp_dir, "instances.json"))
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