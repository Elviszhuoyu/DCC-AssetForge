"""Validate exported package resources before Unreal import."""

from __future__ import absolute_import

import os

from asset_forge.shared.constants import CHECK_STATUS_PASS, CHECK_STATUS_WARNING


class UnrealPackageValidator(object):
    """Summarize whether manifest references point at packaged files."""

    def validate(self, manifest):
        texture_summary = self._texture_summary(manifest.get("textures", []))
        checks = [
            self._fbx_check(manifest.get("fbx_path", "")),
            self._texture_check(texture_summary),
        ]
        warnings = [item for item in checks if item["status"] == CHECK_STATUS_WARNING]
        return {
            "status": CHECK_STATUS_WARNING if warnings else CHECK_STATUS_PASS,
            "checks": checks,
            "textures": texture_summary,
        }

    def _fbx_check(self, fbx_path):
        if fbx_path and os.path.exists(fbx_path):
            return {
                "id": "fbx_path",
                "label": "FBX",
                "status": CHECK_STATUS_PASS,
                "message": "FBX exists",
            }
        return {
            "id": "fbx_path",
            "label": "FBX",
            "status": CHECK_STATUS_WARNING,
            "message": "FBX path is missing or unavailable",
        }

    def _texture_check(self, summary):
        if not summary["missing_package_paths"]:
            return {
                "id": "textures",
                "label": "Textures",
                "status": CHECK_STATUS_PASS,
                "message": "Packaged texture references are available",
            }
        return {
            "id": "textures",
            "label": "Textures",
            "status": CHECK_STATUS_WARNING,
            "message": "Some packaged texture references are missing",
        }

    def _texture_summary(self, textures):
        copied = []
        missing = []
        for texture in textures:
            package_path = texture.get("package_path", "")
            if texture.get("copied") and package_path and os.path.exists(package_path):
                copied.append(package_path)
            elif texture.get("copied"):
                missing.append(package_path or texture.get("path", ""))
        return {
            "total": len(textures),
            "copied": len(copied),
            "missing_package_paths": missing,
        }
