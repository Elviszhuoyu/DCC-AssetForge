# -*- coding: utf-8 -*-
"""Local instance registry for multi-instance Maya MCP bridges."""

from __future__ import absolute_import

import json
import os
import socket
import tempfile
import time
import uuid


REGISTRY_ENV = "MAYA_MCP_REGISTRY_PATH"
DEFAULT_DIR_NAME = "MayaMCP"
DEFAULT_FILE_NAME = "instances.json"
STALE_AFTER_SECONDS = 60 * 60 * 8


TARGET_KEYS = (
    "maya_instance",
    "maya_instance_id",
    "maya_pid",
    "maya_port",
    "maya_scene_contains",
)


class AmbiguousMayaInstanceError(RuntimeError):
    def __init__(self, instances):
        self.instances = list(instances or [])
        RuntimeError.__init__(
            self,
            "Multiple Maya MCP instances are registered. Specify maya_instance, maya_pid, maya_port, or maya_scene_contains.",
        )


class MayaInstanceNotFoundError(RuntimeError):
    pass


def default_registry_path():
    explicit = os.environ.get(REGISTRY_ENV)
    if explicit:
        return os.path.abspath(explicit)
    root = os.environ.get("LOCALAPPDATA") or os.path.join(tempfile.gettempdir(), DEFAULT_DIR_NAME)
    return os.path.abspath(os.path.join(root, DEFAULT_DIR_NAME, DEFAULT_FILE_NAME))


def new_instance_id():
    return "maya-" + str(uuid.uuid4())


def load_instances(path=None, include_stale=False, now=None):
    registry_path = path or default_registry_path()
    if not os.path.exists(registry_path):
        return []
    with open(registry_path, "r", encoding="utf-8-sig") as stream:
        data = json.load(stream)
    instances = data.get("instances", data if isinstance(data, list) else [])
    normalized = [_normalize_instance(item) for item in instances if isinstance(item, dict)]
    if include_stale:
        return [describe_instance(item) for item in normalized]
    return [
        describe_instance(item)
        for item in normalized
        if not _is_stale(item, now=now) and _is_instance_live(item)
    ]


def save_instances(instances, path=None):
    registry_path = path or default_registry_path()
    parent = os.path.dirname(registry_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    payload = {"updated_at_epoch": time.time(), "instances": list(instances or [])}
    temp_path = registry_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temp_path, registry_path)
    return registry_path


def register_instance(instance, path=None):
    active = _normalize_instance(instance)
    active.setdefault("instance_id", new_instance_id())
    active["updated_at_epoch"] = time.time()
    instances = [
        item
        for item in load_instances(path=path, include_stale=False)
        if item.get("instance_id") != active.get("instance_id")
        and not _same_endpoint(item, active)
        and not _same_pid(item, active)
    ]
    instances.append(active)
    save_instances(instances, path=path)
    return active


def unregister_instance(instance_id=None, pid=None, port=None, path=None):
    instances = []
    removed = []
    for item in load_instances(path=path, include_stale=True):
        match = False
        if instance_id and item.get("instance_id") == instance_id:
            match = True
        if pid is not None and int(item.get("pid") or -1) == int(pid):
            match = True
        if port is not None and int(item.get("port") or -1) == int(port):
            match = True
        if match:
            removed.append(item)
        else:
            instances.append(item)
    save_instances(instances, path=path)
    return removed


def resolve_instance(selector=None, path=None):
    selector = selector or {}
    instances = load_instances(path=path)
    matches = _filter_instances(instances, selector)
    if not matches and _has_selector(selector):
        stale_matches = _filter_instances(load_instances(path=path, include_stale=True), selector)
        matches = [item for item in stale_matches if _is_instance_live(item)]
    if not matches:
        raise MayaInstanceNotFoundError("No matching Maya MCP instance is registered.")
    if len(matches) > 1:
        raise AmbiguousMayaInstanceError(matches)
    return matches[0]


def selector_from_arguments(arguments=None):
    arguments = arguments or {}
    return dict((key, arguments.get(key)) for key in TARGET_KEYS if arguments.get(key) not in (None, ""))


def strip_target_arguments(arguments=None):
    clean = dict(arguments or {})
    for key in TARGET_KEYS:
        clean.pop(key, None)
    return clean


def describe_instance(instance):
    item = _normalize_instance(instance)
    scene_path = item.get("scene_path", "") or ""
    scene_name = os.path.basename(scene_path) if scene_path else "Untitled Maya Scene"
    port = item.get("port", "")
    pid = item.get("pid", "")
    item["scene_name"] = scene_name
    item["display_name"] = "{0} | pid {1} | port {2}".format(scene_name, pid or "?", port or "?")
    item["selection_hints"] = _selection_hints(item)
    return item


def _filter_instances(instances, selector):
    selector = selector or {}
    instance_id = selector.get("maya_instance") or selector.get("maya_instance_id")
    pid = selector.get("maya_pid")
    port = selector.get("maya_port")
    scene_contains = selector.get("maya_scene_contains")
    matches = list(instances or [])
    if instance_id:
        matches = [item for item in matches if item.get("instance_id") == instance_id]
    if pid not in (None, ""):
        matches = [item for item in matches if int(item.get("pid") or -1) == int(pid)]
    if port not in (None, ""):
        matches = [item for item in matches if int(item.get("port") or -1) == int(port)]
    if scene_contains:
        needle = str(scene_contains).lower()
        matches = [item for item in matches if needle in str(item.get("scene_path") or "").lower()]
    return matches


def _has_selector(selector):
    return any(selector.get(key) not in (None, "") for key in TARGET_KEYS)


def _normalize_instance(instance):
    item = dict(instance or {})
    if "host" not in item:
        item["host"] = "127.0.0.1"
    if item.get("port") not in (None, ""):
        item["port"] = int(item.get("port"))
    if item.get("pid") not in (None, ""):
        item["pid"] = int(item.get("pid"))
    item.setdefault("token_required", bool(item.get("token")))
    return item


def _selection_hints(instance):
    hints = []
    instance_id = instance.get("instance_id", "")
    pid = instance.get("pid", "")
    port = instance.get("port", "")
    scene_name = instance.get("scene_name", "")
    if instance_id:
        hints.append({"argument": "maya_instance", "value": instance_id})
    if pid:
        hints.append({"argument": "maya_pid", "value": pid})
    if port:
        hints.append({"argument": "maya_port", "value": port})
    if scene_name and scene_name != "Untitled Maya Scene":
        hints.append({"argument": "maya_scene_contains", "value": scene_name})
    return hints


def _is_stale(instance, now=None):
    updated = float(instance.get("updated_at_epoch") or 0.0)
    if not updated:
        return False
    return (time.time() if now is None else float(now)) - updated > STALE_AFTER_SECONDS


def _is_endpoint_alive(instance, timeout=0.25):
    host = instance.get("host") or "127.0.0.1"
    port = instance.get("port")
    if port in (None, ""):
        return False
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def _is_instance_live(instance):
    return _is_process_alive(instance) and _is_endpoint_alive(instance)


def _is_process_alive(instance):
    pid = instance.get("pid")
    if pid in (None, ""):
        return True
    try:
        active_pid = int(pid)
    except (TypeError, ValueError):
        return False
    if active_pid <= 0:
        return False
    if os.name == "nt":
        return _is_windows_pid_alive(active_pid)
    try:
        os.kill(active_pid, 0)
        return True
    except OSError:
        return False


def _is_windows_pid_alive(pid):
    try:
        import ctypes
    except Exception:
        return True
    process_query_limited_information = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return int(kernel32.GetLastError() or 0) == 5


def _same_endpoint(left, right):
    return left.get("host") == right.get("host") and int(left.get("port") or -1) == int(right.get("port") or -2)


def _same_pid(left, right):
    left_pid = int(left.get("pid") or -1)
    right_pid = int(right.get("pid") or -2)
    return left_pid > 0 and left_pid == right_pid
