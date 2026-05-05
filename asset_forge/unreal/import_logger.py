"""Unreal import report helpers."""

from __future__ import absolute_import

import io
import json

from asset_forge.shared.constants import (
    UNREAL_IMPORT_STATUS_FAILED,
    UNREAL_IMPORT_STATUS_SKIPPED,
    UNREAL_IMPORT_STATUS_SUCCESS,
)


class UnrealImportLogger(object):
    """Collect serializable Unreal import results."""

    def success(self, manifest, imported_assets, message="导入成功", preset=None):
        return self._report(UNREAL_IMPORT_STATUS_SUCCESS, manifest, imported_assets, [], message, preset)

    def failed(self, manifest, issues, message="导入失败", preset=None):
        return self._report(UNREAL_IMPORT_STATUS_FAILED, manifest, [], issues, message, preset)

    def skipped(self, manifest, preset, message="预检查通过，未执行导入"):
        return self._report(UNREAL_IMPORT_STATUS_SKIPPED, manifest, [], [], message, preset)

    def _report(self, status, manifest, imported_assets, issues, message, preset=None):
        preset = preset or {}
        return {
            "status": status,
            "message": message,
            "asset_name": manifest.get("asset_name", ""),
            "asset_type": manifest.get("asset_type", ""),
            "source_dcc": manifest.get("source_dcc", ""),
            "target_engine": manifest.get("target_engine", ""),
            "target_platform": manifest.get("target_platform", ""),
            "fbx_path": manifest.get("fbx_path", ""),
            "target_path": manifest.get("target_path", ""),
            "import_preset": manifest.get("import_preset", ""),
            "resolved_preset": preset,
            "materials": manifest.get("materials", []),
            "textures": manifest.get("textures", []),
            "imported_assets": imported_assets,
            "issues": issues,
        }

    def write(self, path, report):
        with io.open(path, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2))
            stream.write("\n")
        return path
