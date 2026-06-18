"""Assign created Material Instances back to imported Static Mesh slots."""

from __future__ import absolute_import

from asset_forge.unreal.unreal_bridge import get_unreal


class UnrealMaterialSlotAssigner(object):
    """Bind planned Material Instances to Static Mesh material slots."""

    def __init__(self, unreal_module=None):
        self.unreal = unreal_module or get_unreal()

    def is_available(self):
        return self.unreal is not None

    def assign_from_report(self, report):
        material_plan = report.get("material_binding_plan", {})
        planned_materials = material_plan.get("materials", [])
        result = {
            "status": "skipped",
            "planned_count": len(planned_materials),
            "assigned_count": 0,
            "assigned": [],
            "unassigned_materials": [],
            "issues": [],
        }
        if not self.is_available():
            result["issues"].append("当前环境不可用 Unreal Python 模块，已跳过材质槽绑定")
            return result

        imported_meshes = report.get("imported_assets", [])
        if not imported_meshes:
            result["issues"].append("没有可绑定材质的 Static Mesh 导入结果")
            return result
        if not planned_materials:
            result["issues"].append("没有材质绑定计划")
            return result

        for mesh_path in imported_meshes:
            static_mesh = self._load_asset(mesh_path)
            if not static_mesh:
                result["issues"].append("无法加载 Static Mesh：{0}".format(mesh_path))
                continue
            self._assign_materials(static_mesh, mesh_path, planned_materials, result)

        result["assigned_count"] = len(result["assigned"])
        result["unassigned_materials"] = self._unassigned_materials(planned_materials, result["assigned"])
        if result["issues"] or result["unassigned_materials"]:
            result["status"] = "warning" if result["assigned"] else "skipped"
        else:
            result["status"] = "success" if result["assigned"] else "skipped"
        return result

    def _assign_materials(self, static_mesh, mesh_path, planned_materials, result):
        assigned_this_mesh = False
        for slot_index, material in self._slot_material_pairs(static_mesh, mesh_path, planned_materials, result):
            material_path = material.get("target_asset_path", "")
            material_asset = self._load_asset(material_path)
            if not material_asset:
                result["issues"].append("无法加载材质实例：{0}".format(material_path))
                continue

            try:
                static_mesh.set_material(slot_index, material_asset)
            except AttributeError:
                result["issues"].append("Static Mesh 不支持 set_material：{0}".format(mesh_path))
                continue

            verification_status = self._verify_assignment(static_mesh, slot_index, material_asset)
            if verification_status == "mismatch":
                result["issues"].append("Static Mesh slot readback mismatch: {0} slot {1}".format(mesh_path, slot_index))

            result["assigned"].append(
                {
                    "static_mesh": mesh_path,
                    "slot_index": slot_index,
                    "material_name": material.get("material_name", ""),
                    "material_instance": material_path,
                    "verification_status": verification_status,
                }
            )
            assigned_this_mesh = True
        if assigned_this_mesh:
            self._save_asset(mesh_path)

    def _slot_material_pairs(self, static_mesh, mesh_path, planned_materials, result):
        static_materials = self._static_materials(static_mesh)
        planned_by_name = {}
        for material in planned_materials:
            material_name = material.get("material_name", "")
            if material_name and material_name not in planned_by_name:
                planned_by_name[material_name] = material

        pairs = []
        for slot_index, slot in enumerate(static_materials):
            slot_name = self._slot_name(slot)
            material = planned_by_name.get(slot_name)
            if material:
                pairs.append((slot_index, material))
            else:
                result["issues"].append("Static Mesh material slot has no matching plan: {0}::{1}".format(mesh_path, slot_name))

        if pairs or static_materials:
            return pairs

        if len(planned_materials) == 1:
            return [(0, planned_materials[0])]

        result["issues"].append("Static Mesh returned no material slots; cannot safely bind multi-material plan: {0}".format(mesh_path))
        return []

    def _planned_material_paths(self, planned_materials):
        return [material.get("target_asset_path", "") for material in planned_materials if material.get("target_asset_path", "")]

    def _unassigned_materials(self, planned_materials, assigned):
        assigned_paths = set(item.get("material_instance", "") for item in assigned)
        return [path for path in self._planned_material_paths(planned_materials) if path not in assigned_paths]

    def _static_materials(self, static_mesh):
        if hasattr(static_mesh, "get_editor_property"):
            try:
                return static_mesh.get_editor_property("static_materials") or []
            except Exception:
                return []
        return getattr(static_mesh, "static_materials", []) or []

    def _slot_name(self, slot):
        if hasattr(slot, "get_editor_property"):
            try:
                return str(slot.get_editor_property("material_slot_name"))
            except Exception:
                return ""
        return str(getattr(slot, "material_slot_name", "") or "")

    def _load_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        self._scan_asset_registry_path(asset_path)
        if library and hasattr(library, "does_asset_exist"):
            try:
                if not any(bool(library.does_asset_exist(candidate)) for candidate in self._asset_path_candidates(asset_path)):
                    return None
            except Exception:
                pass
        if library and hasattr(library, "load_asset"):
            for candidate in self._asset_path_candidates(asset_path):
                asset = library.load_asset(candidate)
                if asset:
                    return asset
        return None

    def _asset_path_candidates(self, asset_path):
        if not asset_path:
            return []
        candidates = [asset_path]
        leaf = asset_path.rsplit("/", 1)[-1]
        if "." not in leaf:
            candidates.append("{0}.{1}".format(asset_path, leaf))
        elif "." in leaf:
            candidates.append(asset_path.rsplit(".", 1)[0])
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

    def _save_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if not library or not hasattr(library, "save_asset"):
            return
        package_path = asset_path.split(".", 1)[0]
        try:
            library.save_asset(package_path)
        except Exception:
            pass

    def _verify_assignment(self, static_mesh, slot_index, material_asset):
        readback = self._read_slot_material(static_mesh, slot_index)
        if readback is None:
            return "not_provided"
        if readback is material_asset:
            return "pass"
        readback_id = self._asset_identifier(readback)
        material_id = self._asset_identifier(material_asset)
        if readback_id and material_id and readback_id == material_id:
            return "pass"
        return "mismatch"

    def _read_slot_material(self, static_mesh, slot_index):
        if hasattr(static_mesh, "assigned_materials"):
            return getattr(static_mesh, "assigned_materials", {}).get(slot_index)
        if hasattr(static_mesh, "get_material"):
            try:
                return static_mesh.get_material(slot_index)
            except Exception:
                pass
        static_materials = self._static_materials(static_mesh)
        if 0 <= slot_index < len(static_materials):
            slot = static_materials[slot_index]
            for property_name in ("material_interface", "MaterialInterface"):
                value = self._slot_property(slot, property_name)
                if value is not None:
                    return value
        return None

    def _slot_property(self, slot, property_name):
        if hasattr(slot, "get_editor_property"):
            try:
                return slot.get_editor_property(property_name)
            except Exception:
                return None
        return getattr(slot, property_name, None)

    def _asset_identifier(self, asset):
        for method_name in ("get_path_name", "get_full_name"):
            method = getattr(asset, method_name, None)
            if method:
                try:
                    return str(method())
                except Exception:
                    pass
        return str(asset) if isinstance(asset, str) else ""
