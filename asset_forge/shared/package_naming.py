# -*- coding: utf-8 -*-
"""Shared package naming policy for DCC exports."""

from __future__ import absolute_import, unicode_literals

import os
import re

from asset_forge.shared.python_compat import to_text

from asset_forge.shared.path_utils import normalize_path


PACKAGE_VERSION_MODE_OVERWRITE = "overwrite"
PACKAGE_VERSION_MODE_AUTO_INCREMENT = "auto_increment"
PACKAGE_VERSION_MODES = (PACKAGE_VERSION_MODE_OVERWRITE, PACKAGE_VERSION_MODE_AUTO_INCREMENT)


def sanitize_package_name(value, fallback="Asset"):
    clean = re.sub(r"[^0-9A-Za-z_]+", "_", to_text(value or "")).strip("_")
    return clean or fallback


def normalize_package_version_mode(value):
    value = to_text(value or "").strip().lower()
    aliases = {
        "": PACKAGE_VERSION_MODE_OVERWRITE,
        "overwrite_current": PACKAGE_VERSION_MODE_OVERWRITE,
        "replace": PACKAGE_VERSION_MODE_OVERWRITE,
        "覆盖当前版本": PACKAGE_VERSION_MODE_OVERWRITE,
        "increment": PACKAGE_VERSION_MODE_AUTO_INCREMENT,
        "versioned": PACKAGE_VERSION_MODE_AUTO_INCREMENT,
        "auto_version": PACKAGE_VERSION_MODE_AUTO_INCREMENT,
        "自动递增版本": PACKAGE_VERSION_MODE_AUTO_INCREMENT,
    }
    value = aliases.get(value, value)
    return value if value in PACKAGE_VERSION_MODES else PACKAGE_VERSION_MODE_OVERWRITE


def resolve_package_naming(
    output_root,
    asset_name,
    package_name_override="",
    version_mode=PACKAGE_VERSION_MODE_OVERWRITE,
    version_padding=3,
    version_start=1,
):
    """Resolve the package folder identity without changing the DCC asset name."""
    clean_asset_name = sanitize_package_name(asset_name)
    manual_name = sanitize_package_name(package_name_override, "") if to_text(package_name_override or "").strip() else ""
    base_package_name = manual_name or clean_asset_name
    mode = normalize_package_version_mode(version_mode)
    padding = _safe_int(version_padding, 3)
    if padding < 1:
        padding = 3
    start = _safe_int(version_start, 1)
    if start < 1:
        start = 1

    output_root = os.path.abspath(output_root or ".")
    if mode == PACKAGE_VERSION_MODE_AUTO_INCREMENT:
        version_number = _next_version_number(output_root, base_package_name, padding, start)
        version_label = "v{0:0{1}d}".format(version_number, padding)
        package_name = "{0}_{1}".format(base_package_name, version_label)
    else:
        version_number = 0
        version_label = ""
        package_name = base_package_name

    package_dir = os.path.join(output_root, package_name)
    return {
        "asset_name": clean_asset_name,
        "package_name": package_name,
        "base_package_name": base_package_name,
        "manual_package_name": manual_name,
        "version_mode": mode,
        "version_padding": padding,
        "version_start": start,
        "version_number": version_number,
        "version_label": version_label,
        "package_dir": normalize_path(package_dir),
        "will_overwrite": os.path.isdir(package_dir),
        "naming_source": "manual_package_name" if manual_name else "asset_name",
    }


def _next_version_number(output_root, base_package_name, padding, start):
    highest = 0
    pattern = re.compile(r"^{0}_v(\d+)$".format(re.escape(base_package_name)), re.IGNORECASE)
    try:
        names = os.listdir(output_root)
    except Exception:
        names = []
    for name in names:
        match = pattern.match(name)
        if not match:
            continue
        try:
            highest = max(highest, int(match.group(1)))
        except ValueError:
            pass
    if highest:
        return highest + 1
    if os.path.isdir(os.path.join(output_root, base_package_name)):
        return max(start, 2)
    return start


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
