"""Plan Unreal material assets and texture slot bindings."""

from __future__ import absolute_import

import os

from asset_forge.shared.material_profile_schema import resolve_material_profile
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.unreal_path import sanitize_unreal_package_path
from asset_forge.unreal.material_library import parameter_api_mapping, resolve_material_variant
from asset_forge.unreal.name_utils import sanitize_unreal_asset_name


class UnrealMaterialBindingPlanner(object):
    """Build a material binding plan without creating UE Material assets."""

    def plan(self, manifest, texture_import_plan, material_profile=None):
        profile = resolve_material_profile(material_profile or manifest.get("material_profile"))
        target_dir = self._target_material_dir(manifest, profile)
        texture_lookup = self._texture_lookup(texture_import_plan)
        texture_plan_lookup = self._texture_plan_lookup(texture_import_plan)
        rule_lookup = self._rule_lookup(profile)
        existing_strategy = manifest.get("existing_material_strategy", profile.get("existing_material_strategy", "reuse"))
        materials = []
        for material in manifest.get("materials", []):
            materials.append(
                self._material_plan(
                    material,
                    target_dir,
                    texture_lookup,
                    texture_plan_lookup,
                    rule_lookup,
                    profile,
                    existing_strategy,
                    manifest.get("textures", []),
                )
            )
        reuse_summary = self._apply_material_instance_reuse(materials)

        return {
            "target_dir": target_dir,
            "profile": profile.get("name", ""),
            "master_material": profile.get("master_material", ""),
            "render_mode": profile.get("render_mode", ""),
            "existing_material_strategy": existing_strategy,
            "count": len(materials),
            "unique_material_instance_count": reuse_summary["unique_count"],
            "material_instance_reuse_count": reuse_summary["reuse_count"],
            "materials": materials,
        }

    def _material_plan(self, material, target_dir, texture_lookup, texture_plan_lookup, rule_lookup, profile, existing_strategy, manifest_textures):
        material_name = material.get("name", "M_Asset")
        target_asset_name = self._material_instance_name(material_name)
        slots = {}
        texture_parameters = {}
        texture_parameter_candidates = {}
        binding_warnings = []
        channel_mappings = {}
        texture_contracts = {}
        virtual_texture_assets = []
        material_textures = self._textures_for_material(material, manifest_textures)
        for texture in material_textures:
            usage = texture.get("usage", "unknown")
            texture_target = self._resolve_texture_target(texture, texture_lookup)
            texture_plan = self._resolve_texture_plan(texture, texture_target, texture_plan_lookup)
            rule = rule_lookup.get(usage, {})
            if texture_target:
                slots[usage] = texture_target
                parameter = rule.get("parameter", texture.get("parameter", ""))
                if parameter:
                    texture_parameter_candidates.setdefault(parameter, []).append(texture_target)
                    if parameter not in texture_parameters:
                        texture_parameters[parameter] = texture_target
                    texture_contracts[parameter] = self._texture_contract(texture, texture_plan, rule)
                if texture_plan.get("requires_virtual_texture_sampling"):
                    virtual_texture_assets.append(texture_target)
            else:
                binding_warnings.append(
                    {
                        "usage": usage,
                        "parameter": rule.get("parameter", texture.get("parameter", "")),
                        "message": "未能把 Maya 材质贴图匹配到 UE 导入贴图资产：{0}".format(
                            texture.get("package_path") or texture.get("path") or texture.get("node") or usage
                        ),
                    }
                )
            channels = texture.get("channels") or rule.get("channels")
            if channels:
                channel_mappings[usage] = dict(channels)
        variant = resolve_material_variant(profile, material_textures)
        planned_texture_parameter_names = list(texture_parameters.keys())
        planned_scalar_names = list(self._scalar_parameters(profile, channel_mappings, variant.get("detected_features", [])).keys())
        planned_vector_names = list((profile.get("vector_parameters", {}) or {}).keys())
        profile_api_mapping = dict(profile.get("parameter_api_mapping", {}) or {})
        profile_api_mapping.update(parameter_api_mapping(planned_texture_parameter_names + planned_scalar_names + planned_vector_names))
        parent_material = variant.get("selected_material_variant") or profile.get("master_material", "")
        static_switch_parameters = self._static_switch_parameters(profile, texture_parameters, variant.get("detected_features", []))
        binding_contract = self._binding_contract(static_switch_parameters, texture_parameters, texture_contracts, virtual_texture_assets)

        return {
            "material_name": material_name,
            "maya_material_name": material_name,
            "parent_material": parent_material,
            "parent_material_path": parent_material,
            "target_asset_path": "{0}/{1}".format(target_dir, target_asset_name),
            "target_asset_name": target_asset_name,
            "material_instance_name": target_asset_name,
            "material_instance_path": "{0}/{1}".format(target_dir, target_asset_name),
            "existing_material_strategy": existing_strategy,
            "slots": slots,
            "texture_parameters": texture_parameters,
            "texture_parameter_candidates": texture_parameter_candidates,
            "texture_contracts": texture_contracts,
            "binding_warnings": binding_warnings,
            "texture_set": self._material_texture_set(material_name),
            "channel_mappings": channel_mappings,
            "detected_features": variant.get("detected_features", []),
            "selected_master_family": variant.get("selected_master_family", ""),
            "selected_material_variant": variant.get("selected_material_variant", ""),
            "material_variant_key": variant.get("variant_key", ""),
            "variant_reason": variant.get("variant_reason", ""),
            "parameter_api_mapping": profile_api_mapping,
            "scalar_parameters": self._scalar_parameters(profile, channel_mappings, variant.get("detected_features", [])),
            "vector_parameters": dict(profile.get("vector_parameters", {})),
            "static_switch_parameters": static_switch_parameters,
            "binding_contract": binding_contract,
        }

    def _texture_lookup(self, texture_import_plan):
        lookup = {}
        for texture in texture_import_plan.get("textures", []):
            target = texture.get("target_asset_path", "")
            if texture.get("node"):
                lookup[texture["node"]] = target
            if texture.get("source_path"):
                lookup[texture["source_path"]] = target
                lookup[normalize_path(texture["source_path"])] = target
                lookup[os.path.basename(texture["source_path"]).lower()] = target
            if texture.get("package_path"):
                lookup[texture["package_path"]] = target
                lookup[normalize_path(texture["package_path"])] = target
                lookup[os.path.basename(texture["package_path"]).lower()] = target
            if texture.get("path"):
                lookup[texture["path"]] = target
                lookup[normalize_path(texture["path"])] = target
                lookup[os.path.basename(texture["path"]).lower()] = target
            if texture.get("usage"):
                lookup.setdefault("usage:{0}".format(texture.get("usage")), target)
        return lookup

    def _texture_plan_lookup(self, texture_import_plan):
        lookup = {}
        for texture in texture_import_plan.get("textures", []):
            target = texture.get("target_asset_path", "")
            if target:
                lookup[target] = texture
            for key in ("node", "source_path", "package_path", "path"):
                value = texture.get(key)
                if value:
                    lookup[value] = texture
                    lookup[normalize_path(value)] = texture
                    lookup[os.path.basename(value).lower()] = texture
            if texture.get("usage"):
                lookup.setdefault("usage:{0}".format(texture.get("usage")), texture)
        return lookup

    def _resolve_texture_target(self, texture, texture_lookup):
        candidates = [
            texture.get("node", ""),
            texture.get("package_path", ""),
            normalize_path(texture.get("package_path", "")),
            texture.get("source_path", ""),
            normalize_path(texture.get("source_path", "")),
            texture.get("path", ""),
            normalize_path(texture.get("path", "")),
        ]
        for candidate in candidates:
            if candidate and candidate in texture_lookup:
                return texture_lookup[candidate]
        for candidate in candidates:
            if candidate:
                target = texture_lookup.get(os.path.basename(candidate).lower())
                if target:
                    return target
        usage = texture.get("usage", "")
        if usage:
            return texture_lookup.get("usage:{0}".format(usage), "")
        return ""

    def _resolve_texture_plan(self, texture, texture_target, texture_plan_lookup):
        if texture_target and texture_target in texture_plan_lookup:
            return texture_plan_lookup[texture_target]
        candidates = [
            texture.get("node", ""),
            texture.get("package_path", ""),
            normalize_path(texture.get("package_path", "")),
            texture.get("source_path", ""),
            normalize_path(texture.get("source_path", "")),
            texture.get("path", ""),
            normalize_path(texture.get("path", "")),
        ]
        for candidate in candidates:
            if candidate and candidate in texture_plan_lookup:
                return texture_plan_lookup[candidate]
        for candidate in candidates:
            if candidate:
                item = texture_plan_lookup.get(os.path.basename(candidate).lower())
                if item:
                    return item
        usage = texture.get("usage", "")
        if usage:
            return texture_plan_lookup.get("usage:{0}".format(usage), {})
        return {}

    def _textures_for_material(self, material, manifest_textures):
        textures = list(material.get("textures", []) or [])
        texture_set = self._material_texture_set(material.get("name", ""))
        if textures:
            return self._merge_missing_set_textures(textures, manifest_textures, texture_set)
        if texture_set:
            fallback = [item for item in manifest_textures if self._texture_matches_set(item, texture_set)]
            if fallback:
                return fallback
        return textures

    def _merge_missing_set_textures(self, textures, manifest_textures, texture_set):
        result = list(textures or [])
        if not texture_set:
            return result
        existing_usages = set(item.get("usage", "") for item in result if item.get("usage", ""))
        existing_keys = set(self._texture_identity(item) for item in result)
        for texture in manifest_textures or []:
            usage = texture.get("usage", "")
            if not usage or usage in existing_usages:
                continue
            if not self._texture_matches_set(texture, texture_set):
                continue
            key = self._texture_identity(texture)
            if key and key in existing_keys:
                continue
            result.append(texture)
            existing_usages.add(usage)
            if key:
                existing_keys.add(key)
        return result

    def _texture_identity(self, texture):
        for key in ("package_path", "source_path", "path", "node"):
            value = normalize_path(texture.get(key, ""))
            if value:
                return value
        return ""

    def _material_texture_set(self, material_name):
        name = (material_name or "").lower()
        tokens = [token for token in name.replace("-", "_").split("_") if token]
        for token in reversed(tokens):
            if len(token) >= 2 and token[0].isalpha() and token[1:].isdigit():
                return token
        return ""

    def _texture_matches_set(self, texture, texture_set):
        texture_set = (texture_set or "").lower()
        selected = str(texture.get("selected_texture_set", "")).lower()
        if selected and selected.endswith(texture_set):
            return True
        for field in ("asset_name", "package_path", "source_path", "path"):
            value = str(texture.get(field, "")).lower()
            if "_{0}_".format(texture_set) in value or value.endswith("_{0}.png".format(texture_set)):
                return True
        return False

    def _target_material_dir(self, manifest, profile):
        target_path = sanitize_unreal_package_path(manifest.get("target_path", "/Game"))
        return profile.get("material_instance_dir", "{target_path}/Materials").format(target_path=target_path)

    def _material_instance_name(self, material_name):
        clean_name = sanitize_unreal_asset_name(material_name, "Material")
        if clean_name.startswith("MI_") or clean_name.endswith("_INST"):
            return clean_name
        return "MI_{0}".format(clean_name)

    def _apply_material_instance_reuse(self, materials):
        signatures = {}
        reuse_count = 0
        for material in materials:
            signature = self._material_reuse_signature(material)
            if not signature:
                material["material_instance_reuse_role"] = "unique"
                continue
            source = signatures.get(signature)
            if not source:
                signatures[signature] = material
                material["material_instance_reuse_role"] = "source"
                continue
            material["target_asset_path"] = source.get("target_asset_path", "")
            material["target_asset_name"] = source.get("target_asset_name", "")
            material["material_instance_path"] = source.get("material_instance_path", "")
            material["material_instance_name"] = source.get("material_instance_name", "")
            material["material_instance_reuse_role"] = "alias"
            material["material_instance_reuse_source"] = source.get("material_name", "")
            material["material_instance_reuse_reason"] = "matching_texture_parameter_signature"
            reuse_count += 1
        unique_paths = set(material.get("target_asset_path", "") for material in materials if material.get("target_asset_path", ""))
        return {"unique_count": len(unique_paths), "reuse_count": reuse_count}

    def _material_reuse_signature(self, material):
        texture_parameters = material.get("texture_parameters", {}) or {}
        slots = material.get("slots", {}) or {}
        if not texture_parameters and not slots:
            return None
        return (
            material.get("parent_material", ""),
            self._stable_items(texture_parameters),
            self._stable_items(material.get("scalar_parameters", {}) or {}),
            self._stable_items(material.get("vector_parameters", {}) or {}),
            self._stable_items(material.get("static_switch_parameters", {}) or {}),
        )

    def _stable_items(self, value):
        if isinstance(value, dict):
            return tuple((key, self._stable_items(value[key])) for key in sorted(value.keys()))
        if isinstance(value, (list, tuple)):
            return tuple(self._stable_items(item) for item in value)
        return value

    def _rule_lookup(self, profile):
        return dict((rule.get("usage", ""), rule) for rule in profile.get("texture_rules", []))

    def _scalar_parameters(self, profile, channel_mappings, detected_features=None):
        parameters = dict(profile.get("scalar_parameters", {}))
        features = set(detected_features or [])
        if "emissive" in features:
            parameters.setdefault("EmissiveIntensity", 1.0)
        for usage, channels in channel_mappings.items():
            for channel, meaning in channels.items():
                name = self._channel_scalar_name(usage, channel, meaning)
                parameters[name] = 1.0
        return parameters

    def _channel_scalar_name(self, usage, channel, meaning):
        clean_usage = sanitize_unreal_asset_name(usage, "Texture")
        clean_meaning = sanitize_unreal_asset_name(meaning, "Channel")
        return "{0}_{1}_{2}".format(clean_usage, str(channel).upper(), clean_meaning)

    def _static_switch_parameters(self, profile, texture_parameters, detected_features):
        features = set(detected_features or [])
        switches = {}
        if profile.get("render_mode") == "masked" or "opacity_mask" in features:
            switches["UseOpacityMask"] = True
            switches["UseSeparateOpacityMask"] = "OpacityMask" in texture_parameters
        if "emissive" in features or "Emissive" in texture_parameters:
            switches["UseEmissive"] = True
        return switches

    def _binding_contract(self, static_switch_parameters, texture_parameters, texture_contracts, virtual_texture_assets):
        opacity_source = "none"
        if static_switch_parameters.get("UseOpacityMask"):
            opacity_source = "separate_opacity_mask" if static_switch_parameters.get("UseSeparateOpacityMask") else "base_color_alpha"
        return {
            "opacity_source": opacity_source,
            "uses_emissive": bool(static_switch_parameters.get("UseEmissive")),
            "uses_separate_opacity_mask": bool(static_switch_parameters.get("UseSeparateOpacityMask")),
            "requires_virtual_texture_sampling": bool(virtual_texture_assets),
            "virtual_texture_assets": sorted(set(virtual_texture_assets)),
            "texture_format_contracts": dict(texture_contracts or {}),
        }

    def _texture_contract(self, texture, texture_plan, rule):
        source = texture_plan or texture or {}
        return {
            "usage": source.get("usage", texture.get("usage", "")),
            "srgb": source.get("srgb", rule.get("srgb", texture.get("srgb"))),
            "compression": source.get("compression", rule.get("compression", texture.get("compression", ""))),
            "channels": dict(source.get("channels") or texture.get("channels") or rule.get("channels", {})),
            "virtual_texture_streaming": source.get("virtual_texture_streaming"),
            "requires_virtual_texture_sampling": bool(source.get("requires_virtual_texture_sampling")),
        }
