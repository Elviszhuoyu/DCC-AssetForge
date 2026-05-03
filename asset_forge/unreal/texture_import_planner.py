"""Plan Unreal texture imports from packaged manifest texture entries."""

from __future__ import absolute_import

import os

from asset_forge.shared.path_utils import normalize_path


class UnrealTextureImportPlanner(object):
    """Build a deterministic texture import plan without importing yet."""

    def plan(self, manifest):
        target_dir = self._target_texture_dir(manifest)
        planned_textures = []
        for texture in manifest.get("textures", []):
            if not self._is_packaged_texture(texture):
                continue
            planned_textures.append(self._texture_plan(texture, target_dir))

        return {
            "target_dir": target_dir,
            "count": len(planned_textures),
            "textures": planned_textures,
        }

    def _is_packaged_texture(self, texture):
        package_path = texture.get("package_path", "")
        return bool(texture.get("copied") and package_path and os.path.exists(package_path))

    def _texture_plan(self, texture, target_dir):
        package_path = normalize_path(texture.get("package_path", ""))
        asset_name = os.path.splitext(os.path.basename(package_path))[0]
        return {
            "source_path": package_path,
            "target_dir": target_dir,
            "target_asset_path": "{0}/{1}".format(target_dir, asset_name),
            "asset_name": asset_name,
            "usage": texture.get("usage", "unknown"),
            "node": texture.get("node", ""),
        }

    def _target_texture_dir(self, manifest):
        target_path = manifest.get("target_path", "/Game").replace("\\", "/").rstrip("/")
        return "{0}/Textures".format(target_path)
