"""Copy referenced texture files into an Asset Forge export package."""

from __future__ import absolute_import

import os
import shutil

from asset_forge.shared.path_utils import ensure_dir, normalize_path


class MayaTexturePackager(object):
    """Package existing texture files without blocking missing placeholders."""

    def package_scan_textures(self, scan_result, package_dir):
        texture_dir = ensure_dir(os.path.join(package_dir, "Textures"))
        for texture in scan_result.get("textures", []):
            self._package_texture(texture, texture_dir)
        return scan_result

    def _package_texture(self, texture, texture_dir):
        source_path = texture.get("path", "")
        texture["source_path"] = source_path
        texture["package_path"] = ""
        texture["copied"] = False

        if not source_path or not os.path.exists(source_path):
            return texture

        destination = self._unique_destination(texture_dir, os.path.basename(source_path))
        shutil.copy2(source_path, destination)
        texture["package_path"] = normalize_path(destination)
        texture["copied"] = True
        return texture

    def _unique_destination(self, texture_dir, file_name):
        base, extension = os.path.splitext(file_name)
        destination = os.path.join(texture_dir, file_name)
        index = 1
        while os.path.exists(destination):
            destination = os.path.join(texture_dir, "{0}_{1}{2}".format(base, index, extension))
            index += 1
        return destination
