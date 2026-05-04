"""Asset Forge Unreal Python bootstrap.

Unreal loads plugin Content/Python scripts when the Python plugin is enabled.
This file keeps the development repository importable without manual console
sys.path setup.
"""

from __future__ import absolute_import

import os
import sys


def bootstrap():
    repo_root = _repo_root_from_plugin_python()
    added_repo_root = _ensure_repo_root(repo_root)
    action_plan = _load_action_plan()
    _log_unreal("Asset Forge Python bootstrap loaded")
    return {
        "repo_root": repo_root.replace("\\", "/"),
        "added_repo_root": added_repo_root,
        "action_count": len(action_plan),
        "actions": [item.get("id", "") for item in action_plan],
    }


def _repo_root_from_plugin_python():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current_dir, "..", "..", "..", ".."))


def _ensure_repo_root(repo_root):
    package_dir = os.path.join(repo_root, "asset_forge")
    if not os.path.isdir(package_dir):
        return False
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
        return True
    return False


def _load_action_plan():
    from asset_forge.unreal.editor_widget_actions import get_action_plan

    return get_action_plan()


def _log_unreal(message):
    try:
        import unreal
    except Exception:
        return
    if hasattr(unreal, "log"):
        unreal.log(message)


BOOTSTRAP_REPORT = bootstrap()
