"""Unreal texture importer for packaged Asset Forge textures."""

from __future__ import absolute_import

from asset_forge.unreal.property_utils import get_unreal_property, set_unreal_property
from asset_forge.unreal.unreal_bridge import get_unreal


class UnrealTextureImporter(object):
    """Import texture files from a texture_import_plan."""

    def __init__(self, unreal_module=None):
        self.unreal = unreal_module or get_unreal()

    def is_available(self):
        return self.unreal is not None

    def import_textures(self, texture_import_plan):
        if not self.is_available():
            raise RuntimeError("unreal module is not available")

        tasks = [self._build_task(texture) for texture in texture_import_plan.get("textures", [])]
        if not tasks:
            return []

        self.unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
        imported = []
        for task in tasks:
            imported.extend(list(get_unreal_property(task, "imported_object_paths", []) or []))
        return imported

    def _build_task(self, texture):
        task = self.unreal.AssetImportTask()
        set_unreal_property(task, "filename", texture["source_path"])
        set_unreal_property(task, "destination_path", texture["target_dir"])
        set_unreal_property(task, "destination_name", texture["asset_name"])
        set_unreal_property(task, "automated", True)
        set_unreal_property(task, "replace_existing", True)
        set_unreal_property(task, "save", True)
        return task
