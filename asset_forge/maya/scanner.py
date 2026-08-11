"""Core Maya scene scanner for DCC AssetForge 0.1."""

from __future__ import absolute_import

from asset_forge.maya.cmds_bridge import get_cmds
from asset_forge.maya.material_scanner import MayaMaterialScanner


def _safe_list(value):
    return value or []


class MayaAssetScanner(object):
    """Collect basic static prop data from Maya using maya.cmds."""

    def __init__(self, cmds_module=None):
        self.cmds = cmds_module or get_cmds()
        self.material_scanner = MayaMaterialScanner(self.cmds) if self.cmds is not None else None

    def is_available(self):
        return self.cmds is not None

    def get_current_selection(self):
        if not self.is_available():
            return []
        selection = _safe_list(self.cmds.ls(selection=True, long=True) or self.cmds.ls(selection=True))
        if selection:
            return selection
        return self._infer_single_mesh_assembly()

    def scan(self, asset_root):
        if not self.is_available():
            raise RuntimeError("maya.cmds is not available")

        identity = self._asset_identity_for_roots([asset_root])
        return self._scan_roots([asset_root], identity)

    def scan_many(self, asset_roots):
        if not self.is_available():
            raise RuntimeError("maya.cmds is not available")
        roots = list(asset_roots or [])
        if not roots:
            raise RuntimeError("没有选中资产")
        identity = self._asset_identity_for_roots(roots)
        return self._scan_roots(roots, identity)

    def rename_with_prefix(self, asset_roots, prefix="SM_"):
        renamed = []
        for root in list(asset_roots or []):
            if self.cmds.nodeType(root) != "transform":
                continue
            short_name = root.split("|")[-1]
            if short_name.startswith(prefix):
                renamed.append(root)
                continue
            new_path = self.cmds.rename(root, prefix + short_name)
            renamed.append(new_path)
        return renamed

    def rename_mesh_transforms_with_prefix(self, asset_roots, prefix="SM_"):
        renamed = []
        scan = self.scan_many(asset_roots)
        for transform in scan.get("transforms", []):
            if self.cmds.nodeType(transform) != "transform":
                continue
            short_name = transform.split("|")[-1]
            if short_name.startswith(prefix):
                continue
            new_path = self.cmds.rename(transform, prefix + short_name)
            renamed.append(new_path)
        return renamed

    def _scan_roots(self, asset_roots, identity):
        asset_name = identity.get("asset_name", asset_roots[0].split("|")[-1])
        meshes = self._unique_nodes([mesh for root in asset_roots for mesh in self._find_meshes(root)])
        transforms = self._mesh_transforms(meshes)
        descendants = self._unique_nodes([node for root in asset_roots for node in self._descendants(root)])
        uv_sets = self._collect_uv_sets(meshes)
        material_data = self.material_scanner.scan_meshes(meshes) if self.material_scanner else {"materials": [], "textures": []}
        collision_data = self._collision_nodes(asset_roots + descendants)

        return {
            "asset_root": asset_roots[0],
            "asset_roots": asset_roots,
            "asset_name": asset_name,
            "asset_name_source": identity.get("asset_name_source", "selected_root"),
            "asset_name_source_path": identity.get("asset_name_source_path", asset_roots[0]),
            "mesh_count": len(meshes),
            "meshes": meshes,
            "transform_count": len(transforms),
            "transforms": transforms,
            "transform_data": self._collect_transform_data(asset_roots + transforms),
            "triangles": self._count_triangles(meshes),
            "vertices": self._count_vertices(meshes),
            "faces": self._count_faces(meshes),
            "material_slots": self._count_material_slots(meshes),
            "materials": material_data.get("materials", []),
            "textures": material_data.get("textures", []),
            "uv_sets": uv_sets,
            "has_uv0": self._has_uv0(uv_sets),
            "has_lightmap_uv": self._has_lightmap_uv(uv_sets),
            "frozen_transform": self._all_transforms_frozen(asset_roots + transforms),
            "empty_meshes": self._empty_meshes(meshes),
            "collision_nodes": collision_data["valid"],
            "invalid_collision_nodes": collision_data["invalid"],
            "hidden_objects": self._hidden_objects(asset_roots, meshes, transforms),
            "history_nodes": self._history_nodes_many(asset_roots),
            "illegal_scale": self._has_illegal_scale(asset_roots + transforms),
        }

    def _find_meshes(self, asset_root):
        if self.cmds.nodeType(asset_root) == "mesh":
            return [asset_root]
        descendants = self._descendants(asset_root)
        return [node for node in descendants if self.cmds.nodeType(node) == "mesh"]

    def _infer_single_mesh_assembly(self):
        try:
            assemblies = _safe_list(self.cmds.ls(assemblies=True, long=True))
        except (RuntimeError, TypeError):
            return []
        candidates = []
        for root in assemblies:
            candidate = self._preferred_asset_root(root)
            if candidate:
                candidates.append(candidate)
        return candidates if len(candidates) == 1 else []

    def _preferred_asset_root(self, root):
        if not self._contains_mesh(root):
            return ""
        short_name = root.split("|")[-1]
        if short_name.startswith("SM_"):
            return root
        mesh_children = []
        for child in self._child_transforms(root):
            if self._contains_mesh(child):
                mesh_children.append(child)
        return mesh_children[0] if len(mesh_children) == 1 else root

    def _child_transforms(self, root):
        try:
            children = _safe_list(self.cmds.listRelatives(root, children=True, fullPath=True))
        except (RuntimeError, TypeError):
            return []
        result = []
        for child in children:
            try:
                if self.cmds.nodeType(child) == "transform":
                    result.append(child)
            except RuntimeError:
                continue
        return result

    def _contains_mesh(self, root):
        try:
            if self.cmds.nodeType(root) == "mesh":
                return True
        except RuntimeError:
            return False
        for node in self._descendants(root):
            try:
                if self.cmds.nodeType(node) == "mesh":
                    return True
            except RuntimeError:
                continue
        return False

    def _descendants(self, asset_root):
        try:
            return _safe_list(self.cmds.listRelatives(asset_root, allDescendents=True, fullPath=True))
        except RuntimeError:
            return []

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

    def _hidden_objects(self, asset_roots, meshes, transforms):
        hidden = []
        nodes = list(asset_roots or []) + meshes + transforms
        for node in nodes:
            if node in hidden:
                continue
            if not self._bool_attr(node, "visibility", True):
                hidden.append(node)
        return hidden

    def _collision_nodes(self, nodes):
        valid = []
        invalid = []
        valid_prefixes = ("UCX_", "UBX_", "USP_", "UCP_")
        loose_prefixes = ("COL_", "COLLISION_", "COLLIDER_")
        for node in nodes:
            name = node.split("|")[-1]
            upper_name = name.upper()
            if upper_name.startswith(valid_prefixes):
                valid.append(node)
            elif upper_name.startswith(loose_prefixes):
                invalid.append(node)
        return {"valid": valid, "invalid": invalid}

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

    def _history_nodes_many(self, asset_roots):
        result = []
        for root in asset_roots:
            for node in self._history_nodes(root):
                if node not in result:
                    result.append(node)
        return result

    def _unique_nodes(self, nodes):
        result = []
        for node in nodes:
            if node not in result:
                result.append(node)
        return result

    def _asset_name_for_roots(self, asset_roots):
        return self._asset_identity_for_roots(asset_roots).get("asset_name", "")

    def _asset_identity_for_roots(self, asset_roots):
        if len(asset_roots) == 1:
            return {
                "asset_name": asset_roots[0].split("|")[-1],
                "asset_name_source": "selected_root",
                "asset_name_source_path": asset_roots[0],
            }
        parents = [root.rsplit("|", 1)[0] for root in asset_roots if "|" in root]
        if parents and parents[0] and all(parent == parents[0] for parent in parents):
            return {
                "asset_name": parents[0].split("|")[-1],
                "asset_name_source": "common_parent",
                "asset_name_source_path": parents[0],
            }
        return {
            "asset_name": asset_roots[0].split("|")[-1],
            "asset_name_source": "first_selection",
            "asset_name_source_path": asset_roots[0],
        }

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
