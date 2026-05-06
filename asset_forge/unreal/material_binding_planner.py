"""Plan Unreal material assets and texture slot bindings."""

from __future__ import absolute_import

from asset_forge.shared.material_profile_schema import resolve_material_profile
from asset_forge.unreal.name_utils import sanitize_unreal_asset_name


class UnrealMaterialBindingPlanner(object):
    """Build a material binding plan without creating UE Material assets."""

    def plan(self, manifest, texture_import_plan, material_profile=None):
        profile = resolve_material_profile(material_profile or manifest.get("material_profile"))
        target_dir = self._target_material_dir(manifest, profile)
        texture_lookup = self._texture_lookup(texture_import_plan)
        rule_lookup = self._rule_lookup(profile)
        existing_strategy = manifest.get("existing_material_strategy", profile.get("existing_material_strategy", "reuse"))
        materials = []
        for material in manifest.get("materials", []):
            materials.append(self._material_plan(material, target_dir, texture_lookup, rule_lookup, profile, existing_strategy))

        return {
            "target_dir": target_dir,
            "profile": profile.get("name", ""),
            "master_material": profile.get("master_material", ""),
            "render_mode": profile.get("render_mode", ""),
            "existing_material_strategy": existing_strategy,
            "count": len(materials),
            "materials": materials,
        }

    def _material_plan(self, material, target_dir, texture_lookup, rule_lookup, profile, existing_strategy):
        material_name = material.get("name", "M_Asset")
        target_asset_name = sanitize_unreal_asset_name(material_name, "M_Asset")
        slots = {}
        texture_parameters = {}
        channel_mappings = {}
        for texture in material.get("textures", []):
            usage = texture.get("usage", "unknown")
            texture_target = texture_lookup.get(texture.get("node", "")) or texture_lookup.get(texture.get("package_path", ""))
            rule = rule_lookup.get(usage, {})
            if texture_target:
                slots[usage] = texture_target
                parameter = rule.get("parameter", texture.get("parameter", ""))
                if parameter:
                    texture_parameters[parameter] = texture_target
            channels = texture.get("channels") or rule.get("channels")
            if channels:
                channel_mappings[usage] = dict(channels)

        return {
            "material_name": material_name,
            "parent_material": profile.get("master_material", ""),
            "target_asset_path": "{0}/{1}".format(target_dir, target_asset_name),
            "target_asset_name": target_asset_name,
            "existing_material_strategy": existing_strategy,
            "slots": slots,
            "texture_parameters": texture_parameters,
            "channel_mappings": channel_mappings,
            "scalar_parameters": dict(profile.get("scalar_parameters", {})),
        }

    def _texture_lookup(self, texture_import_plan):
        lookup = {}
        for texture in texture_import_plan.get("textures", []):
            target = texture.get("target_asset_path", "")
            if texture.get("node"):
                lookup[texture["node"]] = target
            if texture.get("source_path"):
                lookup[texture["source_path"]] = target
        return lookup

    def _target_material_dir(self, manifest, profile):
        target_path = manifest.get("target_path", "/Game").replace("\\", "/").rstrip("/")
        return profile.get("material_instance_dir", "{target_path}/Materials").format(target_path=target_path)

    def _rule_lookup(self, profile):
        return dict((rule.get("usage", ""), rule) for rule in profile.get("texture_rules", []))
