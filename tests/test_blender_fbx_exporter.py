from __future__ import absolute_import

import json
import os
import tempfile
import unittest

from asset_forge.blender.fbx_exporter import BlenderFbxExporter
from asset_forge.blender.provider_asset_forge import BlenderAssetForgeProvider
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
    def __init__(self, empty=False):
        self.vertices = [] if empty else list(range(8))
        self.polygons = [] if empty else [FakePolygon((0, 1, 2)), FakePolygon((0, 2, 3))]
        self.loop_triangles = [] if empty else [0, 1]
        self.uv_layers = [FakeUvLayer("UVMap"), FakeUvLayer("LightmapUV")]


class FakeObject(object):
    def __init__(self, name, empty=False):
        self.name = name
        self.type = "MESH"
        self.data = FakeMeshData(empty=empty)
        self.children = []
        self.material_slots = [FakeMaterialSlot("M_Body")]
        self.location = (0.0, 0.0, 0.0)
        self.rotation_euler = (0.0, 0.0, 0.0)
        self.scale = (1.0, 1.0, 1.0)
        self.hide_viewport = False
        self.library = None
        self.selected = False

    def select_set(self, value):
        self.selected = bool(value)

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
    def __init__(self, objects):
        self.filepath = "E:/Scenes/ExporterTest.blend"
        self.objects = objects


class FakeExportSceneOps(object):
    def __init__(self, owner, create_file=True, result=None):
        self.owner = owner
        self.create_file = create_file
        self.result = result or {"FINISHED"}
        self.calls = []

    def fbx(self, **kwargs):
        self.calls.append(kwargs)
        if self.create_file:
            parent = os.path.dirname(kwargs["filepath"])
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            with open(kwargs["filepath"], "wb") as stream:
                stream.write(b"FBXFAKE")
        return self.result


class FakeOps(object):
    def __init__(self, owner, create_file=True, result=None):
        self.export_scene = FakeExportSceneOps(owner, create_file=create_file, result=result)


class FakeBpy(object):
    def __init__(self, create_file=True, result=None, selected=True, bad_name=False, root_name="SM_BlenderCrate", empty_mesh=False):
        mesh = FakeObject("BadName" if bad_name else root_name, empty=empty_mesh)
        self.data = FakeData([mesh])
        self.context = FakeContext([mesh] if selected else [], mesh)
        self.ops = FakeOps(self, create_file=create_file, result=result)


class BlenderFbxExporterTest(unittest.TestCase):
    def setUp(self):
        bridge.stop_bridge()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: os.path.isdir(self.temp_dir) and __import__("shutil").rmtree(self.temp_dir))
        self.addCleanup(bridge.stop_bridge)

    def test_exporter_writes_selected_fbx_with_static_prop_options(self):
        bpy = FakeBpy()
        output_path = os.path.join(self.temp_dir, "Nested", "SM_BlenderCrate.fbx")

        result = BlenderFbxExporter(bpy_module=bpy).export_selected(output_path)

        self.assertTrue(os.path.exists(result))
        call = bpy.ops.export_scene.calls[0]
        self.assertEqual(call["filepath"], os.path.abspath(output_path))
        self.assertTrue(call["use_selection"])
        self.assertFalse(call["bake_anim"])
        self.assertIn("MESH", call["object_types"])
        self.assertEqual(call["axis_forward"], "-Z")
        self.assertEqual(call["axis_up"], "Y")

    def test_exporter_selects_named_objects_before_export(self):
        bpy = FakeBpy(selected=False)
        output_path = os.path.join(self.temp_dir, "SM_BlenderCrate.fbx")

        BlenderFbxExporter(bpy_module=bpy).export_objects(["SM_BlenderCrate"], output_path)

        self.assertTrue(bpy.data.objects[0].selected)
        self.assertEqual(bpy.context.active_object.name, "SM_BlenderCrate")
        self.assertEqual(bpy.context.selected_objects[0].name, "SM_BlenderCrate")

    def test_provider_exports_ready_package_after_fbx_exists(self):
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy())

        result = provider.export_static_prop_package({"export_root": self.temp_dir, "target_path": "/Game/Props/Blender"})
        manifest = read_manifest(result["manifest_path"])
        with open(result["export_report_path"], "r", encoding="utf-8") as stream:
            report = json.load(stream)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["can_continue_to_ue"])
        self.assertTrue(os.path.exists(result["fbx_path"]))
        self.assertEqual(manifest["source_dcc"], "blender")
        self.assertEqual(manifest["fbx_export_status"], "success")
        self.assertTrue(manifest["can_continue_to_ue"])
        self.assertEqual(manifest["package_contract_status"], "ready")
        self.assertEqual(report["fbx_export_status"], "success")

    def test_provider_exports_non_sm_source_name_as_sm_package(self):
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(root_name="B"))

        result = provider.export_static_prop_package({"export_root": self.temp_dir})
        manifest = read_manifest(result["manifest_path"])

        self.assertEqual(result["status"], "success")
        self.assertEqual(manifest["asset_name"], "SM_B")
        self.assertTrue(os.path.basename(result["fbx_path"]).startswith("SM_B"))
        self.assertTrue(result["can_continue_to_ue"])

    def test_provider_does_not_fake_ready_package_when_preflight_blocks(self):
        provider = BlenderAssetForgeProvider(bpy_module=FakeBpy(empty_mesh=True))

        result = provider.export_static_prop_package({"export_root": self.temp_dir})

        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["can_continue_to_ue"])
        self.assertEqual(result["fbx_export_status"], "blocked")
        self.assertFalse(os.path.exists(os.path.join(result["package_dir"], "SM_BlenderCrate.fbx")))

    def test_bridge_socket_runs_export_action(self):
        port = allocate_port("127.0.0.1", 8900, 8999)
        registered = bridge.start_bridge(
            port=port,
            token="secret",
            bpy_module=FakeBpy(),
            repo_root=self.temp_dir,
            registry_path=os.path.join(self.temp_dir, "instances.json"),
        )
        client = BlenderBridgeClient.from_instance(registered)

        result = client.call("blender_export_static_prop_package", {"export_root": self.temp_dir})

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["fbx_export_status"], "success")
        self.assertTrue(result["can_continue_to_ue"])

    def test_whitelist_adds_export_without_exec(self):
        self.assertIn("blender_export_static_prop_package", ALL_ACTIONS)
        self.assertNotIn("blender_run_python", ALL_ACTIONS)
        self.assertFalse(any("exec" in name or "eval" in name for name in ALL_ACTIONS))


if __name__ == "__main__":
    unittest.main()