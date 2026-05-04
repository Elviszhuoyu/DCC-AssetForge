"""Planned Maya Skeletal Mesh scanner facade."""

from __future__ import absolute_import

from asset_forge.maya.cmds_bridge import get_cmds
from asset_forge.shared.skeletal_scan_schema import create_skeletal_scan_result


def _safe_list(value):
    return value or []


class MayaSkeletalScanner(object):
    """Collect the first Skeletal Mesh scan shape without owning final rules yet."""

    def __init__(self, cmds_module=None):
        self.cmds = cmds_module or get_cmds()

    def is_available(self):
        return self.cmds is not None

    def scan(self, asset_root):
        if not self.is_available():
            raise RuntimeError("maya.cmds is not available")

        joints = self._find_joints(asset_root)
        meshes = self._find_meshes(asset_root)
        skin_clusters = self._find_skin_clusters(meshes)
        return create_skeletal_scan_result(
            asset_name=asset_root.split("|")[-1],
            root_joint=self._root_joint(joints),
            joints=joints,
            skin_clusters=skin_clusters,
            lods=self._find_lods(asset_root),
            materials=self._materials(meshes),
        )

    def _descendants(self, asset_root):
        try:
            return _safe_list(self.cmds.listRelatives(asset_root, allDescendents=True, fullPath=True))
        except RuntimeError:
            return []

    def _find_joints(self, asset_root):
        nodes = [asset_root] + self._descendants(asset_root)
        return [node for node in nodes if self.cmds.nodeType(node) == "joint"]

    def _root_joint(self, joints):
        return joints[0] if joints else ""

    def _find_meshes(self, asset_root):
        nodes = [asset_root] + self._descendants(asset_root)
        return [node for node in nodes if self.cmds.nodeType(node) == "mesh"]

    def _find_skin_clusters(self, meshes):
        clusters = []
        for mesh in meshes:
            for cluster in _safe_list(self.cmds.listConnections(mesh, type="skinCluster")):
                if self._has_cluster(clusters, cluster):
                    continue
                clusters.append(
                    {
                        "name": cluster,
                        "max_influences": self._skin_cluster_max_influences(cluster),
                        "influences": self._skin_cluster_influences(cluster),
                    }
                )
        return clusters

    def _has_cluster(self, clusters, name):
        return any(cluster.get("name") == name for cluster in clusters)

    def _skin_cluster_max_influences(self, cluster):
        try:
            return int(self.cmds.skinCluster(cluster, query=True, maximumInfluences=True) or 0)
        except RuntimeError:
            return 0

    def _skin_cluster_influences(self, cluster):
        try:
            return _safe_list(self.cmds.skinCluster(cluster, query=True, influence=True))
        except RuntimeError:
            return []

    def _find_lods(self, asset_root):
        lods = []
        for node in [asset_root] + self._descendants(asset_root):
            name = node.split("|")[-1]
            if name.upper().startswith("LOD"):
                lods.append({"name": name, "node": node})
        return lods

    def _materials(self, meshes):
        materials = []
        for mesh in meshes:
            for group in _safe_list(self.cmds.listConnections(mesh, type="shadingEngine")):
                for material in _safe_list(self.cmds.listConnections(group + ".surfaceShader")):
                    if material not in [item.get("name") for item in materials]:
                        materials.append({"name": material})
        return materials
