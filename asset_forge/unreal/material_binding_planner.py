"""Plan Unreal material assets and texture slot bindings."""

from __future__ import absolute_import


class UnrealMaterialBindingPlanner(object):
    """Build a material binding plan without creating UE Material assets."""

    def plan(self, manifest, texture_import_plan):
        target_dir = self._target_material_dir(manifest)
        texture_lookup = self._texture_lookup(texture_import_plan)
        materials = []
        for material in manifest.get("materials", []):
            materials.append(self._material_plan(material, target_dir, texture_lookup))

        return {
            "target_dir": target_dir,
            "count": len(materials),
            "materials": materials,
        }

    def _material_plan(self, material, target_dir, texture_lookup):
        material_name = material.get("name", "M_Asset")
        slots = {}
        for texture in material.get("textures", []):
            usage = texture.get("usage", "unknown")
            texture_target = texture_lookup.get(texture.get("node", "")) or texture_lookup.get(texture.get("package_path", ""))
            if texture_target:
                slots[usage] = texture_target

        return {
            "material_name": material_name,
            "target_asset_path": "{0}/{1}".format(target_dir, material_name),
            "slots": slots,
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

    def _target_material_dir(self, manifest):
        target_path = manifest.get("target_path", "/Game").replace("\\", "/").rstrip("/")
        return "{0}/Materials".format(target_path)
