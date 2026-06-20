# -*- coding: utf-8 -*-
"""Socket client used by the MCP stdio process to reach Maya."""

from __future__ import absolute_import

import socket

from integrations.maya_mcp.protocol import (
    encode_message,
    decode_message,
    env_host,
    env_port,
    env_timeout,
    env_token,
    make_request,
    normalize_bridge_response,
)
from integrations.maya_mcp_runtime.registry import (
    AmbiguousMayaInstanceError,
    load_instances,
    resolve_instance,
    selector_from_arguments,
)


class MayaBridgeClient(object):
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
                raise AmbiguousMayaInstanceError(instances)
            return cls()
        instance = resolve_instance(selector)
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
                "无法连接 Maya bridge {0}:{1}。请先在 Maya 中执行 integrations/maya/scripts/asset_forge_maya_bridge.py 并 start_bridge()。原始错误: {2}".format(
                    self.host,
                    self.port,
                    exc,
                )
            )
        except AmbiguousMayaInstanceError:
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
        raise RuntimeError("Maya bridge 未返回响应。")
    return b"".join(chunks).split(b"\n", 1)[0]
