"""Validate DCC AssetForge Unreal plugin content without creating project assets."""

from __future__ import absolute_import

import io
import json
import os

from asset_forge.unreal.material_package_schema import get_default_material_package_plan
from asset_forge.unreal.unreal_bridge import get_unreal


class UnrealPluginContentBootstrap(object):
    """Check the UE plugin descriptor, content folders, and planned assets."""

    def __init__(self, unreal_module=None, descriptor_path=None):
        self.unreal = unreal_module or get_unreal()
        self._plugin_api = getattr(self.unreal, "PluginBlueprintLibrary", None)
        self._registered_descriptor = self._registered_descriptor_path()
        self.descriptor_path = descriptor_path or self._default_descriptor_path()

    def validate(self, plan=None):
        active_plan = plan or get_default_material_package_plan()
        checks = []
        checks.append(self._descriptor_check())
        checks.extend(self._directory_checks(active_plan))
        mount_check = self._content_mount_check(active_plan)
        checks.append(mount_check)
        checks.extend(self._asset_checks(active_plan, mount_check))

        return {
            "status": self._status(checks),
            "plugin_name": "AssetForge",
            "content_mount": active_plan.get("content_mount", active_plan.get("root", "")),
            "disk_content_root": active_plan.get("disk_content_root", ""),
            "descriptor_path": self.descriptor_path.replace("\\", "/"),
            "unreal_available": self.unreal is not None,
            "checks": checks,
            "missing_assets": [item["path"] for item in checks if item["id"] == "asset_exists" and item["status"] == "warning"],
            "missing_compatibility_assets": [item["path"] for item in checks if item["id"] == "asset_exists" and item["status"] == "info"],
        }

    def _registered_descriptor_path(self):
        lookup = getattr(self._plugin_api, "get_plugin_descriptor_file_path", None)
        path = lookup("AssetForge") if lookup else None
        if not isinstance(path, str) or not path:
            return ""
        return self._absolute_unreal_path(path)

    def _absolute_unreal_path(self, path):
        if not os.path.isabs(path):
            convert = getattr(getattr(self.unreal, "Paths", None), "convert_relative_path_to_full", None)
            if convert:
                path = convert(path) or path
        return os.path.abspath(path)

    def _default_descriptor_path(self):
        if self._registered_descriptor:
            return self._registered_descriptor
        python_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        content_root = os.path.dirname(python_root)
        if os.path.basename(python_root).lower() == "python" and os.path.basename(content_root).lower() == "content":
            plugin_root = os.path.dirname(content_root)
            return os.path.join(plugin_root, "AssetForge.uplugin")

        paths_api = getattr(self.unreal, "Paths", None)
        for root in self._active_plugin_roots(paths_api, lowercase=False):
            for subdirectory in ("AssetForge", "Marketplace/AssetForge"):
                candidate = os.path.join(root, subdirectory, "AssetForge.uplugin")
                if os.path.isfile(candidate):
                    return candidate
        return os.path.join(python_root, "Plugins", "AssetForge", "AssetForge.uplugin")

    def _descriptor_check(self):
        if not os.path.isfile(self.descriptor_path):
            return self._check("plugin_descriptor", "error", self.descriptor_path, "缺少 AssetForge.uplugin")

        with io.open(self.descriptor_path, "r", encoding="utf-8") as stream:
            descriptor = json.load(stream)

        if not descriptor.get("CanContainContent", False):
            return self._check("plugin_descriptor", "error", self.descriptor_path, "AssetForge.uplugin 必须设置 CanContainContent=true")
        if descriptor.get("Modules", []):
            return self._check("plugin_descriptor", "pass", self.descriptor_path, "AssetForge.uplugin 声明 Editor C++ 模块，用于原生 UE 导入门禁 UI")
        return self._check("plugin_descriptor", "pass", self.descriptor_path, "AssetForge.uplugin 是 Content/Python-only 插件，不需要 C++ 编译")

    def _directory_checks(self, plan):
        checks = []
        plugin_root = os.path.dirname(self.descriptor_path)
        mount = plan.get("content_mount", plan.get("root", "")).rstrip("/")
        directories = {"Content"}
        if mount:
            prefix = mount + "/"
            # Texture presence keeps its existing asset-level warning policy.
            for entry in self._planned_assets(plan, include_textures=False):
                if entry["required"] and entry["path"].startswith(prefix):
                    directory = entry["path"][len(prefix):].rpartition("/")[0]
                    if directory:
                        directories.add("Content/" + directory)
        for directory in sorted(directories):
            path = os.path.join(plugin_root, directory)
            status = "pass" if os.path.isdir(path) else "error"
            message = "插件内容目录存在" if status == "pass" else "缺少插件内容目录"
            checks.append(self._check("plugin_directory", status, path, message))
        return checks

    def _content_mount_check(self, plan):
        content_mount = plan.get("content_mount", plan.get("root", ""))
        if self.unreal is None:
            return self._check("content_mount", "warning", content_mount, "未在 Unreal Python 环境中运行，跳过插件挂载检查")

        if not os.path.isfile(self.descriptor_path):
            return self._check("content_mount", "warning", content_mount, "找不到本次检查的插件描述文件，无法确认内容挂载")

        is_mounted = getattr(self._plugin_api, "is_plugin_mounted", None)
        if is_mounted and self._registered_descriptor and (
                os.path.normcase(os.path.abspath(self.descriptor_path)) == os.path.normcase(self._registered_descriptor)):
            if is_mounted("AssetForge"):
                return self._check("content_mount", "pass", content_mount, "当前 UE 已挂载 AssetForge 内容")
            return self._check("content_mount", "warning", content_mount, "当前 UE 尚未挂载 AssetForge 内容，请启用插件后重开工程")

        paths_api = getattr(self.unreal, "Paths", None)
        if paths_api is None:
            return self._check("content_mount", "pass", content_mount, "当前环境未提供 Paths API，按测试环境处理")

        plugin_roots = self._active_plugin_roots(paths_api)
        if not plugin_roots:
            return self._check("content_mount", "warning", content_mount, "无法读取当前 UE 项目的插件目录，跳过插件挂载检查")

        descriptor = os.path.abspath(self.descriptor_path).replace("\\", "/").lower()
        for root in plugin_roots:
            if descriptor.startswith(root):
                return self._check("content_mount", "pass", content_mount, "AssetForge 插件位于当前 UE 可挂载插件目录")

        return self._check(
            "content_mount",
            "warning",
            content_mount,
            "AssetForge 插件尚未安装或启用到当前 UE 项目/引擎插件目录，AssetForge 内容根不会被挂载",
        )

    def _active_plugin_roots(self, paths_api, lowercase=True):
        roots = []
        for method_name in ["project_plugins_dir", "engine_plugins_dir"]:
            method = getattr(paths_api, method_name, None)
            if not method:
                continue
            try:
                path = method()
            except Exception:
                path = ""
            if path:
                normalized = self._absolute_unreal_path(path).replace("\\", "/").rstrip("/") + "/"
                roots.append(normalized.lower() if lowercase else normalized)
        return roots

    def _planned_assets(self, plan, include_textures=True):
        asset_entries = []
        if include_textures:
            asset_entries.extend(
                {"path": texture.get("path", ""), "required": texture.get("required_for_import", True)}
                for texture in plan.get("placeholder_textures", [])
            )
        asset_entries.extend({"path": material.get("path", ""), "required": material.get("required_for_import", True)} for material in plan.get("materials", []))
        asset_entries.extend({"path": material_instance.get("path", ""), "required": True} for material_instance in plan.get("material_instances", []))
        asset_entries.extend({"path": function.get("path", ""), "required": True} for function in plan.get("functions", []))
        asset_entries.extend({"path": collection.get("path", ""), "required": True} for collection in plan.get("parameter_collections", []))
        return [entry for entry in asset_entries if entry["path"]]

    def _asset_checks(self, plan, mount_check=None):
        asset_entries = self._planned_assets(plan)
        if self.unreal is None:
            return [
                self._check(
                    "asset_exists",
                    "warning" if entry.get("required", True) else "info",
                    entry["path"],
                    "未在 Unreal Python 环境中运行，跳过插件资产存在性检查",
                )
                for entry in asset_entries
            ]

        if mount_check and mount_check.get("status") != "pass":
            return [
                self._check(
                    "asset_exists",
                    "warning" if entry.get("required", True) else "info",
                    entry["path"],
                    "插件内容根未挂载，跳过资产存在性检查：{0}".format(entry["path"]),
                )
                for entry in asset_entries
            ]

        library = getattr(self.unreal, "EditorAssetLibrary", None)
        does_exist = getattr(library, "does_asset_exist", None)
        load_asset = getattr(library, "load_asset", None)
        existing = set()
        if does_exist:
            existing = {entry["path"] for entry in asset_entries
                        if any(does_exist(path) for path in self._asset_path_candidates(entry["path"]))}

        mount = plan.get("content_mount", plan.get("root", "")).rstrip("/")
        content = os.path.join(os.path.dirname(self.descriptor_path), "Content")
        known_mount = bool(mount and getattr(self.unreal, "Paths", None) and os.path.isdir(content))
        pending = set()
        if does_exist or load_asset:
            for entry in asset_entries:
                asset_path = entry["path"]
                if asset_path in existing:
                    continue
                if known_mount and asset_path.startswith(mount + "/"):
                    relative = asset_path[len(mount) + 1:].split(".", 1)[0]
                    if not os.path.isfile(os.path.join(content, relative + ".uasset")):
                        continue
                pending.add(asset_path)
        if pending:
            folders = {path.rpartition("/")[0] or path for path in pending}
            self._scan_asset_registry_paths(sorted(folders))
            probe = does_exist or load_asset
            existing.update(path for path in pending
                            if any(probe(candidate) for candidate in self._asset_path_candidates(path)))

        checks = []
        for entry in asset_entries:
            asset_path = entry["path"]
            if asset_path in existing:
                checks.append(self._check("asset_exists", "pass", asset_path, "插件资产存在"))
            elif entry.get("required", True):
                checks.append(self._check("asset_exists", "warning", asset_path, "缺少插件资产"))
            else:
                checks.append(self._check("asset_exists", "info", asset_path, "缺少 legacy 兼容资产，不阻断 HardSurface 主线"))
        return checks

    def _asset_path_candidates(self, asset_path):
        if not asset_path:
            return []
        candidates = [asset_path]
        leaf = asset_path.rsplit("/", 1)[-1]
        if "." not in leaf:
            candidates.append("{0}.{1}".format(asset_path, leaf))
        return candidates

    def _scan_asset_registry_paths(self, folders):
        registry_helpers = getattr(self.unreal, "AssetRegistryHelpers", None)
        if registry_helpers is None or not hasattr(registry_helpers, "get_asset_registry"):
            return
        try:
            registry = registry_helpers.get_asset_registry()
            if hasattr(registry, "scan_paths_synchronous"):
                registry.scan_paths_synchronous(folders, True)
            elif hasattr(registry, "wait_for_completion"):
                registry.wait_for_completion()
        except Exception:
            return

    def _status(self, checks):
        if any(item["status"] == "error" for item in checks):
            return "error"
        if any(item["status"] == "warning" for item in checks):
            return "warning"
        return "pass"

    def _check(self, check_id, status, path, message):
        return {
            "id": check_id,
            "status": status,
            "path": path.replace("\\", "/"),
            "message": message,
        }


def validate_assetforge_plugin_content(unreal_module=None):
    return UnrealPluginContentBootstrap(unreal_module).validate()
