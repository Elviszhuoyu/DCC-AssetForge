"""Plan Unreal texture imports from packaged manifest texture entries."""

from __future__ import absolute_import

import os

from asset_forge.shared.material_profile_schema import resolve_material_profile
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.unreal_path import sanitize_unreal_package_path
from asset_forge.unreal.name_utils import sanitize_unreal_asset_name


class UnrealTextureImportPlanner(object):
    """Build a deterministic texture import plan without importing yet."""

    def plan(self, manifest, material_profile=None):
        profile = resolve_material_profile(material_profile or manifest.get("material_profile"))
        target_dir = self._target_texture_dir(manifest, profile)
        rule_lookup = self._rule_lookup(profile)
        existing_strategy = manifest.get("existing_texture_strategy", profile.get("existing_texture_strategy", "overwrite"))
        texture_policy = self._texture_import_policy(manifest, profile)
        planned_textures = []
        for texture in manifest.get("textures", []):
            if not self._is_packaged_texture(texture):
                continue
            planned_textures.append(self._texture_plan(texture, target_dir, rule_lookup.get(texture.get("usage", "")), existing_strategy, texture_policy))
        planned_textures = self._dedupe_asset_names(planned_textures)

        return {
            "target_dir": target_dir,
            "profile": profile.get("name", ""),
            "existing_texture_strategy": existing_strategy,
            "texture_import_policy": texture_policy,
            "count": len(planned_textures),
            "textures": planned_textures,
        }

    def _is_packaged_texture(self, texture):
        package_path = texture.get("package_path", "")
        return bool(texture.get("copied") and package_path and os.path.exists(package_path))

    def _texture_plan(self, texture, target_dir, rule=None, existing_strategy="overwrite", texture_policy=None):
        rule = rule or {}
        texture_policy = dict(texture_policy or {})
        package_path = normalize_path(texture.get("package_path", ""))
        asset_name = sanitize_unreal_asset_name(os.path.splitext(os.path.basename(package_path))[0], "T_Texture")
        srgb = rule.get("srgb", texture.get("srgb"))
        compression = rule.get("compression", texture.get("compression", ""))
        virtual_texture_policy = texture.get("virtual_texture_policy", texture_policy.get("virtual_texture_policy", "project_default"))
        texture_streaming_policy = texture.get("texture_streaming_policy", texture_policy.get("texture_streaming_policy", "project_default"))
        vt_decision = self._virtual_texture_decision(texture, virtual_texture_policy, texture_streaming_policy)
        return {
            "source_path": package_path,
            "package_path": package_path,
            "target_dir": target_dir,
            "target_asset_path": "{0}/{1}".format(target_dir, asset_name),
            "asset_name": asset_name,
            "existing_texture_strategy": texture.get("existing_texture_strategy", existing_strategy),
            "usage": texture.get("usage", "unknown"),
            "parameter": rule.get("parameter", texture.get("parameter", "")),
            "srgb": srgb,
            "compression": compression,
            "format_contract": self._format_contract(texture.get("usage", "unknown"), rule, srgb, compression),
            "virtual_texture_policy": virtual_texture_policy,
            "texture_streaming_policy": texture_streaming_policy,
            "virtual_texture_streaming": vt_decision["virtual_texture_streaming"],
            "requires_virtual_texture_sampling": vt_decision["requires_virtual_texture_sampling"],
            "virtual_texture_reason": vt_decision["reason"],
            "policy_warnings": vt_decision["warnings"],
            "texture_group": texture.get("texture_group", texture_policy.get("texture_group", "project_default")),
            "width": texture.get("width"),
            "height": texture.get("height"),
            "channels": dict(texture.get("channels") or rule.get("channels", {})),
            "node": texture.get("node", ""),
            "source_type": texture.get("source_type", ""),
            "source_label": texture.get("source_label", ""),
        }

    def _format_contract(self, usage, rule, srgb, compression):
        channels = dict(rule.get("channels", {}) or {})
        return {
            "usage": usage,
            "parameter": rule.get("parameter", ""),
            "srgb": bool(srgb),
            "compression": compression or "",
            "is_data_texture": not bool(srgb),
            "channels": channels,
        }

    def _virtual_texture_decision(self, texture, virtual_texture_policy, texture_streaming_policy):
        if texture_streaming_policy == "never_stream":
            return self._vt_decision(False, "never_stream disables virtual texture sampling for this import.", [])
        if virtual_texture_policy == "force_on":
            return self._vt_decision(True, "virtual_texture_policy force_on requires a VT-capable material sampler.", [])
        if virtual_texture_policy in ("force_off", "project_default"):
            return self._vt_decision(False, "{0} keeps DCC AssetForge imports on ordinary Texture2D sampling.".format(virtual_texture_policy), [])
        if virtual_texture_policy == "auto":
            width = self._int_or_none(texture.get("width"))
            height = self._int_or_none(texture.get("height"))
            max_size = max([value for value in (width, height) if value is not None] or [0])
            if max_size >= 4096:
                return self._vt_decision(
                    True,
                    "auto policy detected a texture at or above 4K; importer must use a VT-capable material path or force VT off.",
                    [],
                )
            if max_size:
                return self._vt_decision(False, "auto policy kept this texture below the 4K VT threshold.", [])
            return self._vt_decision(
                None,
                "auto policy has no width/height metadata, so UE must confirm the final VT state.",
                ["virtual_texture_policy=auto needs texture width/height metadata for deterministic planning."],
            )
        return self._vt_decision(None, "unknown virtual texture policy; UE must confirm the final VT state.", [])

    def _vt_decision(self, value, reason, warnings):
        return {
            "virtual_texture_streaming": value,
            "requires_virtual_texture_sampling": value is True,
            "reason": reason,
            "warnings": list(warnings or []),
        }

    def _int_or_none(self, value):
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _target_texture_dir(self, manifest, profile):
        target_path = sanitize_unreal_package_path(manifest.get("target_path", "/Game"))
        return profile.get("texture_dir", "{target_path}/Textures").format(target_path=target_path)

    def _rule_lookup(self, profile):
        return dict((rule.get("usage", ""), rule) for rule in profile.get("texture_rules", []))

    def _texture_import_policy(self, manifest, profile):
        result = dict(profile.get("texture_import_policy", {}) or {})
        result.update(manifest.get("texture_import_policy", {}) or {})
        return {
            "virtual_texture_policy": result.get("virtual_texture_policy", "project_default"),
            "texture_streaming_policy": result.get("texture_streaming_policy", "project_default"),
            "texture_group": result.get("texture_group", "project_default"),
        }

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
