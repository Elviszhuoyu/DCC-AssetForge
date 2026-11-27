# -*- coding: utf-8 -*-
"""Component selection and camera framing for the Maya publish workbench."""
from __future__ import absolute_import, unicode_literals

from asset_forge.maya.workbench_diagnostics import describe


def issue_rows(scan, validation):
    rows = []
    for item in validation.get("checks", []):
        if item.get("status") not in ("error", "warning"):
            continue
        rule = item["id"]
        target_keys = {"empty_mesh": "empty_meshes", "hidden_objects": "hidden_objects",
                       "collision_naming": "invalid_collision_nodes"}
        targets = item.get("affected_meshes") or scan.get(target_keys.get(rule, ""), []) or [item.get("object") or scan.get("asset_root", "")]
        for obj in targets:
            mesh = obj if obj in item.get("affected_meshes", []) or rule == "empty_mesh" else ""
            data = item.get("mesh_results", {}).get(mesh, {})
            indices = []
            kind = ""
            if rule == "zero_area_triangles":
                kind = "f"
                indices = [face["face_index"] for face in data.get("faces", [])]
            elif rule == "zero_length_edges":
                kind = "e"
                indices = data.get("zero_length_edges", [])
            elif rule == "material_assignment":
                kind = "f"
                indices = data.get("face_indices", [])
            diagnostic = describe(item, scan, validation, obj, bool(indices))
            rows.append({"rule": rule, "diagnostic": diagnostic, "mesh": mesh, "object": obj, "kind": kind,
                         "components": indices, "faces": data.get("faces", []) if rule == "zero_area_triangles" else [],
                         "label": diagnostic["title"], "severity": item["status"],
                         "message": item.get("message", ""), "candidates": item.get("candidates", [])})
    return sorted(rows, key=lambda row: row["severity"] != "error")


def _model_panel(cmds):
    focus = cmds.getPanel(withFocus=True)
    visible = cmds.getPanel(visiblePanels=True) or []
    views = [p for p in visible if cmds.getPanel(typeOf=p) == "modelPanel"]
    if focus in views:
        return focus
    return next((p for p in views if cmds.modelEditor(p, query=True, activeView=True)), views[0] if views else None)


def _vertices(cmds, components):
    converted = cmds.polyListComponentConversion(components, toVertex=True) or []
    return sorted(set(cmds.ls(converted, flatten=True, long=True) or [])) if converted else []


def _triangle_vertices(row):
    from maya.api import OpenMaya as om
    selection = om.MSelectionList()
    selection.add(row["mesh"])
    fn = om.MFnMesh(selection.getDagPath(0))
    indices = set()
    for face in row["faces"]:
        polygon = face["face_index"]
        if face["polygon_size"] == 3:
            indices.update(fn.getPolygonVertices(polygon))
        else:
            for local in face["triangle_indices"]:
                indices.update(fn.getPolygonTriangleVertices(polygon, local))
    return [row["mesh"] + ".vtx[{0}]".format(i) for i in sorted(indices)]


def clear_markers():
    """Remove the previous inspection's transient viewport overlay."""
    active = getattr(_mark_vertices, "active", None)
    if active is None:
        return
    try:
        from shiboken6 import isValid
    except ImportError:
        from shiboken2 import isValid
    _mark_vertices.active = None
    if isValid(active):
        active.clear()


def _mark_vertices(cmds, panel, vertices):
    """Use small masked rings. Covering a native VP2 surface with a transparent Qt widget blacks it out."""
    from maya.api import OpenMaya as om, OpenMayaUI as omui
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        from shiboken6 import wrapInstance
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
        from shiboken2 import wrapInstance

    clear_markers()
    if not vertices:
        return
    view = omui.M3dView.getM3dViewFromModelPanel(panel)
    viewport = wrapInstance(int(view.widget()), QtWidgets.QWidget)
    coords = cmds.xform(vertices[:96], query=True, worldSpace=True, translation=True)
    points = [om.MPoint(*p) for p in sorted(set(zip(coords[::3], coords[1::3], coords[2::3])))]
    outer = QtGui.QRegion(0, 0, 20, 20, QtGui.QRegion.Ellipse)
    inner = QtGui.QRegion(3, 3, 14, 14, QtGui.QRegion.Ellipse)
    mask = outer.subtracted(inner)

    class Markers(QtCore.QObject):
        def __init__(self):
            super(Markers, self).__init__(viewport)
            self.rings = []
            for point in points:
                ring = QtWidgets.QWidget(viewport)
                ring.setObjectName("assetForgeVertexMarkers")
                ring.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
                ring.setFixedSize(20, 20)
                ring.setMask(mask)
                ring.setStyleSheet("background-color: #ffd166;")
                self.rings.append((point, ring))
            self.update()
            timer = QtCore.QTimer(self)
            timer.timeout.connect(self.update)
            timer.start(75)

        def update(self):
            width, height = view.portWidth(), view.portHeight()
            for point, ring in self.rings:
                x, y, visible = view.worldToView(point)
                if visible and width and height:
                    ring.move(int(x * viewport.width() / float(width)) - 10,
                              viewport.height() - int(y * viewport.height() / float(height)) - 10)
                    ring.show()
                    ring.raise_()
                else:
                    ring.hide()

        def clear(self):
            for point, ring in self.rings:
                ring.hide()
                ring.deleteLater()
            self.rings = []
            self.deleteLater()
            if cmds.modelPanel(panel, exists=True):
                view.refresh(False, True)

    _mark_vertices.active = Markers()


def locate(cmds, row, mode="source"):
    """Select the reported components while using their endpoints for viewport anchors."""
    mesh = row["mesh"]
    indices = row["components"]
    if not indices:
        target = row["object"]
        if not target or not cmds.objExists(target):
            return {"message": row["message"], "selection": []}
        cmds.selectMode(object=True)
        cmds.select(target, replace=True, noExpand=True)
        return {"message": "已定位  " + target.split("|")[-1], "selection": cmds.ls(selection=True, long=True) or []}

    token = row["kind"]
    source = [mesh + ".{0}[{1}]".format(token, i) for i in indices]
    core = _triangle_vertices(row) if token == "f" and row["faces"] else _vertices(cmds, source)
    if not core:
        raise RuntimeError("组件已变化，请先复检该网格。")
    edges = cmds.polyListComponentConversion(core, toEdge=True) or []
    ring = _vertices(cmds, edges) or core
    owner = (cmds.listRelatives(mesh, parent=True, fullPath=True) or [mesh])[0]
    cmds.selectMode(component=True)
    cmds.hilite(owner, replace=True)
    panel = _model_panel(cmds)
    camera = cmds.modelEditor(panel, query=True, camera=True) if panel else None
    startup_camera = bool(camera and cmds.camera(camera, query=True, startupCamera=True))
    requested = source if mode == "source" else (ring if mode == "ring" else core)
    try:
        if startup_camera:
            cmds.select(ring, replace=True)
            bounds = cmds.exactWorldBoundingBox(ring)
            collapsed = all(bounds[index] == bounds[index + 3] for index in range(3))
            cmds.viewFit(camera, fitFactor=0.60, center=collapsed, animate=False)
        if panel:
            cmds.modelEditor(panel, edit=True, selectionHiliteDisplay=True)
    finally:
        cmds.selectType(polymeshVertex=mode != "source", polymeshFace=mode == "source" and token == "f",
                        polymeshEdge=mode == "source" and token == "e")
        cmds.select(requested, replace=True)
    selected = cmds.ls(selection=True, long=True, flatten=True) or []
    if panel and (row["rule"] != "material_assignment" or mode != "source"):
        _mark_vertices(cmds, panel, core)
    unit = "面" if token == "f" else "边"
    if mode == "source":
        message = "已选 {0} {1}原始{2}".format(len(selected), "个" if token == "f" else "条", unit)
    else:
        message = "{0} {1}  ·  已选 {2} 个{3}顶点".format(
            len(indices), "面" if token == "f" else "边", len(selected), "邻域" if mode == "ring" else "关联")
    if camera and not startup_camera:
        message += "  ·  当前为拍摄镜头，保持机位"
    return {"message": message, "selection": cmds.ls(selection=True, long=True) or [],
            "source": source, "vertices": core, "ring": ring}
