# -*- coding: utf-8 -*-
"""Protocol helpers shared by the Blender MCP server and bridge client."""

from __future__ import absolute_import

import json
import os
import uuid


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8875
DEFAULT_TIMEOUT_SECONDS = 120
LOCAL_ACTIONS = (
    "blender_instances",
)
SUPPORTED_ACTIONS = (
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
)
ALL_ACTIONS = LOCAL_ACTIONS + SUPPORTED_ACTIONS


def env_host():
    return os.environ.get("ASSET_FORGE_BLENDER_MCP_HOST", DEFAULT_HOST)


def env_port():
    return int(os.environ.get("ASSET_FORGE_BLENDER_MCP_PORT", DEFAULT_PORT))


def env_token():
    return os.environ.get("ASSET_FORGE_BLENDER_MCP_TOKEN", "")


def env_timeout():
    return float(os.environ.get("ASSET_FORGE_BLENDER_MCP_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))


def make_request(action, params=None, token=""):
    validate_action(action)
    request = {"id": str(uuid.uuid4()), "action": action, "params": params or {}}
    if token:
        request["token"] = token
    return request


def validate_action(action):
    if action not in ALL_ACTIONS:
        raise ValueError("Unsupported Blender MCP action: {0}".format(action))
    return action


def validate_bridge_action(action):
    if action not in SUPPORTED_ACTIONS:
        raise ValueError("Unsupported Blender bridge action: {0}".format(action))
    return action


def encode_message(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def decode_message(raw):
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def normalize_bridge_response(data):
    if not isinstance(data, dict):
        raise RuntimeError("Blender bridge returned a non-JSON object response.")
    if not data.get("ok"):
        error = data.get("error") or {}
        if isinstance(error, dict):
            message = error.get("message")
        else:
            message = str(error)
        raise RuntimeError(message or "Blender bridge action failed.")
    return data.get("result") or {}