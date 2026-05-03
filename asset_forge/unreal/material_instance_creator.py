"""Create Unreal Material Instances from Asset Forge binding plans."""

from __future__ import absolute_import

from asset_forge.unreal.property_utils import set_unreal_property
from asset_forge.unreal.unreal_bridge import get_unreal


class UnrealMaterialInstanceCreator(object):
    """Create Material Instance assets and bind planned parameters."""

    def __init__(self, unreal_module=None):
        self.unreal = unreal_module or get_unreal()

    def is_available(self):
        return self.unreal is not None

    def create_from_plan(self, material_binding_plan):
        if not self.is_available():
            raise RuntimeError("unreal module is not available")

        created = []
        for material_plan in material_binding_plan.get("materials", []):
            created.append(self._create_material_instance(material_plan))
        return created

    def _create_material_instance(self, material_plan):
        unreal = self.unreal
        parent_material = self._load_asset(material_plan.get("parent_material", ""))
        target_path = material_plan.get("target_asset_path", "")
        package_path, asset_name = target_path.rsplit("/", 1)

        factory = unreal.MaterialInstanceConstantFactoryNew()
        material_instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            asset_name,
            package_path,
            unreal.MaterialInstanceConstant,
            factory,
        )
        set_unreal_property(material_instance, "parent", parent_material)
        self._apply_texture_parameters(material_instance, material_plan.get("texture_parameters", {}))
        self._apply_scalar_parameters(material_instance, material_plan.get("scalar_parameters", {}))
        return target_path

    def _apply_texture_parameters(self, material_instance, texture_parameters):
        editing = getattr(self.unreal, "MaterialEditingLibrary", None)
        if editing is None:
            return
        for name, texture_path in texture_parameters.items():
            texture_asset = self._load_asset(texture_path)
            editing.set_material_instance_texture_parameter_value(material_instance, name, texture_asset)

    def _apply_scalar_parameters(self, material_instance, scalar_parameters):
        editing = getattr(self.unreal, "MaterialEditingLibrary", None)
        if editing is None:
            return
        for name, value in scalar_parameters.items():
            editing.set_material_instance_scalar_parameter_value(material_instance, name, value)

    def _load_asset(self, asset_path):
        if hasattr(self.unreal, "EditorAssetLibrary"):
            return self.unreal.EditorAssetLibrary.load_asset(asset_path)
        return asset_path
