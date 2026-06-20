"""UE runtime/project version guard before writing imported assets."""

from __future__ import absolute_import

import json
import os
import re

from asset_forge.shared.path_utils import normalize_path
from asset_forge.unreal.unreal_bridge import get_unreal


class UnrealEngineVersionPreflight(object):
    """Check that generated UE assets are written by the intended engine."""

    def __init__(self, unreal_module=None, project_file_path=None):
        self.unreal = unreal_module
        self.project_file_path = project_file_path

    def check(self, manifest=None):
        manifest = manifest or {}
        unreal = self.unreal if self.unreal is not None else get_unreal()
        target_version = str(manifest.get("target_engine_version", "") or "").strip()
        current_version = self._current_engine_version(unreal)
        project_file = self.project_file_path or self._project_file_path(unreal)
        association = self._project_engine_association(project_file)

        checks = []
        errors = []
        warnings = []

        target_mm = parse_major_minor(target_version)
        current_mm = parse_major_minor(current_version)
        association_mm = parse_major_minor(association)

        if target_version and current_version:
            if target_mm and current_mm and target_mm != current_mm:
                errors.append(
                    "Manifest target_engine_version is {0}, but current UE runtime is {1}.".format(
                        target_version, current_version
                    )
                )
            checks.append(self._check("manifest_vs_runtime", "error" if errors else "pass", target_version, current_version))
        elif target_version and not current_version:
            warnings.append("Cannot read current UE runtime version; keep this import as manual validation required.")
            checks.append(self._check("manifest_vs_runtime", "warning", target_version, current_version))
        else:
            warnings.append("Manifest has no target_engine_version; record the UE version before release validation.")
            checks.append(self._check("manifest_version_present", "warning", target_version, current_version))

        if association and current_version and association_mm and current_mm and association_mm != current_mm:
            errors.append(
                ".uproject EngineAssociation is {0}, but current UE runtime is {1}.".format(
                    association, current_version
                )
            )
            checks.append(self._check("project_vs_runtime", "error", association, current_version))
        elif association and current_version and association_mm and current_mm:
            checks.append(self._check("project_vs_runtime", "pass", association, current_version))
        elif project_file and not association:
            warnings.append("Cannot read .uproject EngineAssociation; verify the project version manually.")
            checks.append(self._check("project_engine_association", "warning", association, current_version))

        status = "error" if errors else ("warning" if warnings else "pass")
        return {
            "status": status,
            "can_write_assets": status != "error",
            "target_engine_version": target_version,
            "current_engine_version": current_version,
            "project_engine_association": association,
            "project_file_path": normalize_path(project_file) if project_file else "",
            "checks": checks,
            "warnings": [{"message": item} for item in warnings],
            "errors": [{"message": item} for item in errors],
            "message": self._message(status),
            "next_action": self._next_action(status),
        }

    def _current_engine_version(self, unreal):
        system_library = getattr(unreal, "SystemLibrary", None) if unreal is not None else None
        getter = getattr(system_library, "get_engine_version", None)
        if getter is None:
            return ""
        try:
            return str(getter() or "")
        except Exception:
            return ""

    def _project_file_path(self, unreal):
        paths = getattr(unreal, "Paths", None) if unreal is not None else None
        getter = getattr(paths, "get_project_file_path", None)
        if getter is None:
            return ""
        try:
            return str(getter() or "")
        except Exception:
            return ""

    def _project_engine_association(self, project_file_path):
        if not project_file_path or not os.path.exists(project_file_path):
            return ""
        try:
            with open(project_file_path, "r", encoding="utf-8-sig") as stream:
                data = json.load(stream)
        except Exception:
            return ""
        return str(data.get("EngineAssociation", "") or "")

    def _check(self, check_id, status, expected, actual):
        return {
            "id": check_id,
            "status": status,
            "expected": expected,
            "actual": actual,
        }

    def _message(self, status):
        if status == "error":
            return "UE 引擎版本不匹配，已阻止写入资产。"
        if status == "warning":
            return "UE 引擎版本证据不完整，需要人工复核。"
        return "UE 引擎版本与项目配置一致。"

    def _next_action(self, status):
        if status == "error":
            return "请用目标项目 EngineAssociation 对应的 UE 版本重新运行导入，禁止把高版本 .uasset 写入低版本项目。"
        if status == "warning":
            return "补齐 manifest target_engine_version 或确认当前 UE runtime / .uproject 版本后再作为发布证据。"
        return "可以继续执行 UE 导入。"


def parse_major_minor(value):
    match = re.search(r"(\d+)\.(\d+)", str(value or ""))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))
