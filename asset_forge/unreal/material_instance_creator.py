"""Create Unreal Material Instances from Asset Forge binding plans."""

from __future__ import absolute_import

from asset_forge.unreal.property_utils import set_unreal_property
from asset_forge.unreal.unreal_bridge import get_unreal


MATERIAL_INSTANCE_STRATEGY_REUSE = "reuse"
MATERIAL_INSTANCE_STRATEGY_OVERWRITE = "overwrite"
MATERIAL_INSTANCE_STRATEGY_SKIP = "skip"
MATERIAL_INSTANCE_STRATEGY_ERROR = "error"


class UnrealMaterialInstanceCreator(object):
    """Create Material Instance assets and bind planned parameters."""

    def __init__(self, unreal_module=None, existing_strategy=MATERIAL_INSTANCE_STRATEGY_REUSE):
        self.unreal = unreal_module or get_unreal()
        self.existing_strategy = existing_strategy
        self.last_parameter_report = self._empty_parameter_report()
        self.last_creation_report = self._empty_creation_report()

    def is_available(self):
        return self.unreal is not None

    def create_from_plan(self, material_binding_plan):
        if not self.is_available():
            raise RuntimeError("当前环境不可用 Unreal Python 模块")

        self.last_parameter_report = self._empty_parameter_report()
        self.last_creation_report = self._empty_creation_report(material_binding_plan)
        created = []
        for material_plan in material_binding_plan.get("materials", []):
            created_path = self._create_material_instance(
                material_plan,
                material_binding_plan.get("existing_material_strategy", self.existing_strategy),
            )
            if created_path:
                created.append(created_path)
        self._finish_creation_report()
        return created

    def _create_material_instance(self, material_plan, existing_strategy):
        unreal = self.unreal
        parent_material = self._load_asset(material_plan.get("parent_material", ""))
        if not parent_material:
            raise RuntimeError("缺少母材质：{0}".format(material_plan.get("parent_material", "")))

        target_path = material_plan.get("target_asset_path", "")
        package_path, asset_name = target_path.rsplit("/", 1)
        strategy = material_plan.get("existing_material_strategy", existing_strategy) or MATERIAL_INSTANCE_STRATEGY_REUSE
        material_instance = self._load_existing_asset(target_path)

        if material_instance:
            action = self._handle_existing_asset(target_path, strategy)
            if action == "skip":
                self.last_creation_report["actions"].append(self._action(target_path, strategy, "skipped", "同名材质实例已存在，按策略跳过"))
                return ""
            if action == "error":
                raise RuntimeError("同名材质实例已存在：{0}".format(target_path))
            if action == "deleted":
                material_instance = None
            else:
                self.last_creation_report["actions"].append(self._action(target_path, strategy, "reused", "复用已有材质实例"))

        if not material_instance:
            factory = unreal.MaterialInstanceConstantFactoryNew()
            material_instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                asset_name,
                package_path,
                unreal.MaterialInstanceConstant,
                factory,
            )
            if material_instance:
                self.last_creation_report["actions"].append(self._action(target_path, strategy, "created", "创建材质实例"))

        if not material_instance:
            raise RuntimeError("材质实例未创建：{0}".format(target_path))

        set_unreal_property(material_instance, "parent", parent_material)
        self._apply_texture_parameters(material_instance, material_plan.get("texture_parameters", {}))
        self._apply_scalar_parameters(material_instance, material_plan.get("scalar_parameters", {}))
        return target_path

    def _handle_existing_asset(self, target_path, strategy):
        if strategy == MATERIAL_INSTANCE_STRATEGY_SKIP:
            return "skip"
        if strategy == MATERIAL_INSTANCE_STRATEGY_ERROR:
            return "error"
        if strategy == MATERIAL_INSTANCE_STRATEGY_OVERWRITE:
            if self._delete_asset(target_path):
                self.last_creation_report["actions"].append(self._action(target_path, strategy, "deleted", "删除已有材质实例以便重建"))
                return "deleted"
            self.last_creation_report["issues"].append("无法删除已有材质实例，改为复用：{0}".format(target_path))
            return "reuse"
        return "reuse"

    def _load_existing_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if not library or not hasattr(library, "does_asset_exist"):
            return None
        if not library.does_asset_exist(asset_path):
            return None
        return self._load_asset(asset_path)

    def _delete_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "delete_asset"):
            return bool(library.delete_asset(asset_path))
        return False

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

    def _finish_creation_report(self):
        report = self.last_creation_report
        if report.get("issues"):
            report["status"] = "warning"
        elif report.get("actions"):
            report["status"] = "success"
        else:
            report["status"] = "skipped"

    def _action(self, target_path, strategy, action, message):
        return {
            "target_asset_path": target_path,
            "strategy": strategy,
            "action": action,
            "message": message,
        }

    def _empty_creation_report(self, material_binding_plan=None):
        material_binding_plan = material_binding_plan or {}
        return {
            "status": "skipped",
            "existing_material_strategy": material_binding_plan.get("existing_material_strategy", self.existing_strategy),
            "actions": [],
            "issues": [],
        }

    def _empty_parameter_report(self):
        return {
            "status": "skipped",
            "texture_parameters": [],
            "scalar_parameters": [],
            "issues": [],
        }
