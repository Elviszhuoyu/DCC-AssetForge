# -*- coding: utf-8 -*-
"""Drop the delivered copy of this file onto a Maya viewport to install AssetForge."""

import hashlib
import json
import os
import re
import runpy
import shutil
import sys
import tempfile

if sys.version_info[0] >= 3:
    from pathlib import Path, PurePosixPath


PRODUCT = "DCC AssetForge"
DISTRIBUTION_MANIFEST = "_assetforge_payload.json"
SHELF = "AssetForge"
BUTTON = "assetForgeMayaWorkbenchButton"
LAUNCHER = "scripts/maya_launch_asset_forge.py"
DESCRIPTOR = "integrations/maya/AssetForge.mod"


def _sha(path):
    with path.open("rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def _payload_paths(payload):
    manifest = json.loads((payload / DISTRIBUTION_MANIFEST).read_text(encoding="utf-8"))
    version = manifest.get("version", "")
    inventory = manifest.get("files")
    if (manifest.get("product") != PRODUCT or not re.fullmatch(r"\d+\.\d+\.\d+", version)
            or not isinstance(inventory, dict) or not {LAUNCHER, DESCRIPTOR, "asset_forge/__init__.py"} <= inventory.keys()):
        raise ValueError("安装包缺少有效的 Maya 文件清单。")
    paths = []
    for name, digest in inventory.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or ":" in name or "\\" in name:
            raise ValueError("安装包包含无效文件路径。")
        path = payload.joinpath(*relative.parts)
        if payload not in path.resolve().parents or not path.is_file() or _sha(path) != digest:
            raise ValueError("安装包文件不完整或校验失败，请重新解压发布包。")
        paths.append(path)
    return version, paths


def _install_files(payload, target, paths, backup):
    if target.exists():
        if target.resolve() != target or not (target / LAUNCHER).is_file():
            raise RuntimeError("现有安装目录归属无法确认，未替换该目录。")
        if all((target / path.relative_to(payload)).is_file()
               and _sha(target / path.relative_to(payload)) == _sha(path) for path in paths):
            return None
    with tempfile.TemporaryDirectory(prefix="install-", dir=target.parent) as directory:
        staged = Path(directory) / "payload"
        for source in paths:
            destination = staged / source.relative_to(payload)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if _sha(destination) != _sha(source):
                raise OSError("复制后的文件校验失败。")
        if target.is_dir():
            for preset in target.rglob("*.assetforge.json"):
                destination = staged / preset.relative_to(target)
                if preset.is_file() and target in preset.resolve().parents and not destination.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(preset, destination)
            prior = backup / target.name
            os.rename(target, prior)
            try:
                os.rename(staged, target)
            except OSError:
                os.rename(prior, target)
                raise
            return prior
        os.rename(staged, target)
        return None


def _atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".assetforge-", delete=False) as stream:
        pending = Path(stream.name)
        stream.write(data)
    try:
        os.replace(pending, path)
    finally:
        if pending.exists():
            pending.unlink()


def _backup(original, folder):
    if original is not None:
        _atomic_bytes(folder / original.name, original.read_bytes())


def _find_owned_shelf_button(cmds):
    if not cmds.shelfLayout(SHELF, exists=True):
        return ""
    children = cmds.shelfLayout(SHELF, query=True, childArray=True) or ()
    if not children:
        # Maya creates tabs at startup but lazily loads their saved buttons.
        from maya import mel

        mel.eval('loadNamedShelf("AssetForge")')
        children = cmds.shelfLayout(SHELF, query=True, childArray=True) or ()
    owned = []
    for child in children:
        if cmds.shelfButton(child, exists=True):
            command = cmds.shelfButton(child, query=True, command=True)
            if isinstance(command, str) and "maya_launch_asset_forge.py" in command and "bootstrap" in command:
                owned.append(child)
    if len(owned) > 1:
        raise RuntimeError("工具架有多个 DCC AssetForge 按钮。请保留一个后再更新。")
    return owned[0] if owned else ""


def _user_shelf_file(cmds, app):
    # userShelfDir can include third-party search entries; write only into Maya's own prefs.
    prefs = Path(cmds.internalVar(userPrefDir=True)).resolve()
    if prefs != app and app not in prefs.parents:
        raise RuntimeError("Maya 用户首选项与当前安装目录不一致。")
    return prefs / "shelves" / ("shelf_" + SHELF + ".mel")


def _maya_paths(cmds):
    maya_year = str(cmds.about(version=True)).split(".", 1)[0]
    if maya_year not in ("2022", "2023", "2024", "2025", "2026"):
        raise RuntimeError("此工具需要 Maya 2022 至 2026 的 Python 3 模式。Maya 2020 的 Python 2 不受支持。")
    app = Path(os.environ.get("MAYA_APP_DIR") or cmds.internalVar(userAppDir=True)).resolve()
    return (app / "DCC AssetForge" / "Maya",
            app / maya_year / "modules" / "DCC_AssetForge_Local.mod",
            _user_shelf_file(cmds, app))


def _owned_module(module, install_home):
    if not module.exists():
        return None
    if module.resolve() != module:
        raise RuntimeError("Maya 模块目录使用链接，未修改现有文件。")
    data = module.read_bytes()
    lines = data.decode("utf-8-sig").splitlines()
    link = re.fullmatch(r"\+ AssetForge \d+\.\d+\.\d+ (.+)", lines[0] if lines else "")
    if not link or Path(link[1]).parent.resolve() != install_home.resolve():
        raise RuntimeError("Maya 模块目录存在同名文件，未替换其他模块。")
    return data


def install(payload, cmds):
    payload = Path(payload).resolve()
    version, paths = _payload_paths(payload)
    install_home, module, shelf_file = _maya_paths(cmds)
    install_home.mkdir(parents=True, exist_ok=True)
    if install_home.resolve() != install_home or shelf_file.resolve() != shelf_file:
        raise RuntimeError("Maya 用户安装位置使用链接，未修改现有文件。")
    target = install_home / version
    shelf_existed = cmds.shelfLayout(SHELF, exists=True)
    old_button = _find_owned_shelf_button(cmds)
    if cmds.shelfButton(BUTTON, exists=True) and not old_button:
        raise RuntimeError("有其他工具占用 AssetForge 安装按钮名称，未替换该按钮。")
    descriptor = (payload / DESCRIPTOR).read_text(encoding="utf-8").splitlines()
    descriptor[0] = "+ AssetForge {0} {1}".format(version, target.as_posix())
    module_text = ("\n".join(descriptor) + "\n").encode("utf-8")
    old_module = _owned_module(module, install_home)
    old_shelf = shelf_file.read_bytes() if shelf_file.exists() else None
    shelf_args = ("command", "sourceType", "image", "image1", "annotation", "label",
                  "imageOverlayLabel", "overlayLabelColor", "overlayLabelBackColor")
    old_properties = ({flag: cmds.shelfButton(old_button, query=True, **{flag: True}) for flag in shelf_args}
                      if old_button else {})
    backup = (Path(tempfile.mkdtemp(prefix="backup-", dir=install_home))
              if old_shelf or old_module or target.exists() else None)
    if backup:
        _backup(shelf_file if old_shelf is not None else None, backup)
        _backup(module if old_module is not None else None, backup)
    prior = _install_files(payload, target, paths, backup)
    button = ""
    try:
        launcher = runpy.run_path(str(target / LAUNCHER))
        _atomic_bytes(module, module_text)
        shelf = launcher["install_ui_shelf_button"](repo_root=str(target), shelf_name=SHELF, existing_button=old_button)
        button = shelf["button"]
        expected = launcher["_ui_shelf_command"](str(target))
        if cmds.shelfButton(button, query=True, command=True) != expected:
            raise OSError("Maya 工具架按钮未指向已校验的安装目录。")
        shelf_file.parent.mkdir(parents=True, exist_ok=True)
        cmds.saveShelf(shelf["shelf"], str(shelf_file.with_suffix("")))
        if not shelf_file.is_file() or b"maya_launch_asset_forge.py" not in shelf_file.read_bytes():
            raise OSError("Maya 未能保存 AssetForge 工具架。")
    except Exception:
        try:
            if old_button:
                cmds.shelfButton(old_button, edit=True, **old_properties)
            elif not shelf_existed and cmds.shelfLayout(SHELF, exists=True):
                cmds.deleteUI(SHELF)
            elif button and cmds.shelfButton(button, exists=True):
                cmds.deleteUI(button)
        finally:
            for path, data in ((module, old_module), (shelf_file, old_shelf)):
                if data is not None:
                    _atomic_bytes(path, data)
                elif path.is_file():
                    path.unlink()
            if prior is not None:
                os.rename(target, backup / "replacement")
                os.rename(prior, target)
        raise
    return {"version": version, "runtime": str(target), "module": str(module),
            "shelf": str(shelf_file), "button": button, "backup": str(backup) if backup else ""}


def uninstall(cmds):
    install_home, module, shelf_file = _maya_paths(cmds)
    if install_home.resolve() != install_home or shelf_file.resolve() != shelf_file:
        raise RuntimeError("Maya 用户安装位置使用链接，未修改现有文件。")
    old_module = _owned_module(module, install_home)
    button = _find_owned_shelf_button(cmds)
    if old_module is None and not button:
        raise RuntimeError("此 Maya 版本未安装 DCC AssetForge。")
    install_home.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="uninstall-", dir=install_home))
    shelf_before = shelf_file.read_bytes() if shelf_file.is_file() else None
    _backup(shelf_file if shelf_before is not None else None, backup)
    _backup(module if old_module is not None else None, backup)
    try:
        if button:
            cmds.deleteUI(button)
            cmds.saveShelf(SHELF, str(shelf_file.with_suffix("")))
        if old_module is not None:
            module.unlink()
    except Exception:
        if shelf_before is not None:
            _atomic_bytes(shelf_file, shelf_before)
        if old_module is not None:
            _atomic_bytes(module, old_module)
        raise
    workspace = "assetForgePublishWorkspace"
    if cmds.workspaceControl(workspace, exists=True):
        cmds.deleteUI(workspace)
        if cmds.optionVar(exists="workspacesAutoSave") and cmds.optionVar(query="workspacesAutoSave"):
            cmds.workspaceLayoutManager(save=True)
    # Other Maya versions and saved layouts may still reference the versioned runtime.
    return {"backup": str(backup)}


def onMayaDroppedPythonFile(*_unused):
    from maya import cmds

    if sys.version_info[0] < 3:
        cmds.warning(u"DCC AssetForge 需要 Maya 2022 至 2026 的 Python 3 模式。")
        return False
    entry_parent = Path(__file__).resolve().parent
    drop_dir = Path(sys.path[0]).resolve() if sys.path else entry_parent
    if (drop_dir / Path(__file__).name).is_file() and (drop_dir / "Payload" / "Maya").is_dir():
        entry_parent = drop_dir
    try:
        installed = install(entry_parent / "Payload" / "Maya", cmds)
    except (OSError, RuntimeError, ValueError) as exc:
        cmds.warning("{0} 安装未完成：{1}".format(PRODUCT, exc))
        return False
    cmds.inViewMessage(amg="DCC AssetForge v{0} 已安装。请打开 AssetForge 工具架。".format(installed["version"]),
                       pos="topCenter", fade=True)
    return True
