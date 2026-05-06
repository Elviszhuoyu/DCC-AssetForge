"""Focused preflight for the AssetForge Unreal plugin mount."""

from __future__ import absolute_import

from asset_forge.unreal.plugin_content_bootstrap import UnrealPluginContentBootstrap


class UnrealPluginMountPreflight(object):
    """Check whether the /AssetForge plugin content root can be used."""

    def __init__(self, unreal_module=None, descriptor_path=None, content_bootstrap=None):
        self.content_bootstrap = content_bootstrap or UnrealPluginContentBootstrap(unreal_module, descriptor_path)

    def check(self):
        validation = self.content_bootstrap.validate()
        mount_check = self._mount_check(validation)
        descriptor_check = self._first_check(validation, "plugin_descriptor")
        directory_checks = [item for item in validation.get("checks", []) if item.get("id") == "plugin_directory"]
        status = "pass" if self._can_mount(validation, mount_check, descriptor_check) else "warning"
        return {
            "status": status,
            "can_use_plugin_content": status == "pass",
            "plugin_name": validation.get("plugin_name", "AssetForge"),
            "content_mount": validation.get("content_mount", "/AssetForge"),
            "descriptor_path": validation.get("descriptor_path", ""),
            "unreal_available": validation.get("unreal_available", False),
            "message": self._message(status, mount_check),
            "descriptor_check": descriptor_check,
            "mount_check": mount_check,
            "directory_checks": directory_checks,
        }

    def _can_mount(self, validation, mount_check, descriptor_check):
        return (
            validation.get("unreal_available", False)
            and mount_check.get("status") == "pass"
            and descriptor_check.get("status") == "pass"
        )

    def _mount_check(self, validation):
        return self._first_check(validation, "content_mount")

    def _first_check(self, validation, check_id):
        for item in validation.get("checks", []):
            if item.get("id") == check_id:
                return item
        return {"id": check_id, "status": "warning", "message": "未找到检查项", "path": ""}

    def _message(self, status, mount_check):
        if status == "pass":
            return "AssetForge 插件内容根已可用"
        return mount_check.get("message") or "AssetForge 插件内容根暂不可用"


def check_assetforge_plugin_mount(unreal_module=None, descriptor_path=None):
    return UnrealPluginMountPreflight(unreal_module, descriptor_path).check()
