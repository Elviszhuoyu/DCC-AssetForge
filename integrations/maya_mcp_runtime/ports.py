# -*- coding: utf-8 -*-
"""Port allocation helpers for local Maya MCP bridge instances."""

from __future__ import absolute_import

import socket


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_PORT_END = 8799


def is_port_available(host=DEFAULT_HOST, port=DEFAULT_PORT):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    except (AttributeError, OSError):
        pass
    try:
        sock.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def allocate_port(host=DEFAULT_HOST, preferred_port=DEFAULT_PORT, port_end=DEFAULT_PORT_END):
    start = int(preferred_port or DEFAULT_PORT)
    end = int(port_end or DEFAULT_PORT_END)
    for port in range(start, end + 1):
        if is_port_available(host, port):
            return port
    raise RuntimeError("No free Maya MCP port found in range {0}-{1}.".format(start, end))
