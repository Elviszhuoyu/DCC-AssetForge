"""Create Unreal Material Instances from Asset Forge binding plans."""

from __future__ import absolute_import

from asset_forge.unreal.property_utils import get_unreal_property, set_unreal_property
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
        processed_paths = set()
        for material_plan in material_binding_plan.get("materials", []):
            target_path = material_plan.get("target_asset_path", "")
            if target_path and target_path in processed_paths:
                self.last_creation_report["actions"].append(
                    self._action(target_path, material_plan.get("existing_material_strategy", ""), "reused_in_plan", "Reused by another material slot in the same plan.")
                )
                continue
            created_path = self._create_material_instance(
                material_plan,
                material_binding_plan.get("existing_material_strategy", self.existing_strategy),
            )
            if target_path:
                processed_paths.add(target_path)
            if created_path:
                created.append(created_path)
        self._finish_creation_report()
        self._finish_parameter_report()
        return created

    def _create_material_instance(self, material_plan, existing_strategy):
        unreal = self.unreal
        parent_material = self._load_asset(material_plan.get("parent_material", ""))
        if not parent_material:
            message = self._missing_parent_message(material_plan)
            self.last_creation_report["issues"].append(message)
            raise RuntimeError(message)

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

        self._set_material_instance_parent(material_instance, parent_material)
        self._apply_texture_parameters(material_instance, material_plan.get("texture_parameters", {}), material_plan)
        self._apply_scalar_parameters(material_instance, material_plan.get("scalar_parameters", {}), material_plan)
        self._apply_vector_parameters(material_instance, material_plan.get("vector_parameters", {}), material_plan)
        self._apply_static_switch_parameters(material_instance, material_plan.get("static_switch_parameters", {}), material_plan)
        self._update_material_instance(material_instance)
        self._save_asset(target_path)
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
        if not any(bool(library.does_asset_exist(candidate)) for candidate in self._asset_path_candidates(asset_path)):
            return None
        return self._load_asset(asset_path)

    def _delete_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "delete_asset"):
            return bool(library.delete_asset(asset_path))
        return False

    def _apply_texture_parameters(self, material_instance, texture_parameters, material_plan=None):
        material_plan = material_plan or {}
        editing = getattr(self.unreal, "MaterialEditingLibrary", None)
        setter = getattr(editing, "set_material_instance_texture_parameter_value", None) if editing is not None else None
        if setter is None:
            reason = "MaterialEditingLibrary unavailable" if editing is None else "texture parameter setter unavailable"
            for name, texture_path in texture_parameters.items():
                self._record_parameter("texture_parameters", name, False, material_plan, asset_path=texture_path, reason=reason)
            return
        for name, texture_path in texture_parameters.items():
            texture_asset = self._load_asset(texture_path)
            if not texture_asset:
                self._record_parameter("texture_parameters", name, False, material_plan, asset_path=texture_path, reason="texture asset load failed")
                self.last_parameter_report["issues"].append("无法加载贴图参数 {0}：{1}".format(name, texture_path))
                continue
            applied = setter(material_instance, name, texture_asset)
            confirmed = self._setter_confirmed(applied) or self._parameter_applied(material_instance, "texture_parameters", name, texture_path)
            self._record_parameter(
                "texture_parameters",
                name,
                confirmed,
                material_plan,
                asset_path=texture_path,
                reason="" if confirmed else "UE texture parameter setter did not confirm the parameter slot",
            )

    def _apply_scalar_parameters(self, material_instance, scalar_parameters, material_plan=None):
        material_plan = material_plan or {}
        editing = getattr(self.unreal, "MaterialEditingLibrary", None)
        setter = getattr(editing, "set_material_instance_scalar_parameter_value", None) if editing is not None else None
        if setter is None:
            reason = "MaterialEditingLibrary unavailable" if editing is None else "scalar parameter setter unavailable"
            for name, value in scalar_parameters.items():
                self._record_parameter("scalar_parameters", name, False, material_plan, value=value, reason=reason)
            return
        for name, value in scalar_parameters.items():
            applied = setter(material_instance, name, value)
            confirmed = self._setter_confirmed(applied) or self._parameter_applied(material_instance, "scalar_parameters", name, value)
            self._record_parameter(
                "scalar_parameters",
                name,
                confirmed,
                material_plan,
                value=value,
                reason="" if confirmed else "UE scalar parameter setter did not confirm the parameter slot",
            )

    def _apply_vector_parameters(self, material_instance, vector_parameters, material_plan=None):
        material_plan = material_plan or {}
        editing = getattr(self.unreal, "MaterialEditingLibrary", None)
        setter = getattr(editing, "set_material_instance_vector_parameter_value", None) if editing is not None else None
        if setter is None:
            reason = "MaterialEditingLibrary unavailable" if editing is None else "vector parameter setter unavailable"
            if vector_parameters:
                self.last_parameter_report["issues"].append("当前 UE Python API 缺少 vector parameter setter")
            for name, value in vector_parameters.items():
                self._record_parameter("vector_parameters", name, False, material_plan, value=value, reason=reason)
            return
        for name, value in vector_parameters.items():
            converted = self._linear_color(value)
            if converted is None:
                self._record_parameter("vector_parameters", name, False, material_plan, value=value, reason="invalid LinearColor value")
                continue
            applied = setter(material_instance, name, converted)
            confirmed = self._setter_confirmed(applied) or self._parameter_applied(material_instance, "vector_parameters", name, value)
            self._record_parameter(
                "vector_parameters",
                name,
                confirmed,
                material_plan,
                value=value,
                reason="" if confirmed else "UE vector parameter setter did not confirm the parameter slot",
            )

    def _apply_static_switch_parameters(self, material_instance, static_switch_parameters, material_plan=None):
        material_plan = material_plan or {}
        editing = getattr(self.unreal, "MaterialEditingLibrary", None)
        setter = getattr(editing, "set_material_instance_static_switch_parameter_value", None) if editing is not None else None
        scalar_setter = getattr(editing, "set_material_instance_scalar_parameter_value", None) if editing is not None else None
        if setter is None:
            reason = "MaterialEditingLibrary unavailable" if editing is None else "static switch parameter setter unavailable"
            if static_switch_parameters:
                self.last_parameter_report["issues"].append("当前 UE Python API 缺少 static switch parameter setter")
            for name, value in static_switch_parameters.items():
                self._record_parameter("static_switch_parameters", name, False, material_plan, value=bool(value), reason=reason)
            return
        for name, value in static_switch_parameters.items():
            scalar_value = 1.0 if bool(value) else 0.0
            if scalar_setter is not None:
                scalar_applied = scalar_setter(material_instance, name, scalar_value)
                scalar_confirmed = self._setter_confirmed(scalar_applied) or self._parameter_applied(material_instance, "scalar_parameters", name, scalar_value)
                self._record_parameter(
                    "scalar_parameters",
                    name,
                    scalar_confirmed,
                    material_plan,
                    value=scalar_value,
                    reason="" if scalar_confirmed else "UE scalar mirror for switch parameter did not confirm the parameter slot",
                )
            if setter is not None:
                applied = setter(material_instance, name, bool(value))
                confirmed = self._setter_confirmed(applied) or self._parameter_applied(material_instance, "static_switch_parameters", name, bool(value))
                self._record_parameter(
                    "static_switch_parameters",
                    name,
                    confirmed,
                    material_plan,
                    value=bool(value),
                    reason="" if confirmed else "UE static switch parameter setter did not confirm the parameter slot",
                )

    def _setter_confirmed(self, result):
        return result is True

    def _parameter_applied(self, material_instance, category, name, expected):
        if self._parameter_getter_confirms(material_instance, category, name):
            return True
        property_names = {
            "texture_parameters": ["TextureParameterValues", "texture_parameter_values"],
            "scalar_parameters": ["ScalarParameterValues", "scalar_parameter_values"],
            "vector_parameters": ["VectorParameterValues", "vector_parameter_values"],
            "static_switch_parameters": ["StaticParameters", "static_parameters"],
        }.get(category, "")
        if not property_names:
            return False
        for property_name in property_names:
            value = get_unreal_property(material_instance, property_name, "")
            text = str(value)
            if 'Name="{0}"'.format(name) not in text and "Name={0}".format(name) not in text:
                continue
            if category == "texture_parameters" and expected:
                return str(expected).split(".", 1)[0] in text
            return True
        return False

    def _parameter_getter_confirms(self, material_instance, category, name):
        editing = getattr(self.unreal, "MaterialEditingLibrary", None)
        getter_name = {
            "texture_parameters": "get_material_instance_texture_parameter_value",
            "scalar_parameters": "get_material_instance_scalar_parameter_value",
            "vector_parameters": "get_material_instance_vector_parameter_value",
            "static_switch_parameters": "get_material_instance_static_switch_parameter_value",
        }.get(category, "")
        getter = getattr(editing, getter_name, None) if editing is not None else None
        if getter is None:
            return False
        try:
            return getter(material_instance, name) is not None
        except Exception:
            return False

    def _load_asset(self, asset_path):
        self._scan_asset_registry_path(asset_path)
        if hasattr(self.unreal, "EditorAssetLibrary"):
            for candidate in self._asset_path_candidates(asset_path):
                asset = self.unreal.EditorAssetLibrary.load_asset(candidate)
                if asset:
                    return asset
            return None
        return asset_path

    def _asset_path_candidates(self, asset_path):
        if not asset_path:
            return []
        candidates = [asset_path]
        leaf = asset_path.rsplit("/", 1)[-1]
        if "." not in leaf:
            candidates.append("{0}.{1}".format(asset_path, leaf))
        return candidates

    def _scan_asset_registry_path(self, asset_path):
        if not asset_path:
            return
        registry_helpers = getattr(self.unreal, "AssetRegistryHelpers", None)
        if registry_helpers is None or not hasattr(registry_helpers, "get_asset_registry"):
            return
        folder = asset_path.rsplit("/", 1)[0] if "/" in asset_path else asset_path
        try:
            registry = registry_helpers.get_asset_registry()
            if hasattr(registry, "scan_paths_synchronous"):
                registry.scan_paths_synchronous([folder], True)
            if hasattr(registry, "wait_for_completion"):
                registry.wait_for_completion()
        except Exception:
            return

    def _set_material_instance_parent(self, material_instance, parent_material):
        editing = getattr(self.unreal, "MaterialEditingLibrary", None)
        setter = getattr(editing, "set_material_instance_parent", None) if editing is not None else None
        if setter:
            result = setter(material_instance, parent_material)
            if result is not False:
                return
        set_unreal_property(material_instance, "parent", parent_material)

    def _linear_color(self, value):
        if hasattr(self.unreal, "LinearColor"):
            if isinstance(value, (list, tuple)) and len(value) >= 3:
                alpha = value[3] if len(value) > 3 else 1.0
                return self.unreal.LinearColor(float(value[0]), float(value[1]), float(value[2]), float(alpha))
            if isinstance(value, dict):
                return self.unreal.LinearColor(
                    float(value.get("r", 0.0)),
                    float(value.get("g", 0.0)),
                    float(value.get("b", 0.0)),
                    float(value.get("a", 1.0)),
                )
            return value
        return value

    def _update_material_instance(self, material_instance):
        editing = getattr(self.unreal, "MaterialEditingLibrary", None)
        if editing is not None and hasattr(editing, "update_material_instance"):
            editing.update_material_instance(material_instance)

    def _save_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "save_asset"):
            library.save_asset(asset_path)

    def _finish_creation_report(self):
        report = self.last_creation_report
        if report.get("issues"):
            report["status"] = "warning"
        elif report.get("actions"):
            report["status"] = "success"
        else:
            report["status"] = "skipped"

    def _finish_parameter_report(self):
        report = self.last_parameter_report
        applied_count = (
            len(report.get("texture_parameters", []))
            + len(report.get("scalar_parameters", []))
            + len(report.get("vector_parameters", []))
            + len(report.get("static_switch_parameters", []))
        )
        if report.get("issues"):
            report["status"] = "warning" if applied_count else "skipped"
        else:
            report["status"] = "success" if applied_count else "skipped"
        report["applied_count"] = len(
            [
                item
                for group in ("texture_parameters", "scalar_parameters", "vector_parameters", "static_switch_parameters")
                for item in report.get(group, [])
                if item.get("applied")
            ]
        )
        report["failed_count"] = len(
            [
                item
                for group in ("texture_parameters", "scalar_parameters", "vector_parameters", "static_switch_parameters")
                for item in report.get(group, [])
                if item.get("applied") is False
            ]
        )
        if report["failed_count"]:
            report["status"] = "warning"

    def _record_parameter(self, group, name, applied, material_plan, asset_path=None, value=None, reason=""):
        entry = {
            "name": name,
            "applied": bool(applied),
            "material_instance_path": material_plan.get("target_asset_path", ""),
            "parent_material": material_plan.get("parent_material", ""),
        }
        if asset_path is not None:
            entry["asset_path"] = asset_path
            if group == "texture_parameters":
                entry["texture_asset_path"] = asset_path
        if value is not None:
            entry["value"] = value
        if reason:
            entry["reason"] = reason
        self.last_parameter_report[group].append(entry)
        if not applied:
            self.last_parameter_report["issues"].append(
                "材质实例参数未应用：{0}.{1}，原因：{2}".format(group, name, reason or "unknown")
            )

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
            "vector_parameters": [],
            "static_switch_parameters": [],
            "issues": [],
        }

    def _missing_parent_message(self, material_plan):
        return (
            "缺少母材质：{0}；目标材质实例：{1}。"
            "请先确认 AssetForge 插件内容已挂载，并在 UE 5.6 中执行默认材质 Bootstrap 后重试。"
        ).format(material_plan.get("parent_material", ""), material_plan.get("target_asset_path", ""))
