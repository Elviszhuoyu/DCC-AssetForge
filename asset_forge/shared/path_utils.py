"""Path helpers shared by DCC and Unreal integrations."""

from __future__ import absolute_import

import os


def normalize_path(path):
    if not path:
        return ""
    return os.path.abspath(path).replace("\\", "/")


def ensure_dir(path):
    if path and not os.path.exists(path):
        os.makedirs(path)
    return path
