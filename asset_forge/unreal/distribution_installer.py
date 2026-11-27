"""Plan and apply Windows editor plugin changes to a selected engine or project."""

import contextlib
import csv
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile


RELEASE_VERSION = "0.2.0"
ENGINE_VERSION = (5, 8, 4)
# The plugin manager compares the descriptor with the engine ABI compatibility floor.
PLUGIN_COMPATIBLE_ENGINE_VERSION = "5.8.0"
BUILD_ID = "55116800"
PLUGIN_NAME = "AssetForge"
MODULE_NAME = "AssetForgeEditor"
EDITOR_IMAGES = ("UnrealEditor.exe", "UnrealEditor-Cmd.exe")

MODULES_FILE = "Binaries/Win64/UnrealEditor.modules"
MODULE_BINARY = "Binaries/Win64/UnrealEditor-AssetForgeEditor.dll"
SOURCE_RULES = "Source/AssetForgeEditor/AssetForgeEditor.Build.cs"
SOURCE_SUFFIXES = (".cs", ".cpp", ".h", ".inl")


@lru_cache(maxsize=1)
def stock_asset_files():
    from asset_forge.unreal.material_package_schema import get_default_material_package_plan

    plan = get_default_material_package_plan()
    groups = ("placeholder_textures", "materials", "material_instances", "functions", "parameter_collections")
    prefix = "/AssetForge/"
    return frozenset(
        "Content/" + entry["path"][len(prefix):] + ".uasset"
        for group in groups for entry in plan[group] if entry["path"].startswith(prefix)
    )


REQUIRED_FILES = stock_asset_files() | frozenset((
    "AssetForge.uplugin",
    MODULES_FILE,
    MODULE_BINARY,
    "Content/Python/init_unreal.py",
    "Content/Python/asset_forge/__init__.py",
    "Content/Python/asset_forge/unreal/editor_menu.py",
    "Content/Python/asset_forge/unreal/review_workbench.py",
    "Content/Python/asset_forge/shared/__init__.py",
    "Content/Python/config/import_presets.json",
    "Content/Python/config/material_profiles.json",
    "Content/Python/config/project_rules.json",
    "Resources/Workbench/brand/af_shelf.png",
    "LICENSE",
    "NOTICE.md",
    "THIRD_PARTY_NOTICES.md",
    "BRAND_ASSET_POLICY.md",
    "Config/FilterPlugin.ini",
    "Content/Python/config/project_settings.example.json",
))


class InstallProblem(RuntimeError):
    def __init__(self, message, needs_engine_root=False):
        super().__init__(message)
        self.needs_engine_root = needs_engine_root


def plan_install(project_file, payload_plugin_dir, engine_root=None, *, source=False, engine_install=False, check_running=True):
    """Inspect the target and select a compatible payload without writing."""
    result = _result()
    try:
        _plan(project_file, payload_plugin_dir, engine_root, result, source, engine_install, check_running)
    except (InstallProblem, OSError, ValueError) as error:
        return _failure(result, error)
    if result["payload_mode"] == "source":
        message = "可安装源码。打开工程后，按 Unreal 提示编译插件。"
    else:
        message = "已找到匹配的预编译插件，可以直接安装。"
    result.update(status="ready", message=message)
    return result


def install(project_file, payload_plugin_dir, engine_root=None, *, source=False, engine_install=False):
    """Stage, verify and swap the plugin while retaining a recoverable backup."""
    result = _result()
    try:
        project, target, files, original, updated, engine = _plan(
            project_file, payload_plugin_dir, engine_root, result, source, engine_install,
        )
        _publish(project, target, files, original, updated, result, engine)
    except (InstallProblem, OSError, ValueError) as error:
        return _failure(result, error)
    if engine_install:
        message = "安装完成。打开工程，在「编辑 → 插件」搜索 DCC AssetForge 并启用。"
    elif result["payload_mode"] == "source":
        message = "源码安装完成。打开工程，按 Unreal 提示编译插件。若提示缺少编译工具，请查看安装指南。"
    else:
        message = "安装完成。重新打开此工程，点击工具栏的 AF 图标。"
    result.update(status="success", message=message, enabled_in_project=not engine_install)
    return result


def uninstall(project_file=None, engine_root=None, *, engine_install=False):
    """Remove the owned plugin and its project reference after making a backup."""
    result = _result()
    try:
        project, target, original, descriptor, _ = _target(project_file, engine_root, engine_install, result)
        if target.exists():
            plugin = _decode_object((target / "AssetForge.uplugin").read_bytes(), "现有插件描述文件")
            if plugin.get("FriendlyName") != "DCC AssetForge":
                raise InstallProblem("该位置的插件归属无法确认，未移动原目录。")
        updated = _disable_plugin(descriptor, original) if project else None
        _check_project_closed(project)
        if not target.exists() and updated == original:
            raise InstallProblem("此位置没有需要卸载的 DCC AssetForge。")
        _publish(project, target, None, original, updated, result, None)
    except (InstallProblem, OSError, ValueError) as error:
        return _failure(result, error)
    result.update(status="success", message="已卸载此位置的 DCC AssetForge，原文件已备份。")
    return result


def payload_file_allowed(relative, source=False):
    """Limit installation to the product's runtime and shipped assets."""
    if source and relative in (MODULES_FILE, MODULE_BINARY):
        return False
    if relative in REQUIRED_FILES:
        return True
    if source and relative.startswith("Source/AssetForgeEditor/"):
        return Path(relative).suffix in SOURCE_SUFFIXES
    if relative.startswith("Content/Python/asset_forge/"):
        return relative.endswith(".py") and "/__pycache__/" not in relative
    return relative.startswith("Resources/") and Path(relative).suffix in (
        ".png", ".html", ".css", ".js", ".txt",
    )


def _target(project_file, engine_root, engine_install, result):
    if engine_install:
        if not engine_root:
            raise InstallProblem("请选择要安装插件的 Unreal Engine。", needs_engine_root=True)
        engine = _engine_info(engine_root)
        base = engine["root"] / "Engine"
        target = base / "Plugins" / "Marketplace" / PLUGIN_NAME
        project = original = descriptor = None
    else:
        project = Path(project_file or ".").absolute()
        if project.suffix.lower() != ".uproject" or not project.is_file():
            raise InstallProblem("请选择 Unreal 工程文件（.uproject）。")
        _reject_redirect(project)
        project = project.resolve(strict=True)
        base = project.parent
        target = base / "Plugins" / PLUGIN_NAME
        original = project.read_bytes()
        descriptor = _decode_object(original, "UE 工程描述文件")
        engine = None

    for path in reversed((target,) + tuple(parent for parent in target.parents if base in parent.parents)):
        _reject_redirect(path)
        if path.exists() and not path.is_dir():
            raise InstallProblem("插件安装路径被文件占用。请恢复目录后重试。")
    result.update(project_file=str(project) if project else "", target_plugin_dir=str(target),
                  requires_backup=target.exists())
    return project, target, original, descriptor, engine


def _plan(project_file, payload_plugin_dir, engine_root, result, source, engine_install, check_running=True):
    project, target, original, descriptor, engine = _target(project_file, engine_root, engine_install, result)
    if project:
        engine = _select_engine(descriptor, engine_root, project)
        updated = _enable_plugin(descriptor, original)
    else:
        updated = None
    result.update(engine_root=str(engine["root"]), engine_version=engine["version_text"], build_id=engine["build_id"])
    payload = Path(payload_plugin_dir or ".").absolute()
    _reject_redirect(payload)
    payload = payload.resolve()
    root, source = _select_payload(payload, engine, source, engine_install, result)
    if root == target or root in target.parents or target in root.parents:
        raise InstallProblem("安装来源与目标插件目录重叠。请从独立解压的发行包重新打开安装助手。")
    files = _payload_files(root, engine, source)
    result["payload_mode"] = "source" if source else "binary"
    if check_running:
        _check_project_closed(project)
    return project, target, files, original, updated, engine


def _select_payload(payload, engine, source, engine_install, result):
    if (payload / "AssetForge.uplugin").is_file():
        if engine["version"] != ENGINE_VERSION or engine["build_id"] != BUILD_ID:
            raise InstallProblem("此 Unreal 的版本或构建编号与单版本插件不匹配。请选择匹配的引擎。")
        return payload, False
    binary = payload / engine["version_text"] / PLUGIN_NAME
    source_root = payload / "Source" / PLUGIN_NAME
    _reject_redirect(binary.parent)
    _reject_redirect(binary)
    _reject_redirect(source_root.parent)
    _reject_redirect(source_root)
    if not source and (binary / MODULES_FILE).is_file() and engine["build_id"]:
        manifest = binary / MODULES_FILE
        _reject_redirect(manifest)
        if _decode_object(manifest.read_bytes(), "插件构建信息").get("BuildId") == engine["build_id"]:
            return binary, False
    if (source_root / "AssetForge.uplugin").is_file():
        result["source_available"] = True
        if engine_install:
            raise InstallProblem("此引擎没有匹配的预编译插件。切换到「安装到 UE 工程」后可选择源码安装。")
        if source:
            return source_root, True
        raise InstallProblem("此引擎没有匹配的预编译插件。可选择「源码安装」，由 Unreal 编译。")
    raise InstallProblem("未找到适用于此引擎的插件文件。请确认发行包已完整解压。")


def _decode_object(data, name):
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as error:
        raise InstallProblem("{}无法读取。请检查文件完整性。".format(name)) from error
    if not isinstance(obj, dict):
        raise InstallProblem("{}格式不受支持。".format(name))
    return obj


def _enable_plugin(descriptor, original):
    plugins = descriptor.setdefault("Plugins", [])
    if not isinstance(plugins, list) or any(not isinstance(plugin, dict) for plugin in plugins):
        raise InstallProblem("工程的插件列表格式不受支持。请先在 Unreal Editor 中恢复工程设置。")
    entries = [item for item in plugins if str(item.get("Name", "")).casefold() == PLUGIN_NAME.casefold()]
    if len(entries) > 1:
        raise InstallProblem("工程中有重复的 AssetForge 插件设置。请先在 Unreal Editor 中修正。")
    if not entries:
        plugins.append({"Name": PLUGIN_NAME, "Enabled": True})
    elif entries[0].get("Enabled") is True:
        return original
    else:
        entries[0]["Enabled"] = True
    return (json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _disable_plugin(descriptor, original):
    plugins = descriptor.get("Plugins", [])
    if not isinstance(plugins, list) or any(not isinstance(plugin, dict) for plugin in plugins):
        raise InstallProblem("工程的插件列表格式无法识别。请先在 Unreal Editor 中恢复工程设置。")
    kept = [item for item in plugins if str(item.get("Name", "")).casefold() != PLUGIN_NAME.casefold()]
    if len(kept) == len(plugins):
        return original
    descriptor["Plugins"] = kept
    return (json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _engine_info(engine_root):
    root = Path(engine_root).resolve()
    if root.name.casefold() == "engine":
        root = root.parent
    engine = root / "Engine"
    _reject_redirect(engine)
    binary = engine / "Binaries" / "Win64"
    build_file = engine / "Build" / "Build.version"
    modules_file = binary / "UnrealEditor.modules"
    if not build_file.is_file() or not (binary / "UnrealEditor.exe").is_file():
        raise InstallProblem("请选择包含 Unreal Editor 的完整引擎文件夹。", needs_engine_root=True)
    version = _decode_object(build_file.read_bytes(), "Unreal Engine 版本信息")
    found = tuple(version.get(key) for key in ("MajorVersion", "MinorVersion", "PatchVersion"))
    if not all(type(value) is int for value in found) or found[0] != 5 or not 3 <= found[1] <= 8 or found[2] < 0:
        raise InstallProblem("此版本超出本发行包支持范围。请选择 Windows UE 5.3 至 5.8。")
    modules = _decode_object(modules_file.read_bytes(), "Unreal Editor 构建信息") if modules_file.is_file() else {}
    build_id = modules.get("BuildId") or ""
    return dict(root=root, version=found, version_text=".".join(map(str, found)), build_id=build_id)


def _select_engine(descriptor, engine_root, project):
    association = descriptor.get("EngineAssociation", "")
    if not isinstance(association, str):
        raise InstallProblem("UE 工程的引擎关联无法识别。请在 Unreal 中检查此工程的引擎版本。")
    association = association.strip()
    registered = _discover_engines()
    detected = registered.get(association.casefold())
    numeric = re.fullmatch(r"\d+\.\d+(?:\.\d+)?", association)
    if not detected and numeric:
        detected = registered.get(".".join(association.split(".")[:2]))
    if not detected and not association:
        detected = next((parent for parent in project.parents if (parent / "Engine" / "Build" / "Build.version").is_file()), None)
    if detected and not (Path(detected) / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe").is_file():
        detected = None
    chosen = engine_root or detected
    if not chosen:
        raise InstallProblem("未找到此工程关联的 Unreal。请选择工程实际使用的引擎目录。", needs_engine_root=True)
    chosen_root = Path(chosen).resolve()
    if chosen_root.name.casefold() == "engine":
        chosen_root = chosen_root.parent
    if detected and chosen_root != Path(detected).resolve():
        raise InstallProblem("此工程已关联另一处 Unreal 安装。请选择工程当前关联的引擎目录。")
    engine = _engine_info(chosen_root)
    if numeric and not (engine["version_text"] == association or
                        engine["version_text"].rsplit(".", 1)[0] == association):
        raise InstallProblem("此工程关联 UE {}。请选择对应的引擎目录。".format(association))
    return engine


def discover_engines():
    """Return usable registered UE installations, one row per directory."""
    engines = {}
    for path in _discover_engines().values():
        try:
            engine = _engine_info(path)
        except (InstallProblem, OSError, ValueError):
            # A stale or unsupported registration is not an installation target.
            continue
        engines[engine["root"]] = engine
    return sorted(engines.values(), key=lambda item: (item["version"], str(item["root"])), reverse=True)


def _discover_engines():
    found = {}
    base = os.environ.get("ProgramData")
    if base:
        index = Path(base) / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat"
        if index.is_file():
            try:
                entries = _decode_object(index.read_bytes(), "Epic Launcher 安装列表").get("InstallationList", [])
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, dict):
                            name = entry.get("AppName", "")
                            location = entry.get("InstallLocation", "")
                            if isinstance(name, str) and name.startswith("UE_") and isinstance(location, str) and location:
                                found[name[3:].casefold()] = location
            except (InstallProblem, OSError):
                # A stale launcher index leaves manual engine selection available.
                pass
    if os.name != "nt":
        return found
    import winreg

    subkey = r"SOFTWARE\Epic Games\Unreal Engine\Builds"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
            for index in range(winreg.QueryInfoKey(key)[1]):
                name, location, value_type = winreg.EnumValue(key, index)
                if value_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and location:
                    found.setdefault(name.casefold(), os.path.expandvars(location))
    except (FileNotFoundError, PermissionError):
        # Launcher registrations and manual directory selection remain available.
        pass
    for minor in range(3, 9):
        version = f"5.{minor}"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\EpicGames\Unreal Engine\{version}") as key:
                location, _ = winreg.QueryValueEx(key, "InstalledDirectory")
                if location:
                    found.setdefault(version, location)
        except (FileNotFoundError, PermissionError):
            # Some Launcher versions register only in LauncherInstalled.dat.
            continue
    return found


def _payload_files(root, engine, source):
    if not root.is_dir():
        raise InstallProblem("缺少 UE 插件文件。请把发行包解压完整后重新打开安装助手。")
    files = {}
    for folder, directories, names in os.walk(root, onerror=_raise):
        for name in directories + names:
            path = Path(folder) / name
            _reject_redirect(path)
        for name in names:
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            if not path.is_file() or not payload_file_allowed(relative, source):
                raise InstallProblem("UE 安装包包含不受支持的文件。请重新解压完整发行包。")
            files[relative] = path
    required = (REQUIRED_FILES - {MODULES_FILE, MODULE_BINARY}) | {SOURCE_RULES} if source else REQUIRED_FILES
    if required - files.keys():
        raise InstallProblem("UE 插件文件不完整。请重新解压完整发行包。")
    descriptor = _decode_object(files["AssetForge.uplugin"].read_bytes(), "AssetForge 插件描述")
    if descriptor.get("VersionName") != RELEASE_VERSION or descriptor.get("Version") != 2:
        raise InstallProblem("AssetForge 插件版本与安装助手不匹配。请重新解压同一份发行包。")
    if source:
        if descriptor.get("EngineVersion") or descriptor.get("Installed"):
            raise InstallProblem("源码插件包含预编译版本配置。请使用同一发行包附带的源码插件。")
    else:
        modules = _decode_object(files[MODULES_FILE].read_bytes(), "AssetForge 插件构建信息")
        compatible = "{}.{}.0".format(*engine["version"])
        if descriptor.get("EngineVersion") != compatible or descriptor.get("Installed") is not True:
            raise InstallProblem("此插件版本与所选 Unreal 不匹配。请重新解压同一份发行包。")
        if (modules.get("BuildId") != engine["build_id"]
                or modules.get("Modules") != {MODULE_NAME: Path(MODULE_BINARY).name}):
            raise InstallProblem("此 AssetForge 插件的二进制不适用于所选 Unreal。请重新解压正确的发行包。")
    return files


def _raise(error):
    raise error


def _reject_redirect(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise InstallProblem("安装路径包含重定向目录或链接。请选择工程与安装包的实际路径。")


def _check_project_closed(project):
    for command in _editor_commands():
        opened = _project_from_editor_command(command)
        if project is None or not opened or not opened.is_absolute() or opened.resolve() == project:
            raise InstallProblem("请关闭目标工程的 Unreal Editor 后重试。" if project else
                                 "请关闭 Unreal Editor 后重试。引擎插件更新期间请保持编辑器关闭。")


def _project_from_editor_command(command):
    for value in re.findall(r'(?:[^\s"]+|"[^"]*")+', command or ""):
        value = value.replace('"', "")
        if value.casefold().startswith("-project="):
            value = value.split("=", 1)[1]
        if value.casefold().endswith(".uproject"):
            return Path(value)
    return None


def _editor_commands():
    if os.name != "nt":
        return []
    command = (
        "$ErrorActionPreference='Stop'; "
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "
        "$rows=@(Get-CimInstance Win32_Process -Filter "
        "\"Name='UnrealEditor.exe' OR Name='UnrealEditor-Cmd.exe'\" | "
        "Select-Object CommandLine); ConvertTo-Json -InputObject $rows -Compress"
    )
    system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    powershell = system / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    options = {"stdin": subprocess.DEVNULL, "capture_output": True, "timeout": 8,
               "creationflags": subprocess.CREATE_NO_WINDOW}
    try:
        probe = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", command], **options,
        )
        if probe.returncode == 0:
            rows = json.loads(probe.stdout.decode("utf-8-sig"))
            if isinstance(rows, list):
                return [row.get("CommandLine") if isinstance(row, dict) else None for row in rows]
    except (subprocess.SubprocessError, OSError, ValueError):
        # If WMI cannot see command lines, fall back to checking whether any editor exists.
        pass
    for name in EDITOR_IMAGES:
        try:
            probe = subprocess.run([str(system / "tasklist.exe"), "/FI", "IMAGENAME eq " + name, "/FO", "CSV", "/NH"], **options)
            if probe.returncode != 0:
                raise OSError("tasklist failed")
        except (subprocess.SubprocessError, OSError) as error:
            raise InstallProblem("无法确认工程是否已关闭。请关闭 Unreal Editor 后重新打开安装器。") from error
        output = probe.stdout.decode("ascii", errors="replace").splitlines()
        if any(row and row[0].casefold() == name.casefold() for row in csv.reader(output)):
            return [None]
    return []


def _publish(project, target, files, original, updated, result, engine):
    backup_base = project.parent if project else target.parents[2]
    for directory in ("Saved", "AssetForge", "InstallerBackups"):
        backup_base = backup_base / directory
        _reject_redirect(backup_base)
        backup_base.mkdir(exist_ok=True)

    with _install_lock(backup_base / "install.lock"):
        with tempfile.TemporaryDirectory(prefix="assetforge_stage_", dir=backup_base) as temp:
            stage = Path(temp)
            stage_plugin = stage / PLUGIN_NAME if files is not None else None
            if stage_plugin is not None:
                for relative, source in files.items():
                    _reject_redirect(source)
                    staged = stage_plugin / relative
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, staged)
                _payload_files(stage_plugin, engine, result["payload_mode"] == "source")
                _carry_presets(target, stage_plugin)
            stage_project = stage / project.name if project and updated != original else None
            if stage_project:
                stage_project.write_bytes(updated)

            _check_project_closed(project)
            _reject_redirect(target.parent)
            _reject_redirect(target)
            if project:
                _reject_redirect(project)
                if project.read_bytes() != original:
                    raise InstallProblem("工程设置在操作过程中发生了变化。请重新选择工程后重试。")
            backup = Path(tempfile.mkdtemp(prefix="prior_", dir=backup_base))
            if project:
                (backup / project.name).write_bytes(original)
            result["backup_dir"] = str(backup)
            if stage_plugin is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
            _swap(stage_plugin, stage_project, target, project, backup)


def _carry_presets(target, stage_plugin):
    if not target.is_dir():
        return
    for preset in target.rglob("*.assetforge.json"):
        relative = preset.relative_to(target)
        for depth in range(len(relative.parts)):
            _reject_redirect(target.joinpath(*relative.parts[:depth + 1]))
        destination = stage_plugin / relative
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(preset, destination)


@contextlib.contextmanager
def _install_lock(path):
    try:
        path.mkdir()
    except FileExistsError as error:
        raise InstallProblem("此工程已有安装操作。请等待完成后再试。") from error
    try:
        yield
    finally:
        path.rmdir()


def _swap(incoming, staged_project, target, project, backup):
    previous = backup / PLUGIN_NAME
    if target.exists():
        os.replace(target, previous)

    published = False
    try:
        if incoming is not None:
            os.replace(incoming, target)
            published = True
        if staged_project is not None:
            os.replace(staged_project, project)
    except OSError:
        try:
            if published:
                os.replace(target, incoming)
            if previous.exists():
                os.replace(previous, target)
        except OSError as rollback_error:
            raise InstallProblem("安装未完成，自动恢复遇到文件占用。原工程备份仍保存在安装报告所示目录。") from rollback_error
        raise InstallProblem("安装未完成，已保留原工程和插件。请确认工程关闭且目录可写后重试。")


def _result():
    return dict(status="error", message="", project_file="", engine_root="", target_plugin_dir="",
                build_id="", requires_backup=False, backup_dir="", enabled_in_project=False,
                needs_engine_root=False, source_available=False, payload_mode="", engine_version="",
                permission_required=False)


def _failure(result, error):
    if isinstance(error, InstallProblem):
        result.update(message=str(error), needs_engine_root=error.needs_engine_root)
    elif isinstance(error, PermissionError):
        result.update(message="无法读写插件目录。请关闭宿主软件并确认当前用户拥有目录权限。",
                      permission_required=True)
    else:
        result["message"] = "无法读取或写入安装所需文件。请检查工程、安装目录及剩余磁盘空间。"
    return result

