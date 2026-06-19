# -*- coding: utf-8 -*-
"""Read-only Blender scene scanning for Asset Forge Static Prop provider."""

from __future__ import absolute_import


def _safe_list(value):
    return list(value or [])


class BlenderStaticPropScanner(object):
    def __init__(self, bpy_module=None):
        self.bpy = bpy_module or self._load_bpy()

    def is_available(self):
        return self.bpy is not None

    def get_current_selection(self):
        if not self.is_available():
            return []
        context = getattr(self.bpy, "context", None)
        return [item.name for item in _safe_list(getattr(context, "selected_objects", []))]

    def scan_selection(self):
        if not self.is_available():
            raise RuntimeError("bpy is not available")
        context = getattr(self.bpy, "context", None)
        selected = _safe_list(getattr(context, "selected_objects", []))
        if not selected:
            raise RuntimeError("没有选中资产")
        return self.scan_objects(selected)

    def scan_by_names(self, names):
        if not self.is_available():
            raise RuntimeError("bpy is not available")
        objects = []
        by_name = dict((item.name, item) for item in _safe_list(getattr(getattr(self.bpy, "data", None), "objects", [])))
        for name in list(names or []):
            if name in by_name:
                objects.append(by_name[name])
        if not objects:
            raise RuntimeError("没有找到指定 Blender 对象")
        return self.scan_objects(objects)

    def scan_objects(self, roots):
        roots = _safe_list(roots)
        meshes = self._unique_objects([mesh for root in roots for mesh in self._find_mesh_objects(root)])
        asset_name = self._asset_name(roots)
        materials = self._materials(meshes)
        uv_sets = self._uv_sets(meshes)
        return {
            "asset_root": roots[0].name if roots else "",
            "asset_roots": [item.name for item in roots],
            "asset_name": asset_name,
            "asset_name_source": "selected_root" if len(roots) == 1 else "first_selection",
            "asset_name_source_path": roots[0].name if roots else "",
            "mesh_count": len(meshes),
            "meshes": [item.name for item in meshes],
            "transform_count": len(roots),
            "transforms": [item.name for item in roots],
            "transform_data": self._transform_data(roots),
            "triangles": sum(self._triangle_count(item) for item in meshes),
            "vertices": sum(self._vertex_count(item) for item in meshes),
            "faces": sum(self._face_count(item) for item in meshes),
            "material_slots": len(self._material_slots(meshes, materials)),
            "material_slot_details": self._material_slots(meshes, materials),
            "materials": materials,
            "textures": [],
            "uv_sets": uv_sets,
            "has_uv0": any(bool(value) for value in uv_sets.values()),
            "has_lightmap_uv": any(len(value) >= 2 for value in uv_sets.values()),
            "frozen_transform": self._all_transforms_frozen(roots),
            "empty_meshes": [item.name for item in meshes if self._vertex_count(item) == 0 or self._face_count(item) == 0],
            "collision_nodes": self._collision_nodes(roots + meshes)["valid"],
            "invalid_collision_nodes": self._collision_nodes(roots + meshes)["invalid"],
            "hidden_objects": [item.name for item in roots + meshes if self._is_hidden(item)],
            "history_nodes": [],
            "illegal_scale": self._has_illegal_scale(roots),
            "source_dcc": "blender",
            "scene_path": getattr(getattr(self.bpy, "data", None), "filepath", "") or "",
        }

    def _load_bpy(self):
        try:
            import bpy  # type: ignore
        except ImportError:
            return None
        return bpy

    def _find_mesh_objects(self, root):
        result = []
        if getattr(root, "type", "") == "MESH":
            result.append(root)
        for child in _safe_list(getattr(root, "children", [])):
            result.extend(self._find_mesh_objects(child))
        return result

    def _asset_name(self, roots):
        if not roots:
            return ""
        return getattr(roots[0], "name", "Asset") or "Asset"

    def _materials(self, meshes):
        result = []
        seen = set()
        for mesh in meshes:
            for slot in _safe_list(getattr(mesh, "material_slots", [])):
                material = getattr(slot, "material", None)
                name = getattr(material, "name", "") if material else getattr(slot, "name", "")
                if not name or name in seen:
                    continue
                seen.add(name)
                result.append({"name": name, "material_name": name, "source_dcc": "blender"})
        return result

    def _material_slots(self, meshes, materials):
        slots = []
        seen = set()
        for mesh in meshes:
            for slot in _safe_list(getattr(mesh, "material_slots", [])):
                material = getattr(slot, "material", None)
                name = getattr(material, "name", "") if material else getattr(slot, "name", "")
                if not name or name in seen:
                    continue
                seen.add(name)
                slots.append({"index": len(slots), "name": name, "mesh": getattr(mesh, "name", "")})
        if slots:
            return slots
        return [{"index": index, "name": item.get("name", "")} for index, item in enumerate(materials or [])]

    def _uv_sets(self, meshes):
        result = {}
        for mesh in meshes:
            data = getattr(mesh, "data", None)
            layers = _safe_list(getattr(data, "uv_layers", []))
            result[getattr(mesh, "name", "")] = [getattr(layer, "name", "UVMap") for layer in layers]
        return result

    def _triangle_count(self, obj):
        data = getattr(obj, "data", None)
        loop_triangles = getattr(data, "loop_triangles", None)
        if loop_triangles is not None:
            return len(loop_triangles)
        count = 0
        for poly in _safe_list(getattr(data, "polygons", [])):
            vertices = _safe_list(getattr(poly, "vertices", []))
            count += max(1, len(vertices) - 2) if vertices else 1
        return count

    def _vertex_count(self, obj):
        return len(_safe_list(getattr(getattr(obj, "data", None), "vertices", [])))

    def _face_count(self, obj):
        return len(_safe_list(getattr(getattr(obj, "data", None), "polygons", [])))

    def _transform_data(self, objects):
        result = {}
        for obj in objects:
            result[getattr(obj, "name", "")] = {
                "translate": tuple(getattr(obj, "location", (0.0, 0.0, 0.0))),
                "rotate": tuple(getattr(obj, "rotation_euler", (0.0, 0.0, 0.0))),
                "scale": tuple(getattr(obj, "scale", (1.0, 1.0, 1.0))),
                "visible": not self._is_hidden(obj),
            }
        return result

    def _all_transforms_frozen(self, objects):
        for obj in objects:
            if not self._near_tuple(getattr(obj, "location", (0.0, 0.0, 0.0)), (0.0, 0.0, 0.0)):
                return False
            if not self._near_tuple(getattr(obj, "rotation_euler", (0.0, 0.0, 0.0)), (0.0, 0.0, 0.0)):
                return False
            if not self._near_tuple(getattr(obj, "scale", (1.0, 1.0, 1.0)), (1.0, 1.0, 1.0)):
                return False
        return True

    def _near_tuple(self, value, expected, epsilon=0.0001):
        value = tuple(value or ())
        if len(value) != len(expected):
            return False
        return all(abs(value[index] - expected[index]) <= epsilon for index in range(len(expected)))

    def _has_illegal_scale(self, objects):
        for obj in objects:
            scale = tuple(getattr(obj, "scale", (1.0, 1.0, 1.0)))
            if len(scale) == 3 and (scale[0] <= 0.0 or scale[1] <= 0.0 or scale[2] <= 0.0):
                return True
        return False

    def _is_hidden(self, obj):
        hide_get = getattr(obj, "hide_get", None)
        if callable(hide_get):
            try:
                return bool(hide_get())
            except TypeError:
                pass
        return bool(getattr(obj, "hide_viewport", False))

    def _collision_nodes(self, nodes):
        valid = []
        invalid = []
        valid_prefixes = ("UCX_", "UBX_", "USP_", "UCP_")
        loose_prefixes = ("COL_", "COLLISION_", "COLLIDER_")
        for node in nodes:
            name = getattr(node, "name", "")
            upper_name = name.upper()
            if upper_name.startswith(valid_prefixes):
                valid.append(name)
            elif upper_name.startswith(loose_prefixes):
                invalid.append(name)
        return {"valid": valid, "invalid": invalid}

    def _unique_objects(self, objects):
        result = []
        seen = set()
        for obj in objects:
            identity = id(obj)
            if identity in seen:
                continue
            seen.add(identity)
            result.append(obj)
        return result