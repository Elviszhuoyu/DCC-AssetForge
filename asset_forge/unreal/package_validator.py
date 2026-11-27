"""Validate exported package resources before Unreal import."""

from __future__ import absolute_import

import os

from asset_forge.shared.constants import CHECK_STATUS_ERROR, CHECK_STATUS_PASS, CHECK_STATUS_WARNING


class UnrealPackageValidator(object):
    """Summarize whether manifest references point at packaged files."""

    def validate(self, manifest):
        texture_summary = self._texture_summary(manifest.get("textures", []))
        checks = [
            self._fbx_check(manifest.get("fbx_path", "")),
            self._texture_check(texture_summary),
        ]
        statuses = [item["status"] for item in checks]
        return {
            "status": CHECK_STATUS_ERROR if CHECK_STATUS_ERROR in statuses else (CHECK_STATUS_WARNING if CHECK_STATUS_WARNING in statuses else CHECK_STATUS_PASS),
            "checks": checks,
            "textures": texture_summary,
        }

    def _fbx_check(self, fbx_path):
        if fbx_path and os.path.isfile(fbx_path):
            return {
                "id": "fbx_path",
                "label": "FBX 文件",
                "status": CHECK_STATUS_PASS,
                "message": "FBX 文件存在",
            }
        return {
            "id": "fbx_path",
            "label": "FBX 文件",
            "status": CHECK_STATUS_ERROR,
            "message": "FBX 文件缺失或路径不是文件。请重新导出包，或恢复 manifest.fbx_path 对应的 FBX。",
        }

    def _texture_check(self, summary):
        if not summary["missing_package_paths"]:
            return {
                "id": "textures",
                "label": "贴图",
                "status": CHECK_STATUS_PASS,
                "message": "已打包贴图引用可用",
            }
        return {
            "id": "textures",
            "label": "贴图",
            "status": CHECK_STATUS_WARNING,
            "message": "部分已打包贴图引用缺失",
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
