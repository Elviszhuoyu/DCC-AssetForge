"""UE asset naming helpers."""

from __future__ import absolute_import

import re


INVALID_ASSET_CHARS = re.compile(r"[^A-Za-z0-9_]+")


def sanitize_unreal_asset_name(name, fallback="Asset"):
    """Return a conservative UE asset name using letters, numbers, and underscores."""
    cleaned = INVALID_ASSET_CHARS.sub("_", str(name or "")).strip("_")
    if not cleaned:
        cleaned = fallback
    if cleaned[0].isdigit():
        cleaned = fallback + "_" + cleaned
    return cleaned
