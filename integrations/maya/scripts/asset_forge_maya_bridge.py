# -*- coding: utf-8 -*-
"""Localhost JSON bridge for driving Asset Forge inside Maya."""

from __future__ import absolute_import, print_function

import json
import os
import socketserver
import sys
import threading
import traceback
import time
import uuid
from datetime import datetime


BRIDGE_VERSION = "0.2.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
BRIDGE_WINDOW_NAME = "assetForgeMayaMcpBridgeStatusWindow"
BRIDGE_SHELF_NAME = "AssetForge"
BRIDGE_SHELF_BUTTON = "assetForgeMcpBridgeButton"
_SERVER = None
_THREAD = None
_METRICS_LOCK = threading.Lock()
_BRIDGE_METRICS = {}
_WINDOW_CONTROLS = {}
_MONITOR_JOB = None
_LAST_MONITOR_REFRESH = 0.0
_STATUS_LISTENERS = []


class AssetForgeMayaBridgeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = False

    def __init__(self, server_address, request_handler, token="", repo_root="", instance_id=""):
        socketserver.ThreadingTCPServer.__init__(self, server_address, request_handler)
        self.token = token or ""
        self.repo_root = repo_root or _repo_root()
        self.instance_id = instance_id or ""
        self.registry_path = ""


class AssetForgeMayaBridgeHandler(socketserver.StreamRequestHandler):
    def handle(self):
        for raw_line in self.rfile:
            response = self._handle_line(raw_line)
            self.wfile.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))

    def _handle_line(self, raw_line):
        action = ""
        request_id = ""
        try:
            if not _is_local_address(self.client_address[0]):
                raise RuntimeError("只允许 localhost 访问 Maya bridge。")
            request = json.loads(raw_line.decode("utf-8"))
            request_id = request.get("id") or str(uuid.uuid4())
            if self.server.token and request.get("token") != self.server.token:
                raise RuntimeError("Maya bridge token 不匹配。")
            action = request.get("action")
            params = request.get("params") or {}
            params.setdefault("repo_root", self.server.repo_root)
            _register_bridge_instance(self.server)
            _mark_request_start(action, request_id, self.client_address[0])
            result = _execute_in_maya_main_thread(action, params)
            _mark_request_finish(action, request_id, "success", "")
            return {"id": request_id, "ok": True, "result": result, "error": None}
        except Exception as exc:
            _mark_request_finish(action, request_id, "error", str(exc))
            return {
                "id": request_id,
                "ok": False,
                "result": None,
                "error": {"message": str(exc), "traceback": traceback.format_exc()},
            }


def start_bridge(host=None, port=None, token=None, repo_root=None):
    """Start the bridge in the current Maya Python process."""
    global _SERVER, _THREAD
    if _SERVER is not None:
        if _bridge_thread_alive():
            status = bridge_status()
            _safe_show_status_window(status)
            _notify_status_listeners(status)
            return status
        _discard_dead_server("start_bridge")
    _require_maya_process()
    active_host = host or os.environ.get("ASSET_FORGE_MAYA_MCP_HOST") or DEFAULT_HOST
    active_root = os.path.abspath(repo_root or os.environ.get("ASSET_FORGE_REPO_ROOT") or _repo_root())
    _ensure_repo_on_path(active_root)
    explicit_port = port or os.environ.get("ASSET_FORGE_MAYA_MCP_PORT")
    active_port = int(explicit_port) if explicit_port else _allocate_bridge_port(active_host, DEFAULT_PORT)
    active_token = token if token is not None else os.environ.get("ASSET_FORGE_MAYA_MCP_TOKEN", "")
    _reset_metrics(active_root)
    _SERVER = AssetForgeMayaBridgeServer((active_host, active_port), AssetForgeMayaBridgeHandler, token=active_token, repo_root=active_root)
    _register_bridge_instance(_SERVER)
    _THREAD = threading.Thread(target=_SERVER.serve_forever)
    _THREAD.daemon = True
    _THREAD.start()
    print("[AssetForgeMayaBridge] listening on {0}:{1}".format(active_host, active_port))
    status = bridge_status()
    _log_bridge_event("mcp_bridge_start", "success", active_root, outputs=status)
    _safe_show_status_window(status)
    _notify_status_listeners(status)
    return status


def stop_bridge():
    global _SERVER, _THREAD
    if _SERVER is None:
        status = _stopped_status()
        _safe_show_status_window(status)
        _notify_status_listeners(status)
        return status
    repo_root = _SERVER.repo_root
    instance_id = getattr(_SERVER, "instance_id", "")
    port = _SERVER.server_address[1]
    _SERVER.shutdown()
    _SERVER.server_close()
    _unregister_bridge_instance(instance_id=instance_id, port=port)
    _SERVER = None
    _THREAD = None
    status = _stopped_status(repo_root)
    _set_metrics_status("stopped", "mcp_bridge_stop", "")
    _log_bridge_event("mcp_bridge_stop", "success", repo_root, outputs=status)
    _safe_show_status_window(status)
    _notify_status_listeners(status)
    return status


def bridge_status():
    if _SERVER is None:
        return _stopped_status()
    if not _bridge_thread_alive():
        status = _stopped_status(_SERVER.repo_root)
        status.update(
            {
                "health": "error",
                "last_error": "Maya MCP bridge thread is not listening.",
                "next_action": "点击启动重新创建 Maya MCP bridge；旧端口不会继续注册为可用实例。",
            }
        )
        return status
    _register_bridge_instance(_SERVER)
    host, port = _SERVER.server_address
    metrics = _metrics_snapshot()
    status = {
        "status": "running",
        "health": _health_from_metrics(metrics),
        "bridge_version": BRIDGE_VERSION,
        "instance_id": getattr(_SERVER, "instance_id", ""),
        "pid": os.getpid(),
        "host": host,
        "port": port,
        "scene_path": _current_scene_path(),
        "registry_path": getattr(_SERVER, "registry_path", ""),
        "repo_root": _SERVER.repo_root,
        "token_required": bool(_SERVER.token),
        "latest_maya_log": _latest_log_path(_SERVER.repo_root),
        "next_action": "Codex can connect through maya-mcp. Use maya_instances to select this Maya instance.",
    }
    status.update(metrics)
    return status


def show_bridge_status_window():
    """Show a small Maya UI that makes the MCP bridge state visible."""
    _require_maya_process()
    status = bridge_status()
    _show_status_window(status)
    _notify_status_listeners(status)
    return status


def register_status_listener(callback):
    """Let the main Asset Forge UI mirror Stop Bridge / Refresh state changes."""
    if callback not in _STATUS_LISTENERS:
        _STATUS_LISTENERS.append(callback)
    return callback


def unregister_status_listener(callback):
    if callback in _STATUS_LISTENERS:
        _STATUS_LISTENERS.remove(callback)


def install_bridge_shelf_button(repo_root=None, shelf_name=BRIDGE_SHELF_NAME):
    """Install a one-click Maya shelf button for starting the MCP bridge."""
    _require_maya_process()
    active_root = os.path.abspath(repo_root or os.environ.get("ASSET_FORGE_REPO_ROOT") or _repo_root())
    _ensure_repo_on_path(active_root)
    cmds = _maya_cmds()
    shelf = _ensure_shelf(cmds, shelf_name)
    if cmds.shelfButton(BRIDGE_SHELF_BUTTON, exists=True):
        cmds.deleteUI(BRIDGE_SHELF_BUTTON)
    command = _bridge_start_command(active_root)
    icon_path = _asset_forge_shelf_icon(active_root)
    button = cmds.shelfButton(
        BRIDGE_SHELF_BUTTON,
        parent=shelf,
        label="Maya MCP",
        annotation="Start Maya MCP bridge for Codex",
        image=icon_path,
        image1=icon_path,
        imageOverlayLabel="",
        overlayLabelColor=(0.80, 0.92, 1.0),
        overlayLabelBackColor=(0.03, 0.08, 0.12, 0.75),
        command=command,
        sourceType="python",
    )
    status = {
        "status": "success",
        "bridge_version": BRIDGE_VERSION,
        "shelf": shelf,
        "button": button,
        "repo_root": active_root,
        "icon": icon_path,
        "next_action": "Shelf 按钮 Maya MCP 已安装；以后点击它即可启动当前 Maya 的 bridge。",
    }
    _log_bridge_event("mcp_bridge_install_shelf_button", "success", active_root, outputs=status)
    return status


def _asset_forge_shelf_icon(repo_root):
    candidates = [
        os.path.join(repo_root, "Plugins", "AssetForge", "Resources", "IconMayaMcpShelf.png"),
        os.path.join(repo_root, "Plugins", "AssetForge", "Resources", "IconMayaShelf.png"),
        os.path.join(repo_root, "Plugins", "AssetForge", "Resources", "IconToolbar.png"),
        os.path.join(repo_root, "Plugins", "AssetForge", "Resources", "Icon128.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path.replace("\\", "/")
    return "commandButton.png"


def _execute_in_maya_main_thread(action, params):
    def _run():
        from asset_forge.maya.mcp_actions import dispatch_action

        return dispatch_action(action, params)

    try:
        import maya.utils as maya_utils

        return maya_utils.executeInMainThreadWithResult(_run)
    except ImportError:
        return _run()


def _ensure_repo_on_path(repo_root):
    maya_scripts = os.path.join(repo_root, "integrations", "maya", "scripts")
    repo_scripts = os.path.join(repo_root, "scripts")
    for path in [repo_scripts, repo_root, maya_scripts]:
        normalized = os.path.normcase(os.path.abspath(path))
        sys.path[:] = [item for item in sys.path if os.path.normcase(os.path.abspath(item)) != normalized]
        sys.path.insert(0, path)


def _repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir))


def _allocate_bridge_port(host, preferred_port):
    from integrations.maya_mcp_runtime.ports import allocate_port

    return allocate_port(host=host, preferred_port=preferred_port)


def _register_bridge_instance(server):
    from integrations.maya_mcp_runtime.registry import default_registry_path, new_instance_id, register_instance

    host, port = server.server_address
    if not getattr(server, "instance_id", ""):
        server.instance_id = new_instance_id()
    server.registry_path = default_registry_path()
    instance = register_instance(
        {
            "instance_id": server.instance_id,
            "pid": os.getpid(),
            "host": host,
            "port": port,
            "repo_root": server.repo_root,
            "scene_path": _current_scene_path(),
            "maya_version": _maya_version(),
            "bridge_version": BRIDGE_VERSION,
            "token_required": bool(server.token),
            "started_at": _BRIDGE_METRICS.get("started_at", ""),
        }
    )
    server.instance_id = instance.get("instance_id", server.instance_id)
    return instance


def _unregister_bridge_instance(instance_id=None, port=None):
    try:
        from integrations.maya_mcp_runtime.registry import unregister_instance

        return unregister_instance(instance_id=instance_id, pid=os.getpid(), port=port)
    except Exception as exc:
        print("[AssetForgeMayaBridge] registry unregister failed: {0}".format(exc))
        return []


def _bridge_thread_alive():
    return _SERVER is not None and _THREAD is not None and _THREAD.is_alive()


def _discard_dead_server(action=""):
    global _SERVER, _THREAD
    if _SERVER is None:
        return
    repo_root = getattr(_SERVER, "repo_root", "") or _repo_root()
    instance_id = getattr(_SERVER, "instance_id", "")
    try:
        _unregister_bridge_instance(instance_id=instance_id, port=_SERVER.server_address[1])
    finally:
        try:
            _SERVER.server_close()
        except Exception:
            pass
        _SERVER = None
        _THREAD = None
        _set_metrics_status("error", action or "mcp_bridge_restart", "Maya MCP bridge thread is not listening.")
        _log_bridge_event(
            "mcp_bridge_discard_dead_server",
            "warning",
            repo_root,
            errors=[{"message": "Maya MCP bridge thread is not listening."}],
        )


def _current_scene_path():
    try:
        cmds = _maya_cmds()
        return (cmds.file(query=True, sceneName=True) or "").replace("\\", "/")
    except Exception:
        return ""


def _maya_version():
    try:
        cmds = _maya_cmds()
        return cmds.about(version=True)
    except Exception:
        return ""


def _is_local_address(value):
    return value in ("127.0.0.1", "::1", "localhost")


def _require_maya_process():
    try:
        import maya.cmds  # noqa: F401
    except ImportError:
        raise RuntimeError("Asset Forge Maya bridge 必须在 Maya 进程内启动；请在 Maya 2026 Script Editor 中执行 --bridge 启动入口。")


def _maya_cmds():
    import maya.cmds as cmds

    return cmds


def _now_label():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _empty_metrics():
    return {
        "started_at": "",
        "started_at_epoch": 0.0,
        "last_heartbeat": "",
        "last_heartbeat_epoch": 0.0,
        "uptime_seconds": 0,
        "request_count": 0,
        "active_requests": 0,
        "current_action": "",
        "last_action": "",
        "last_action_started_at": "",
        "last_action_finished_at": "",
        "last_status": "idle",
        "last_error": "",
        "last_client": "",
        "last_request_id": "",
    }


def _reset_metrics(repo_root=""):
    now = time.time()
    metrics = _empty_metrics()
    metrics.update(
        {
            "started_at": _now_label(),
            "started_at_epoch": now,
            "last_heartbeat": _now_label(),
            "last_heartbeat_epoch": now,
            "repo_root": repo_root,
        }
    )
    with _METRICS_LOCK:
        _BRIDGE_METRICS.clear()
        _BRIDGE_METRICS.update(metrics)


def _metrics_snapshot():
    now = time.time()
    with _METRICS_LOCK:
        if not _BRIDGE_METRICS:
            metrics = _empty_metrics()
        else:
            _BRIDGE_METRICS["last_heartbeat"] = _now_label()
            _BRIDGE_METRICS["last_heartbeat_epoch"] = now
            metrics = dict(_BRIDGE_METRICS)
    started_at_epoch = float(metrics.get("started_at_epoch") or 0.0)
    metrics["uptime_seconds"] = int(max(0.0, now - started_at_epoch)) if started_at_epoch else 0
    return metrics


def _set_metrics_status(status, action="", error=""):
    with _METRICS_LOCK:
        if not _BRIDGE_METRICS:
            _BRIDGE_METRICS.update(_empty_metrics())
        _BRIDGE_METRICS["last_status"] = status
        _BRIDGE_METRICS["last_error"] = error or ""
        _BRIDGE_METRICS["last_action"] = action or _BRIDGE_METRICS.get("last_action", "")
        _BRIDGE_METRICS["current_action"] = ""
        _BRIDGE_METRICS["active_requests"] = 0
        _BRIDGE_METRICS["last_action_finished_at"] = _now_label()


def _mark_request_start(action, request_id, client):
    label = action or "unknown"
    with _METRICS_LOCK:
        if not _BRIDGE_METRICS:
            _BRIDGE_METRICS.update(_empty_metrics())
        _BRIDGE_METRICS["request_count"] = int(_BRIDGE_METRICS.get("request_count") or 0) + 1
        _BRIDGE_METRICS["active_requests"] = int(_BRIDGE_METRICS.get("active_requests") or 0) + 1
        _BRIDGE_METRICS["current_action"] = label
        _BRIDGE_METRICS["last_action"] = label
        _BRIDGE_METRICS["last_action_started_at"] = _now_label()
        _BRIDGE_METRICS["last_status"] = "running"
        _BRIDGE_METRICS["last_error"] = ""
        _BRIDGE_METRICS["last_client"] = client or ""
        _BRIDGE_METRICS["last_request_id"] = request_id or ""
    print("[AssetForgeMayaBridge] request start: {0} ({1})".format(label, request_id or "no-id"))
    _safe_refresh_status_window()


def _mark_request_finish(action, request_id, status, error):
    label = action or "unknown"
    with _METRICS_LOCK:
        if not _BRIDGE_METRICS:
            _BRIDGE_METRICS.update(_empty_metrics())
        active = int(_BRIDGE_METRICS.get("active_requests") or 0)
        _BRIDGE_METRICS["active_requests"] = max(0, active - 1)
        _BRIDGE_METRICS["current_action"] = label if _BRIDGE_METRICS["active_requests"] else ""
        _BRIDGE_METRICS["last_action"] = label
        _BRIDGE_METRICS["last_action_finished_at"] = _now_label()
        _BRIDGE_METRICS["last_status"] = status
        _BRIDGE_METRICS["last_error"] = error or ""
        _BRIDGE_METRICS["last_request_id"] = request_id or _BRIDGE_METRICS.get("last_request_id", "")
    print("[AssetForgeMayaBridge] request {0}: {1} ({2})".format(status, label, request_id or "no-id"))
    _safe_refresh_status_window()


def _health_from_metrics(metrics):
    if int(metrics.get("active_requests") or 0) > 0:
        return "busy"
    if metrics.get("last_status") == "error":
        return "error"
    return "healthy"


def _stopped_status(repo_root=None):
    active_root = repo_root or os.environ.get("ASSET_FORGE_REPO_ROOT") or _repo_root()
    status = {
        "status": "stopped",
        "health": "stopped",
        "bridge_version": BRIDGE_VERSION,
        "pid": os.getpid(),
        "registry_path": "",
        "repo_root": active_root,
        "latest_maya_log": _latest_log_path(active_root),
        "next_action": "点击 shelf 按钮 MCP 或重新执行 start_bridge() 启动当前 Maya 的 bridge。",
    }
    status.update(_metrics_snapshot())
    status["status"] = "stopped"
    status["health"] = "stopped"
    status["active_requests"] = 0
    return status


def _safe_show_status_window(status):
    try:
        _show_status_window(status)
    except Exception as exc:
        print("[AssetForgeMayaBridge] status window failed: {0}".format(exc))


def _notify_status_listeners(status):
    for callback in list(_STATUS_LISTENERS):
        try:
            callback(status)
        except Exception as exc:
            print("[AssetForgeMayaBridge] status listener failed: {0}".format(exc))


def _safe_refresh_status_window():
    try:
        import maya.utils as maya_utils

        maya_utils.executeDeferred(lambda: _refresh_status_window_controls(bridge_status()))
    except Exception:
        try:
            _refresh_status_window_controls(bridge_status())
        except Exception:
            pass


def _show_status_window(status):
    global _WINDOW_CONTROLS
    cmds = _maya_cmds()
    if cmds.window(BRIDGE_WINDOW_NAME, exists=True) and _WINDOW_CONTROLS:
        _refresh_status_window_controls(status)
        return
    if cmds.window(BRIDGE_WINDOW_NAME, exists=True):
        cmds.deleteUI(BRIDGE_WINDOW_NAME)
    _WINDOW_CONTROLS = {}
    cmds.window(BRIDGE_WINDOW_NAME, title="Maya MCP Bridge", widthHeight=(560, 380), sizeable=False)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAttach=("both", 8))
    cmds.text(label="Maya MCP Bridge", align="left")
    _WINDOW_CONTROLS["state"] = cmds.text(label=_status_label(status), align="left")
    cmds.rowLayout(numberOfColumns=4, adjustableColumn=1)
    cmds.button(label="Refresh", command=lambda *_args: show_bridge_status_window())
    cmds.button(label="Save Log", command=lambda *_args: _save_status_log(status.get("repo_root", "")))
    cmds.button(label="Install Shelf Button", command=lambda *_args: install_bridge_shelf_button(status.get("repo_root", "")))
    cmds.button(label="Stop Bridge", command=lambda *_args: stop_bridge())
    cmds.setParent("..")
    _WINDOW_CONTROLS["details"] = cmds.scrollField(editable=False, wordWrap=True, height=210, text=_format_status_text(status))
    cmds.showWindow(BRIDGE_WINDOW_NAME)
    _start_monitor_job()


def _refresh_status_window_controls(status):
    global _MONITOR_JOB
    cmds = _maya_cmds()
    if not cmds.window(BRIDGE_WINDOW_NAME, exists=True):
        _WINDOW_CONTROLS.clear()
        _MONITOR_JOB = None
        return
    if not _WINDOW_CONTROLS:
        return
    state_control = _WINDOW_CONTROLS.get("state")
    details_control = _WINDOW_CONTROLS.get("details")
    if state_control:
        cmds.text(state_control, edit=True, label=_status_label(status))
    if details_control:
        cmds.scrollField(details_control, edit=True, text=_format_status_text(status))


def _start_monitor_job():
    global _MONITOR_JOB
    if _MONITOR_JOB:
        return
    try:
        cmds = _maya_cmds()
        _MONITOR_JOB = cmds.scriptJob(parent=BRIDGE_WINDOW_NAME, idleEvent=_monitor_tick, protected=True)
    except Exception:
        _MONITOR_JOB = None


def _monitor_tick():
    global _LAST_MONITOR_REFRESH
    now = time.time()
    if now - _LAST_MONITOR_REFRESH < 1.0:
        return
    _LAST_MONITOR_REFRESH = now
    try:
        _refresh_status_window_controls(bridge_status())
    except Exception:
        pass


def _status_label(status):
    health = status.get("health") or status.get("status", "unknown")
    current = status.get("current_action") or status.get("last_action") or "idle"
    active = int(status.get("active_requests") or 0)
    return "Health: {0} | Active: {1} | Action: {2}".format(health, active, current)


def _save_status_log(repo_root=None):
    active_root = repo_root or (_SERVER.repo_root if _SERVER is not None else "") or os.environ.get("ASSET_FORGE_REPO_ROOT") or _repo_root()
    status = bridge_status()
    text = _format_status_text(status)
    result = _log_bridge_event(
        "mcp_bridge_status_snapshot",
        "success",
        active_root,
        outputs={"bridge_status": status, "status_text": text},
    )
    status["last_manual_log"] = result.get("path", "") if isinstance(result, dict) else ""
    _safe_refresh_status_window()
    return {"status": "success", "log": result, "bridge_status": status}


def _format_status_text(status):
    repo_root = status.get("repo_root", "") or os.environ.get("ASSET_FORGE_REPO_ROOT", "")
    lines = [
        "Bridge Version: {0}".format(status.get("bridge_version", BRIDGE_VERSION)),
        "Status: {0}".format(status.get("status", "")),
        "Health: {0}".format(status.get("health", "")),
        "Instance: {0}".format(status.get("instance_id", "")),
        "PID: {0}".format(status.get("pid", "")),
        "Host: {0}".format(status.get("host", DEFAULT_HOST)),
        "Port: {0}".format(status.get("port", DEFAULT_PORT)),
        "Scene: {0}".format(status.get("scene_path", "")),
        "Uptime: {0}s".format(status.get("uptime_seconds", 0)),
        "Last Heartbeat: {0}".format(status.get("last_heartbeat", "")),
        "",
        "Live Activity:",
        "Active Requests: {0}".format(status.get("active_requests", 0)),
        "Total Requests: {0}".format(status.get("request_count", 0)),
        "Current Action: {0}".format(status.get("current_action", "") or "idle"),
        "Last Action: {0}".format(status.get("last_action", "") or "none"),
        "Last Status: {0}".format(status.get("last_status", "")),
        "Last Client: {0}".format(status.get("last_client", "")),
        "Last Request ID: {0}".format(status.get("last_request_id", "")),
        "Started At: {0}".format(status.get("started_at", "")),
        "Action Started: {0}".format(status.get("last_action_started_at", "")),
        "Action Finished: {0}".format(status.get("last_action_finished_at", "")),
    ]
    if status.get("last_error"):
        lines.append("Last Error: {0}".format(status.get("last_error", "")))
    lines.extend(
        [
            "",
            "Repo: {0}".format(repo_root),
            "Registry: {0}".format(status.get("registry_path", "")),
            "Latest Maya Log: {0}".format(status.get("latest_maya_log", _latest_log_path(repo_root))),
            "",
            "Codex MCP Server:",
            "maya-mcp -> py -X utf8 -m integrations.maya_mcp.server",
            "",
            "Recent Bridge Log:",
        ]
    )
    entries = _latest_log_entries(repo_root, 8)
    if not entries:
        lines.append("- no latest_maya.log entries yet")
    for entry in entries:
        lines.append("- {0} | {1} | {2}".format(entry.get("timestamp", ""), entry.get("operation", ""), entry.get("status", "")))
    lines.extend(["", "Next: {0}".format(status.get("next_action", ""))])
    return "\n".join(lines)


def _latest_log_path(repo_root):
    try:
        from asset_forge.maya.operation_logger import latest_log_path

        return latest_log_path(repo_root)
    except Exception:
        return os.path.abspath(os.path.join(repo_root or _repo_root(), "AssetForgeReports", "logs", "latest_maya.log")).replace("\\", "/")


def _latest_log_entries(repo_root, max_entries=8):
    try:
        from asset_forge.maya.operation_logger import read_latest_log_tail

        return read_latest_log_tail(repo_root, max_entries)
    except Exception:
        return []


def _log_bridge_event(operation, status, repo_root, outputs=None, errors=None):
    try:
        from asset_forge.maya.operation_logger import MayaOperationLogger

        return MayaOperationLogger(root=repo_root).log(operation, status, outputs=outputs or {}, errors=errors or [])
    except Exception as exc:
        print("[AssetForgeMayaBridge] log failed: {0}".format(exc))
        return {}


def _ensure_shelf(cmds, shelf_name):
    if cmds.shelfLayout(shelf_name, exists=True):
        return shelf_name
    try:
        import maya.mel as mel

        top_level = mel.eval("$tmp=$gShelfTopLevel")
    except Exception:
        top_level = ""
    if top_level:
        return cmds.shelfLayout(shelf_name, parent=top_level)
    return cmds.shelfLayout(shelf_name)


def _bridge_start_command(repo_root):
    bootstrap = os.path.join(repo_root, "scripts", "maya_launch_asset_forge.py").replace("\\", "/")
    return "\n".join(
        [
            "_bootstrap = r\"{0}\"".format(bootstrap),
            "_globals = {",
            "    \"__file__\": _bootstrap,",
            "    \"__name__\": \"asset_forge_maya_bridge_shelf\",",
            "    \"ASSET_FORGE_REPO_ROOT\": r\"{0}\",".format(repo_root.replace("\\", "/")),
            "}",
            "exec(compile(open(_bootstrap, \"rb\").read(), _bootstrap, \"exec\"), _globals)",
            "print(_globals[\"start_bridge\"](repo_root=r\"{0}\"))".format(repo_root.replace("\\", "/")),
        ]
    )


if __name__ == "__main__":
    start_bridge()
