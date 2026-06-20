# -*- coding: utf-8 -*-
"""Run a real Blender background smoke for Asset Forge Blender export."""

from __future__ import absolute_import

import argparse
import json
import os
import sys
import time


def _repo_root_from_script():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _make_scene(bpy):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    root = bpy.data.objects.new("B", None)
    bpy.context.collection.objects.link(root)

    _make_mesh_part(bpy, root, "B_a", (0.72, 0.64, 0.55, 1.0), -1.25)
    _make_mesh_part(bpy, root, "B_b", (0.28, 0.31, 0.34, 1.0), 1.25)

    bpy.ops.object.select_all(action="DESELECT")
    root.select_set(True)
    bpy.context.view_layer.objects.active = root
    return root


def _make_mesh_part(bpy, root, name, color, x_offset):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color

    mesh = bpy.data.meshes.new(name + "Mesh")
    vertices = [
        (x_offset - 0.5, -0.5, 0.0),
        (x_offset + 0.5, -0.5, 0.0),
        (x_offset + 0.5, 0.5, 0.0),
        (x_offset - 0.5, 0.5, 0.0),
        (x_offset, 0.0, 0.75),
    ]
    faces = [(0, 1, 2, 3), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mesh.uv_layers.new(name="UVMap")
    mesh.uv_layers.new(name="LightmapUV")

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = root
    obj.data.materials.append(material)
    return obj

def _write_json(path, payload):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _script_args():
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1 :]
    return []


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=_repo_root_from_script())
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--target-path", default="/Game/Props/BlenderSmoke")
    parser.add_argument("--blend-file", default="")
    parser.add_argument("--selection", action="append", default=[])
    parser.add_argument("--texture-folder", default="")
    parser.add_argument("--mesh-prefix", default="")
    parser.add_argument("--triangle-budget", type=int, default=0)
    args = parser.parse_args(argv)

    repo_root = os.path.abspath(args.repo_root)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    import bpy  # type: ignore
    from integrations.blender.asset_forge_extension import bridge
    from integrations.blender_mcp.client import BlenderBridgeClient
    from integrations.blender_mcp_runtime.ports import allocate_port

    if args.blend_file:
        bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args.blend_file))
        root = None
        selection = list(args.selection or ["B"])
    else:
        root = _make_scene(bpy)
        selection = list(args.selection or [root.name])
    registry_path = os.path.join(args.output_root, "instances.json")
    port = allocate_port("127.0.0.1", 8950, 8999)
    registered = bridge.start_bridge(
        port=port,
        token="asset-forge-smoke",
        bpy_module=bpy,
        repo_root=repo_root,
        registry_path=registry_path,
        log_path=os.path.join(args.output_root, "latest_blender.log"),
    )
    client = BlenderBridgeClient.from_instance(registered)
    status = client.call("blender_status", {})
    scan_params = {"selection": selection}
    export_params = {
        "selection": selection,
        "export_root": os.path.join(args.output_root, "packages"),
        "target_path": args.target_path,
    }
    if args.mesh_prefix:
        scan_params["mesh_prefix"] = args.mesh_prefix
        export_params["mesh_prefix"] = args.mesh_prefix
    if args.triangle_budget > 0:
        scan_params["triangle_budget"] = args.triangle_budget
        export_params["triangle_budget"] = args.triangle_budget
    if args.texture_folder:
        export_params["texture_folder"] = os.path.abspath(args.texture_folder)
    scan = client.call("blender_scan_static_prop", scan_params)
    preflight = client.call("blender_preflight_static_prop", export_params)
    export = client.call(
        "blender_export_static_prop_package",
        export_params,
    )
    summary = {
        "status": "success" if export.get("can_continue_to_ue") else "blocked",
        "created_at_epoch": time.time(),
        "blender_version": getattr(bpy.app, "version_string", ""),
        "scene_root": root.name if root is not None else ",".join(selection),
        "registered": registered,
        "bridge_status": status,
        "scan_asset_name": scan.get("scan", {}).get("asset_name", ""),
        "scan_asset_name_prefix": scan.get("scan", {}).get("asset_name_prefix", ""),
        "source_asset_name": scan.get("scan", {}).get("source_asset_name", ""),
        "preflight": preflight,
        "export": export,
        "fbx_exists": os.path.exists(export.get("fbx_path", "")),
        "can_continue_to_ue": bool(export.get("can_continue_to_ue")),
    }
    _write_json(args.report_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    bridge.stop_bridge()
    return 0 if summary["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main(_script_args()))
