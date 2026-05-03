"""Scan Painter or Designer texture folders using a Material Profile."""

from __future__ import absolute_import

import os

from asset_forge.shared.path_utils import normalize_path


DEFAULT_TEXTURE_EXTENSIONS = [".png", ".tga", ".jpg", ".jpeg", ".tif", ".tiff", ".exr"]


class TextureFolderScanner(object):
    """Match texture files to profile rules by asset name and suffix."""

    def __init__(self, extensions=None):
        self.extensions = [item.lower() for item in (extensions or DEFAULT_TEXTURE_EXTENSIONS)]

    def scan(self, texture_folder, asset_name, material_profile):
        files = self._texture_files(texture_folder)
        matched_paths = set()
        textures = []
        issues = []

        for rule in material_profile.get("texture_rules", []):
            matches = self._matches_for_rule(files, asset_name, rule)
            if not matches:
                if rule.get("required", False):
                    issues.append(
                        {
                            "status": "warning",
                            "message": "Missing required texture for usage: {0}".format(rule.get("usage", "")),
                            "usage": rule.get("usage", ""),
                        }
                    )
                continue

            if len(matches) > 1:
                issues.append(
                    {
                        "status": "warning",
                        "message": "Multiple textures matched usage: {0}".format(rule.get("usage", "")),
                        "usage": rule.get("usage", ""),
                        "matches": [normalize_path(path) for path in matches],
                    }
                )

            selected = matches[0]
            matched_paths.add(selected)
            textures.append(self._texture_entry(selected, rule))

        return {
            "asset_name": asset_name,
            "profile": material_profile.get("name", ""),
            "texture_folder": normalize_path(texture_folder),
            "textures": textures,
            "issues": issues,
            "unrecognized": [normalize_path(path) for path in files if path not in matched_paths],
        }

    def _texture_files(self, texture_folder):
        if not texture_folder or not os.path.isdir(texture_folder):
            return []
        result = []
        for file_name in sorted(os.listdir(texture_folder)):
            path = os.path.join(texture_folder, file_name)
            if os.path.isfile(path) and os.path.splitext(file_name)[1].lower() in self.extensions:
                result.append(path)
        return result

    def _matches_for_rule(self, files, asset_name, rule):
        matches = []
        suffixes = rule.get("suffixes", [])
        for path in files:
            stem = os.path.splitext(os.path.basename(path))[0]
            if not self._belongs_to_asset(stem, asset_name):
                continue
            if any(stem.endswith(suffix) for suffix in suffixes):
                matches.append(path)
        return matches

    def _belongs_to_asset(self, stem, asset_name):
        return not asset_name or stem == asset_name or stem.startswith(asset_name + "_")

    def _texture_entry(self, path, rule):
        entry = {
            "node": "",
            "path": normalize_path(path),
            "source_path": normalize_path(path),
            "package_path": "",
            "copied": False,
            "usage": rule.get("usage", "unknown"),
            "parameter": rule.get("parameter", ""),
            "srgb": bool(rule.get("srgb", False)),
            "compression": rule.get("compression", ""),
        }
        if rule.get("channels"):
            entry["channels"] = dict(rule["channels"])
        return entry
