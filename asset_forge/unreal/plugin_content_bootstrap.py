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

    def _default_descriptor_path(self):
        active_descriptor = self._active_installed_descriptor_path()
        if active_descriptor:
            return active_descriptor
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        return os.path.join(repo_root, "Plugins", "AssetForge", "AssetForge.uplugin")

    def _active_installed_descriptor_path(self):
        if self.unreal is None:
            return ""
        paths_api = getattr(self.unreal, "Paths", None)
        if paths_api is None:
            return ""
        for root in self._active_plugin_roots(paths_api, lowercase=False):
            candidate = os.path.join(root, "AssetForge", "AssetForge.uplugin")
            if os.path.exists(candidate):
                return candidate
        return ""

    def _descriptor_check(self):
        if not os.path.exists(self.descriptor_path):
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
        content_root = os.path.dirname(self.descriptor_path)
        for directory in ["Content", "Content/Materials", "Content/MaterialInstances", "Content/MaterialFunctions", "Content/ParameterCollections"]:
            path = os.path.join(content_root, directory)
            status = "pass" if os.path.isdir(path) else "error"
            message = "插件内容目录存在" if status == "pass" else "缺少插件内容目录"
            checks.append(self._check("plugin_directory", status, path, message))
        return checks

    def _content_mount_check(self, plan):
        content_mount = plan.get("content_mount", plan.get("root", ""))
        if self.unreal is None:
            return self._check("content_mount", "warning", content_mount, "未在 Unreal Python 环境中运行，跳过插件挂载检查")

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
                normalized = os.path.abspath(path).replace("\\", "/").rstrip("/") + "/"
                roots.append(normalized.lower() if lowercase else normalized)
        return roots

    def _asset_checks(self, plan, mount_check=None):
        asset_entries = []
        asset_entries.extend({"path": texture.get("path", ""), "required": texture.get("required_for_import", True)} for texture in plan.get("placeholder_textures", []))
        asset_entries.extend({"path": material.get("path", ""), "required": material.get("required_for_import", True)} for material in plan.get("materials", []))
        asset_entries.extend({"path": material_instance.get("path", ""), "required": True} for material_instance in plan.get("material_instances", []))
        asset_entries.extend({"path": function.get("path", ""), "required": True} for function in plan.get("functions", []))
        asset_entries.extend({"path": collection.get("path", ""), "required": True} for collection in plan.get("parameter_collections", []))
        asset_entries = [entry for entry in asset_entries if entry.get("path")]

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

        return [self._asset_exists_check(entry["path"], required=entry.get("required", True)) for entry in asset_entries]

    def _asset_exists_check(self, asset_path, required=True):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        exists = False
        self._scan_asset_registry_path(asset_path)
        if library and hasattr(library, "does_asset_exist"):
            exists = any(bool(library.does_asset_exist(candidate)) for candidate in self._asset_path_candidates(asset_path))
        elif library and hasattr(library, "load_asset"):
            exists = any(bool(library.load_asset(candidate)) for candidate in self._asset_path_candidates(asset_path))

        status = "pass" if exists else ("warning" if required else "info")
        message = "插件资产存在" if exists else ("缺少插件资产" if required else "缺少 legacy 兼容资产，不阻断 HardSurface 主线")
        return self._check("asset_exists", status, asset_path, message)

    def _asset_path_candidates(self, asset_path):
        if not asset_path:
            return []
        candidates = [asset_path]
        leaf = asset_path.rsplit("/", 1)[-1]
        if "." not in leaf:
            candidates.append("{0}.{1}".format(asset_path, leaf))
        return candidates

    def _scan_asset_registry_path(self, asset_path):
        if not asset_path:
            return
        registry_helpers = getattr(self.unreal, "AssetRegistryHelpers", None)
        if registry_helpers is None or not hasattr(registry_helpers, "get_asset_registry"):
            return
        folder = asset_path.rsplit("/", 1)[0] if "/" in asset_path else asset_path
        try:
            registry = registry_helpers.get_asset_registry()
            if hasattr(registry, "scan_paths_synchronous"):
                registry.scan_paths_synchronous([folder], True)
            if hasattr(registry, "wait_for_completion"):
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
