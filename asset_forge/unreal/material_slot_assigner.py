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
        result = {
            "status": "skipped",
            "assigned": [],
            "issues": [],
        }
        if not self.is_available():
            result["issues"].append("unreal module is not available")
            return result

        imported_meshes = report.get("imported_assets", [])
        material_plan = report.get("material_binding_plan", {})
        created_materials = set(report.get("created_material_instances", []))
        if not imported_meshes:
            result["issues"].append("no imported Static Mesh assets")
            return result
        if not material_plan.get("materials"):
            result["issues"].append("no material binding plan")
            return result

        for mesh_path in imported_meshes:
            static_mesh = self._load_asset(mesh_path)
            if not static_mesh:
                result["issues"].append("failed to load Static Mesh: {0}".format(mesh_path))
                continue
            self._assign_materials(static_mesh, mesh_path, material_plan, created_materials, result)

        if result["issues"]:
            result["status"] = "warning" if result["assigned"] else "skipped"
        else:
            result["status"] = "success" if result["assigned"] else "skipped"
        return result

    def _assign_materials(self, static_mesh, mesh_path, material_plan, created_materials, result):
        for index, material in enumerate(material_plan.get("materials", [])):
            material_path = material.get("target_asset_path", "")
            if created_materials and material_path not in created_materials:
                result["issues"].append("material instance was not created: {0}".format(material_path))
                continue

            material_asset = self._load_asset(material_path)
            if not material_asset:
                result["issues"].append("failed to load Material Instance: {0}".format(material_path))
                continue

            slot_index = self._slot_index(static_mesh, material.get("material_name", ""), index)
            try:
                static_mesh.set_material(slot_index, material_asset)
            except AttributeError:
                result["issues"].append("Static Mesh does not expose set_material: {0}".format(mesh_path))
                continue

            result["assigned"].append(
                {
                    "static_mesh": mesh_path,
                    "slot_index": slot_index,
                    "material_name": material.get("material_name", ""),
                    "material_instance": material_path,
                }
            )

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
