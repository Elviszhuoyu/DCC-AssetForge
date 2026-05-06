"""Unreal texture importer for packaged Asset Forge textures."""

from __future__ import absolute_import

from asset_forge.unreal.property_utils import get_unreal_property, set_unreal_property
from asset_forge.unreal.unreal_bridge import get_unreal


COMPRESSION_SETTING_BY_PROFILE = {
    "default": "TC_DEFAULT",
    "normalmap": "TC_NORMALMAP",
    "masks": "TC_MASKS",
}

TEXTURE_STRATEGY_OVERWRITE = "overwrite"
TEXTURE_STRATEGY_REUSE = "reuse"
TEXTURE_STRATEGY_SKIP = "skip"
TEXTURE_STRATEGY_ERROR = "error"


class UnrealTextureImporter(object):
    """Import texture files from a texture_import_plan."""

    def __init__(self, unreal_module=None):
        self.unreal = unreal_module or get_unreal()
        self.last_configuration_report = self._empty_configuration_report()
        self.last_import_policy_report = self._empty_policy_report()

    def is_available(self):
        return self.unreal is not None

    def import_textures(self, texture_import_plan):
        if not self.is_available():
            raise RuntimeError("当前环境不可用 Unreal Python 模块")

        self.last_configuration_report = self._empty_configuration_report()
        self.last_import_policy_report = self._empty_policy_report(texture_import_plan)
        imported = []
        tasks = []
        task_textures = []
        for texture in texture_import_plan.get("textures", []):
            action = self._existing_action(texture)
            if action == "skip":
                self._record_policy(texture, "skipped", "同名贴图已存在，按策略跳过")
                continue
            if action == "error":
                raise RuntimeError("同名贴图已存在：{0}".format(texture.get("target_asset_path", "")))
            if action == "reuse":
                asset_path = texture.get("target_asset_path", "")
                imported.append(asset_path)
                self._record_policy(texture, "reused", "复用已有贴图资产")
                self._configure_imported_texture(texture, [asset_path])
                continue

            tasks.append(self._build_task(texture, replace_existing=True))
            task_textures.append(texture)
            self._record_policy(texture, "queued", "贴图已加入导入队列")

        if tasks:
            self.unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
            for task, texture in zip(tasks, task_textures):
                imported_paths = list(get_unreal_property(task, "imported_object_paths", []) or [])
                imported.extend(imported_paths)
                self._configure_imported_texture(texture, imported_paths)

        self._finish_configuration_report()
        self._finish_policy_report()
        return imported

    def _existing_action(self, texture):
        strategy = texture.get("existing_texture_strategy", TEXTURE_STRATEGY_OVERWRITE)
        asset_path = texture.get("target_asset_path", "")
        exists = self._asset_exists(asset_path)
        if not exists:
            return "import"
        if strategy == TEXTURE_STRATEGY_SKIP:
            return "skip"
        if strategy == TEXTURE_STRATEGY_ERROR:
            return "error"
        if strategy == TEXTURE_STRATEGY_REUSE:
            return "reuse"
        return "import"

    def _build_task(self, texture, replace_existing=True):
        task = self.unreal.AssetImportTask()
        set_unreal_property(task, "filename", texture["source_path"])
        set_unreal_property(task, "destination_path", texture["target_dir"])
        set_unreal_property(task, "destination_name", texture["asset_name"])
        set_unreal_property(task, "automated", True)
        set_unreal_property(task, "replace_existing", bool(replace_existing))
        set_unreal_property(task, "save", True)
        return task

    def _configure_imported_texture(self, texture_plan, imported_paths):
        asset_path = self._primary_asset_path(imported_paths, texture_plan)
        if not asset_path:
            self.last_configuration_report["issues"].append("贴图导入后未返回资产路径：{0}".format(texture_plan.get("asset_name", "")))
            return

        texture_asset = self._load_asset(asset_path)
        if not texture_asset:
            self.last_configuration_report["issues"].append("无法加载导入后的贴图资产：{0}".format(asset_path))
            return

        set_unreal_property(texture_asset, "srgb", bool(texture_plan.get("srgb", False)))
        compression_value = self._compression_value(texture_plan.get("compression", ""))
        if compression_value is not None:
            set_unreal_property(texture_asset, "compression_settings", compression_value)
        self._save_asset(asset_path)
        self.last_configuration_report["configured"].append(
            {
                "asset_path": asset_path,
                "usage": texture_plan.get("usage", ""),
                "srgb": bool(texture_plan.get("srgb", False)),
                "compression": texture_plan.get("compression", ""),
            }
        )

    def _primary_asset_path(self, imported_paths, texture_plan):
        if imported_paths:
            return imported_paths[0].split(".", 1)[0]
        return texture_plan.get("target_asset_path", "")

    def _asset_exists(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "does_asset_exist"):
            return bool(library.does_asset_exist(asset_path))
        if library and hasattr(library, "load_asset"):
            return bool(library.load_asset(asset_path))
        return False

    def _load_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "load_asset"):
            return library.load_asset(asset_path)
        return None

    def _save_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "save_asset"):
            library.save_asset(asset_path)

    def _compression_value(self, compression):
        enum_name = COMPRESSION_SETTING_BY_PROFILE.get(compression)
        if not enum_name:
            return None
        enum_type = getattr(self.unreal, "TextureCompressionSettings", None)
        if enum_type is None:
            return enum_name
        return getattr(enum_type, enum_name, enum_name)

    def _record_policy(self, texture, action, message):
        self.last_import_policy_report["actions"].append(
            {
                "target_asset_path": texture.get("target_asset_path", ""),
                "strategy": texture.get("existing_texture_strategy", TEXTURE_STRATEGY_OVERWRITE),
                "action": action,
                "message": message,
            }
        )

    def _finish_configuration_report(self):
        report = self.last_configuration_report
        if report["issues"]:
            report["status"] = "warning" if report["configured"] else "skipped"
        else:
            report["status"] = "success" if report["configured"] else "skipped"

    def _finish_policy_report(self):
        report = self.last_import_policy_report
        report["status"] = "success" if report["actions"] else "skipped"

    def _empty_policy_report(self, texture_import_plan=None):
        texture_import_plan = texture_import_plan or {}
        return {
            "status": "skipped",
            "existing_texture_strategy": texture_import_plan.get("existing_texture_strategy", TEXTURE_STRATEGY_OVERWRITE),
            "actions": [],
            "issues": [],
        }

    def _empty_configuration_report(self):
        return {
            "status": "skipped",
            "configured": [],
            "issues": [],
        }
