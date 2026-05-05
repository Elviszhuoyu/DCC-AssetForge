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
        created_materials = set(report.get("created_material_instances", []))
        if not imported_meshes:
            result["issues"].append("没有可绑定材质的 Static Mesh 导入结果")
            return result
        if not planned_materials:
            result["issues"].append("没有材质绑定计划")
            return result
        if not created_materials:
            result["unassigned_materials"] = self._planned_material_paths(planned_materials)
            result["issues"].append("没有可绑定的材质实例，已跳过材质槽绑定")
            return result

        for mesh_path in imported_meshes:
            static_mesh = self._load_asset(mesh_path)
            if not static_mesh:
                result["issues"].append("无法加载 Static Mesh：{0}".format(mesh_path))
                continue
            self._assign_materials(static_mesh, mesh_path, planned_materials, created_materials, result)

        result["assigned_count"] = len(result["assigned"])
        result["unassigned_materials"] = self._unassigned_materials(planned_materials, result["assigned"])
        if result["issues"] or result["unassigned_materials"]:
            result["status"] = "warning" if result["assigned"] else "skipped"
        else:
            result["status"] = "success" if result["assigned"] else "skipped"
        return result

    def _assign_materials(self, static_mesh, mesh_path, planned_materials, created_materials, result):
        for index, material in enumerate(planned_materials):
            material_path = material.get("target_asset_path", "")
            if created_materials and material_path not in created_materials:
                result["issues"].append("材质实例未创建：{0}".format(material_path))
                continue

            material_asset = self._load_asset(material_path)
            if not material_asset:
                result["issues"].append("无法加载材质实例：{0}".format(material_path))
                continue

            slot_index = self._slot_index(static_mesh, material.get("material_name", ""), index)
            try:
                static_mesh.set_material(slot_index, material_asset)
            except AttributeError:
                result["issues"].append("Static Mesh 不支持 set_material：{0}".format(mesh_path))
                continue

            result["assigned"].append(
                {
                    "static_mesh": mesh_path,
                    "slot_index": slot_index,
                    "material_name": material.get("material_name", ""),
                    "material_instance": material_path,
                }
            )

    def _planned_material_paths(self, planned_materials):
        return [material.get("target_asset_path", "") for material in planned_materials if material.get("target_asset_path", "")]

    def _unassigned_materials(self, planned_materials, assigned):
        assigned_paths = set(item.get("material_instance", "") for item in assigned)
        return [path for path in self._planned_material_paths(planned_materials) if path not in assigned_paths]

    def _slot_index(self, static_mesh, material_name, fallback_index):
        static_materials = self._static_materials(static_mesh)
        for index, slot in enumerate(static_materials):
            slot_name = self._slot_name(slot)
            if slot_name and slot_name == material_name:
                return index
        return fallback_index

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
        if library and hasattr(library, "load_asset"):
            asset = library.load_asset(asset_path)
            if asset:
                return asset
        if "." in asset_path and library and hasattr(library, "load_asset"):
            return library.load_asset(asset_path.split(".", 1)[0])
        return None
