"""DCC AssetForge offline environment doctor."""

from __future__ import absolute_import

import importlib
import io
import json
import os
import tempfile

from asset_forge.shared.acceptance_gate import apply_acceptance_gate, create_gate_policy
from asset_forge.shared.interface_contract import validate_package_contract
from asset_forge.shared.manifest_schema import create_manifest, validate_manifest
from asset_forge.shared.report_artifacts import attach_report_artifact_metadata, default_report_path
from asset_forge.shared.report_schema import attach_acceptance_summary, attach_report_schema_validation, create_acceptance_summary, write_report
from asset_forge.maya.operation_logger import MayaOperationLogger, latest_log_path as latest_maya_log_path
from asset_forge.unreal.operation_logger import latest_log_path
from asset_forge.unreal.operation_logger import UnrealOperationLogger


REQUIRED_MODULES = [
    "asset_forge.shared.manifest_schema",
    "asset_forge.shared.material_profile_schema",
    "asset_forge.unreal.package_acceptance",
    "asset_forge.unreal.acceptance_runner",
]

MOJIBAKE_MARKERS = [
    chr(0x3F) * 4,
    chr(0x93B5),
    chr(0x5BB8),
    chr(0x6DC7),
    chr(0x6960),
    chr(0x9340),
    chr(0x7CA8),
    chr(0x7468),
    chr(0x7EDB),
    chr(0x95C3),
    chr(0x7035),
]


class AssetForgeDoctor(object):
    """Check offline files and Python imports needed by DCC AssetForge."""

    def __init__(self, repo_root=None):
        self.repo_root = os.path.abspath(repo_root or self._default_repo_root())

    def run(self, report_path=None, strict=False, block_warnings=None, command_args=None):
        checks = []
        checks.append(self._file_check("material_profiles_config", "config/material_profiles.json", "Material Profile 配置"))
        checks.append(self._file_check("import_presets_config", "config/import_presets.json", "Unreal import preset 配置"))
        checks.append(self._file_check("plugin_descriptor", "Plugins/AssetForge/AssetForge.uplugin", "AssetForge 插件描述文件"))
        checks.append(self._file_check("maya_bootstrap_launcher", "scripts/maya_launch_asset_forge.py", "Maya bootstrap 启动脚本"))
        checks.append(self._file_check("ue_python_init", "Plugins/AssetForge/Content/Python/init_unreal.py", "UE Python init 入口"))
        checks.extend(self._plugin_descriptor_checks())
        checks.extend(self._directory_checks())
        checks.extend(self._document_checks())
        checks.extend(self._module_checks())
        checks.extend(self._writable_directory_checks())
        checks.extend(self._operation_log_checks())
        checks.extend(self._config_json_checks())
        checks.append(self._manifest_schema_smoke_check())
        checks.extend(self._material_profile_contract_checks())
        checks.extend(self._encoding_checks())
        checks.append(self._latest_log_check())
        if command_args:
            checks.extend(self._optional_contract_checks(command_args))

        warnings = [self._message(item) for item in checks if item.get("status") == "warning"]
        errors = [self._message(item) for item in checks if item.get("status") == "error"]
        summary = create_acceptance_summary(
            "error" if errors else ("warning" if warnings else "pass"),
            warnings,
            errors,
            "修复 Doctor 报告中的阻断项后重新运行环境自检" if errors else ("检查 Doctor 警告后继续" if warnings else "环境自检通过"),
        )
        report = {
            "version": "0.1",
            "stage": "asset_forge_doctor",
            "repo_root": self.repo_root.replace("\\", "/"),
            "status": summary.get("status", ""),
            "checks": checks,
            "pre_validation_summary": self._pre_validation_summary(checks),
            "pretest_summary": self._pretest_summary(checks),
            "manual_validation_required": self._manual_validation_required(),
            "summary": summary,
        }
        attach_acceptance_summary(report, summary)
        apply_acceptance_gate(report, create_gate_policy(strict, block_warnings, False))
        active_report_path = report_path or default_report_path(self.repo_root, "asset_forge_doctor")
        attach_report_artifact_metadata(report, active_report_path, command_args)
        attach_report_schema_validation(report, require_gate=True)
        write_report(active_report_path, report)
        return report

    def _directory_checks(self):
        checks = []
        for rel_path, label in [
            ("Plugins/AssetForge/Content", "插件 Content 根目录"),
            ("Plugins/AssetForge/Content/Materials", "插件 Materials 目录"),
            ("Plugins/AssetForge/Content/MaterialFunctions", "插件 MaterialFunctions 目录"),
            ("Plugins/AssetForge/Content/ParameterCollections", "插件 ParameterCollections 目录"),
        ]:
            path = os.path.join(self.repo_root, rel_path)
            checks.append(
                self._check(
                    "plugin_content_directory",
                    "pass" if os.path.isdir(path) else "warning",
                    path,
                    "{0}存在".format(label) if os.path.isdir(path) else "{0}缺失".format(label),
                )
            )
        return checks

    def _module_checks(self):
        checks = []
        for module_name in REQUIRED_MODULES:
            try:
                importlib.import_module(module_name)
                checks.append(self._check("python_module", "pass", module_name, "关键 Python 模块可导入：{0}".format(module_name)))
            except Exception as exc:
                checks.append(self._check("python_module", "error", module_name, "关键 Python 模块导入失败：{0}；{1}".format(module_name, exc)))
        return checks

    def _writable_directory_checks(self):
        checks = []
        for rel_path, label in [
            ("AssetForgeReports", "报告目录"),
            ("AssetForgeReports/logs", "本地运行日志目录"),
        ]:
            path = os.path.join(self.repo_root, rel_path)
            try:
                if not os.path.isdir(path):
                    os.makedirs(path)
                handle, temp_path = tempfile.mkstemp(prefix="asset_forge_doctor_", suffix=".tmp", dir=path)
                os.close(handle)
                os.remove(temp_path)
                checks.append(self._check("writable_directory", "pass", path, "{0}可写：{1}".format(label, path)))
            except Exception as exc:
                checks.append(self._check("writable_directory", "error", path, "{0}不可写：{1}".format(label, exc)))
        return checks

    def _operation_log_checks(self):
        checks = []
        for check_id, label, logger_class, latest_path_func in [
            ("maya_operation_log_writable", "Maya latest log", MayaOperationLogger, latest_maya_log_path),
            ("unreal_operation_log_writable", "UE latest log", UnrealOperationLogger, latest_log_path),
        ]:
            try:
                entry = logger_class(root=self.repo_root).log(
                    "doctor_pretest_log_probe",
                    "success",
                    outputs={"note": "复测前自检日志写入验证"},
                )
                path = entry.get("log_path") or latest_path_func(self.repo_root)
                checks.append(self._check(check_id, "pass", path, "{0} 可写，中文日志写入验证通过。".format(label)))
            except Exception as exc:
                checks.append(self._check(check_id, "error", latest_path_func(self.repo_root), "{0} 写入失败：{1}".format(label, exc)))
        return checks

    def _config_json_checks(self):
        checks = []
        for rel_path, label in [
            ("config/material_profiles.json", "Material Profile 配置"),
            ("config/import_presets.json", "Import Preset 配置"),
            ("config/project_settings.example.json", "项目设置示例配置"),
        ]:
            path = os.path.join(self.repo_root, rel_path)
            try:
                with io.open(path, "r", encoding="utf-8-sig") as stream:
                    json.load(stream)
                checks.append(self._check("config_json", "pass", path, "{0} JSON 可读取。".format(label)))
            except Exception as exc:
                checks.append(self._check("config_json", "error", path, "{0} JSON 读取失败：{1}".format(label, exc)))
        return checks

    def _document_checks(self):
        checks = []
        for rel_path, label in [
            ("README.md", "英文使用说明"),
            ("README.zh-CN.md", "中文使用说明"),
            ("LICENSE", "开源许可证"),
            ("THIRD_PARTY_NOTICES.md", "第三方许可说明"),
        ]:
            path = os.path.join(self.repo_root, rel_path)
            try:
                with io.open(path, "r", encoding="utf-8-sig") as stream:
                    text = stream.read()
                status = "pass" if text.strip() else "warning"
                message = "{0} 可读取。".format(label) if text.strip() else "{0} 为空，请确认文档是否完整。".format(label)
                checks.append(self._check("document_readable", status, path, message))
            except Exception as exc:
                checks.append(self._check("document_readable", "error", path, "{0} 读取失败：{1}".format(label, exc)))
        return checks

    def _manifest_schema_smoke_check(self):
        try:
            manifest = create_manifest("SM_DoctorSmoke", "D:/AssetForge/SM_DoctorSmoke.fbx", "/Game/Props")
            issues = validate_manifest(manifest)
            return self._check(
                "manifest_schema_smoke",
                "pass" if not issues else "error",
                "asset_forge.shared.manifest_schema",
                "Manifest schema smoke 通过。" if not issues else "Manifest schema smoke 失败：{0}".format(", ".join(issues)),
            )
        except Exception as exc:
            return self._check("manifest_schema_smoke", "error", "asset_forge.shared.manifest_schema", "Manifest schema smoke 异常：{0}".format(exc))

    def _material_profile_contract_checks(self):
        try:
            from asset_forge.shared.material_profile_contract import validate_material_profile_contract
            from asset_forge.shared.material_profile_schema import get_project_material_profiles
        except Exception as exc:
            return [self._check("material_profile_contract", "error", "material_profile_contract", "无法导入 Material Profile Contract 校验：{0}".format(exc))]

        checks = []
        for profile in get_project_material_profiles().get("profiles", []):
            name = profile.get("name", "")
            report = validate_material_profile_contract(name)
            status = "error" if report.get("status") == "error" else ("warning" if report.get("status") == "warning" else "pass")
            message = "Material Profile 契约检查：{0} -> {1}".format(name, report.get("status", ""))
            checks.append(self._check("material_profile_contract", status, name, message))
        return checks

    def _encoding_checks(self):
        checks = []
        roots = ["asset_forge", "config", "scripts", "tests", "Plugins"]
        for root_name in roots:
            root = os.path.join(self.repo_root, root_name)
            if not os.path.isdir(root):
                continue
            offenders = []
            for current_root, _, names in os.walk(root):
                for name in names:
                    if os.path.splitext(name)[1].lower() not in (".py", ".json", ".md", ".txt"):
                        continue
                    path = os.path.join(current_root, name)
                    try:
                        with io.open(path, "r", encoding="utf-8-sig") as stream:
                            text = stream.read()
                    except Exception:
                        continue
                    found = [marker for marker in MOJIBAKE_MARKERS if marker in text]
                    if found:
                        offenders.append(path.replace("\\", "/"))
            checks.append(
                self._check(
                    "encoding_mojibake",
                    "error" if offenders else "pass",
                    root,
                    "发现疑似中文乱码：{0}".format(", ".join(offenders[:5])) if offenders else "{0} 未发现常见中文乱码片段。".format(root_name),
                )
            )
        return checks

    def _latest_log_check(self):
        path = latest_log_path(self.repo_root)
        exists = os.path.exists(path)
        return self._check(
            "latest_unreal_log",
            "pass" if exists else "warning",
            path,
            "UE latest log 存在，可用于排错。" if exists else "尚未生成 latest_unreal.log；运行 UE bootstrap 或 CLI 后会生成。",
        )

    def _optional_contract_checks(self, command_args):
        candidates = [item for item in list(command_args or []) if item and not str(item).startswith("-")]
        if not candidates:
            return []
        path = candidates[0]
        if not os.path.exists(path):
            return []
        if not self._looks_like_manifest_or_package_path(path):
            return []
        report = validate_package_contract(path)
        return [
            self._check(
                "interface_contract",
                report.get("status", "warning"),
                path,
                "接口契约检查：{0}；{1}".format(report.get("status", ""), report.get("next_action", "")),
            )
        ]

    def _looks_like_manifest_or_package_path(self, path):
        if os.path.isfile(path):
            name = os.path.basename(path).lower()
            return name.endswith(".json") and "manifest" in name
        if not os.path.isdir(path):
            return False
        try:
            names = os.listdir(path)
        except Exception:
            return False
        for name in names:
            lowered = name.lower()
            if lowered.endswith(".json") and "manifest" in lowered:
                return True
        return False

    def _plugin_descriptor_checks(self):
        descriptor_path = os.path.join(self.repo_root, "Plugins", "AssetForge", "AssetForge.uplugin")
        if not os.path.exists(descriptor_path):
            return []
        try:
            with io.open(descriptor_path, "r", encoding="utf-8") as stream:
                descriptor = json.load(stream)
        except Exception as exc:
            return [self._check("plugin_descriptor_json", "error", descriptor_path, "无法读取 AssetForge.uplugin：{0}".format(exc))]

        modules = descriptor.get("Modules", [])
        return [
            self._check(
                "plugin_can_contain_content",
                "pass" if descriptor.get("CanContainContent", False) else "error",
                descriptor_path,
                "AssetForge.uplugin 支持 Content/Python 插件内容" if descriptor.get("CanContainContent", False) else "AssetForge.uplugin 必须设置 CanContainContent=true",
            ),
            self._check(
                "plugin_cpp_modules",
                "pass",
                descriptor_path,
                "AssetForge.uplugin 使用 Editor C++ 模块提供原生 UE 前端；安装/启用后需要 UE 编译" if modules else "AssetForge.uplugin 当前为 Content/Python-only 模式",
            ),
        ]

    def _pre_validation_summary(self, checks):
        errors = [item for item in checks if item.get("status") == "error"]
        warnings = [item for item in checks if item.get("status") == "warning"]
        return {
            "offline_verified": [item["id"] for item in checks if item.get("status") == "pass"],
            "needs_real_maya": ["Maya UI 交互、真实选择导出、真实 FBX 导出"],
            "needs_real_unreal": ["UE 插件加载、材质节点生成、FBX 导入、MI 创建、导入后 Static Mesh / 材质验收"],
            "missing_items": [item.get("message", "") for item in errors + warnings],
            "next_action": "先修复 error；warning 需在真实 Maya / UE 验收时确认。" if errors or warnings else "离线自检通过，下一步进入真实 Maya / UE 验收。",
        }

    def _pretest_summary(self, checks):
        errors = [item for item in checks if item.get("status") == "error"]
        warnings = [item for item in checks if item.get("status") == "warning"]
        return {
            "status": "error" if errors else ("warning" if warnings else "pass"),
            "can_accept": not errors,
            "checked_count": len(checks),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "manual_validation_required": self._manual_validation_required(),
            "next_action": "修复 error 后再安排 Maya/UE 复测。" if errors else "离线复测前自检通过，可安排真实 Maya/UE 复测。",
        }

    def _manual_validation_required(self):
        return [
            "真实 Maya：打开 UI、加载/保存项目设置、扫描选择、Preflight 阻断解释、导出当前选择。",
            "真实 UE 5.6：插件加载、/AssetForge mount、母材质网络生成、FBX 导入、贴图导入、MI 创建与 slot 绑定。",
        ]

    def _file_check(self, check_id, rel_path, label):
        path = os.path.join(self.repo_root, rel_path)
        return self._check(
            check_id,
            "pass" if os.path.exists(path) else "error",
            path,
            "{0}存在".format(label) if os.path.exists(path) else "{0}缺失".format(label),
        )

    def _check(self, check_id, status, path, message):
        return {
            "id": check_id,
            "label": check_id,
            "status": status,
            "path": str(path).replace("\\", "/"),
            "message": message,
        }

    def _message(self, item):
        return {
            "source": item.get("id", ""),
            "path": item.get("path", ""),
            "message": item.get("message", ""),
        }

    def _default_repo_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def run_asset_forge_doctor(repo_root=None, report_path=None, strict=False, block_warnings=None, command_args=None):
    return AssetForgeDoctor(repo_root).run(report_path, strict, block_warnings, command_args)
