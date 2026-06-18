"""Blender extension package plan for Asset Forge."""

from __future__ import absolute_import

import importlib.util
import os


try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11 fallback for future hosts.
    tomllib = None


BLENDER_EXTENSION_ROOT = os.path.join("integrations", "blender", "asset_forge_extension")
BLENDER_MANIFEST = os.path.join(BLENDER_EXTENSION_ROOT, "blender_manifest.toml")
BLENDER_ENTRY = os.path.join(BLENDER_EXTENSION_ROOT, "__init__.py")


def get_blender_extension_package_plan():
    """Return the planned Blender extension layout."""
    return {
        "extension_id": "asset_forge",
        "package_type": "blender_extension",
        "root": BLENDER_EXTENSION_ROOT,
        "manifest": BLENDER_MANIFEST,
        "entry": BLENDER_ENTRY,
        "required_entry_functions": ["register", "unregister"],
        "blender_version_min": "4.2.0",
        "status": "packaging_gate",
        "support": "roadmap",
        "real_exporter": False,
        "roadmap": "Extension package contract only; real Blender selection, scan, and FBX export are not implemented in the TA portfolio MVP.",
    }


def read_blender_manifest(path=BLENDER_MANIFEST):
    """Read blender_manifest.toml."""
    if tomllib is None:
        return _read_simple_toml(path)
    with open(path, "rb") as stream:
        return tomllib.load(stream)


def validate_blender_extension_package(plan=None):
    """Return structural issues for the Blender extension gate."""
    active = plan or get_blender_extension_package_plan()
    issues = []
    if not os.path.isdir(active.get("root", "")):
        issues.append("missing Blender extension root: {0}".format(active.get("root", "")))
    if not os.path.exists(active.get("manifest", "")):
        issues.append("missing blender_manifest.toml")
        return issues
    if not os.path.exists(active.get("entry", "")):
        issues.append("missing Blender extension __init__.py")
        return issues

    manifest = read_blender_manifest(active["manifest"])
    for field in ["schema_version", "id", "version", "name", "type", "blender_version_min"]:
        if field not in manifest:
            issues.append("blender_manifest.toml missing field: {0}".format(field))
    if manifest.get("id") != active.get("extension_id"):
        issues.append("unexpected Blender extension id: {0}".format(manifest.get("id")))
    if manifest.get("type") != "add-on":
        issues.append("Blender extension type must be add-on")

    entry = _load_entry_module(active["entry"])
    for function_name in active.get("required_entry_functions", []):
        if not callable(getattr(entry, function_name, None)):
            issues.append("missing Blender entry function: {0}".format(function_name))
    return issues


def _load_entry_module(path):
    spec = importlib.util.spec_from_file_location("asset_forge_blender_extension", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_simple_toml(path):
    """Small fallback for Python 3.9 test hosts; supports this flat manifest only."""
    data = {}
    with open(path, "r", encoding="utf-8") as stream:
        for raw_line in stream:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = [item.strip() for item in line.split("=", 1)]
            if value.startswith("[") and value.endswith("]"):
                items = [item.strip().strip('"') for item in value[1:-1].split(",") if item.strip()]
                data[key] = items
            else:
                data[key] = value.strip('"')
    return data
