"""Lightweight texture metadata readers for offline validation."""

from __future__ import absolute_import

import os
import struct


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def read_texture_metadata(path):
    """Read width/height for simple texture headers without image dependencies."""
    extension = os.path.splitext(path or "")[1].lower()
    try:
        if extension == ".png":
            return _read_png(path)
        if extension == ".tga":
            return _read_tga(path)
        return _metadata("info", path, "暂不读取此贴图格式的尺寸元数据")
    except Exception as exc:
        return _metadata("warning", path, "贴图尺寸元数据读取失败：{0}".format(exc))


def apply_texture_metadata(texture, path=None):
    """Attach readable metadata fields to a manifest texture entry."""
    source_path = path or texture.get("package_path") or texture.get("source_path") or texture.get("path", "")
    metadata = read_texture_metadata(source_path)
    texture["texture_metadata_status"] = metadata.get("status", "")
    texture["texture_metadata_message"] = metadata.get("message", "")
    if metadata.get("width") and metadata.get("height"):
        texture["width"] = metadata["width"]
        texture["height"] = metadata["height"]
    return texture


def _read_png(path):
    with open(path, "rb") as stream:
        header = stream.read(24)
    if len(header) < 24:
        return _metadata("warning", path, "PNG header 不完整")
    if not header.startswith(PNG_SIGNATURE):
        return _metadata("warning", path, "PNG signature 不匹配")
    if header[12:16] != b"IHDR":
        return _metadata("warning", path, "PNG 缺少 IHDR chunk")
    width, height = struct.unpack(">II", header[16:24])
    return _metadata("pass", path, "PNG 尺寸读取成功", width, height)


def _read_tga(path):
    with open(path, "rb") as stream:
        header = stream.read(18)
    if len(header) < 18:
        return _metadata("warning", path, "TGA header 不完整")
    width = struct.unpack("<H", header[12:14])[0]
    height = struct.unpack("<H", header[14:16])[0]
    if not width or not height:
        return _metadata("warning", path, "TGA 尺寸为 0")
    return _metadata("pass", path, "TGA 尺寸读取成功", width, height)


def _metadata(status, path, message, width=0, height=0):
    return {
        "status": status,
        "path": (path or "").replace("\\", "/"),
        "width": width,
        "height": height,
        "message": message,
    }
