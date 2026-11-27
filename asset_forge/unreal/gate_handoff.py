"""Durable receipts for the meshes a native workbench import actually wrote."""

from hashlib import sha256
import os
from pathlib import Path
import re
from uuid import uuid4

from asset_forge.shared.report_schema import read_report, write_report
from asset_forge.shared.unreal_path import sanitize_unreal_package_path
from asset_forge.unreal.manifest_reader import UnrealManifestReader


_OBJECT_PATH = re.compile(r"^/Game/(?:[^/.:'\s]+/)*[^/.:'\s]+\.[^/.:'\s]+$", re.I)


def canonical_path(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _same_file(actual, expected):
    return isinstance(actual, str) and bool(actual) and canonical_path(actual) == canonical_path(expected)


def handoff_path(package, project_file):
    if not project_file or not os.path.isfile(project_file):
        return None
    key = sha256(canonical_path(package).encode("utf-8")).hexdigest()
    return Path(project_file).parent / "Saved" / "AssetForge" / "Gate" / "Handoffs" / (key + ".json")


def _read(path):
    try:
        value = read_report(str(path)) if path else {}
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _static_meshes(paths, target, unreal):
    if not isinstance(paths, list):
        return []
    folders = target.rstrip("/").casefold() + "/"
    matches = [
        path for path in dict.fromkeys(path for path in paths if isinstance(path, str))
        if _OBJECT_PATH.fullmatch(path) and path.casefold().startswith(folders)
    ]
    if not matches:
        return []
    registry = getattr(unreal, "AssetRegistryHelpers", None)
    registry = registry.get_asset_registry() if registry else None
    meshes = []
    for path in matches:
        package_name, _, name = path.rpartition(".")
        if registry is not None:
            assets = registry.get_assets_by_package_name(package_name, True) or []
            found = any(str(row.asset_name).casefold() == name.casefold()
                        and str(row.asset_class_path.asset_name) == "StaticMesh" for row in assets)
        else:
            asset = unreal.load_asset(path)
            found = isinstance(asset, unreal.StaticMesh)
        if found:
            meshes.append(path)
    return meshes


def _import_evidence(report, package, project_file, manifest_path):
    imported = report.get("import") or {}
    post = report.get("post_import_validation") or imported.get("post_import_validation") or {}
    if not (
        report.get("stage") == "package_acceptance_flow"
        and _same_file(report.get("workbench_project_file"), project_file)
        and _same_file(report.get("package_dir"), package)
        and _same_file(report.get("source_manifest_path"), manifest_path)
        and report.get("run_import") is True and report.get("gate_passed") is True
        and not report.get("errors") and imported.get("status") == "success"
        and post.get("can_accept", post.get("status") == "pass") is True
    ):
        return {}, ""
    acceptance = report.get("package_acceptance") or {}
    try:
        target = sanitize_unreal_package_path(imported.get("target_path", ""))
        accepted = sanitize_unreal_package_path(acceptance.get("target_path", ""))
    except ValueError:
        return {}, ""
    return (imported, target) if target.casefold() == accepted.casefold() else ({}, "")


def _create_receipt(report, package, project_file, manifest_path, manifest_sha256, unreal):
    imported, target = _import_evidence(report, package, project_file, manifest_path)
    if not imported:
        return {}
    meshes = _static_meshes(imported.get("imported_assets"), target, unreal)
    if not meshes:
        return {}
    policy = imported.get("review_policy")
    acceptance = report["package_acceptance"]
    manifest = acceptance.get("manifest_validation", {}).get("manifest") or {}
    result = {
        "receipt": uuid4().hex,
        "meshes": meshes,
        "policy": policy if isinstance(policy, dict) else {},
        "package_dir": str(package),
        "project_file": str(project_file),
        "source_manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "target_path": target,
        # Count actual import results, which can include assets retained by a reuse policy.
        "result_counts": {
            "mesh_count": len(meshes),
            "texture_count": _asset_result_count(imported.get("imported_textures")),
            "material_count": _asset_result_count(imported.get("created_material_instances")),
        },
    }
    budgets = manifest.get("asset_budgets")
    if isinstance(budgets, dict) and all(type(budgets.get(key)) is int and budgets[key] > 0
                                      for key in ("triangles", "material_slots")):
        result["asset_budgets"] = {key: budgets[key] for key in ("triangles", "material_slots")}
    return result


def _asset_result_count(paths):
    return len({path.rsplit(".", 1)[0].casefold() for path in paths if isinstance(path, str) and path}) if isinstance(paths, list) else 0


def save_handoff(report, package, project_file, manifest_path, manifest_sha256, unreal):
    path = handoff_path(package, project_file)
    if not path or not manifest_path or not manifest_sha256:
        return {}
    receipt = _create_receipt(report, package, project_file, manifest_path, manifest_sha256, unreal)
    if receipt:
        write_report(str(path), receipt)
    return receipt


def invalidate_handoff(package, project_file):
    path = handoff_path(package, project_file)
    if path and path.is_file():
        write_report(str(path), {"invalidated": True})


def read_handoff(package, project_file, manifest_path, manifest_sha256, unreal, legacy_report=None,
                 *, validate_assets=True):
    path = handoff_path(package, project_file)
    if not path or not manifest_path or not manifest_sha256:
        return {}
    stored = _read(path)
    if stored.get("invalidated"):
        return {}
    if (
        isinstance(stored.get("receipt"), str) and stored["receipt"]
        and _same_file(stored.get("project_file"), project_file)
        and _same_file(stored.get("package_dir"), package)
        and _same_file(stored.get("source_manifest_path"), manifest_path)
        and stored.get("manifest_sha256") == manifest_sha256
        and isinstance(stored.get("policy"), dict)
        and isinstance(stored.get("meshes"), list) and stored["meshes"]
    ):
        if not validate_assets:
            return stored
        try:
            target = sanitize_unreal_package_path(stored.get("target_path", ""))
            live = _static_meshes(stored["meshes"], target, unreal)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return {}
        return dict(stored, meshes=live) if live else {}

    if not legacy_report:
        return {}
    imported, _ = _import_evidence(legacy_report, package, project_file, manifest_path)
    if not imported:
        return {}
    old = legacy_report.get("package_acceptance", {}).get("manifest_validation", {}).get("manifest")
    if not isinstance(old, dict):
        return {}
    current = UnrealManifestReader().load(manifest_path, require_fbx_exists=False).get("manifest")
    if old != current:
        return {}
    return save_handoff(legacy_report, package, project_file, manifest_path, manifest_sha256, unreal)
