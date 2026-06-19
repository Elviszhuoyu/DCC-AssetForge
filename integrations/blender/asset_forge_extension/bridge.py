# -*- coding: utf-8 -*-
"""Minimal local TCP bridge for Asset Forge Blender MCP integration."""

from __future__ import absolute_import

import os
import socketserver
import threading
import time
import traceback

from integrations.blender_mcp.protocol import (
    decode_message,
    encode_message,
    validate_bridge_action,
)
from integrations.blender_mcp_runtime.ports import allocate_port
from integrations.blender_mcp_runtime.registry import register_instance, unregister_instance


DEFAULT_HOST = "127.0.0.1"
DEFAULT_LOG_TAIL = 200
_BRIDGE = None


class BlenderBridge(object):
    def __init__(self, host=DEFAULT_HOST, port=None, token="", bpy_module=None, repo_root="", registry_path=None, log_path=""):
        self.host = host or DEFAULT_HOST
        self.port = int(port or allocate_port(self.host))
        self.token = token or ""
        self.bpy = bpy_module
        self.repo_root = repo_root or _guess_repo_root()
        self.registry_path = registry_path
        self.log_path = log_path or _default_log_path(self.repo_root)
        self.instance_id = ""
        self.started_at_epoch = 0.0
        self._server = None
        self._thread = None

    def start(self):
        if self._server:
            return self.instance_payload()
        self.started_at_epoch = time.time()
        self._server = _BridgeServer((self.host, self.port), _BridgeRequestHandler)
        self._server.bridge = self
        self._thread = threading.Thread(target=self._server.serve_forever, name="AssetForgeBlenderBridge")
        self._thread.daemon = True
        self._thread.start()
        payload = register_instance(self.instance_payload(), path=self.registry_path)
        self.instance_id = payload.get("instance_id", self.instance_id)
        return payload

    def stop(self):
        if self.instance_id:
            unregister_instance(instance_id=self.instance_id, path=self.registry_path)
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(2.0)
        self._server = None
        self._thread = None

    def instance_payload(self):
        bpy_module = self._bpy()
        scene_path = _scene_path(bpy_module)
        payload = {
            "instance_id": self.instance_id or "blender-{0}".format(os.getpid()),
            "pid": os.getpid(),
            "host": self.host,
            "port": self.port,
            "scene_path": scene_path,
            "blend_file": scene_path,
            "project_root": self.repo_root,
            "started_at_epoch": self.started_at_epoch or time.time(),
            "token_required": bool(self.token),
            "provider_ids": ["asset_forge.blender.bridge"],
        }
        if self.token:
            payload["token"] = self.token
        return payload

    def handle_request(self, request):
        try:
            action = request.get("action", "")
            validate_bridge_action(action)
            self._validate_token(request)
            params = request.get("params") or {}
            result = self._dispatch(action, params)
            result.setdefault("mcp_target", self.target_summary())
            return {"ok": True, "id": request.get("id"), "result": result}
        except Exception as exc:
            return {
                "ok": False,
                "id": request.get("id") if isinstance(request, dict) else "",
                "error": {
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=4),
                },
            }

    def target_summary(self):
        return {
            "instance_id": self.instance_id,
            "pid": os.getpid(),
            "host": self.host,
            "port": self.port,
            "scene_path": _scene_path(self._bpy()),
        }

    def _dispatch(self, action, params):
        if action == "blender_status":
            return self._status()
        if action == "blender_get_selection":
            return self._selection()
        if action == "blender_get_scene_summary":
            return self._scene_summary()
        if action == "blender_get_latest_log":
            return self._latest_log(int(params.get("tail") or DEFAULT_LOG_TAIL))
        raise ValueError("Unsupported Blender bridge action: {0}".format(action))

    def _validate_token(self, request):
        if self.token and request.get("token") != self.token:
            raise PermissionError("Blender bridge token mismatch.")

    def _bpy(self):
        if self.bpy is not None:
            return self.bpy
        try:
            import bpy  # type: ignore
        except ImportError:
            return None
        return bpy

    def _status(self):
        bpy_module = self._bpy()
        return {
            "status": "success",
            "can_accept": True,
            "bridge": {
                "host": self.host,
                "port": self.port,
                "started_at_epoch": self.started_at_epoch,
                "token_required": bool(self.token),
            },
            "blender": {
                "available": bpy_module is not None,
                "version": _blender_version(bpy_module),
                "scene_path": _scene_path(bpy_module),
            },
            "providers": ["asset_forge.blender.bridge"],
            "next_action": "读取选择或场景概要后进入 Blender Static Prop 扫描。",
        }

    def _selection(self):
        bpy_module = self._bpy()
        context = getattr(bpy_module, "context", None)
        selected = list(getattr(context, "selected_objects", []) or []) if context else []
        active = getattr(getattr(context, "view_layer", None), "objects", None) if context else None
        active_object = getattr(active, "active", None) if active else getattr(context, "active_object", None) if context else None
        return {
            "status": "success",
            "can_accept": True,
            "active_object": _object_summary(active_object) if active_object else None,
            "selected_objects": [_object_summary(item) for item in selected],
            "selected_count": len(selected),
        }

    def _scene_summary(self):
        bpy_module = self._bpy()
        objects = list(getattr(getattr(bpy_module, "data", None), "objects", []) or []) if bpy_module else []
        by_type = {}
        for item in objects:
            object_type = getattr(item, "type", "UNKNOWN") or "UNKNOWN"
            by_type[object_type] = by_type.get(object_type, 0) + 1
        return {
            "status": "success",
            "can_accept": True,
            "scene_path": _scene_path(bpy_module),
            "object_count": len(objects),
            "object_types": by_type,
            "selected_count": len(getattr(getattr(bpy_module, "context", None), "selected_objects", []) or []) if bpy_module else 0,
        }

    def _latest_log(self, tail):
        path = self.log_path
        if not path or not os.path.exists(path):
            return {
                "status": "success",
                "can_accept": True,
                "log_path": path,
                "exists": False,
                "lines": [],
                "text": "",
            }
        with open(path, "r", encoding="utf-8", errors="replace") as stream:
            lines = stream.readlines()
        tail_lines = lines[-max(1, int(tail)) :]
        return {
            "status": "success",
            "can_accept": True,
            "log_path": path,
            "exists": True,
            "line_count": len(lines),
            "lines": [line.rstrip("\n") for line in tail_lines],
            "text": "".join(tail_lines),
        }


class _BridgeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _BridgeRequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        raw = _read_line(self.request)
        request = decode_message(raw)
        response = self.server.bridge.handle_request(request)
        self.request.sendall(encode_message(response))


def start_bridge(host=DEFAULT_HOST, port=None, token="", bpy_module=None, repo_root="", registry_path=None, log_path=""):
    global _BRIDGE
    if _BRIDGE:
        return _BRIDGE.instance_payload()
    _BRIDGE = BlenderBridge(
        host=host,
        port=port,
        token=token,
        bpy_module=bpy_module,
        repo_root=repo_root,
        registry_path=registry_path,
        log_path=log_path,
    )
    return _BRIDGE.start()


def stop_bridge():
    global _BRIDGE
    if _BRIDGE:
        _BRIDGE.stop()
    _BRIDGE = None


def register_extension():
    return start_bridge()


def unregister_extension():
    stop_bridge()


def _read_line(sock):
    chunks = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    if not chunks:
        raise RuntimeError("Blender bridge received an empty request.")
    return b"".join(chunks).split(b"\n", 1)[0]


def _object_summary(obj):
    if obj is None:
        return None
    return {
        "name": getattr(obj, "name", ""),
        "type": getattr(obj, "type", "UNKNOWN") or "UNKNOWN",
        "library": bool(getattr(obj, "library", None)),
    }


def _scene_path(bpy_module):
    if not bpy_module:
        return ""
    return getattr(getattr(bpy_module, "data", None), "filepath", "") or ""


def _blender_version(bpy_module):
    if not bpy_module:
        return ""
    app = getattr(bpy_module, "app", None)
    return getattr(app, "version_string", "") or ""


def _guess_repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _default_log_path(repo_root):
    return os.path.join(repo_root or _guess_repo_root(), "AssetForgeReports", "logs", "latest_blender.log")