from __future__ import absolute_import

import json
import os
import tempfile
import unittest

from integrations.blender.asset_forge_extension import bridge
from integrations.blender.asset_forge_extension.bridge import BlenderBridge
from integrations.blender_mcp.client import BlenderBridgeClient
from integrations.blender_mcp.protocol import make_request
from integrations.blender_mcp_runtime.ports import allocate_port
from integrations.blender_mcp_runtime.registry import load_instances


class FakeObject(object):
    def __init__(self, name, object_type):
        self.name = name
        self.type = object_type
        self.library = None


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


class FakeApp(object):
    version_string = "4.2.1 Test"


class FakeBpy(object):
    def __init__(self):
        cube = FakeObject("SM_Cube", "MESH")
        light = FakeObject("Key_Light", "LIGHT")
        camera = FakeObject("Camera", "CAMERA")
        self.data = FakeData("E:/Scenes/BridgeTest.blend", [cube, light, camera])
        self.context = FakeContext([cube, light], cube)
        self.app = FakeApp()


class BlenderMcpBridgeTest(unittest.TestCase):
    def setUp(self):
        bridge.stop_bridge()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: os.path.isdir(self.temp_dir) and __import__("shutil").rmtree(self.temp_dir))
        self.addCleanup(bridge.stop_bridge)

    def test_status_selection_and_scene_summary_use_fake_bpy(self):
        active_bridge = BlenderBridge(port=allocate_port("127.0.0.1", 8900, 8999), bpy_module=FakeBpy(), repo_root=self.temp_dir)

        status = active_bridge.handle_request(make_request("blender_status"))["result"]
        selection = active_bridge.handle_request(make_request("blender_get_selection"))["result"]
        summary = active_bridge.handle_request(make_request("blender_get_scene_summary"))["result"]

        self.assertTrue(status["can_accept"])
        self.assertEqual(status["blender"]["version"], "4.2.1 Test")
        self.assertEqual(status["blender"]["scene_path"], "E:/Scenes/BridgeTest.blend")
        self.assertEqual(selection["active_object"]["name"], "SM_Cube")
        self.assertEqual(selection["selected_count"], 2)
        self.assertEqual(summary["object_count"], 3)
        self.assertEqual(summary["object_types"], {"MESH": 1, "LIGHT": 1, "CAMERA": 1})

    def test_latest_log_reads_tail_without_modifying_scene(self):
        log_path = os.path.join(self.temp_dir, "latest_blender.log")
        with open(log_path, "w", encoding="utf-8") as stream:
            stream.write("one\n")
            stream.write("two\n")
            stream.write("three\n")
        active_bridge = BlenderBridge(port=allocate_port("127.0.0.1", 8900, 8999), bpy_module=FakeBpy(), repo_root=self.temp_dir, log_path=log_path)

        result = active_bridge.handle_request(make_request("blender_get_latest_log", {"tail": 2}))["result"]

        self.assertTrue(result["exists"])
        self.assertEqual(result["lines"], ["two", "three"])

    def test_rejects_unknown_action_and_bad_token(self):
        active_bridge = BlenderBridge(port=allocate_port("127.0.0.1", 8900, 8999), token="secret", bpy_module=FakeBpy())

        bad_action = active_bridge.handle_request({"id": "1", "action": "blender_run_python", "params": {}})
        bad_token = active_bridge.handle_request({"id": "2", "action": "blender_status", "params": {}, "token": "wrong"})

        self.assertFalse(bad_action["ok"])
        self.assertEqual(bad_action["error"]["type"], "ValueError")
        self.assertFalse(bad_token["ok"])
        self.assertEqual(bad_token["error"]["type"], "PermissionError")

    def test_start_bridge_registers_instance_and_client_can_call_it(self):
        registry_path = os.path.join(self.temp_dir, "instances.json")
        port = allocate_port("127.0.0.1", 8900, 8999)

        registered = bridge.start_bridge(
            port=port,
            token="secret",
            bpy_module=FakeBpy(),
            repo_root=self.temp_dir,
            registry_path=registry_path,
        )
        client = BlenderBridgeClient.from_instance(registered)
        result = client.call("blender_status", {})

        self.assertEqual(registered["port"], port)
        self.assertEqual(load_instances(path=registry_path)[0]["port"], port)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["mcp_target"]["port"], port)

    def test_client_can_resolve_started_bridge_from_registry(self):
        registry_path = os.path.join(self.temp_dir, "instances.json")
        old_path = os.environ.get("BLENDER_MCP_REGISTRY_PATH")
        os.environ["BLENDER_MCP_REGISTRY_PATH"] = registry_path
        port = allocate_port("127.0.0.1", 8900, 8999)
        try:
            bridge.start_bridge(port=port, token="secret", bpy_module=FakeBpy(), repo_root=self.temp_dir, registry_path=registry_path)

            client = BlenderBridgeClient.from_arguments({"blender_port": port})
            result = client.call("blender_get_selection", {})

            self.assertEqual(client.port, port)
            self.assertEqual(result["selected_count"], 2)
            self.assertEqual(result["active_object"]["name"], "SM_Cube")
        finally:
            if old_path is None:
                os.environ.pop("BLENDER_MCP_REGISTRY_PATH", None)
            else:
                os.environ["BLENDER_MCP_REGISTRY_PATH"] = old_path


if __name__ == "__main__":
    unittest.main()