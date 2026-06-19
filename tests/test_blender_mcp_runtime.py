from __future__ import absolute_import

import json
import os
import socket
import tempfile
import unittest

from integrations.blender_mcp.client import BlenderBridgeClient
from integrations.blender_mcp.protocol import ALL_ACTIONS, validate_action, validate_bridge_action
from integrations.blender_mcp.tools import call_tool, tool_definitions
from integrations.blender_mcp_runtime.ports import allocate_port
from integrations.blender_mcp_runtime.registry import (
    AmbiguousBlenderInstanceError,
    load_instances,
    register_instance,
    resolve_instance,
    strip_target_arguments,
    unregister_instance,
)


class BlenderMcpRuntimeTest(unittest.TestCase):
    def test_registry_registers_and_resolves_instances(self):
        path = self._registry_path()
        first = register_instance(
            {
                "instance_id": "blender-a",
                "pid": 201,
                "host": "127.0.0.1",
                "port": 8875,
                "scene_path": "E:/A.blend",
            },
            path=path,
        )
        register_instance(
            {
                "instance_id": "blender-b",
                "pid": 202,
                "host": "127.0.0.1",
                "port": 8876,
                "blend_file": "E:/B.blend",
            },
            path=path,
        )

        self.assertEqual(first["instance_id"], "blender-a")
        self.assertEqual(len(load_instances(path=path)), 2)
        self.assertEqual(resolve_instance({"blender_pid": 202}, path=path)["instance_id"], "blender-b")
        self.assertEqual(resolve_instance({"blender_scene_contains": "A.blend"}, path=path)["port"], 8875)
        instances = load_instances(path=path)
        first = instances[0]
        self.assertEqual(first["scene_name"], "A.blend")
        self.assertIn("A.blend", first["display_name"])
        self.assertIn({"argument": "blender_scene_contains", "value": "A.blend"}, first["selection_hints"])

    def test_registry_reports_ambiguous_instance_without_selector(self):
        path = self._registry_path()
        register_instance({"instance_id": "blender-a", "pid": 201, "port": 8875}, path=path)
        register_instance({"instance_id": "blender-b", "pid": 202, "port": 8876}, path=path)

        with self.assertRaises(AmbiguousBlenderInstanceError) as caught:
            resolve_instance({}, path=path)

        self.assertEqual(len(caught.exception.instances), 2)

    def test_client_refuses_to_guess_when_multiple_instances_are_registered(self):
        path = self._registry_path()
        old_path = os.environ.get("BLENDER_MCP_REGISTRY_PATH")
        os.environ["BLENDER_MCP_REGISTRY_PATH"] = path
        try:
            register_instance({"instance_id": "blender-a", "pid": 201, "port": 8875}, path=path)
            register_instance({"instance_id": "blender-b", "pid": 202, "port": 8876}, path=path)

            with self.assertRaises(AmbiguousBlenderInstanceError):
                BlenderBridgeClient.from_arguments({})
        finally:
            if old_path is None:
                os.environ.pop("BLENDER_MCP_REGISTRY_PATH", None)
            else:
                os.environ["BLENDER_MCP_REGISTRY_PATH"] = old_path

    def test_client_uses_selected_registered_instance(self):
        path = self._registry_path()
        old_path = os.environ.get("BLENDER_MCP_REGISTRY_PATH")
        os.environ["BLENDER_MCP_REGISTRY_PATH"] = path
        try:
            register_instance({"instance_id": "blender-a", "pid": 201, "port": 8875}, path=path)
            register_instance({"instance_id": "blender-b", "pid": 202, "port": 8876}, path=path)

            client = BlenderBridgeClient.from_arguments({"blender_port": 8876})

            self.assertEqual(client.port, 8876)
            self.assertEqual(client.instance["instance_id"], "blender-b")
        finally:
            if old_path is None:
                os.environ.pop("BLENDER_MCP_REGISTRY_PATH", None)
            else:
                os.environ["BLENDER_MCP_REGISTRY_PATH"] = old_path

    def test_registry_unregisters_by_instance_or_port(self):
        path = self._registry_path()
        register_instance({"instance_id": "blender-a", "pid": 201, "port": 8875}, path=path)
        register_instance({"instance_id": "blender-b", "pid": 202, "port": 8876}, path=path)

        removed = unregister_instance(instance_id="blender-a", path=path)

        self.assertEqual(removed[0]["instance_id"], "blender-a")
        self.assertEqual(load_instances(path=path)[0]["instance_id"], "blender-b")

    def test_strip_target_arguments_keeps_action_payload_clean(self):
        clean = strip_target_arguments({"blender_pid": 201, "selection": ["Cube"]})

        self.assertEqual(clean, {"selection": ["Cube"]})

    def test_allocate_port_skips_busy_preferred_port(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        busy_port = sock.getsockname()[1]
        try:
            port = allocate_port("127.0.0.1", busy_port, busy_port + 1)
        finally:
            sock.close()

        self.assertEqual(port, busy_port + 1)

    def test_tool_definitions_are_whitelisted_and_targetable(self):
        names = [item["name"] for item in tool_definitions()]

        self.assertEqual(
            names,
            [
                "blender_instances",
                "blender_status",
                "blender_get_selection",
                "blender_get_scene_summary",
                "blender_get_latest_log",
            ],
        )
        self.assertNotIn("blender_run_python", names)
        self.assertFalse(any("exec" in name or "eval" in name for name in ALL_ACTIONS))
        validate_action("blender_instances")
        validate_bridge_action("blender_get_selection")
        with self.assertRaises(ValueError):
            validate_action("blender_run_python")

        status_schema = [item for item in tool_definitions() if item["name"] == "blender_status"][0]
        self.assertIn("blender_pid", status_schema["inputSchema"]["properties"])

    def test_blender_instances_tool_reads_registry(self):
        path = self._registry_path()
        old_path = os.environ.get("BLENDER_MCP_REGISTRY_PATH")
        os.environ["BLENDER_MCP_REGISTRY_PATH"] = path
        try:
            register_instance({"instance_id": "blender-a", "pid": 201, "port": 8875, "scene_path": "E:/A.blend"}, path=path)

            result = call_tool("blender_instances", {})
            payload = json.loads(result["content"][0]["text"])

            self.assertFalse(result["isError"])
            self.assertEqual(payload["instance_count"], 1)
            self.assertEqual(payload["selection_summary"][0]["blender_instance"], "blender-a")
        finally:
            if old_path is None:
                os.environ.pop("BLENDER_MCP_REGISTRY_PATH", None)
            else:
                os.environ["BLENDER_MCP_REGISTRY_PATH"] = old_path

    def _registry_path(self):
        if not hasattr(self, "_temp_dir"):
            self._temp_dir = tempfile.mkdtemp()
            self.addCleanup(lambda: os.path.isdir(self._temp_dir) and __import__("shutil").rmtree(self._temp_dir))
        return os.path.join(self._temp_dir, "instances.json")


if __name__ == "__main__":
    unittest.main()