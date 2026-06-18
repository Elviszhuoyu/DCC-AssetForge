from __future__ import absolute_import

import os
import tempfile
import unittest

from integrations.maya_mcp_runtime.ports import allocate_port
from integrations.maya_mcp.client import MayaBridgeClient
from integrations.maya_mcp_runtime.registry import (
    AmbiguousMayaInstanceError,
    load_instances,
    register_instance,
    resolve_instance,
    strip_target_arguments,
    unregister_instance,
)


class MayaMcpRuntimeTest(unittest.TestCase):
    def test_registry_registers_and_resolves_instances(self):
        path = self._registry_path()
        first = register_instance(
            {
                "instance_id": "maya-a",
                "pid": 101,
                "host": "127.0.0.1",
                "port": 8765,
                "scene_path": "E:/A.ma",
            },
            path=path,
        )
        register_instance(
            {
                "instance_id": "maya-b",
                "pid": 102,
                "host": "127.0.0.1",
                "port": 8766,
                "scene_path": "E:/B.ma",
            },
            path=path,
        )

        self.assertEqual(first["instance_id"], "maya-a")
        self.assertEqual(len(load_instances(path=path)), 2)
        self.assertEqual(resolve_instance({"maya_pid": 102}, path=path)["instance_id"], "maya-b")
        self.assertEqual(resolve_instance({"maya_scene_contains": "A.ma"}, path=path)["port"], 8765)
        instances = load_instances(path=path)
        first = instances[0]
        self.assertEqual(first["scene_name"], "A.ma")
        self.assertIn("A.ma", first["display_name"])
        self.assertIn({"argument": "maya_scene_contains", "value": "A.ma"}, first["selection_hints"])

    def test_registry_reports_ambiguous_instance_without_selector(self):
        path = self._registry_path()
        register_instance({"instance_id": "maya-a", "pid": 101, "port": 8765}, path=path)
        register_instance({"instance_id": "maya-b", "pid": 102, "port": 8766}, path=path)

        with self.assertRaises(AmbiguousMayaInstanceError) as caught:
            resolve_instance({}, path=path)

        self.assertEqual(len(caught.exception.instances), 2)

    def test_client_refuses_to_guess_when_multiple_instances_are_registered(self):
        path = self._registry_path()
        old_path = os.environ.get("MAYA_MCP_REGISTRY_PATH")
        os.environ["MAYA_MCP_REGISTRY_PATH"] = path
        try:
            register_instance({"instance_id": "maya-a", "pid": 101, "port": 8765}, path=path)
            register_instance({"instance_id": "maya-b", "pid": 102, "port": 8766}, path=path)

            with self.assertRaises(AmbiguousMayaInstanceError):
                MayaBridgeClient.from_arguments({})
        finally:
            if old_path is None:
                os.environ.pop("MAYA_MCP_REGISTRY_PATH", None)
            else:
                os.environ["MAYA_MCP_REGISTRY_PATH"] = old_path

    def test_registry_unregisters_by_instance_or_port(self):
        path = self._registry_path()
        register_instance({"instance_id": "maya-a", "pid": 101, "port": 8765}, path=path)
        register_instance({"instance_id": "maya-b", "pid": 102, "port": 8766}, path=path)

        removed = unregister_instance(instance_id="maya-a", path=path)

        self.assertEqual(removed[0]["instance_id"], "maya-a")
        self.assertEqual(load_instances(path=path)[0]["instance_id"], "maya-b")

    def test_strip_target_arguments_keeps_action_payload_clean(self):
        clean = strip_target_arguments({"maya_pid": 101, "selection": ["|SM_A"]})

        self.assertEqual(clean, {"selection": ["|SM_A"]})

    def test_allocate_port_skips_busy_preferred_port(self):
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        busy_port = sock.getsockname()[1]
        try:
            port = allocate_port("127.0.0.1", busy_port, busy_port + 1)
        finally:
            sock.close()

        self.assertEqual(port, busy_port + 1)

    def _registry_path(self):
        if not hasattr(self, "_temp_dir"):
            self._temp_dir = tempfile.mkdtemp()
            self.addCleanup(lambda: os.path.isdir(self._temp_dir) and __import__("shutil").rmtree(self._temp_dir))
        return os.path.join(self._temp_dir, "instances.json")


if __name__ == "__main__":
    unittest.main()
