"""Post-import validation for DCC AssetForge Unreal imports."""

from __future__ import absolute_import

from asset_forge.shared.constants import CHECK_STATUS_ERROR, CHECK_STATUS_PASS
from asset_forge.shared.unreal_path import sanitize_unreal_package_path


class UnrealPostImportValidator(object):
    """Validate the basic contract after Unreal returns imported asset paths."""

    def validate(self, manifest, imported_assets, import_options_report=None):
        expected_mesh_count = self._expected_mesh_count(manifest, import_options_report)
        imported_mesh_count = len(imported_assets or [])
        checks = [
            self._check_imported_assets(imported_assets),
            self._check_target_path(manifest, imported_assets),
        ]
        errors = [item for item in checks if item["status"] == CHECK_STATUS_ERROR]
        return {
            "status": CHECK_STATUS_ERROR if errors else CHECK_STATUS_PASS,
            "can_accept": not errors,
            "expected_static_mesh_count": expected_mesh_count,
            "imported_static_mesh_count": imported_mesh_count,
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
        target_path = sanitize_unreal_package_path(manifest.get("target_path", ""))
        is_multi_mesh_result = len(normalized_assets) > 1 or self._expected_mesh_count(manifest) > 1
        if is_multi_mesh_result and normalized_assets and all(path.startswith(target_path + "/") for path in normalized_assets):
            invalid_names = [path.rsplit("/", 1)[-1] for path in normalized_assets if not path.rsplit("/", 1)[-1].startswith("SM_")]
            if invalid_names:
                return {
                    "id": "static_mesh_name",
                    "label": "Static Mesh 命名",
                    "status": CHECK_STATUS_ERROR,
                    "message": "多 Mesh 导入结果存在未规范化命名：{0}。请通过 Maya UI 一键修复资产名前缀后重新导出。".format(", ".join(invalid_names)),
                }
            return {
                "id": "target_path",
                "label": "目标路径",
                "status": CHECK_STATUS_PASS,
                "message": "多 Mesh 资产包已导入到 manifest 目标目录；返回资产为：{0}".format(", ".join(normalized_assets)),
            }
        return {
            "id": "target_path",
            "label": "目标路径",
            "status": CHECK_STATUS_ERROR,
            "message": "导入资产不在预期路径下：{0}".format(expected),
        }

    def _expected_asset_path(self, manifest):
        target_path = sanitize_unreal_package_path(manifest.get("target_path", ""))
        asset_name = manifest.get("asset_name", "")
        return "{0}/{1}".format(target_path, asset_name)

    def _package_path(self, asset_path):
        normalized = asset_path.replace("\\", "/")
        return normalized.split(".", 1)[0]

    def _expected_mesh_count(self, manifest, import_options_report=None):
        if self._combine_meshes_enabled(import_options_report):
            return 1
        checks = manifest.get("checks", {}) if isinstance(manifest, dict) else {}
        mesh_check = checks.get("mesh_exists", {}) if isinstance(checks, dict) else {}
        try:
            return int(mesh_check.get("value", 1))
        except (TypeError, ValueError):
            return 1

    def _combine_meshes_enabled(self, import_options_report):
        if not isinstance(import_options_report, dict):
            return False
        options = import_options_report.get("options", {})
        if not isinstance(options, dict):
            return False
        return bool(options.get("combine_meshes", False))
