# -*- coding: utf-8 -*-
"""Force-launch DCC AssetForge inside Maya from the current repository checkout.

This file is intentionally independent from ``asset_forge_maya`` so it can fix
the case where Maya has already imported an older module from another sys.path.
"""

from __future__ import absolute_import, print_function

import os
import json
import sys


MODULE_NAME = "asset_forge_maya"
BRIDGE_MODULE_NAME = "asset_forge_maya_bridge"
UI_SHELF_NAME = "AssetForge"
UI_SHELF_BUTTON = "assetForgeMayaWorkbenchButton"
PURGE_MODULE_NAMES = (
    MODULE_NAME,
    "asset_forge",
)
PURGE_PREFIXES = (
    "asset_forge.",
)


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _prepend_sys_path(path):
    normalized = _norm(path)
    kept = [item for item in sys.path if _norm(item) != normalized]
    sys.path[:] = [path] + kept


def _bootstrap_path_from_globals():
    for name in ("__file__", "ASSET_FORGE_BOOTSTRAP_PATH", "_bootstrap"):
        value = globals().get(name)
        if value:
            return os.path.abspath(value)
    return ""


def _repo_root_from_context():
    explicit_root = globals().get("ASSET_FORGE_REPO_ROOT")
    if explicit_root:
        return os.path.abspath(explicit_root)

    bootstrap_path = _bootstrap_path_from_globals()
    if bootstrap_path:
        return os.path.abspath(os.path.join(os.path.dirname(bootstrap_path), os.pardir))

    raise RuntimeError(
        "无法定位 DCC AssetForge 仓库根目录：Maya exec 环境没有 __file__。"
        "请设置 ASSET_FORGE_REPO_ROOT，或使用推荐启动代码注入 __file__ / ASSET_FORGE_BOOTSTRAP_PATH。"
    )


def _maya_scripts_dir(repo_root):
    return os.path.join(repo_root, "integrations", "maya", "scripts")


def _repo_scripts_dir(repo_root):
    return os.path.join(repo_root, "scripts")


def _entry_script_path(repo_root):
    return os.path.join(_maya_scripts_dir(repo_root), MODULE_NAME + ".py")


def _purge_asset_forge_modules():
    purged = []
    for module_name in sorted(list(sys.modules.keys()), reverse=True):
        if module_name in PURGE_MODULE_NAMES or module_name.startswith(PURGE_PREFIXES):
            purged.append(module_name)
            del sys.modules[module_name]
    return purged


def _load_entry_module(entry_script):
    if not os.path.exists(entry_script):
        raise RuntimeError("找不到 DCC AssetForge Maya 入口脚本: {0}".format(entry_script))

    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(MODULE_NAME, entry_script)
        module = importlib.util.module_from_spec(spec)
        sys.modules[MODULE_NAME] = module
        spec.loader.exec_module(module)
        return module
    except ImportError:
        import imp

        return imp.load_source(MODULE_NAME, entry_script)


def _load_bridge_module(repo_root):
    """Load the bridge script from this checkout, not Maya's cached sys.modules."""
    bridge_script = os.path.join(_maya_scripts_dir(repo_root), BRIDGE_MODULE_NAME + ".py")
    if not os.path.exists(bridge_script):
        raise RuntimeError("找不到 DCC AssetForge Maya bridge 脚本: {0}".format(bridge_script))

    old_bridge = sys.modules.get(BRIDGE_MODULE_NAME)
    if old_bridge is not None and getattr(old_bridge, "_SERVER", None) is not None:
        try:
            old_bridge.stop_bridge()
        except Exception:
            pass
    sys.modules.pop(BRIDGE_MODULE_NAME, None)

    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(BRIDGE_MODULE_NAME, bridge_script)
        module = importlib.util.module_from_spec(spec)
        sys.modules[BRIDGE_MODULE_NAME] = module
        spec.loader.exec_module(module)
        return module
    except ImportError:
        import imp

        return imp.load_source(BRIDGE_MODULE_NAME, bridge_script)


def current_bridge_module(repo_root=None):
    """Return the active bridge module without stopping a running MCP server."""
    active_root = os.path.abspath(repo_root or _repo_root_from_context())
    _prepend_sys_path(_repo_scripts_dir(active_root))
    _prepend_sys_path(active_root)
    _prepend_sys_path(_maya_scripts_dir(active_root))
    bridge_module = sys.modules.get(BRIDGE_MODULE_NAME)
    if (
        bridge_module is not None
        and getattr(bridge_module, "_SERVER", None) is not None
        and callable(getattr(bridge_module, "show_bridge_status_window", None))
    ):
        return bridge_module
    return _load_bridge_module(active_root)


def usage_text():
    return "\n".join(
        [
            "Usage:",
            "  maya_launch_asset_forge.py",
            "  maya_launch_asset_forge.py --install-ui-shelf [repo_root]",
            "  maya_launch_asset_forge.py --bridge [repo_root]",
            "  maya_launch_asset_forge.py --install-bridge-shelf [repo_root]",
            "  maya_launch_asset_forge.py --check [repo_root]",
            "  maya_launch_asset_forge.py --help",
            "",
            "Next action:",
            "  在 Maya Script Editor 中优先使用带 __file__ / ASSET_FORGE_BOOTSTRAP_PATH 的推荐粘贴代码；MCP 复测使用 --bridge。",
        ]
    )


def _write_text(stream, text):
    if hasattr(stream, "buffer"):
        stream.buffer.write(text.encode("utf-8"))
    else:
        stream.write(text)


def _print_json(data):
    _write_text(sys.stdout, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def bootstrap(repo_root=None, open_ui=True, quiet=False):
    """Clear stale Maya modules, load the repo entry script, and optionally show UI."""
    active_root = os.path.abspath(repo_root or _repo_root_from_context())
    maya_scripts = _maya_scripts_dir(active_root)
    repo_scripts = _repo_scripts_dir(active_root)
    entry_script = _entry_script_path(active_root)

    _prepend_sys_path(repo_scripts)
    _prepend_sys_path(active_root)
    _prepend_sys_path(maya_scripts)
    purged = _purge_asset_forge_modules()
    module = _load_entry_module(entry_script)

    if not callable(getattr(module, "reload_and_show", None)):
        raise RuntimeError(
            "DCC AssetForge Maya 入口已加载，但缺少 reload_and_show: {0}".format(
                getattr(module, "__file__", "<unknown>")
            )
        )

    if not quiet:
        print("[DCC AssetForge] repo_root = {0}".format(active_root))
        print("[DCC AssetForge] entry = {0}".format(getattr(module, "__file__", entry_script)))
        print("[DCC AssetForge] purged_modules = {0}".format(len(purged)))

    if open_ui:
        return module.reload_and_show()

    return {
        "repo_root": active_root,
        "repo_scripts": repo_scripts,
        "entry_script": entry_script,
        "module_file": getattr(module, "__file__", entry_script),
        "purged_modules": purged,
        "has_reload_and_show": callable(getattr(module, "reload_and_show", None)),
    }


def restore_saved_workspace():
    """Populate the control Maya already restored, including shelf-only installations."""
    _prepend_sys_path(_repo_root_from_context())
    from asset_forge.maya import ui
    restore = getattr(ui, "defer_workspace_restore", ui.restore_workspace)
    return restore()


def launch():
    """Maya-friendly alias used by paste snippets."""
    return bootstrap(open_ui=True)


def install_ui_shelf_button(repo_root=None, shelf_name=UI_SHELF_NAME, existing_button=""):
    """Install the main DCC AssetForge Maya workbench shelf button."""
    active_root = os.path.abspath(repo_root or _repo_root_from_context())
    import maya.cmds as cmds

    shelf = _ensure_shelf(cmds, shelf_name)
    command = _ui_shelf_command(active_root)
    icon_path = _asset_forge_icon_path(active_root)
    properties = dict(label="DCC AssetForge", annotation="打开 DCC AssetForge 工作台",
                      image=icon_path, image1=icon_path, imageOverlayLabel="",
                      overlayLabelColor=(0.82, 0.96, 0.88), overlayLabelBackColor=(0.03, 0.09, 0.07, 0.75),
                      command=command, sourceType="python")
    if existing_button:
        cmds.shelfButton(existing_button, edit=True, **properties)
        button = existing_button
    else:
        if cmds.shelfButton(UI_SHELF_BUTTON, exists=True):
            cmds.deleteUI(UI_SHELF_BUTTON)
        button = cmds.shelfButton(UI_SHELF_BUTTON, parent=shelf, **properties)
    return {
        "status": "success",
        "shelf": shelf,
        "button": button,
        "repo_root": active_root,
        "icon": icon_path,
        "next_action": "Shelf 按钮 DCC AssetForge 已安装；点击后会清理旧模块并打开当前仓库的 Maya 发布工作台。",
    }


def _ensure_shelf(cmds, shelf_name):
    try:
        import maya.mel as mel

        top_level = mel.eval("$tmp=$gShelfTopLevel")
    except Exception:
        top_level = "ShelfTopLevel"
    if not cmds.shelfLayout(shelf_name, exists=True):
        cmds.shelfLayout(shelf_name, parent=top_level)
    return shelf_name


def _asset_forge_icon_path(repo_root):
    path = os.path.join(repo_root, "Plugins", "AssetForge", "Resources", "Workbench", "brand", "af_shelf.png")
    return path.replace("\\", "/") if os.path.isfile(path) else "commandButton.png"


def _ui_shelf_command(repo_root):
    bootstrap = os.path.join(repo_root, "scripts", "maya_launch_asset_forge.py").replace("\\", "/")
    # Maya executes shelf commands in __main__; run_path gives the launcher its own globals.
    return (
        "__import__('runpy').run_path(\n"
        "    {0!r}, init_globals={{'ASSET_FORGE_REPO_ROOT': {1!r}}}\n"
        ")['bootstrap'](open_ui=True)"
    ).format(bootstrap, repo_root.replace("\\", "/"))


def _check_log_root(repo_root):
    return os.environ.get("ASSET_FORGE_LOG_ROOT") or repo_root


def _write_check_log(report):
    try:
        from asset_forge.maya.operation_logger import MayaOperationLogger

        bootstrap_info = report.get("bootstrap", {})
        repo_root = bootstrap_info.get("repo_root") or os.path.abspath(os.getcwd())
        logger = MayaOperationLogger(root=_check_log_root(repo_root))
        logger.log(
            "maya_bootstrap_check",
            report.get("status", "unknown"),
            outputs={
                "stage": report.get("stage", ""),
                "can_accept": report.get("can_accept", False),
                "repo_root": repo_root,
                "entry_script": bootstrap_info.get("entry_script", ""),
                "has_reload_and_show": bootstrap_info.get("has_reload_and_show", False),
            },
            errors=report.get("errors", []),
            warnings=report.get("warnings", []),
        )
    except Exception:
        # The check command must stay useful even if the log folder is locked.
        pass


def check(repo_root=None, write_log=False):
    try:
        result = bootstrap(repo_root=repo_root, open_ui=False, quiet=True)
        report = {
            "stage": "maya_bootstrap_check",
            "status": "pass",
            "can_accept": True,
            "warnings": [],
            "errors": [],
            "next_action": "Maya bootstrap 链路可加载；下一步在真实 Maya 中打开 UI 复测。",
            "bootstrap": result,
        }
    except Exception as exc:
        report = {
            "stage": "maya_bootstrap_check",
            "status": "error",
            "can_accept": False,
            "warnings": [],
            "errors": [{"source": "maya_bootstrap", "message": str(exc)}],
            "next_action": "确认传入的是 DCC AssetForge 仓库根目录，或使用推荐粘贴代码注入 ASSET_FORGE_REPO_ROOT / ASSET_FORGE_BOOTSTRAP_PATH。",
            "bootstrap": {},
        }
    if write_log:
        _write_check_log(report)
    return report


def start_bridge(repo_root=None, host=None, port=None, token=None):
    """Start the DCC AssetForge Maya MCP bridge from the same bootstrap entry."""
    active_root = os.path.abspath(repo_root or _repo_root_from_context())
    _prepend_sys_path(_repo_scripts_dir(active_root))
    _prepend_sys_path(active_root)
    _prepend_sys_path(_maya_scripts_dir(active_root))
    bridge_module = sys.modules.get(BRIDGE_MODULE_NAME)
    if (
        bridge_module is None
        or getattr(bridge_module, "_SERVER", None) is None
        or not callable(getattr(bridge_module, "start_bridge", None))
    ):
        bridge_module = _load_bridge_module(active_root)
    start_maya_bridge = bridge_module.start_bridge

    return start_maya_bridge(host=host, port=port, token=token, repo_root=active_root)


def install_bridge_shelf_button(repo_root=None):
    """Install the one-click DCC AssetForge Maya MCP bridge shelf button."""
    active_root = os.path.abspath(repo_root or _repo_root_from_context())
    _prepend_sys_path(_repo_scripts_dir(active_root))
    _prepend_sys_path(active_root)
    _prepend_sys_path(_maya_scripts_dir(active_root))
    bridge_module = sys.modules.get(BRIDGE_MODULE_NAME)
    if (
        bridge_module is None
        or getattr(bridge_module, "_SERVER", None) is None
        or not callable(getattr(bridge_module, "install_bridge_shelf_button", None))
    ):
        bridge_module = _load_bridge_module(active_root)
    install_button = bridge_module.install_bridge_shelf_button

    return install_button(repo_root=active_root)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        _write_text(sys.stdout, usage_text() + "\n")
        return 0
    known = set(["--check", "--bridge", "--install-bridge-shelf", "--install-ui-shelf"])
    unknown = [item for item in argv if item.startswith("-") and item not in known]
    if unknown:
        _write_text(sys.stderr, "Error: 未知参数：{0}\nNext action: 运行 --help 查看 Maya bootstrap 支持的命令。\n\n{1}\n".format(", ".join(unknown), usage_text()))
        return 2
    if "--bridge" in argv:
        args = [item for item in argv if item not in known]
        report = start_bridge(args[0] if args else None)
        _print_json(report)
        return 0 if report.get("status") == "running" else 2
    if "--install-bridge-shelf" in argv:
        args = [item for item in argv if item not in known]
        report = install_bridge_shelf_button(args[0] if args else None)
        _print_json(report)
        return 0 if report.get("status") == "success" else 2
    if "--install-ui-shelf" in argv:
        args = [item for item in argv if item not in known]
        report = install_ui_shelf_button(args[0] if args else None)
        _print_json(report)
        return 0 if report.get("status") == "success" else 2
    if "--check" in argv:
        args = [item for item in argv if item not in known]
        report = check(args[0] if args else None, write_log=True)
        _print_json(report)
        return 0 if report.get("can_accept") else 2
    launch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
