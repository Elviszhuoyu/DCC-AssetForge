"""Maya module package plan for DCC AssetForge."""

from __future__ import absolute_import

import io
import os


MAYA_MODULE_NAME = "AssetForge"
MAYA_MODULE_VERSION = "0.1"
MAYA_MODULE_DESCRIPTOR = os.path.join("integrations", "maya", "AssetForge.mod")


def get_maya_module_package_plan():
    """Return the planned official Maya module layout."""
    return {
        "module_name": MAYA_MODULE_NAME,
        "version": MAYA_MODULE_VERSION,
        "descriptor": MAYA_MODULE_DESCRIPTOR,
        "module_root": "../..",
        "python_path": ".",
        "directories": [
            os.path.join("integrations", "maya", "scripts"),
            os.path.join("integrations", "maya", "icons"),
            os.path.join("integrations", "maya", "plug-ins"),
        ],
        "entry_script": os.path.join("integrations", "maya", "scripts", "asset_forge_maya.py"),
        "entry_functions": ["show", "reload_and_show", "scan_selection", "export_selected"],
    }


def read_maya_module_descriptor(path=MAYA_MODULE_DESCRIPTOR):
    """Read the DCC AssetForge .mod descriptor using UTF-8."""
    with io.open(path, "r", encoding="utf-8") as stream:
        return [line.strip() for line in stream.readlines() if line.strip()]


def validate_maya_module_package(plan=None):
    """Return structural issues for the Maya module package."""
    active = plan or get_maya_module_package_plan()
    issues = []
    descriptor = active.get("descriptor", "")
    if not os.path.exists(descriptor):
        return ["missing Maya module descriptor: {0}".format(descriptor)]

    lines = read_maya_module_descriptor(descriptor)
    expected_header = "+ {0} {1} {2}".format(
        active.get("module_name", MAYA_MODULE_NAME),
        active.get("version", MAYA_MODULE_VERSION),
        active.get("module_root", "../.."),
    )
    if expected_header not in lines:
        issues.append("missing module header: {0}".format(expected_header))
    if "PYTHONPATH +:= {0}".format(active.get("python_path", ".")) not in lines:
        issues.append("missing PYTHONPATH mapping")

    for directory in active.get("directories", []):
        if not os.path.isdir(directory):
            issues.append("missing Maya module directory: {0}".format(directory))
    for label in ["scripts", "icons", "plug-ins"]:
        if not any(line.startswith(label + ":") for line in lines):
            issues.append("missing Maya module mapping: {0}".format(label))

    entry_script = active.get("entry_script", "")
    if not os.path.exists(entry_script):
        issues.append("missing Maya entry script: {0}".format(entry_script))
    return issues
