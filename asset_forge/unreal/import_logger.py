"""Unreal import report helpers."""

from __future__ import absolute_import

import io
import json

from asset_forge.shared.constants import (
    UNREAL_IMPORT_STATUS_FAILED,
    UNREAL_IMPORT_STATUS_SUCCESS,
)


class UnrealImportLogger(object):
    """Collect serializable Unreal import results."""

    def success(self, manifest, imported_assets, message="Imported successfully"):
        return self._report(UNREAL_IMPORT_STATUS_SUCCESS, manifest, imported_assets, [], message)

    def failed(self, manifest, issues, message="Import failed"):
        return self._report(UNREAL_IMPORT_STATUS_FAILED, manifest, [], issues, message)

    def _report(self, status, manifest, imported_assets, issues, message):
        return {
            "status": status,
            "message": message,
            "asset_name": manifest.get("asset_name", ""),
            "fbx_path": manifest.get("fbx_path", ""),
            "target_path": manifest.get("target_path", ""),
            "import_preset": manifest.get("import_preset", ""),
            "imported_assets": imported_assets,
            "issues": issues,
        }

    def write(self, path, report):
        with io.open(path, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2))
            stream.write("\n")
        return path
