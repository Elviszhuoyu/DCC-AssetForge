# -*- coding: utf-8 -*-
"""Helpers for Unreal package paths such as /Game/Props."""

from __future__ import absolute_import, unicode_literals

import re

from asset_forge.shared.python_compat import to_text


CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_unreal_package_path(path, required_prefix="/Game"):
    """Normalize a UE package path and reject hidden control characters."""
    value = to_text(path or "").replace("\\", "/").strip()
    if CONTROL_CHAR_PATTERN.search(value):
        raise ValueError("UE 资源路径不能包含换行、制表符或其他控制字符：{0!r}".format(path))
    value = re.sub(r"/+", "/", value).rstrip("/")
    if not value:
        raise ValueError("UE 资源路径不能为空")
    if required_prefix and not (value == required_prefix or value.startswith(required_prefix + "/")):
        raise ValueError("UE 资源路径必须以 {0}/ 开头：{1}".format(required_prefix, value))
    return value
