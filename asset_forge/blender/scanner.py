# -*- coding: utf-8 -*-
"""Read-only Blender scene scanning for Asset Forge Static Prop provider."""

from __future__ import absolute_import

import os
import re


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
        return [item.name for item in self._current_objects(context)]

    def scan_selection(self):
        if not self.is_available():
            raise RuntimeError("bpy is not available")
        context = getattr(self.bpy, "context", None)
        selected = self._current_objects(context)
        roots = self._effective_roots(selected)
        if not roots:
            raise RuntimeError("没有选中资产")
        return self.scan_objects(roots)

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
        return self.scan_objects(self._effective_roots(objects))

    def scan_objects(self, roots):
        roots = _safe_list(roots)
        meshes = self._unique_objects([mesh for root in roots for mesh in self._find_mesh_objects(root)])
        identity = self._asset_identity(roots)
        asset_name = identity["asset_name"]
        materials = self._materials(meshes)
        uv_sets = self._uv_sets(meshes)
        return {
            "asset_root": roots[0].name if roots else "",
            "asset_roots": [item.name for item in roots],
            "asset_name": asset_name,
            "source_asset_name": identity["source_asset_name"],
            "asset_name_source": identity["asset_name_source"],
            "asset_name_source_name": identity["asset_name_source_name"],
            "asset_name_source_path": roots[0].name if roots else "",
            "asset_name_candidates": identity["asset_name_candidates"],
            "mesh_count": len(meshes),
            "meshes": [item.name for item in meshes],
            "transform_count": len(roots),
            "transforms": [item.name for item in roots],
            "transform_data": self._transform_data(roots),
            "mesh_transform_data": self._transform_data(meshes),
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
            "frozen_transform": self._all_transforms_frozen(meshes),
            "container_frozen_transform": self._all_transforms_frozen(roots),
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

    def _current_objects(self, context):
        selected = _safe_list(getattr(context, "selected_objects", []))
        if selected:
            return selected
        active = self._active_object(context)
        return [active] if active is not None else []

    def _active_object(self, context):
        if context is None:
            return None
        view_layer = getattr(context, "view_layer", None)
        active_proxy = getattr(view_layer, "objects", None) if view_layer else None
        active = getattr(active_proxy, "active", None) if active_proxy else None
        return active or getattr(context, "active_object", None)

    def _effective_roots(self, objects):
        roots = []
        seen = set()
        for obj in _safe_list(objects):
            for root in self._asset_roots_from_object(obj):
                identity = id(root)
                if identity in seen:
                    continue
                seen.add(identity)
                roots.append(root)
        return roots

    def _asset_roots_from_object(self, obj):
        if obj is None:
            return []
        if self._is_organization_root(obj):
            children = [child for child in _safe_list(getattr(obj, "children", [])) if self._find_mesh_objects(child)]
            return children or []
        current = obj
        visited = set()
        while getattr(current, "parent", None) is not None and id(current) not in visited:
            visited.add(id(current))
            parent = current.parent
            if self._is_organization_root(parent):
                return [current]
            current = parent
        return [current]

    def _is_organization_root(self, obj):
        name = str(getattr(obj, "name", "") or "").lower()
        if name in ("collection", "scene", "root"):
            return True
        return name.startswith("group") and name[5:].isdigit()

    def _find_mesh_objects(self, root):
        result = []
        if getattr(root, "type", "") == "MESH":
            result.append(root)
        for child in _safe_list(getattr(root, "children", [])):
            result.extend(self._find_mesh_objects(child))
        return result

    def _asset_identity(self, roots):
        source_name = getattr(roots[0], "name", "Asset") if roots else "Asset"
        clean_name = self._clean_asset_name(source_name)
        asset_name = clean_name if clean_name.startswith("SM_") else "SM_" + clean_name
        return {
            "asset_name": asset_name,
            "source_asset_name": source_name,
            "asset_name_source": "selected_root_auto_prefix" if len(roots) == 1 else "first_selection_auto_prefix",
            "asset_name_source_name": source_name,
            "asset_name_candidates": [asset_name, clean_name, source_name],
        }

    def _clean_asset_name(self, name):
        clean = re.sub(r"[^0-9A-Za-z_]+", "_", name or "Asset").strip("_")
        return clean or "Asset"

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
                result.append(
                    {
                        "name": name,
                        "material_name": name,
                        "source_dcc": "blender",
                        "base_color": self._material_base_color(material),
                        "textures": self._material_textures(material),
                    }
                )
        return result

    def _material_base_color(self, material):
        color = getattr(material, "diffuse_color", None)
        if color is None:
            return [0.72, 0.72, 0.72, 1.0]
        values = list(color)
        if len(values) < 3:
            return [0.72, 0.72, 0.72, 1.0]
        while len(values) < 4:
            values.append(1.0)
        return [float(max(0.0, min(1.0, item))) for item in values[:4]]

    def _material_textures(self, material):
        if material is None or not getattr(material, "use_nodes", False):
            return []
        node_tree = getattr(material, "node_tree", None)
        textures = []
        seen = set()
        for node in _safe_list(getattr(node_tree, "nodes", [])):
            if getattr(node, "type", "") != "TEX_IMAGE":
                continue
            image = getattr(node, "image", None)
            path = self._image_path(image)
            if not path:
                continue
            usage = self._texture_usage(node, path)
            if not usage:
                continue
            key = (usage, path)
            if key in seen:
                continue
            seen.add(key)
            textures.append(self._texture_entry(node, image, path, usage))
        return textures

    def _image_path(self, image):
        filepath = getattr(image, "filepath", "") if image is not None else ""
        if not filepath:
            return ""
        bpy_path = getattr(self.bpy, "path", None) if self.bpy is not None else None
        abspath = getattr(bpy_path, "abspath", None) if bpy_path is not None else None
        if callable(abspath):
            try:
                filepath = abspath(filepath)
            except TypeError:
                filepath = abspath(filepath, library=getattr(image, "library", None))
        elif filepath.startswith("//"):
            scene_path = getattr(getattr(self.bpy, "data", None), "filepath", "") if self.bpy is not None else ""
            filepath = os.path.join(os.path.dirname(scene_path), filepath[2:]) if scene_path else filepath[2:]
        return os.path.abspath(filepath)

    def _texture_usage(self, node, path):
        link_usage = self._texture_usage_from_links(node)
        file_usage = self._texture_usage_from_name(path)
        return link_usage or file_usage

    def _texture_usage_from_links(self, node):
        for output in _safe_list(getattr(node, "outputs", [])):
            for link in _safe_list(getattr(output, "links", [])):
                usage = self._usage_from_link_target(link)
                if usage:
                    return usage
        return ""

    def _usage_from_link_target(self, link):
        target_node = getattr(link, "to_node", None)
        target_socket = getattr(link, "to_socket", None)
        node_type = getattr(target_node, "type", "")
        socket_name = str(getattr(target_socket, "name", "") or "").lower()
        if node_type == "BSDF_PRINCIPLED":
            if socket_name == "base color":
                return "base_color"
            if socket_name == "normal":
                return "normal"
        if node_type == "NORMAL_MAP":
            return "normal"
        return ""

    def _texture_usage_from_name(self, path):
        stem = os.path.splitext(os.path.basename(path or ""))[0].lower()
        compact = re.sub(r"[^a-z0-9]+", "", stem)
        tokens = [item for item in re.split(r"[^a-z0-9]+", stem) if item]
        last_token = tokens[-1] if tokens else ""
        if compact.endswith(("normal", "normalmap")) or last_token == "n":
            return "normal"
        if compact.endswith(("arm", "orm", "occlusionroughnessmetallic")):
            return "packed_arm"
        if compact.endswith(("basecolor", "basecolour", "bc", "color", "colour", "albedo", "diffuse")) or last_token == "b":
            return "base_color"
        return ""

    def _texture_entry(self, node, image, path, usage):
        entry = {
            "node": getattr(node, "name", ""),
            "path": path.replace("\\", "/"),
            "source_path": path.replace("\\", "/"),
            "package_path": "",
            "copied": False,
            "source_type": "blender_image_node",
            "source_label": "Blender Image Texture 节点",
            "usage": usage,
            "parameter": {"base_color": "BaseColor", "normal": "Normal", "packed_arm": "ARM"}.get(usage, ""),
            "srgb": usage == "base_color",
            "compression": {"base_color": "default", "normal": "normalmap", "packed_arm": "masks"}.get(usage, "default"),
            "match_mode": "blender_node_link_or_filename",
            "image_name": getattr(image, "name", "") if image is not None else "",
            "colorspace": self._image_colorspace(image),
        }
        if usage == "packed_arm":
            entry["channels"] = {"r": "ao", "g": "roughness", "b": "metallic"}
        return entry

    def _image_colorspace(self, image):
        settings = getattr(image, "colorspace_settings", None) if image is not None else None
        return getattr(settings, "name", "") if settings is not None else ""

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
