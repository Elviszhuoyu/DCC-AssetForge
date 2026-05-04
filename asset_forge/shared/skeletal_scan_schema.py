"""Shared planned scan schema for Skeletal Mesh assets."""

from __future__ import absolute_import


def create_skeletal_scan_result(
    asset_name,
    root_joint="",
    joints=None,
    skin_clusters=None,
    lods=None,
    materials=None,
):
    joints = joints or []
    skin_clusters = skin_clusters or []
    lods = lods or []
    materials = materials or []
    return {
        "asset_name": asset_name,
        "asset_type": "skeletal_mesh",
        "root_joint": root_joint,
        "joints": joints,
        "joint_count": len(joints),
        "skin_clusters": skin_clusters,
        "skin_cluster_count": len(skin_clusters),
        "max_influences": _max_influences(skin_clusters),
        "lods": lods,
        "lod_count": len(lods),
        "materials": materials,
        "material_slots": len(materials),
    }


def skeletal_manifest_fields_from_scan(scan_result):
    return {
        "root_joint": scan_result.get("root_joint", ""),
        "joint_count": scan_result.get("joint_count", 0),
        "skin_cluster_count": scan_result.get("skin_cluster_count", 0),
        "max_influences": scan_result.get("max_influences", 0),
        "lods": scan_result.get("lods", []),
        "materials": scan_result.get("materials", []),
    }


def validate_skeletal_scan_result(scan_result):
    issues = []
    if scan_result.get("asset_type") != "skeletal_mesh":
        issues.append("scan result asset_type must be skeletal_mesh")
    if not scan_result.get("root_joint"):
        issues.append("missing root_joint")
    if scan_result.get("joint_count", 0) <= 0:
        issues.append("joint_count must be greater than 0")
    if scan_result.get("skin_cluster_count", 0) <= 0:
        issues.append("skin_cluster_count must be greater than 0")
    if scan_result.get("max_influences", 0) <= 0:
        issues.append("max_influences must be greater than 0")
    return issues


def _max_influences(skin_clusters):
    values = [cluster.get("max_influences", 0) for cluster in skin_clusters]
    return max(values) if values else 0
