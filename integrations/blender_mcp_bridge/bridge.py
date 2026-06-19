# -*- coding: utf-8 -*-
"""Independent local TCP bridge for Blender MCP integration."""

from __future__ import absolute_import

import importlib
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
from asset_forge.blender.provider_asset_forge import BlenderAssetForgeProvider


DEFAULT_HOST = "127.0.0.1"
DEFAULT_LOG_TAIL = 200
ALLOWED_RELOAD_ADDONS = ("asset_forge_extension",)
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
        self._provider = None
        self.event_log = []

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
        self.log_event("bridge_start", "success", "Bridge running on {0}:{1}".format(self.host, self.port))
        return payload

    def stop(self):
        self.log_event("bridge_stop", "success", "Bridge stopping")
        if self.instance_id:
            unregister_instance(instance_id=self.instance_id, path=self.registry_path)
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(2.0)
        self._server = None
        self._thread = None
        self._provider = None

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
            "provider_ids": ["blender.mcp.bridge", "asset_forge.blender.provider"],
        }
        if self.token:
            payload["token"] = self.token
        return payload

    def handle_request(self, request):
        action = request.get("action", "") if isinstance(request, dict) else ""
        try:
            validate_bridge_action(action)
            self._validate_token(request)
            params = request.get("params") or {}
            result = self._dispatch(action, params)
            result.setdefault("mcp_target", self.target_summary())
            self.log_event(action, "success", _action_message(result))
            return {"ok": True, "id": request.get("id"), "result": result}
        except Exception as exc:
            self.log_event(action or "unknown", "error", str(exc))
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

    def log_event(self, action, status, message=""):
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "epoch": time.time(),
            "action": action or "unknown",
            "status": status or "info",
            "message": message or "",
        }
        self.event_log.append(entry)
        self.event_log = self.event_log[-200:]
        self._append_log_file(entry)
        return entry

    def _append_log_file(self, entry):
        path = self.log_path
        if not path:
            return
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        line = "{time} | {status} | {action} | {message}\n".format(**entry)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(line)

    def _dispatch(self, action, params):
        if action == "blender_status":
            return self._status()
        if action == "blender_get_selection":
            return self._selection()
        if action == "blender_get_scene_summary":
            return self._scene_summary()
        if action == "blender_get_latest_log":
            return self._latest_log(int(params.get("tail") or DEFAULT_LOG_TAIL))
        if action == "blender_get_bridge_event_log":
            return self._bridge_event_log(int(params.get("tail") or 50))
        if action == "blender_reload_asset_forge_addons":
            return self._reload_asset_forge_addons(params)
        if action == "blender_scan_static_prop":
            return self._asset_forge_provider().scan_static_prop(params)
        if action == "blender_preflight_static_prop":
            return self._asset_forge_provider().preflight_static_prop(params)
        if action == "blender_build_static_prop_package_contract":
            return self._asset_forge_provider().build_static_prop_package_contract(params)
        if action == "blender_export_static_prop_package":
            return self._asset_forge_provider().export_static_prop_package(params)
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
                "event_count": len(self.event_log),
            },
            "blender": {
                "available": bpy_module is not None,
                "version": _blender_version(bpy_module),
                "scene_path": _scene_path(bpy_module),
            },
            "providers": ["blender.mcp.bridge", "asset_forge.blender.provider"],
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
        file_lines = []
        exists = bool(path and os.path.exists(path))
        if exists:
            with open(path, "r", encoding="utf-8", errors="replace") as stream:
                file_lines = stream.readlines()
        tail_lines = file_lines[-max(1, int(tail)) :] if file_lines else []
        return {
            "status": "success",
            "can_accept": True,
            "log_path": path,
            "exists": exists,
            "line_count": len(file_lines),
            "lines": [line.rstrip("\n") for line in tail_lines],
            "text": "".join(tail_lines),
            "event_log": self._bridge_event_log(tail).get("events", []),
        }

    def _bridge_event_log(self, tail):
        events = self.event_log[-max(1, int(tail)) :]
        return {
            "status": "success",
            "can_accept": True,
            "event_count": len(self.event_log),
            "events": events,
            "lines": ["{time} | {status} | {action} | {message}".format(**item) for item in events],
        }

    def _reload_asset_forge_addons(self, params):
        requested = params.get("addons") or ["asset_forge_extension"]
        unknown = [item for item in requested if item not in ALLOWED_RELOAD_ADDONS]
        if unknown:
            raise ValueError("Unsupported reload add-on(s): {0}".format(", ".join(unknown)))
        try:
            import addon_utils  # type: ignore
            import bpy  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Blender addon reload is only available inside Blender: {0}".format(exc))
        results = []
        for addon in requested:
            before = addon_utils.check(addon)
            try:
                addon_utils.disable(addon, default_set=True)
            except Exception:
                pass
            addon_utils.enable(addon, default_set=True, persistent=True)
            after = addon_utils.check(addon)
            results.append({"addon": addon, "before": list(before), "after": list(after), "status": "reloaded" if after[0] else "failed"})
        if bool(params.get("save_userpref", False)):
            bpy.ops.wm.save_userpref()
        refresh = _refresh_asset_forge_blender_modules()
        self._provider = None
        return {
            "status": "success",
            "can_accept": True,
            "reloaded": results,
            "refreshed_modules": refresh,
            "next_action": "Asset Forge Blender add-on 已安全重载，可继续刷新 UI 或运行扫描。",
        }

    def _asset_forge_provider(self):
        if self._provider is None:
            self._provider = BlenderAssetForgeProvider(bpy_module=self._bpy())
        return self._provider


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


def current_bridge():
    """Return the running in-process bridge, if any."""
    return _BRIDGE


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
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _default_log_path(repo_root):
    return os.path.join(repo_root or _guess_repo_root(), "AssetForgeReports", "logs", "latest_blender_mcp.log")


def _action_message(result):
    if not isinstance(result, dict):
        return ""
    if result.get("scan", {}).get("asset_name"):
        return "asset={0}".format(result.get("scan", {}).get("asset_name"))
    if result.get("selected_count") is not None:
        return "selected={0}".format(result.get("selected_count"))
    if result.get("object_count") is not None:
        return "objects={0}".format(result.get("object_count"))
    if result.get("event_count") is not None:
        return "events={0}".format(result.get("event_count"))
    return result.get("status", "")


def _refresh_asset_forge_blender_modules():
    """Refresh cached Blender provider modules after a safe add-on reload."""
    global BlenderAssetForgeProvider
    modules = [
        "asset_forge.blender.scanner",
        "asset_forge.blender.fbx_exporter",
        "asset_forge.blender.provider_asset_forge",
    ]
    refreshed = []
    for module_name in modules:
        module = importlib.import_module(module_name)
        importlib.reload(module)
        refreshed.append(module_name)
    from asset_forge.blender.provider_asset_forge import BlenderAssetForgeProvider as refreshed_provider

    BlenderAssetForgeProvider = refreshed_provider
    return refreshed
