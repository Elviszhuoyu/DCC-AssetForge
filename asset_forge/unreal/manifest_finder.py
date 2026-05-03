"""Find Asset Forge manifest files for Unreal import."""

from __future__ import absolute_import

import os

from asset_forge.shared.path_utils import normalize_path


def find_manifest_files(export_root):
    root = os.path.abspath(export_root)
    manifests = []
    if not os.path.isdir(root):
        return manifests

    for current_root, dir_names, file_names in os.walk(root):
        dir_names.sort()
        for file_name in sorted(file_names):
            if file_name.endswith("_manifest.json") or file_name == "manifest.json":
                manifests.append(normalize_path(os.path.join(current_root, file_name)))
    return manifests


def find_latest_manifest(export_root):
    manifests = find_manifest_files(export_root)
    if not manifests:
        return None
    return max(manifests, key=lambda item: os.path.getmtime(item))
