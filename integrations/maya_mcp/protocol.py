# -*- coding: utf-8 -*-
"""Protocol helpers shared by the Maya MCP server and bridge client."""

from __future__ import absolute_import

import json
import os
import uuid


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TIMEOUT_SECONDS = 120
LOCAL_ACTIONS = (
    "maya_instances",
)
SUPPORTED_ACTIONS = (
    "maya_status",
    "maya_load_asset_forge",
    "maya_install_asset_forge_ui_shelf",
    "maya_install_mcp_bridge_shelf",
    "maya_open_scene",
    "maya_import_fbx",
    "maya_scan_static_prop",
    "maya_preflight_static_prop",
    "maya_export_static_prop_package",
    "maya_run_static_prop_ui_flow",
    "maya_get_latest_log",
    "maya_viewport_screenshot",
    "maya_reset_session",
    "maya_run_python",
)
ALL_ACTIONS = LOCAL_ACTIONS + SUPPORTED_ACTIONS


def env_host():
    return os.environ.get("ASSET_FORGE_MAYA_MCP_HOST", DEFAULT_HOST)


def env_port():
    return int(os.environ.get("ASSET_FORGE_MAYA_MCP_PORT", DEFAULT_PORT))


def env_token():
    return os.environ.get("ASSET_FORGE_MAYA_MCP_TOKEN", "")


def env_timeout():
    return float(os.environ.get("ASSET_FORGE_MAYA_MCP_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))


def make_request(action, params=None, token=""):
    validate_action(action)
    request = {"id": str(uuid.uuid4()), "action": action, "params": params or {}}
    if token:
        request["token"] = token
    return request


def validate_action(action):
    if action not in ALL_ACTIONS:
        raise ValueError("Unsupported Maya MCP action: {0}".format(action))
    return action


def validate_bridge_action(action):
    if action not in SUPPORTED_ACTIONS:
        raise ValueError("Unsupported Maya bridge action: {0}".format(action))
    return action


def encode_message(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def decode_message(raw):
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def normalize_bridge_response(data):
    if not isinstance(data, dict):
        raise RuntimeError("Maya bridge 返回了非 JSON object 响应。")
    if not data.get("ok"):
        error = data.get("error") or {}
        if isinstance(error, dict):
            message = error.get("message")
        else:
            message = str(error)
        raise RuntimeError(message or "Maya bridge action failed.")
    return data.get("result") or {}
