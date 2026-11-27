"""Stage the native Maya drop installer and Blender extension ZIP for local delivery."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import runpy
import shutil
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile


REPO = Path(__file__).resolve().parents[1]
RESOURCES = Path("Plugins/AssetForge/Resources")
CORE_TREES = (Path("asset_forge"), Path("config"))
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".git", "AssetForgeReports", "node_modules", "docs", "AGENTS.md", "*.local.*",
)
MAYA_RUNTIME = tuple(Path("integrations/maya_mcp_runtime") / name
                     for name in ("__init__.py", "ports.py", "registry.py"))


def _copy(source, root):
    destination = root / source
    destination.parent.mkdir(parents=True, exist_ok=True)
    if (REPO / source).is_dir():
        shutil.copytree(REPO / source, destination, ignore=IGNORE)
    else:
        shutil.copy2(REPO / source, destination)


def _assets(root):
    for icon in sorted((REPO / RESOURCES).glob("*.png")):
        _copy(icon.relative_to(REPO), root)


def _maya(root, version):
    for path in CORE_TREES + MAYA_RUNTIME + (Path("integrations/maya"),
                                              Path("scripts/maya_launch_asset_forge.py"),
                                              RESOURCES / "Workbench", Path("LICENSE")):
        _copy(path, root)
    _assets(root)
    files = {path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
             for path in sorted(root.rglob("*")) if path.is_file()}
    (root / "_assetforge_payload.json").write_text(
        json.dumps({"product": "DCC AssetForge", "version": version, "files": files}, indent=2) + "\n",
        encoding="utf-8",
    )


BLENDER_BOOTSTRAP = '''"""Resolve this installed Blender extension's bundled runtime."""

from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parent / "runtime"


def configure():
    current = sys.modules.get("asset_forge")
    source = getattr(current, "__file__", "") if current else ""
    if source and not Path(source).resolve().is_relative_to(ROOT):
        raise RuntimeError("Blender 已加载另一份 DCC AssetForge。请禁用旧插件并重启后启用本扩展。")
    runtime = str(ROOT)
    if runtime not in sys.path:
        sys.path.insert(0, runtime)
    os.environ["ASSET_FORGE_REPO_ROOT"] = runtime
    return runtime


def user_report_root():
    import bpy

    return bpy.utils.extension_path_user(__package__, path="AssetForgeReports", create=True)
'''


def _blender(archive_path, version, workspace):
    source = REPO / "integrations" / "blender" / "asset_forge_extension"
    addon = workspace / "blender"
    runtime = addon / "runtime"
    shutil.copytree(source, addon, ignore=IGNORE)
    for path in CORE_TREES + (Path("integrations/blender_mcp"), Path("integrations/blender_mcp_runtime")):
        _copy(path, runtime)
    _assets(runtime)
    shutil.copy2(REPO / "LICENSE", addon / "LICENSE")
    (addon / "_asset_forge_bootstrap.py").write_text(BLENDER_BOOTSTRAP, encoding="utf-8")
    descriptor = (addon / "blender_manifest.toml").read_text(encoding="utf-8")
    if 'version = "{0}"'.format(version) not in descriptor.splitlines():
        raise ValueError("Blender manifest and distribution version differ")
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        for path in sorted(addon.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(addon).as_posix())


def stage(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    version = runpy.run_path(str(REPO / "asset_forge" / "__init__.py"))["__version__"]
    if not (REPO / "integrations" / "maya" / "AssetForge.mod").read_text(
            encoding="utf-8").startswith("+ AssetForge {0} ".format(version)):
        raise ValueError("Maya module and distribution version differ")
    payload = output / "Payload"
    maya = payload / "Maya"
    drop = output / "Install_DCC_AssetForge_Maya.py"
    blender = payload / "Blender" / "DCC-AssetForge-Blender-v{0}.zip".format(version)
    for path in (maya, drop, blender):
        if path.exists():
            raise FileExistsError(path)
    with tempfile.TemporaryDirectory(prefix=".dcc-stage-", dir=output) as directory:
        work = Path(directory)
        staged_maya = work / "maya"
        staged_maya.mkdir()
        _maya(staged_maya, version)
        staged_blender = work / "blender.zip"
        _blender(staged_blender, version, work)
        staged_drop = work / drop.name
        shutil.copy2(REPO / "scripts" / "install_assetforge_maya.py", staged_drop)
        blender.parent.mkdir(parents=True, exist_ok=True)
        staged_maya.rename(maya)
        staged_blender.rename(blender)
        staged_drop.rename(drop)
    return {"version": version, "maya": str(drop), "blender": str(blender)}


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(stage(parser.parse_args().output), ensure_ascii=False, indent=2))
