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

        return {
            "asset_root": asset_root,
            "asset_name": asset_root.split("|")[-1],
            "mesh_count": len(meshes),
            "meshes": meshes,
            "transform_count": len(transforms),
            "triangles": self._count_triangles(meshes),
            "material_slots": self._count_material_slots(meshes),
            "uv_sets": self._collect_uv_sets(meshes),
            "has_uv0": self._has_uv0(meshes),
            "has_lightmap_uv": self._has_lightmap_uv(meshes),
            "frozen_transform": self._is_frozen_transform(asset_root),
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

    def _has_uv0(self, meshes):
        for uv_sets in self._collect_uv_sets(meshes).values():
            if uv_sets:
                return True
        return False

    def _has_lightmap_uv(self, meshes):
        for uv_sets in self._collect_uv_sets(meshes).values():
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

    def _near_tuple(self, value, expected, epsilon=0.0001):
        for index, item in enumerate(value):
            if abs(item - expected[index]) > epsilon:
                return False
        return True

