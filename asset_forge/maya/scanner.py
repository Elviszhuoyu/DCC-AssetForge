"""Core Maya scene scanner for Asset Forge v0.1."""

from __future__ import absolute_import

from asset_forge.maya.cmds_bridge import get_cmds


def _safe_list(value):
    return value or []


class MayaAssetScanner(object):
    """Collect basic static prop data from Maya using maya.cmds."""

    def __init__(self, cmds_module=None):
        self.cmds = cmds_module or get_cmds()

    def is_available(self):
        return self.cmds is not None

    def get_current_selection(self):
        if not self.is_available():
            return []
        return _safe_list(self.cmds.ls(selection=True, long=True))

    def scan(self, asset_root):
        if not self.is_available():
            raise RuntimeError("maya.cmds is not available")

        meshes = self._find_meshes(asset_root)
        transforms = self._mesh_transforms(meshes)
        uv_sets = self._collect_uv_sets(meshes)

        return {
            "asset_root": asset_root,
            "asset_name": asset_root.split("|")[-1],
            "mesh_count": len(meshes),
            "meshes": meshes,
            "transform_count": len(transforms),
            "transforms": transforms,
            "transform_data": self._collect_transform_data([asset_root] + transforms),
            "triangles": self._count_triangles(meshes),
            "vertices": self._count_vertices(meshes),
            "faces": self._count_faces(meshes),
            "material_slots": self._count_material_slots(meshes),
            "uv_sets": uv_sets,
            "has_uv0": self._has_uv0(uv_sets),
            "has_lightmap_uv": self._has_lightmap_uv(uv_sets),
            "frozen_transform": self._all_transforms_frozen([asset_root] + transforms),
            "empty_meshes": self._empty_meshes(meshes),
            "hidden_objects": self._hidden_objects(asset_root, meshes, transforms),
            "history_nodes": self._history_nodes(asset_root),
            "illegal_scale": self._has_illegal_scale([asset_root] + transforms),
        }

    def _find_meshes(self, asset_root):
        if self.cmds.nodeType(asset_root) == "mesh":
            return [asset_root]
        descendants = _safe_list(self.cmds.listRelatives(asset_root, allDescendents=True, fullPath=True))
        return [node for node in descendants if self.cmds.nodeType(node) == "mesh"]

    def _mesh_transforms(self, meshes):
        transforms = []
        for mesh in meshes:
            parents = _safe_list(self.cmds.listRelatives(mesh, parent=True, fullPath=True))
            for parent in parents:
                if parent not in transforms:
                    transforms.append(parent)
        return transforms

    def _count_triangles(self, meshes):
        count = 0
        for mesh in meshes:
            try:
                count += int(self.cmds.polyEvaluate(mesh, triangle=True) or 0)
            except RuntimeError:
                pass
        return count

    def _count_vertices(self, meshes):
        count = 0
        for mesh in meshes:
            try:
                count += int(self.cmds.polyEvaluate(mesh, vertex=True) or 0)
            except RuntimeError:
                pass
        return count

    def _count_faces(self, meshes):
        count = 0
        for mesh in meshes:
            try:
                count += int(self.cmds.polyEvaluate(mesh, face=True) or 0)
            except RuntimeError:
                pass
        return count

    def _count_material_slots(self, meshes):
        shading_groups = []
        for mesh in meshes:
            groups = _safe_list(self.cmds.listConnections(mesh, type="shadingEngine"))
            for group in groups:
                if group not in shading_groups:
                    shading_groups.append(group)
        return len(shading_groups)

    def _collect_uv_sets(self, meshes):
        result = {}
        for mesh in meshes:
            try:
                result[mesh] = _safe_list(self.cmds.polyUVSet(mesh, query=True, allUVSets=True))
            except RuntimeError:
                result[mesh] = []
        return result

    def _has_uv0(self, uv_sets_by_mesh):
        for uv_sets in uv_sets_by_mesh.values():
            if uv_sets:
                return True
        return False

    def _has_lightmap_uv(self, uv_sets_by_mesh):
        for uv_sets in uv_sets_by_mesh.values():
            if len(uv_sets) >= 2:
                return True
        return False

    def _is_frozen_transform(self, asset_root):
        if self.cmds.nodeType(asset_root) != "transform":
            return True

        translate = self.cmds.getAttr(asset_root + ".translate")[0]
        rotate = self.cmds.getAttr(asset_root + ".rotate")[0]
        scale = self.cmds.getAttr(asset_root + ".scale")[0]

        return (
            self._near_tuple(translate, (0.0, 0.0, 0.0))
            and self._near_tuple(rotate, (0.0, 0.0, 0.0))
            and self._near_tuple(scale, (1.0, 1.0, 1.0))
        )

    def _all_transforms_frozen(self, transforms):
        for transform in transforms:
            if not self._is_frozen_transform(transform):
                return False
        return True

    def _near_tuple(self, value, expected, epsilon=0.0001):
        for index, item in enumerate(value):
            if abs(item - expected[index]) > epsilon:
                return False
        return True

    def _collect_transform_data(self, transforms):
        result = {}
        for transform in transforms:
            if self.cmds.nodeType(transform) != "transform":
                continue
            result[transform] = {
                "translate": self._tuple_attr(transform, "translate"),
                "rotate": self._tuple_attr(transform, "rotate"),
                "scale": self._tuple_attr(transform, "scale"),
                "visible": self._bool_attr(transform, "visibility", True),
            }
        return result

    def _tuple_attr(self, node, attr_name):
        try:
            return tuple(self.cmds.getAttr(node + "." + attr_name)[0])
        except RuntimeError:
            return ()

    def _bool_attr(self, node, attr_name, default):
        try:
            return bool(self.cmds.getAttr(node + "." + attr_name))
        except RuntimeError:
            return default

    def _empty_meshes(self, meshes):
        empty = []
        for mesh in meshes:
            try:
                vertices = int(self.cmds.polyEvaluate(mesh, vertex=True) or 0)
                faces = int(self.cmds.polyEvaluate(mesh, face=True) or 0)
            except RuntimeError:
                vertices = 0
                faces = 0
            if vertices == 0 or faces == 0:
                empty.append(mesh)
        return empty

    def _hidden_objects(self, asset_root, meshes, transforms):
        hidden = []
        nodes = [asset_root] + meshes + transforms
        for node in nodes:
            if node in hidden:
                continue
            if not self._bool_attr(node, "visibility", True):
                hidden.append(node)
        return hidden

    def _history_nodes(self, asset_root):
        try:
            history = _safe_list(self.cmds.listHistory(asset_root, pruneDagObjects=True))
        except RuntimeError:
            return []

        result = []
        for node in history:
            node_type = self.cmds.nodeType(node)
            if node_type in ("mesh", "transform", "shadingEngine"):
                continue
            if node not in result:
                result.append(node)
        return result

    def _has_illegal_scale(self, transforms):
        for transform in transforms:
            if self.cmds.nodeType(transform) != "transform":
                continue
            scale = self._tuple_attr(transform, "scale")
            if len(scale) != 3:
                continue
            if scale[0] <= 0.0 or scale[1] <= 0.0 or scale[2] <= 0.0:
                return True
        return False
