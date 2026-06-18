# -*- coding: utf-8 -*-
"""Minimal stdio MCP server for local Maya bridge instances."""

from __future__ import absolute_import, print_function

import json
import sys

from integrations.maya_mcp.tools import call_tool, error_tool_result, tool_definitions


SERVER_INFO = {"name": "maya-mcp", "version": "0.2.0"}
PROTOCOL_VERSION = "2025-06-18"


def handle_message(message, client=None):
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        return _response(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _response(request_id, {})
    if method == "tools/list":
        return _response(request_id, {"tools": tool_definitions()})
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            result = call_tool(params.get("name"), params.get("arguments") or {}, client=client)
        except Exception as exc:
            result = error_tool_result(exc)
        return _response(request_id, result)
    if method == "resources/list":
        return _response(request_id, {"resources": []})
    if method == "prompts/list":
        return _response(request_id, {"prompts": []})
    return _error(request_id, -32601, "Unsupported MCP method: {0}".format(method))


def serve(stdin=None, stdout=None, client=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = handle_message(message, client=client)
        except Exception as exc:
            response = _error(None, -32603, str(exc))
        if response is None:
            continue
        _write_json_line(stdout, response)


def _response(request_id, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _write_json_line(stdout, response):
    line = json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n"
    if hasattr(stdout, "buffer"):
        stdout.buffer.write(line.encode("utf-8"))
    else:
        stdout.write(line)
    stdout.flush()


def main():
    serve()


if __name__ == "__main__":
    main()
