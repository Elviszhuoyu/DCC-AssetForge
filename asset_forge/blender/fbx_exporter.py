# -*- coding: utf-8 -*-
"""Blender FBX exporter for Asset Forge Static Prop assets."""

from __future__ import absolute_import

import os

from asset_forge.shared.path_utils import normalize_path


DEFAULT_FBX_EXPORT_PRESET = {
    "use_selection": True,
    "object_types": {"MESH", "EMPTY"},
    "use_mesh_modifiers": True,
    "mesh_smooth_type": "FACE",
    "use_tspace": True,
    "bake_anim": False,
    "add_leaf_bones": False,
    "axis_forward": "-Z",
    "axis_up": "Y",
    "global_scale": 1.0,
    "apply_unit_scale": True,
    "apply_scale_options": "FBX_SCALE_UNITS",
}


class BlenderFbxExporter(object):
    def __init__(self, bpy_module=None):
        self.bpy = bpy_module or self._load_bpy()

    def is_available(self):
        return self.bpy is not None and getattr(getattr(self.bpy, "ops", None), "export_scene", None) is not None

    def export_selected(self, output_path, preset=None):
        if not self.is_available():
            raise RuntimeError("当前环境不可用 bpy.ops.export_scene.fbx")
        selected = list(getattr(getattr(self.bpy, "context", None), "selected_objects", []) or [])
        if not selected:
            raise RuntimeError("没有选中可导出的 Blender 对象")
        return self._export(output_path, preset or DEFAULT_FBX_EXPORT_PRESET, selected)

    def export_objects(self, object_names, output_path, preset=None, rename_map=None):
        if not self.is_available():
            raise RuntimeError("当前环境不可用 bpy.ops.export_scene.fbx")
        names = list(object_names or [])
        if not names:
            return self.export_selected(output_path, preset)
        selected = self._select_objects(names)
        restore_names = self._apply_temporary_names(selected, rename_map or {})
        try:
            return self._export(output_path, preset or DEFAULT_FBX_EXPORT_PRESET, selected)
        finally:
            self._restore_names(restore_names)

    def _export(self, output_path, preset, selected_objects=None):
        self._ensure_parent_dir(output_path)
        kwargs = dict(preset or DEFAULT_FBX_EXPORT_PRESET)
        kwargs["filepath"] = os.path.abspath(output_path)
        result = self._call_fbx_export(kwargs, selected_objects or [])
        if result not in (None, {"FINISHED"}):
            # Blender normally returns {'FINISHED'}; fake bpy tests may return None.
            if isinstance(result, set) and "FINISHED" in result:
                pass
            else:
                raise RuntimeError("Blender FBX export failed: {0}".format(result))
        return normalize_path(output_path)

    def _call_fbx_export(self, kwargs, selected_objects):
        context = getattr(self.bpy, "context", None)
        temp_override = getattr(context, "temp_override", None) if context is not None else None
        if callable(temp_override) and selected_objects:
            active = selected_objects[0]
            with temp_override(selected_objects=selected_objects, active_object=active, object=active):
                return self.bpy.ops.export_scene.fbx(**kwargs)
        return self.bpy.ops.export_scene.fbx(**kwargs)

    def _select_objects(self, names):
        wanted = set(names)
        data = getattr(self.bpy, "data", None)
        objects = list(getattr(data, "objects", []) or [])
        roots = [obj for obj in objects if getattr(obj, "name", "") in wanted]
        if not roots:
            raise RuntimeError("没有找到指定 Blender 对象：{0}".format(", ".join(names)))
        selected = self._objects_with_descendants(roots)
        selected_ids = set(id(obj) for obj in selected)
        for obj in objects:
            set_select = getattr(obj, "select_set", None)
            if callable(set_select):
                set_select(id(obj) in selected_ids)
        context = getattr(self.bpy, "context", None)
        if context is not None:
            active = selected[0]
            view_layer = getattr(context, "view_layer", None)
            objects_proxy = getattr(view_layer, "objects", None) if view_layer else None
            if objects_proxy is not None:
                objects_proxy.active = active
            if hasattr(context, "active_object"):
                context.active_object = active
        return selected

    def _objects_with_descendants(self, roots):
        result = []
        seen = set()
        stack = list(roots or [])
        while stack:
            obj = stack.pop(0)
            identity = id(obj)
            if identity in seen:
                continue
            seen.add(identity)
            result.append(obj)
            stack.extend(list(getattr(obj, "children", []) or []))
        return result
    def _apply_temporary_names(self, selected, rename_map):
        restore = []
        for obj in selected or []:
            original = getattr(obj, "name", "")
            target = rename_map.get(original)
            if not target or target == original:
                continue
            restore.append((obj, original))
            obj.name = target
        return restore

    def _restore_names(self, restore_names):
        for obj, original in reversed(restore_names or []):
            obj.name = original
    def _ensure_parent_dir(self, path):
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.exists(parent):
            os.makedirs(parent)

    def _load_bpy(self):
        try:
            import bpy  # type: ignore
        except ImportError:
            return None
        return bpy