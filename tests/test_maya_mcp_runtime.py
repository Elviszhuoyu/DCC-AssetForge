from __future__ import absolute_import

import os
import socket
import tempfile
import unittest

from integrations.maya.scripts import asset_forge_maya_bridge
from integrations.maya_mcp_runtime.ports import allocate_port
from integrations.maya_mcp.client import MayaBridgeClient
from integrations.maya_mcp_runtime.registry import (
    AmbiguousMayaInstanceError,
    MayaInstanceNotFoundError,
    load_instances,
    register_instance,
    resolve_instance,
    save_instances,
    strip_target_arguments,
    unregister_instance,
)


class MayaMcpRuntimeTest(unittest.TestCase):
    def test_registry_registers_and_resolves_instances(self):
        path = self._registry_path()
        with self._listening_socket() as port_a, self._listening_socket() as port_b:
            first = register_instance(
                {
                    "instance_id": "maya-a",
                    "pid": 101,
                    "host": "127.0.0.1",
                    "port": port_a,
                    "scene_path": "E:/A.ma",
                },
                path=path,
            )
            register_instance(
                {
                    "instance_id": "maya-b",
                    "pid": 102,
                    "host": "127.0.0.1",
                    "port": port_b,
                    "scene_path": "E:/B.ma",
                },
                path=path,
            )

            self.assertEqual(first["instance_id"], "maya-a")
            self.assertEqual(len(load_instances(path=path)), 2)
            self.assertEqual(resolve_instance({"maya_pid": 102}, path=path)["instance_id"], "maya-b")
            self.assertEqual(resolve_instance({"maya_scene_contains": "A.ma"}, path=path)["port"], port_a)
            instances = load_instances(path=path)
            first = instances[0]
            self.assertEqual(first["scene_name"], "A.ma")
            self.assertIn("A.ma", first["display_name"])
            self.assertIn({"argument": "maya_scene_contains", "value": "A.ma"}, first["selection_hints"])

    def test_registry_reports_ambiguous_instance_without_selector(self):
        path = self._registry_path()
        with self._listening_socket() as port_a, self._listening_socket() as port_b:
            register_instance({"instance_id": "maya-a", "pid": 101, "port": port_a}, path=path)
            register_instance({"instance_id": "maya-b", "pid": 102, "port": port_b}, path=path)

            with self.assertRaises(AmbiguousMayaInstanceError) as caught:
                resolve_instance({}, path=path)

            self.assertEqual(len(caught.exception.instances), 2)

    def test_registry_filters_fresh_but_dead_endpoint(self):
        path = self._registry_path()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        dead_port = sock.getsockname()[1]
        sock.close()
        save_instances(
            [
                {
                    "instance_id": "maya-dead-fresh",
                    "pid": 101,
                    "host": "127.0.0.1",
                    "port": dead_port,
                    "updated_at_epoch": __import__("time").time(),
                }
            ],
            path=path,
        )

        self.assertEqual(load_instances(path=path), [])
        with self.assertRaises(MayaInstanceNotFoundError):
            resolve_instance({}, path=path)

    def test_registry_resolves_stale_but_live_selected_instance(self):
        path = self._registry_path()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        live_port = sock.getsockname()[1]
        try:
            save_instances(
                [
                    {
                        "instance_id": "maya-stale-live",
                        "pid": 101,
                        "host": "127.0.0.1",
                        "port": live_port,
                        "updated_at_epoch": 1,
                    }
                ],
                path=path,
            )

            resolved = resolve_instance({"maya_port": live_port}, path=path)
        finally:
            sock.close()

        self.assertEqual(resolved["instance_id"], "maya-stale-live")

    def test_registry_rejects_stale_dead_selected_instance(self):
        path = self._registry_path()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        dead_port = sock.getsockname()[1]
        sock.close()
        save_instances(
            [
                {
                    "instance_id": "maya-stale-live",
                    "pid": 101,
                    "host": "127.0.0.1",
                    "port": dead_port,
                    "updated_at_epoch": 1,
                }
            ],
            path=path,
        )

        with self.assertRaises(MayaInstanceNotFoundError):
            resolve_instance({"maya_port": dead_port}, path=path)

    def test_registry_does_not_guess_stale_live_instance_without_selector(self):
        path = self._registry_path()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        live_port = sock.getsockname()[1]
        try:
            save_instances(
                [
                    {
                        "instance_id": "maya-stale-live",
                        "pid": 101,
                        "host": "127.0.0.1",
                        "port": live_port,
                        "updated_at_epoch": 1,
                    }
                ],
                path=path,
            )

            with self.assertRaises(MayaInstanceNotFoundError):
                resolve_instance({}, path=path)
        finally:
            sock.close()

    def test_client_refuses_to_guess_when_multiple_instances_are_registered(self):
        path = self._registry_path()
        old_path = os.environ.get("MAYA_MCP_REGISTRY_PATH")
        os.environ["MAYA_MCP_REGISTRY_PATH"] = path
        try:
            with self._listening_socket() as port_a, self._listening_socket() as port_b:
                register_instance({"instance_id": "maya-a", "pid": 101, "port": port_a}, path=path)
                register_instance({"instance_id": "maya-b", "pid": 102, "port": port_b}, path=path)

                with self.assertRaises(AmbiguousMayaInstanceError):
                    MayaBridgeClient.from_arguments({})
        finally:
            if old_path is None:
                os.environ.pop("MAYA_MCP_REGISTRY_PATH", None)
            else:
                os.environ["MAYA_MCP_REGISTRY_PATH"] = old_path

    def test_client_uses_explicit_stale_live_registered_instance(self):
        path = self._registry_path()
        old_path = os.environ.get("MAYA_MCP_REGISTRY_PATH")
        os.environ["MAYA_MCP_REGISTRY_PATH"] = path
        try:
            with self._listening_socket() as live_port:
                save_instances(
                    [
                        {
                            "instance_id": "maya-stale",
                            "pid": 101,
                            "host": "127.0.0.1",
                            "port": live_port,
                            "scene_path": "E:/A.ma",
                            "updated_at_epoch": 1,
                        }
                    ],
                    path=path,
                )

                client = MayaBridgeClient.from_arguments({"maya_instance": "maya-stale"})

                self.assertEqual(client.port, live_port)
                self.assertEqual(client.instance["instance_id"], "maya-stale")
        finally:
            if old_path is None:
                os.environ.pop("MAYA_MCP_REGISTRY_PATH", None)
            else:
                os.environ["MAYA_MCP_REGISTRY_PATH"] = old_path

    def test_registry_unregisters_by_instance_or_port(self):
        path = self._registry_path()
        with self._listening_socket() as port_a, self._listening_socket() as port_b:
            register_instance({"instance_id": "maya-a", "pid": 101, "port": port_a}, path=path)
            register_instance({"instance_id": "maya-b", "pid": 102, "port": port_b}, path=path)

            removed = unregister_instance(instance_id="maya-a", path=path)

            self.assertEqual(removed[0]["instance_id"], "maya-a")
            self.assertEqual(load_instances(path=path)[0]["instance_id"], "maya-b")

    def test_strip_target_arguments_keeps_action_payload_clean(self):
        clean = strip_target_arguments({"maya_pid": 101, "selection": ["|SM_A"]})

        self.assertEqual(clean, {"selection": ["|SM_A"]})

    def test_allocate_port_skips_busy_preferred_port(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        busy_port = sock.getsockname()[1]
        try:
            port = allocate_port("127.0.0.1", busy_port, busy_port + 1)
        finally:
            sock.close()

        self.assertEqual(port, busy_port + 1)

    def test_bridge_status_does_not_register_dead_server_thread(self):
        class DeadServer(object):
            repo_root = "E:/Repo"
            instance_id = "maya-dead"
            server_address = ("127.0.0.1", 8765)
            token = ""
            registry_path = ""

            def __init__(self):
                self.closed = False

            def server_close(self):
                self.closed = True

        dead_server = DeadServer()
        old_server = asset_forge_maya_bridge._SERVER
        old_thread = asset_forge_maya_bridge._THREAD
        old_unregister = asset_forge_maya_bridge._unregister_bridge_instance
        old_log = asset_forge_maya_bridge._log_bridge_event
        removed = []
        try:
            asset_forge_maya_bridge._SERVER = dead_server
            asset_forge_maya_bridge._THREAD = None
            asset_forge_maya_bridge._unregister_bridge_instance = lambda **kwargs: removed.append(kwargs) or []
            asset_forge_maya_bridge._log_bridge_event = lambda *args, **kwargs: {}

            status = asset_forge_maya_bridge.bridge_status()
            asset_forge_maya_bridge._discard_dead_server("test")
        finally:
            asset_forge_maya_bridge._SERVER = old_server
            asset_forge_maya_bridge._THREAD = old_thread
            asset_forge_maya_bridge._unregister_bridge_instance = old_unregister
            asset_forge_maya_bridge._log_bridge_event = old_log

        self.assertEqual(status["status"], "stopped")
        self.assertEqual(status["health"], "error")
        self.assertTrue(dead_server.closed)
        self.assertEqual(removed[0]["instance_id"], "maya-dead")

    def test_stop_bridge_detaches_server_before_closing(self):
        class FakeServer(object):
            repo_root = "E:/Repo"
            instance_id = "maya-live"
            server_address = ("127.0.0.1", 8765)
            token = ""
            registry_path = ""

        class FakeThread(object):
            def is_alive(self):
                return True

        old_server = asset_forge_maya_bridge._SERVER
        old_thread = asset_forge_maya_bridge._THREAD
        old_unregister = asset_forge_maya_bridge._unregister_bridge_instance
        old_close = asset_forge_maya_bridge._close_server_without_blocking_ui
        old_log = asset_forge_maya_bridge._log_bridge_event
        old_show = asset_forge_maya_bridge._safe_show_status_window
        closed = []
        try:
            asset_forge_maya_bridge._SERVER = FakeServer()
            asset_forge_maya_bridge._THREAD = FakeThread()
            asset_forge_maya_bridge._unregister_bridge_instance = lambda **_kwargs: []
            asset_forge_maya_bridge._close_server_without_blocking_ui = lambda server, thread, action: closed.append((server, thread, action, asset_forge_maya_bridge._SERVER))
            asset_forge_maya_bridge._log_bridge_event = lambda *args, **kwargs: {}
            asset_forge_maya_bridge._safe_show_status_window = lambda _status: None

            status = asset_forge_maya_bridge.stop_bridge()
        finally:
            asset_forge_maya_bridge._SERVER = old_server
            asset_forge_maya_bridge._THREAD = old_thread
            asset_forge_maya_bridge._unregister_bridge_instance = old_unregister
            asset_forge_maya_bridge._close_server_without_blocking_ui = old_close
            asset_forge_maya_bridge._log_bridge_event = old_log
            asset_forge_maya_bridge._safe_show_status_window = old_show

        self.assertEqual(status["status"], "stopped")
        self.assertEqual(closed[0][2], "stop_bridge")
        self.assertIsNone(closed[0][3])

    def _registry_path(self):
        if not hasattr(self, "_temp_dir"):
            self._temp_dir = tempfile.mkdtemp()
            self.addCleanup(lambda: os.path.isdir(self._temp_dir) and __import__("shutil").rmtree(self._temp_dir))
        return os.path.join(self._temp_dir, "instances.json")

    def _listening_socket(self):
        class Listener(object):
            def __enter__(self_inner):
                self_inner.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self_inner.sock.bind(("127.0.0.1", 0))
                self_inner.sock.listen(5)
                return self_inner.sock.getsockname()[1]

            def __exit__(self_inner, exc_type, exc, tb):
                self_inner.sock.close()

        return Listener()


if __name__ == "__main__":
    unittest.main()
