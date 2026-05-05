"""Maya material and texture reference scanner."""

from __future__ import absolute_import

from asset_forge.maya.cmds_bridge import get_cmds
from asset_forge.shared.path_utils import normalize_path


def _safe_list(value):
    return value or []


class MayaMaterialScanner(object):
    """Collect material slots and file texture references from Maya meshes."""

    def __init__(self, cmds_module=None):
        self.cmds = cmds_module or get_cmds()

    def scan_meshes(self, meshes):
        if self.cmds is None:
            raise RuntimeError("当前环境不可用 maya.cmds")

        materials = []
        textures = []
        seen_materials = set()
        seen_textures = set()

        for shading_group in self._shading_groups(meshes):
            material_node = self._surface_material(shading_group)
            material_name = material_node or shading_group
            if material_name not in seen_materials:
                materials.append(
                    {
                        "name": material_name,
                        "shading_group": shading_group,
                        "type": self._node_type(material_name),
                        "textures": [],
                    }
                )
                seen_materials.add(material_name)

            material_entry = materials[-1] if materials and materials[-1]["name"] == material_name else self._find_material(materials, material_name)
            for texture in self._file_textures(material_node):
                texture_key = texture.get("path") or texture.get("node")
                if texture_key not in seen_textures:
                    textures.append(texture)
                    seen_textures.add(texture_key)
                material_entry["textures"].append(texture)

        return {"materials": materials, "textures": textures}

    def _shading_groups(self, meshes):
        result = []
        for mesh in meshes:
            groups = _safe_list(self.cmds.listConnections(mesh, type="shadingEngine"))
            for group in groups:
                if group not in result:
                    result.append(group)
        return result

    def _surface_material(self, shading_group):
        connections = _safe_list(self.cmds.listConnections(shading_group + ".surfaceShader", source=True, destination=False))
        return connections[0] if connections else ""

    def _file_textures(self, material_node):
        if not material_node:
            return []
        history = _safe_list(self.cmds.listHistory(material_node))
        textures = []
        for node in history:
            if self._node_type(node) != "file":
                continue
            path = self._file_texture_path(node)
            textures.append(
                {
                    "node": node,
                    "path": normalize_path(path) if path else "",
                    "source_type": "maya_file_node",
                    "source_label": "Maya 文件贴图节点",
                    "usage": self._guess_usage(node),
                }
            )
        return textures

    def _file_texture_path(self, file_node):
        try:
            return self.cmds.getAttr(file_node + ".fileTextureName")
        except RuntimeError:
            return ""

    def _guess_usage(self, file_node):
        outputs = _safe_list(self.cmds.listConnections(file_node, source=False, destination=True, plugs=True))
        joined = " ".join(outputs).lower()
        if "normal" in joined or "bump" in joined:
            return "normal"
        if "roughness" in joined:
            return "roughness"
        if "metal" in joined:
            return "metallic"
        if "basecolor" in joined or "color" in joined:
            return "base_color"
        return "unknown"

    def _node_type(self, node):
        if not node:
            return ""
        try:
            return self.cmds.nodeType(node)
        except RuntimeError:
            return ""

    def _find_material(self, materials, material_name):
        for material in materials:
            if material["name"] == material_name:
                return material
        return {"name": material_name, "textures": []}
