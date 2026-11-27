"""Small runtime differences shared by Maya's Python 2 and modern hosts."""

from __future__ import absolute_import, unicode_literals

import io
import json
import os

try:
    text_type = unicode
except NameError:
    text_type = str


def to_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return text_type(value)


def write_utf8_json(path, value, **options):
    # Python 2's JSON encoder can mix bytes and Unicode when writing chunks.
    content = to_text(json.dumps(value, ensure_ascii=False, **options))
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(content + "\n")


def replace_file(source, target):
    if hasattr(os, "replace"):
        os.replace(source, target)
    elif os.name == "nt":
        import ctypes
        from ctypes import wintypes
        from sys import getfilesystemencoding

        def wide_path(path):
            return path if isinstance(path, text_type) else path.decode(getfilesystemencoding())

        move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
        move.restype = wintypes.BOOL
        if not move(wide_path(source), wide_path(target), 1):  # MOVEFILE_REPLACE_EXISTING
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.rename(source, target)
