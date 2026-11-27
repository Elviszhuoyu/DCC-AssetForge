"""Assemble the public Win64 release from the verified host payloads."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from asset_forge import __version__
from scripts.audit_windows_assetforge_distribution import INSTALLER_RUNTIME, ReleaseAudit, check_setup_executable


SETUP_NAME = "DCC-AssetForge-Setup"
SETUP_PROJECT = REPO_ROOT / "tools/windows_setup/wpf/AssetForge.Setup.csproj"

PACKAGE_NAME = "DCC-AssetForge-v{}-Win64".format(__version__)
LEGAL_FILES = ("LICENSE", "NOTICE.md", "THIRD_PARTY_NOTICES.md", "BRAND_ASSET_POLICY.md")
PRIVATE_NAMES = frozenset((".git", "__pycache__", ".tmp", "node_modules", "docs", "AGENTS.md", "AssetForgeReports"))
SOURCE_ASSET_EXTENSIONS = frozenset((".pdb", ".pyc", ".uproject", ".fbx", ".ma", ".mb", ".blend", ".log"))
GUIDE_NAME = "安装指南.md"
UNREAL_RELEASES = ("5.6.1", "5.8.4")
UNREAL_STOCK_SAMPLE = "Content/Materials/M_AF_Props_Opaque_Master.uasset"
AUTOMATION_FILES = {
    "Install_DCC_AssetForge_Unreal.ps1": "install_assetforge_unreal.ps1",
    "Scripts/InstallUnreal.py": "install_assetforge_unreal_cli.py",
}
README = """# DCC AssetForge v{version} · Windows 64 位

1. 下载 ZIP 后，右键选择「全部解压缩」，请解压至纯英文、无空格的本地目录，避开 OneDrive 同步目录。
2. 双击解压目录里的 **DCC-AssetForge-Setup.exe**。请把整个 Payload 文件夹和 EXE 放在一起。
3. 选中要安装的软件，核对版本和位置，再点击安装。

如果 Windows 提示保护电脑，确认 ZIP 来自项目官方发布页后，点击「更多信息」，
再点「仍要运行」。[安装指南](安装指南.md)包含各软件的备用安装方式和第一次使用的步骤。

发行 ZIP 的校验值见同名 .zip.sha256 文件，解压文件的校验值见 SHA256SUMS.txt。
DCC-AssetForge-Setup.exe 的 SHA-256 为 `{setup_sha256}`。
"""


def _copy_unreal_runtime(plugin):
    src = REPO_ROOT / "Plugins" / "AssetForge"
    shutil.copytree(src / "Config", plugin / "Config")
    from asset_forge.unreal.distribution_installer import payload_file_allowed

    for resource in (src / "Resources").rglob("*"):
        relative = resource.relative_to(src)
        if resource.is_file() and payload_file_allowed(relative.as_posix()):
            target = plugin / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(resource, target)
    runtime = plugin / "Content" / "Python"
    runtime.mkdir(parents=True)
    shutil.copyfile(src / "Content" / "Python" / "init_unreal.py", runtime / "init_unreal.py")
    for name in ("asset_forge", "config"):
        shutil.copytree(REPO_ROOT / name, runtime / name, ignore=shutil.ignore_patterns(
            *PRIVATE_NAMES, "*.pyc", "*.local.*",
        ))
    for name in LEGAL_FILES:
        shutil.copyfile(REPO_ROOT / name, plugin / name)


def stage_unreal(stage, binary_roots, stock_roots, source_stock):
    """Copy only the listed stock assets and verified Win64 Editor outputs."""
    from asset_forge.unreal.distribution_installer import stock_asset_files
    from scripts.verify_unreal_release_binary import verify_dll

    expected_assets = sorted(stock_asset_files())
    source_descriptor = REPO_ROOT / "Plugins" / "AssetForge" / "AssetForge.uplugin"
    unreal = stage / "Payload" / "Unreal"
    unreal.mkdir(parents=True, exist_ok=False)
    for version in (*UNREAL_RELEASES, "Source"):
        plugin = unreal / version / "AssetForge"
        _copy_unreal_runtime(plugin)
        descriptor = json.loads(source_descriptor.read_text(encoding="utf-8"))
        stock = source_stock if version == "Source" else stock_roots[version]
        for name in expected_assets:
            target = plugin / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stock / name, target)

        if version == "Source":
            shutil.copytree(source_descriptor.parent / "Source", plugin / "Source")
            descriptor.pop("Installed", None)
            descriptor.pop("EngineVersion", None)
        else:
            bin_root, build_id, compat_version = binary_roots[version]
            module_name = "UnrealEditor-AssetForgeEditor.dll"
            binary = bin_root / module_name
            manifest = bin_root / "UnrealEditor.modules"
            metadata = json.loads(manifest.read_text(encoding="utf-8-sig"))
            if metadata.get("BuildId") != build_id or metadata.get("Modules") != {"AssetForgeEditor": module_name}:
                raise ValueError("Unreal module metadata does not match " + version)
            verification = verify_dll(binary.read_bytes(), (str(REPO_ROOT), str(Path.home())))
            if verification["status"] != "pass":
                raise ValueError("Unreal release DLL did not pass verification for " + version)
            win64 = plugin / "Binaries" / "Win64"
            win64.mkdir(parents=True)
            shutil.copyfile(binary, win64 / module_name)
            shutil.copyfile(manifest, win64 / manifest.name)
            descriptor["Installed"] = True
            descriptor["EngineVersion"] = compat_version

        (plugin / "AssetForge.uplugin").write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")


def _msbuild():
    programs = Path(os.environ["ProgramFiles(x86)"])
    version = programs / "Reference Assemblies/Microsoft/Framework/.NETFramework/v4.8"
    if not (version / "PresentationFramework.dll").is_file():
        raise FileNotFoundError(".NET Framework 4.8 Developer Pack (WPF) was not found.")
    vswhere = programs / "Microsoft Visual Studio/Installer/vswhere.exe"
    if vswhere.is_file():
        output = subprocess.check_output([
            str(vswhere), "-latest", "-products", "*", "-find", r"MSBuild\Current\Bin\MSBuild.exe", "-utf8",
        ], text=True, encoding="utf-8").splitlines()
        for value in output:
            executable = Path(value.strip())
            if executable.is_file():
                return executable
    configured = shutil.which("MSBuild.exe")
    if not configured:
        raise FileNotFoundError("Windows MSBuild with .NET Framework 4.8 support was not found.")
    return Path(configured)


def build_setup(cache):
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / "app"
    intermediate = cache / "obj"
    subprocess.run([
        str(_msbuild()), str(SETUP_PROJECT), "/nologo", "/restore:false", "/m:1",
        "/p:Configuration=Release", "/p:Platform=x64",
        f"/p:OutDir={target}{os.sep}", f"/p:BaseIntermediateOutputPath={intermediate}{os.sep}",
    ], check=True, cwd=SETUP_PROJECT.parent)
    executable = target / (SETUP_NAME + ".exe")
    check_setup_executable(executable)
    return executable


def stage_files(stage, *, include_checksums=True):
    if (stage / INSTALLER_RUNTIME).exists():
        raise ValueError("Cannot publish the retired installer runtime directory")
    unreal = "Payload/Unreal"
    required = [
        "Install_DCC_AssetForge_Maya.py",
        "Payload/Maya/asset_forge/__init__.py",
        f"{unreal}/Source/AssetForge/AssetForge.uplugin",
        f"{unreal}/Source/AssetForge/Source/AssetForgeEditor/AssetForgeEditor.Build.cs",
        f"{unreal}/Source/AssetForge/{UNREAL_STOCK_SAMPLE}",
    ]
    for version in UNREAL_RELEASES:
        plugin = f"{unreal}/{version}/AssetForge"
        required.extend((
            plugin + "/AssetForge.uplugin",
            plugin + "/Binaries/Win64/UnrealEditor.modules",
            plugin + "/Binaries/Win64/UnrealEditor-AssetForgeEditor.dll",
            plugin + "/" + UNREAL_STOCK_SAMPLE,
        ))
    source_payload = stage / unreal / "Source" / "AssetForge"
    if (source_payload / "Binaries").exists() or (source_payload / "Intermediate").exists():
        raise ValueError("The source payload contains build outputs")
    blender_zip = "Payload/Blender/DCC-AssetForge-Blender-v{}.zip".format(__version__)
    required.append(blender_zip)
    missing = [name for name in required if not (stage / name).is_file()]
    if missing:
        raise ValueError("Missing verified release payloads: " + ", ".join(missing))
    names = [SETUP_NAME + ".exe", "README.md", GUIDE_NAME, required[0], *AUTOMATION_FILES]
    if include_checksums:
        names.append("SHA256SUMS.txt")
    files = [stage / name for name in names]
    files.extend(stage / name for name in LEGAL_FILES)
    files.extend(sorted(file for file in (stage / "Payload").rglob("*") if file.is_file()))
    for file in files:
        relative = file.relative_to(stage)
        if stage not in file.resolve().parents or file.is_symlink() or _private_entry(relative):
            raise ValueError("Unexpected file in release payload: " + relative.as_posix())
    nested = stage / blender_zip
    with ZipFile(nested) as archive:
        if archive.testzip():
            raise ValueError("Blender archive CRC failed")
        for member in archive.namelist():
            part = PurePosixPath(member)
            if part.is_absolute() or ".." in part.parts or "\\" in member or _private_entry(part):
                raise ValueError("Unexpected file in Blender archive: " + member)
    return files


def _private_entry(path):
    return bool(PRIVATE_NAMES.intersection(path.parts)) or path.suffix.lower() in SOURCE_ASSET_EXTENSIONS


def _sha256(file):
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_install_entries(stage, setup):
    check_setup_executable(setup)
    target = stage / (SETUP_NAME + ".exe")
    shutil.copyfile(setup, target)
    for name in LEGAL_FILES:
        shutil.copyfile(REPO_ROOT / name, stage / name)
    shutil.copyfile(REPO_ROOT / GUIDE_NAME, stage / GUIDE_NAME)
    for destination, filename in AUTOMATION_FILES.items():
        path = stage / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / "scripts" / filename, path)
    readme = README.format(version=__version__, setup_sha256=_sha256(target))
    (stage / "README.md").write_text(readme, encoding="utf-8")
    lines = [
        "{}  {}\n".format(_sha256(file), file.relative_to(stage).as_posix())
        for file in stage_files(stage, include_checksums=False)
    ]
    (stage / "SHA256SUMS.txt").write_text("".join(lines), encoding="utf-8")


def archive_distribution(stage, output):
    output.mkdir(parents=True, exist_ok=True)
    files = stage_files(stage)
    archive = output / (PACKAGE_NAME + ".zip")
    pending = archive.with_suffix(".zip.part")
    if archive.exists() or pending.exists():
        raise FileExistsError(archive)
    with ZipFile(pending, "x", compression=ZIP_DEFLATED) as result:
        for file in files:
            result.write(file, file.relative_to(stage).as_posix())
    with ZipFile(pending) as result:
        bad = result.testzip()
        if bad:
            raise ValueError("Release archive CRC failed: " + bad)
    pending.replace(archive)
    archive.with_suffix(".zip.sha256").write_text(_sha256(archive) + "  " + archive.name + "\n", encoding="ascii")
    return archive


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-cache", type=Path, required=True)
    parser.add_argument("--machine-root", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    stage = args.stage.resolve(strict=True)
    if stage.name != PACKAGE_NAME:
        parser.error("The staging directory must be named " + PACKAGE_NAME)
    setup = build_setup(args.build_cache.resolve())
    stage_install_entries(stage, setup)
    audit = ReleaseAudit((REPO_ROOT, Path.home(), Path(sys.base_prefix), *args.machine_root)).scan(stage)
    if audit["status"] != "pass":
        parser.error("Public staging failed privacy verification.\n" + json.dumps(audit, indent=2))
    print(archive_distribution(stage, args.output.resolve()))


if __name__ == "__main__":
    main()
