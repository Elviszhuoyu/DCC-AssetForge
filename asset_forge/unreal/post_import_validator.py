"""Post-import validation for Unreal Asset Forge imports."""

from __future__ import absolute_import

from asset_forge.shared.constants import CHECK_STATUS_ERROR, CHECK_STATUS_PASS


class UnrealPostImportValidator(object):
    """Validate the basic contract after Unreal returns imported asset paths."""

    def validate(self, manifest, imported_assets):
        checks = [
            self._check_imported_assets(imported_assets),
            self._check_target_path(manifest, imported_assets),
        ]
        errors = [item for item in checks if item["status"] == CHECK_STATUS_ERROR]
        return {
            "status": CHECK_STATUS_ERROR if errors else CHECK_STATUS_PASS,
            "can_accept": not errors,
            "checks": checks,
        }

    def _check_imported_assets(self, imported_assets):
        if imported_assets:
            return {
                "id": "imported_assets",
                "label": "导入资产",
                "status": CHECK_STATUS_PASS,
                "message": "Unreal 返回了导入资产路径",
            }
        return {
            "id": "imported_assets",
            "label": "导入资产",
            "status": CHECK_STATUS_ERROR,
            "message": "Unreal 未返回任何导入资产路径",
        }

    def _check_target_path(self, manifest, imported_assets):
        expected = self._expected_asset_path(manifest)
        normalized_assets = [self._package_path(path) for path in imported_assets]
        if expected in normalized_assets:
            return {
                "id": "target_path",
                "label": "目标路径",
                "status": CHECK_STATUS_PASS,
                "message": "导入资产路径与 manifest 目标路径一致",
            }
        return {
            "id": "target_path",
            "label": "目标路径",
            "status": CHECK_STATUS_ERROR,
            "message": "导入资产不在预期路径下：{0}".format(expected),
        }

    def _expected_asset_path(self, manifest):
        target_path = manifest.get("target_path", "").replace("\\", "/").rstrip("/")
        asset_name = manifest.get("asset_name", "")
        return "{0}/{1}".format(target_path, asset_name)

    def _package_path(self, asset_path):
        normalized = asset_path.replace("\\", "/")
        return normalized.split(".", 1)[0]
