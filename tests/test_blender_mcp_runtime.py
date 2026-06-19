from __future__ import absolute_import

import json
import os
import socket
import tempfile
import unittest

from integrations.blender_mcp.client import BlenderBridgeClient
from integrations.blender_mcp.protocol import ALL_ACTIONS, validate_action, validate_bridge_action
from integrations.blender_mcp.tools import call_tool, tool_definitions
from integrations.blender_mcp.server import handle_message
from integrations.blender_mcp_bridge.bridge import BlenderBridge
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
            port = allocate_port("127.0.0.1", busy_port, busy_port + 50)
        finally:
            sock.close()

        self.assertNotEqual(port, busy_port)

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
                "blender_get_bridge_event_log",
                "blender_reload_asset_forge_addons",
                "blender_scan_static_prop",
                "blender_preflight_static_prop",
                "blender_build_static_prop_package_contract",
                "blender_export_static_prop_package",
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

    def test_blender_stdio_server_lists_tools(self):
        response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

        names = [item["name"] for item in response["result"]["tools"]]
        self.assertIn("blender_instances", names)
        self.assertIn("blender_export_static_prop_package", names)

    def test_independent_blender_bridge_advertises_generic_provider(self):
        bridge_instance = BlenderBridge(port=8875, repo_root="")

        payload = bridge_instance.instance_payload()

        self.assertIn("blender.mcp.bridge", payload["provider_ids"])
        self.assertIn("asset_forge.blender.provider", payload["provider_ids"])
    def test_bridge_records_event_log_for_requests(self):
        bridge_instance = BlenderBridge(port=8875, repo_root="")

        response = bridge_instance.handle_request({"id": "1", "action": "blender_status", "params": {}})
        log_response = bridge_instance.handle_request({"id": "2", "action": "blender_get_bridge_event_log", "params": {"tail": 5}})

        self.assertTrue(response["ok"])
        self.assertTrue(log_response["ok"])
        self.assertGreaterEqual(log_response["result"]["event_count"], 1)
        self.assertIn("blender_status", [item["action"] for item in log_response["result"]["events"]])

    def test_bridge_reload_rejects_non_whitelisted_addons(self):
        bridge_instance = BlenderBridge(port=8875, repo_root="")

        response = bridge_instance.handle_request({"id": "1", "action": "blender_reload_asset_forge_addons", "params": {"addons": ["evil_addon"]}})

        self.assertFalse(response["ok"])
        self.assertIn("Unsupported reload", response["error"]["message"])
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