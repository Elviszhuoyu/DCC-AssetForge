"""Plan Unreal texture imports from packaged manifest texture entries."""

from __future__ import absolute_import

import os

from asset_forge.shared.material_profile_schema import resolve_material_profile
from asset_forge.shared.path_utils import normalize_path
from asset_forge.unreal.name_utils import sanitize_unreal_asset_name


class UnrealTextureImportPlanner(object):
    """Build a deterministic texture import plan without importing yet."""

    def plan(self, manifest, material_profile=None):
        profile = resolve_material_profile(material_profile or manifest.get("material_profile"))
        target_dir = self._target_texture_dir(manifest, profile)
        rule_lookup = self._rule_lookup(profile)
        planned_textures = []
        for texture in manifest.get("textures", []):
            if not self._is_packaged_texture(texture):
                continue
            planned_textures.append(self._texture_plan(texture, target_dir, rule_lookup.get(texture.get("usage", ""))))
        planned_textures = self._dedupe_asset_names(planned_textures)

        return {
            "target_dir": target_dir,
            "profile": profile.get("name", ""),
            "count": len(planned_textures),
            "textures": planned_textures,
        }

    def _is_packaged_texture(self, texture):
        package_path = texture.get("package_path", "")
        return bool(texture.get("copied") and package_path and os.path.exists(package_path))

    def _texture_plan(self, texture, target_dir, rule=None):
        rule = rule or {}
        package_path = normalize_path(texture.get("package_path", ""))
        asset_name = sanitize_unreal_asset_name(os.path.splitext(os.path.basename(package_path))[0], "T_Texture")
        return {
            "source_path": package_path,
            "target_dir": target_dir,
            "target_asset_path": "{0}/{1}".format(target_dir, asset_name),
            "asset_name": asset_name,
            "usage": texture.get("usage", "unknown"),
            "parameter": rule.get("parameter", texture.get("parameter", "")),
            "srgb": rule.get("srgb", texture.get("srgb")),
            "compression": rule.get("compression", texture.get("compression", "")),
            "node": texture.get("node", ""),
            "source_type": texture.get("source_type", ""),
            "source_label": texture.get("source_label", ""),
        }

    def _target_texture_dir(self, manifest, profile):
        target_path = manifest.get("target_path", "/Game").replace("\\", "/").rstrip("/")
        return profile.get("texture_dir", "{target_path}/Textures").format(target_path=target_path)

    def _rule_lookup(self, profile):
        return dict((rule.get("usage", ""), rule) for rule in profile.get("texture_rules", []))

    def _dedupe_asset_names(self, textures):
        seen = {}
        result = []
        for texture in textures:
            item = dict(texture)
            base_name = item.get("asset_name", "T_Texture")
            count = seen.get(base_name, 0) + 1
            seen[base_name] = count
            if count > 1:
                item["asset_name"] = "{0}_{1}".format(base_name, count)
                item["target_asset_path"] = "{0}/{1}".format(item.get("target_dir", ""), item["asset_name"])
            result.append(item)
        return result
