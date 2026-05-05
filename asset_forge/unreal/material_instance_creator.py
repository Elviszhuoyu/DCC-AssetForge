"""Create Unreal Material Instances from Asset Forge binding plans."""

from __future__ import absolute_import

from asset_forge.unreal.property_utils import set_unreal_property
from asset_forge.unreal.unreal_bridge import get_unreal


class UnrealMaterialInstanceCreator(object):
    """Create Material Instance assets and bind planned parameters."""

    def __init__(self, unreal_module=None):
        self.unreal = unreal_module or get_unreal()
        self.last_parameter_report = self._empty_parameter_report()

    def is_available(self):
        return self.unreal is not None

    def create_from_plan(self, material_binding_plan):
        if not self.is_available():
            raise RuntimeError("当前环境不可用 Unreal Python 模块")

        self.last_parameter_report = self._empty_parameter_report()
        created = []
        for material_plan in material_binding_plan.get("materials", []):
            created.append(self._create_material_instance(material_plan))
        return created

    def _create_material_instance(self, material_plan):
        unreal = self.unreal
        parent_material = self._load_asset(material_plan.get("parent_material", ""))
        if not parent_material:
            raise RuntimeError("缺少母材质：{0}".format(material_plan.get("parent_material", "")))

        target_path = material_plan.get("target_asset_path", "")
        package_path, asset_name = target_path.rsplit("/", 1)

        material_instance = self._load_existing_asset(target_path)
        if not material_instance:
            factory = unreal.MaterialInstanceConstantFactoryNew()
            material_instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                asset_name,
                package_path,
                unreal.MaterialInstanceConstant,
                factory,
            )
        if not material_instance:
            raise RuntimeError("材质实例未创建：{0}".format(target_path))

        set_unreal_property(material_instance, "parent", parent_material)
        self._apply_texture_parameters(material_instance, material_plan.get("texture_parameters", {}))
        self._apply_scalar_parameters(material_instance, material_plan.get("scalar_parameters", {}))
        return target_path

    def _load_existing_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if not library or not hasattr(library, "does_asset_exist"):
            return None
        if not library.does_asset_exist(asset_path):
            return None
        return self._load_asset(asset_path)

    def _apply_texture_parameters(self, material_instance, texture_parameters):
        editing = getattr(self.unreal, "MaterialEditingLibrary", None)
        if editing is None:
            return
        for name, texture_path in texture_parameters.items():
            texture_asset = self._load_asset(texture_path)
            if not texture_asset:
                self.last_parameter_report["issues"].append("无法加载贴图参数 {0}：{1}".format(name, texture_path))
                continue
            editing.set_material_instance_texture_parameter_value(material_instance, name, texture_asset)
            self.last_parameter_report["texture_parameters"].append({"name": name, "asset_path": texture_path})

    def _apply_scalar_parameters(self, material_instance, scalar_parameters):
        editing = getattr(self.unreal, "MaterialEditingLibrary", None)
        if editing is None:
            return
        for name, value in scalar_parameters.items():
            editing.set_material_instance_scalar_parameter_value(material_instance, name, value)
            self.last_parameter_report["scalar_parameters"].append({"name": name, "value": value})

    def _load_asset(self, asset_path):
        if hasattr(self.unreal, "EditorAssetLibrary"):
            return self.unreal.EditorAssetLibrary.load_asset(asset_path)
        return asset_path

    def _empty_parameter_report(self):
        return {
            "status": "skipped",
            "texture_parameters": [],
            "scalar_parameters": [],
            "issues": [],
        }
