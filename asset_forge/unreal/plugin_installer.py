"""Install the Asset Forge Unreal plugin into a UE project."""

from __future__ import absolute_import

import fnmatch
import io
import json
import os
import shutil


PLUGIN_NAME = "AssetForge"
SKIP_DIRS = {".git", "__pycache__", "Binaries", "Intermediate", "Saved"}
SKIP_PATTERNS = ["*.pyc", "*.pyo"]


class UnrealPluginInstaller(object):
    """Copy the repo plugin package into a project's Plugins directory."""

    def __init__(self, source_plugin_dir=None):
        self.source_plugin_dir = os.path.abspath(source_plugin_dir or self._default_source_plugin_dir())

    def plan(self, project_path):
        project_info = self._resolve_project(project_path)
        source_descriptor = os.path.join(self.source_plugin_dir, PLUGIN_NAME + ".uplugin")
        target_dir = os.path.join(project_info.get("project_root", ""), "Plugins", PLUGIN_NAME)
        checks = [
            self._check("source_plugin", os.path.isdir(self.source_plugin_dir), self.source_plugin_dir, "源插件目录存在", "源插件目录不存在"),
            self._check("source_descriptor", os.path.exists(source_descriptor), source_descriptor, "源 .uplugin 存在", "源 .uplugin 不存在"),
            self._check("project_root", bool(project_info.get("project_root")), project_info.get("project_root", ""), "UE 项目目录有效", "无法解析 UE 项目目录"),
            self._check("project_file", bool(project_info.get("project_file")), project_info.get("project_file", ""), ".uproject 文件存在", "未找到 .uproject 文件"),
        ]
        can_install = all(item["status"] == "pass" for item in checks)
        action = "update" if os.path.isdir(target_dir) else "install"
        return {
            "status": "ready" if can_install else "error",
            "plugin_name": PLUGIN_NAME,
            "action": action,
            "can_install": can_install,
            "source_plugin_dir": self._norm(self.source_plugin_dir),
            "source_descriptor": self._norm(source_descriptor),
            "project_root": self._norm(project_info.get("project_root", "")),
            "project_file": self._norm(project_info.get("project_file", "")),
            "target_plugin_dir": self._norm(target_dir),
            "target_descriptor": self._norm(os.path.join(target_dir, PLUGIN_NAME + ".uplugin")),
            "content_mount": "/AssetForge",
            "requires_editor_restart": True,
            "checks": checks,
        }

    def install(self, project_path, enable_in_project=True, dry_run=False):
        install_plan = self.plan(project_path)
        report = {
            "status": "skipped" if dry_run else "failed",
            "message": "插件安装预检查完成，未执行复制" if dry_run else "插件安装失败",
            "plan": install_plan,
            "copied_files": [],
            "enabled_in_project": False,
            "issues": [],
        }
        if not install_plan["can_install"]:
            report["issues"] = [item["message"] for item in install_plan["checks"] if item["status"] == "error"]
            return report
        if dry_run:
            return report

        copied = self._copy_plugin_tree(install_plan["target_plugin_dir"])
        report["copied_files"] = copied
        if enable_in_project:
            report["enabled_in_project"] = self._enable_plugin_in_project(install_plan["project_file"])

        report["status"] = "success"
        report["message"] = "AssetForge 插件已安装到 UE 项目，重启编辑器后 /AssetForge 内容根才会挂载"
        return report

    def _resolve_project(self, project_path):
        if not project_path:
            return {"project_root": "", "project_file": ""}
        path = os.path.abspath(project_path)
        if os.path.isfile(path) and path.lower().endswith(".uproject"):
            return {"project_root": os.path.dirname(path), "project_file": path}
        if os.path.isdir(path):
            project_files = [os.path.join(path, name) for name in os.listdir(path) if name.lower().endswith(".uproject")]
            project_file = sorted(project_files)[0] if project_files else ""
            return {"project_root": path, "project_file": project_file}
        return {"project_root": "", "project_file": ""}

    def _default_source_plugin_dir(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        return os.path.join(repo_root, "Plugins", PLUGIN_NAME)

    def _copy_plugin_tree(self, target_dir):
        copied = []
        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)
        for root, dir_names, file_names in os.walk(self.source_plugin_dir):
            dir_names[:] = [name for name in dir_names if name not in SKIP_DIRS]
            relative_root = os.path.relpath(root, self.source_plugin_dir)
            target_root = target_dir if relative_root == "." else os.path.join(target_dir, relative_root)
            if not os.path.isdir(target_root):
                os.makedirs(target_root)
            for file_name in file_names:
                if self._should_skip_file(file_name):
                    continue
                source_path = os.path.join(root, file_name)
                target_path = os.path.join(target_root, file_name)
                shutil.copy2(source_path, target_path)
                copied.append(self._norm(target_path))
        return copied

    def _enable_plugin_in_project(self, project_file):
        with io.open(project_file, "r", encoding="utf-8") as stream:
            data = json.load(stream)

        plugins = data.setdefault("Plugins", [])
        for plugin in plugins:
            if plugin.get("Name") == PLUGIN_NAME:
                changed = plugin.get("Enabled") is not True
                plugin["Enabled"] = True
                self._write_project(project_file, data)
                return changed

        plugins.append({"Name": PLUGIN_NAME, "Enabled": True})
        self._write_project(project_file, data)
        return True

    def _write_project(self, project_file, data):
        with io.open(project_file, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(data, ensure_ascii=False, indent=2))
            stream.write("\n")

    def _should_skip_file(self, file_name):
        return any(fnmatch.fnmatch(file_name, pattern) for pattern in SKIP_PATTERNS)

    def _check(self, check_id, passed, path, pass_message, fail_message):
        return {
            "id": check_id,
            "status": "pass" if passed else "error",
            "path": self._norm(path),
            "message": pass_message if passed else fail_message,
        }

    def _norm(self, path):
        return (path or "").replace("\\", "/")


def plan_assetforge_plugin_install(project_path, source_plugin_dir=None):
    return UnrealPluginInstaller(source_plugin_dir).plan(project_path)


def install_assetforge_plugin(project_path, source_plugin_dir=None, enable_in_project=True, dry_run=False):
    return UnrealPluginInstaller(source_plugin_dir).install(project_path, enable_in_project, dry_run)
