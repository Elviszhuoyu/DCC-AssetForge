# -*- coding: utf-8 -*-
"""Core Maya scene scanner for DCC AssetForge 0.1."""

from __future__ import absolute_import, unicode_literals

from collections import Counter

from asset_forge.maya.cmds_bridge import get_cmds
from asset_forge.maya.material_scanner import MayaMaterialScanner, valid_texture_count
from asset_forge.shared.rule_validator import summarize_mesh_uvs
from asset_forge.shared.mesh_geometry import inspect_mesh_triangles


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

    def scene_textures(self, asset_roots):
        if not self.material_scanner:
            return []
        meshes = self._unique_nodes([mesh for root in asset_roots for mesh in self._find_meshes(root)])
        return self.material_scanner.scan_meshes(meshes)["textures"]

    def count_scene_textures(self, asset_roots):
        return valid_texture_count(self.scene_textures(asset_roots))

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
        material_data = self.material_scanner.scan_meshes(meshes) if self.material_scanner else {"materials": [], "textures": []}
        collision_data = self._collision_nodes(asset_roots + descendants)

        result = {
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
            "scene_texture_count": valid_texture_count(material_data.get("textures", [])),
            "frozen_transform": self._all_transforms_frozen(asset_roots + transforms),
            "empty_meshes": self._empty_meshes(meshes),
            "collision_nodes": collision_data["valid"],
            "invalid_collision_nodes": collision_data["invalid"],
            "hidden_objects": self._hidden_objects(asset_roots, meshes, transforms),
            "history_nodes": self._history_nodes_many(asset_roots + meshes),
            "illegal_scale": self._has_illegal_scale(asset_roots + transforms),
        }
        result.update(self._collect_uv_sets(meshes, set(collision_data["valid"])))
        result["mesh_geometry"] = self._geometry_triangles(result["uv_coordinate_counts"])
        result["naming_issues"] = self._naming_issues(asset_roots + transforms, identity["asset_name_source_path"])
        assignment = self._material_assignment(result["uv_coordinate_counts"])
        if assignment is not None:
            result["material_assignment"] = assignment
        return result

    def _naming_issues(self, nodes, identity_path):
        names = Counter(node.rsplit("|", 1)[-1] for node in dict.fromkeys(nodes))
        invalid = [name for name in names if not name.replace("_", "a").isalnum() or name[0].isdigit()]
        duplicates = {name for name, count in names.items() if count > 1}
        if hasattr(self.cmds, "objExists"):
            name = identity_path.rsplit("|", 1)[-1]
            if len(self.cmds.ls(name, long=True, type="transform") or []) > 1:
                duplicates.add(name)
        return (["命名空间或非法字符：" + "、".join(sorted(invalid))] if invalid else []) + (
            ["重名：" + "、".join(sorted(duplicates))] if duplicates else [])

    def _material_assignment(self, meshes):
        try:
            from maya.api import OpenMaya as om
        except ImportError:
            return None
        result = {}
        default_nodes = set(self.cmds.ls(defaultNodes=True) or [])
        for mesh in meshes:
            try:
                selection = om.MSelectionList()
                selection.add(mesh)
                path = selection.getDagPath(0)
                fn = om.MFnMesh(path)
                shaders, indices = fn.getConnectedShaders(path.instanceNumber())
                groups = [om.MFnDependencyNode(shader).name() for shader in shaders]
                invalid_groups = set()
                for index, group in enumerate(groups):
                    material = self.material_scanner._surface_material(group)
                    if group == "initialShadingGroup" or not material or material in default_nodes:
                        invalid_groups.add(index)
                faces = [face for face in range(fn.numPolygons)
                         if face >= len(indices) or indices[face] < 0 or indices[face] in invalid_groups]
                if faces:
                    result[mesh] = {"face_indices": faces}
            except (RuntimeError, ValueError, IndexError):
                result[mesh] = {"read_error": True}
        return result

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

    def _geometry_triangles(self, meshes):
        try:
            from maya.api import OpenMaya as om
        except ImportError:
            return {}
        results = {}
        for mesh in meshes:
            try:
                selection = om.MSelectionList()
                selection.add(mesh)
                fn = om.MFnMesh(selection.getDagPath(0))
                points = [(p.x, p.y, p.z) for p in fn.getPoints(om.MSpace.kObject)]
                face_sizes, face_ids = fn.getVertices()
                counts, triangle_ids = fn.getTriangles()
                def triangles():
                    corner = 0
                    first_vertex = 0
                    for face, count in enumerate(counts):
                        size = face_sizes[face]
                        if size == 3 and count == 0:
                            # Maya may omit a collapsed native triangle from its tessellation.
                            yield (face, size, points[face_ids[first_vertex]], points[face_ids[first_vertex + 1]], points[face_ids[first_vertex + 2]])
                        for local in range(count):
                            yield (face, size, points[triangle_ids[corner]], points[triangle_ids[corner + 1]], points[triangle_ids[corner + 2]])
                            corner += 3
                        first_vertex += size
                result = inspect_mesh_triangles(triangles())
                # Only vertices sharing an exact position can belong to a zero-length edge.
                zero_edges = []
                if len(set(points)) != len(points):
                    for edge in range(fn.numEdges):
                        a, b = fn.getEdgeVertices(edge)
                        if points[a] == points[b]:
                            zero_edges.append(edge)
                result["zero_length_edges"] = zero_edges
                results[mesh] = result
            except (RuntimeError, TypeError, IndexError, ValueError) as exc:
                results[mesh] = {"read_error": str(exc)}
        return results

    def _collect_uv_sets(self, meshes, collision_nodes):
        names = {}
        counts = {}
        for mesh in meshes:
            try:
                names[mesh] = _safe_list(self.cmds.polyUVSet(mesh, query=True, allUVSets=True))
            except RuntimeError:
                names[mesh] = []
            if mesh in collision_nodes or mesh.rpartition("|")[0] in collision_nodes:
                continue
            if self.cmds.getAttr(mesh + ".intermediateObject"):
                continue
            counts[mesh] = []
            for uv_set in names[mesh][:2]:
                try:
                    count = int(self.cmds.polyEvaluate(mesh, uvcoord=True, uvSetName=uv_set))
                except (RuntimeError, TypeError, ValueError):
                    count = None
                counts[mesh].append(count)
        return summarize_mesh_uvs(names, counts)

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
            # Maya uses groupId to track component membership, including per-face materials.
            if node_type in ("mesh", "transform", "shadingEngine", "groupId"):
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
