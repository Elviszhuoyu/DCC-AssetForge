# -*- coding: utf-8 -*-
"""Socket client used by the MCP stdio process to reach Blender."""

from __future__ import absolute_import

import socket

from integrations.blender_mcp.protocol import (
    decode_message,
    encode_message,
    env_host,
    env_port,
    env_timeout,
    env_token,
    make_request,
    normalize_bridge_response,
)
from integrations.blender_mcp_runtime.registry import (
    AmbiguousBlenderInstanceError,
    BlenderInstanceNotFoundError,
    load_instances,
    resolve_instance,
    selector_from_arguments,
)


class BlenderBridgeClient(object):
    def __init__(self, host=None, port=None, token=None, timeout=None, instance=None):
        self.host = host or env_host()
        self.port = int(port or env_port())
        self.token = env_token() if token is None else token
        self.timeout = float(timeout or env_timeout())
        self.instance = dict(instance or {})

    @classmethod
    def from_arguments(cls, arguments=None):
        selector = selector_from_arguments(arguments or {})
        if not selector:
            instances = load_instances()
            if len(instances) == 1:
                return cls.from_instance(instances[0])
            if len(instances) > 1:
                raise AmbiguousBlenderInstanceError(instances)
            return cls()
        try:
            instance = resolve_instance(selector)
        except BlenderInstanceNotFoundError:
            instance = _resolve_explicit_stale_instance(selector)
            if instance is None:
                raise
        return cls.from_instance(instance)

    @classmethod
    def from_instance(cls, instance):
        token = instance.get("token", "")
        return cls(
            host=instance.get("host") or env_host(),
            port=instance.get("port") or env_port(),
            token=token,
            timeout=env_timeout(),
            instance=instance,
        )

    def call(self, action, params=None):
        request = make_request(action, params or {}, self.token)
        try:
            sock = socket.create_connection((self.host, self.port), self.timeout)
        except OSError as exc:
            raise RuntimeError(
                "Cannot connect to Blender bridge {0}:{1}. Start the Asset Forge Blender bridge in the target Blender window first. Original error: {2}".format(
                    self.host,
                    self.port,
                    exc,
                )
            )
        except AmbiguousBlenderInstanceError:
            raise
        with sock:
            sock.settimeout(self.timeout)
            sock.sendall(encode_message(request))
            raw = _read_line(sock)
        result = normalize_bridge_response(decode_message(raw))
        if isinstance(result, dict):
            result.setdefault("mcp_target", self.target_summary())
        return result

    def target_summary(self):
        return {
            "instance_id": self.instance.get("instance_id", ""),
            "pid": self.instance.get("pid", ""),
            "host": self.host,
            "port": self.port,
            "scene_path": self.instance.get("scene_path", ""),
        }


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
        raise RuntimeError("Blender bridge returned no response.")
    return b"".join(chunks).split(b"\n", 1)[0]


def _resolve_explicit_stale_instance(selector):
    matches = [item for item in load_instances(include_stale=True) if _matches_selector(item, selector)]
    if len(matches) > 1:
        raise AmbiguousBlenderInstanceError(matches)
    if matches:
        return matches[0]
    return None


def _matches_selector(instance, selector):
    instance_id = selector.get("blender_instance") or selector.get("blender_instance_id")
    if instance_id and instance.get("instance_id") != instance_id:
        return False
    pid = selector.get("blender_pid")
    if pid not in (None, "") and int(instance.get("pid") or -1) != int(pid):
        return False
    port = selector.get("blender_port")
    if port not in (None, "") and int(instance.get("port") or -1) != int(port):
        return False
    scene_contains = selector.get("blender_scene_contains")
    if scene_contains:
        needle = str(scene_contains).lower()
        scene_path = instance.get("scene_path") or instance.get("blend_file") or ""
        if needle not in str(scene_path).lower():
            return False
    return True
