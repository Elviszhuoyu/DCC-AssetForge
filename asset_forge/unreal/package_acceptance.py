"""Unified acceptance report for one DCC AssetForge export package."""

from __future__ import absolute_import

import os

from asset_forge.shared.acceptance_gate import apply_acceptance_gate, create_gate_policy
from asset_forge.shared.interface_contract import validate_manifest_contract
from asset_forge.shared.manifest_lint import lint_static_prop_manifest
from asset_forge.shared.material_profile_contract import validate_material_profile_contract
from asset_forge.shared.material_profile_schema import get_material_profile, read_material_profiles
from asset_forge.shared.report_artifacts import attach_report_artifact_metadata, default_report_path
from asset_forge.shared.report_schema import attach_acceptance_summary, attach_report_schema_validation, create_acceptance_summary, write_report
from asset_forge.shared.material_profile_validator import (
    validate_material_texture_coverage,
    validate_material_texture_quality,
    validate_packed_texture_channel_rules,
)
from asset_forge.shared.path_utils import normalize_path
from asset_forge.unreal.manifest_finder import find_latest_manifest
from asset_forge.unreal.manifest_reader import UnrealManifestReader
from asset_forge.unreal.dependency_audit import audit_unreal_dependencies
from asset_forge.unreal.engine_version_preflight import UnrealEngineVersionPreflight
from asset_forge.unreal.material_asset_bootstrap import UnrealMaterialAssetBootstrap
from asset_forge.unreal.material_binding_contract import validate_material_binding_contract
from asset_forge.unreal.material_binding_planner import UnrealMaterialBindingPlanner
from asset_forge.unreal.material_graph_evidence import build_material_graph_evidence_report
from asset_forge.unreal.package_validator import UnrealPackageValidator
from asset_forge.unreal.plugin_content_bootstrap import UnrealPluginContentBootstrap
from asset_forge.unreal.plugin_mount_preflight import UnrealPluginMountPreflight
from asset_forge.unreal.slot_binding_preflight import validate_static_mesh_slot_bindings
from asset_forge.unreal.strategy_simulator import simulate_same_name_strategies
from asset_forge.unreal.texture_import_planner import UnrealTextureImportPlanner


class UnrealPackageAcceptanceValidator(object):
    """Build one report that says whether an exported package is ready."""

    def __init__(
        self,
        reader=None,
        package_validator=None,
        plugin_content_bootstrap=None,
        material_asset_bootstrap=None,
        texture_import_planner=None,
        material_binding_planner=None,
        plugin_mount_preflight=None,
        engine_version_preflight=None,
    ):
        self.reader = reader or UnrealManifestReader()
        self.package_validator = package_validator or UnrealPackageValidator()
        self.plugin_content_bootstrap = plugin_content_bootstrap or UnrealPluginContentBootstrap()
        self.material_asset_bootstrap = material_asset_bootstrap or UnrealMaterialAssetBootstrap()
        self.texture_import_planner = texture_import_planner or UnrealTextureImportPlanner()
        self.material_binding_planner = material_binding_planner or UnrealMaterialBindingPlanner()
        self.plugin_mount_preflight = plugin_mount_preflight or UnrealPluginMountPreflight(content_bootstrap=self.plugin_content_bootstrap)
        self.engine_version_preflight = engine_version_preflight or UnrealEngineVersionPreflight()

    def validate(self, manifest_or_package_path, report_path=None, strict=False, block_warnings=None, require_import=False, command_args=None):
        manifest_path = self._resolve_manifest_path(manifest_or_package_path)
        if not manifest_path:
            report = self._missing_manifest_report(manifest_or_package_path)
            apply_acceptance_gate(report, create_gate_policy(strict, block_warnings, require_import))
            active_report_path = normalize_path(report_path or default_report_path(manifest_or_package_path if os.path.isdir(manifest_or_package_path) else os.getcwd(), "package_acceptance"))
            attach_report_artifact_metadata(report, active_report_path, command_args)
            attach_report_schema_validation(report, require_gate=True)
            write_report(active_report_path, report)
            return report

        prepared = self.reader.load(manifest_path, require_fbx_exists=True)
        manifest = prepared.get("manifest", {})
        interface_contract = validate_manifest_contract(manifest, manifest_path)
        manifest_lint = lint_static_prop_manifest(manifest)
        package_validation = self.package_validator.validate(manifest)
        engine_version_preflight = self.engine_version_preflight.check(manifest)
        plugin_content_validation = self.plugin_content_bootstrap.validate()
        plugin_mount = self.plugin_mount_preflight.check()
        material_asset_validation = self.material_asset_bootstrap.inspect_assets()
        texture_plan = self.texture_import_planner.plan(manifest)
        material_plan = self.material_binding_planner.plan(manifest, texture_plan, manifest.get("material_profile"))
        material_profile_validation = validate_material_texture_coverage(manifest.get("material_profile"), manifest.get("textures", []))
        material_profile_contract = validate_material_profile_contract(manifest.get("material_profile"), material_plan)
        material_profile_reference = self._material_profile_reference_validation(manifest)
        material_profile_snapshot = self._material_profile_snapshot_validation(manifest)
        texture_quality_validation = validate_material_texture_quality(manifest.get("material_profile"), manifest.get("textures", []))
        channel_validation = validate_packed_texture_channel_rules(manifest.get("material_profile"))
        parent_material_validation = self._parent_material_validation(material_plan, material_asset_validation)
        material_binding_contract = validate_material_binding_contract(manifest, material_plan)
        material_graph_evidence = build_material_graph_evidence_report(
            material_binding_plan=material_plan,
            parent_material_validation=parent_material_validation,
            material_network_reports=self._material_network_plans_for_evidence(),
            material_sampler_policy_validation={"status": "manual_validation_required"},
        )
        slot_binding_preflight = validate_static_mesh_slot_bindings(manifest, material_plan)
        strategy_simulation = simulate_same_name_strategies(manifest, texture_plan, material_plan)
        release_dependency_audit = audit_unreal_dependencies(
            {
                "manifest": manifest,
                "texture_import_plan": texture_plan,
                "material_binding_plan": material_plan,
                "parent_material_validation": parent_material_validation,
                "material_graph_evidence_report": material_graph_evidence,
            },
            allow_plugin_dependencies=True,
        )
        static_mesh_lod_policy = self._static_mesh_lod_policy_validation(manifest)

        checks = [
            self._check("manifest", "pass" if prepared.get("can_import") else "error", "Manifest", prepared.get("issues", [])),
            self._check("interface_contract", interface_contract.get("status"), "Maya -> UE 接口契约", self._messages(interface_contract)),
            self._check("manifest_lint", manifest_lint.get("status"), "Manifest Lint", self._messages(manifest_lint)),
            self._check("package", package_validation.get("status"), "导出包资源", self._messages(package_validation)),
            self._check("plugin_mount", plugin_mount.get("status"), "UE 插件挂载", [plugin_mount.get("message", "")]),
            self._check("plugin_content", plugin_content_validation.get("status"), "UE 插件内容", self._messages(plugin_content_validation)),
            self._check("material_assets", material_asset_validation.get("status"), "默认材质资产", [material_asset_validation.get("message", "")]),
            self._check("parent_materials", parent_material_validation.get("status"), "母材质", self._messages(parent_material_validation)),
            self._check("material_binding_contract", material_binding_contract.get("status"), "Material Binding Contract", self._messages(material_binding_contract)),
            self._check("material_graph_evidence", material_graph_evidence.get("status"), "Material Graph Evidence", self._messages(material_graph_evidence)),
            self._check("material_profile_reference", material_profile_reference.get("status"), "Material Profile 引用", self._messages(material_profile_reference)),
            self._check("material_profile_snapshot", material_profile_snapshot.get("status"), "Material Profile 快照", self._messages(material_profile_snapshot)),
            self._check("material_profile", material_profile_validation.get("status"), "Material Profile", self._messages(material_profile_validation)),
            self._check("material_profile_contract", material_profile_contract.get("status"), "Material Profile 参数契约", self._messages(material_profile_contract)),
            self._check("texture_quality", texture_quality_validation.get("status"), "贴图质量", self._messages(texture_quality_validation)),
            self._check("packed_channels", channel_validation.get("status"), "打包贴图通道", self._messages(channel_validation)),
            self._check("slot_binding_preflight", slot_binding_preflight.get("status"), "Static Mesh Slot 预验证", self._messages(slot_binding_preflight)),
            self._check("same_name_strategy", strategy_simulation.get("status"), "同名资产策略模拟", self._messages(strategy_simulation)),
            self._check("release_dependency_audit", release_dependency_audit.get("status"), "Release Dependency Audit", self._messages(release_dependency_audit)),
            self._check("static_mesh_lod_policy", static_mesh_lod_policy.get("status"), "Static Mesh LOD 策略", self._messages(static_mesh_lod_policy)),
        ]
        checks.append(
            self._check(
                "engine_version_preflight",
                engine_version_preflight.get("status"),
                "UE Engine Version",
                self._messages(engine_version_preflight),
            )
        )
        summary = self._summary(checks)
        report = {
            "version": "0.1",
            "schema_version": "0.2",
            "asset_forge_schema_version": "0.2",
            "status": summary.get("status", "warning"),
            "stage": "package_acceptance",
            "manifest_path": normalize_path(manifest_path),
            "asset_name": manifest.get("asset_name", ""),
            "target_path": manifest.get("target_path", ""),
            "checks": checks,
            "summary": summary,
            "import_strategy_summary": self._import_strategy_summary(manifest, texture_plan, material_plan),
            "import_policy_summary": self._import_policy_summary(manifest, texture_plan, material_asset_validation),
            "manual_validation_required": self._manual_validation_required(),
            "manifest_validation": prepared,
            "interface_contract_validation": interface_contract,
            "manifest_lint": manifest_lint,
            "package_validation": package_validation,
            "engine_version_preflight": engine_version_preflight,
            "plugin_mount_preflight": plugin_mount,
            "plugin_content_validation": plugin_content_validation,
            "material_asset_validation": material_asset_validation,
            "texture_import_plan": texture_plan,
            "material_binding_plan": material_plan,
            "parent_material_validation": parent_material_validation,
            "material_binding_contract": material_binding_contract,
            "material_graph_evidence_report": material_graph_evidence,
            "material_profile_reference_validation": material_profile_reference,
            "material_profile_snapshot_validation": material_profile_snapshot,
            "material_profile_validation": material_profile_validation,
            "material_profile_contract_validation": material_profile_contract,
            "texture_quality_validation": texture_quality_validation,
            "packed_channel_validation": channel_validation,
            "slot_binding_preflight": slot_binding_preflight,
            "same_name_strategy_simulation": strategy_simulation,
            "release_dependency_audit": release_dependency_audit,
            "static_mesh_lod_policy_validation": static_mesh_lod_policy,
        }
        attach_acceptance_summary(report, summary)
        apply_acceptance_gate(report, create_gate_policy(strict, block_warnings, require_import))
        active_report_path = normalize_path(report_path or default_report_path(os.path.dirname(os.path.abspath(manifest_path)), "package_acceptance"))
        attach_report_artifact_metadata(report, active_report_path, command_args)
        attach_report_schema_validation(report, require_gate=True)
        write_report(active_report_path, report)
        return report

    def _resolve_manifest_path(self, manifest_or_package_path):
        if os.path.isfile(manifest_or_package_path):
            return manifest_or_package_path
        if os.path.isdir(manifest_or_package_path):
            return find_latest_manifest(manifest_or_package_path)
        return ""

    def _missing_manifest_report(self, path):
        check = self._check("manifest", "error", "Manifest", ["未找到 DCC AssetForge manifest：{0}".format(path)])
        report = {
            "status": "error",
            "version": "0.1",
            "schema_version": "0.2",
            "asset_forge_schema_version": "0.2",
            "stage": "package_acceptance",
            "manifest_path": "",
            "asset_name": "",
            "target_path": "",
            "checks": [check],
            "summary": self._summary([check]),
        }
        attach_acceptance_summary(report, report["summary"])
        apply_acceptance_gate(report, create_gate_policy(False, None, False))
        active_report_path = normalize_path(report.get("report_path", ""))
        if active_report_path:
            attach_report_artifact_metadata(report, active_report_path)
        attach_report_schema_validation(report, require_gate=False)
        return report

    def _parent_material_validation(self, material_plan, material_asset_validation):
        if hasattr(self.material_asset_bootstrap, "validate_parent_materials"):
            return self.material_asset_bootstrap.validate_parent_materials(material_plan)

        missing_assets = set(material_asset_validation.get("missing_assets", []))
        checks = []
        for material in material_plan.get("materials", []):
            parent = material.get("parent_material", "")
            if parent and parent in missing_assets:
                checks.append(
                    {
                        "id": "parent_material_exists",
                        "label": "母材质",
                        "status": "error",
                        "path": parent,
                        "parent_material": parent,
                        "target_asset_path": material.get("target_asset_path", ""),
                        "message": "缺少母材质：{0}，无法安全创建材质实例".format(parent),
                    }
                )
        return {
            "status": "error" if checks else "pass",
            "can_create_material_instances": not checks,
            "message": "母材质检查通过" if not checks else "母材质缺失，无法安全创建材质实例",
            "checks": checks,
            "missing_parent_materials": [item.get("parent_material", "") for item in checks],
            "next_action": "" if not checks else "先确认 AssetForge 插件内容已挂载，并执行默认材质 Bootstrap 后重新检查母材质",
        }

    def _static_mesh_lod_policy_validation(self, manifest):
        policy = dict(manifest.get("static_mesh_import_policy", {}) or {})
        if not policy:
            policy = {"nanite_policy": "project_default", "lod_group": "project_default", "import_lod_policy": "import_existing"}
        return {
            "status": "pass",
            "policy": policy,
            "messages": ["Static Mesh Nanite / LOD 策略已进入 manifest/report；Nanite 是虚拟化几何系统，不等同传统 LOD，需真实 UE 导入后确认。"],
            "next_action": "在 UE 中打开 Static Mesh，确认 Nanite、LODGroup 与 LOD 导入结果。",
        }

    def _material_network_plans_for_evidence(self):
        try:
            if hasattr(self.material_asset_bootstrap, "plan"):
                plan = self.material_asset_bootstrap.plan()
            else:
                plan = UnrealMaterialAssetBootstrap().plan()
            return list(plan.get("material_network_plans", []) or [])
        except Exception:
            return []

    def _material_profile_reference_validation(self, manifest):
        profile_name = manifest.get("material_profile", "")
        if isinstance(profile_name, dict):
            check = self._report_check("material_profile_reference", "pass", profile_name.get("name", "inline_profile"), "manifest 使用内联 Material Profile")
            return self._report_from_checks([check], "Material Profile 引用有效")
        if not profile_name:
            check = self._report_check("material_profile_reference", "warning", "", "manifest 未指定 material_profile，将使用默认 Material Profile")
            return self._report_from_checks([check], "manifest 未指定 material_profile")
        if get_material_profile(profile_name):
            check = self._report_check("material_profile_reference", "pass", profile_name, "manifest material_profile 可在项目配置中找到")
            return self._report_from_checks([check], "Material Profile 引用有效")
        check = self._report_check("material_profile_reference", "warning", profile_name, "未知 material_profile：{0}".format(profile_name))
        return self._report_from_checks([check], "Material Profile 引用存在警告")

    def _material_profile_snapshot_validation(self, manifest):
        snapshot_path = manifest.get("material_profiles_snapshot_path", "")
        profile_name = manifest.get("material_profile", "")
        if not snapshot_path:
            check = self._report_check("material_profile_snapshot", "warning", "", "manifest 未记录 material_profiles_snapshot_path")
            return self._report_from_checks([check], "Material Profile 快照缺失")
        if not os.path.exists(snapshot_path):
            check = self._report_check("material_profile_snapshot", "warning", snapshot_path, "Material Profile 快照文件不存在")
            return self._report_from_checks([check], "Material Profile 快照缺失")
        try:
            snapshot = read_material_profiles(snapshot_path)
        except Exception as exc:
            check = self._report_check("material_profile_snapshot", "warning", snapshot_path, "Material Profile 快照读取失败：{0}".format(exc))
            return self._report_from_checks([check], "Material Profile 快照读取失败")
        if profile_name and get_material_profile(profile_name, snapshot):
            check = self._report_check("material_profile_snapshot", "pass", snapshot_path, "manifest material_profile 存在于快照中")
            return self._report_from_checks([check], "Material Profile 快照一致")
        check = self._report_check("material_profile_snapshot", "warning", snapshot_path, "manifest material_profile 不在快照中：{0}".format(profile_name or "未指定"))
        return self._report_from_checks([check], "Material Profile 快照不一致")

    def _report_check(self, check_id, status, path, message):
        return {
            "id": check_id,
            "label": check_id,
            "status": status,
            "path": normalize_path(path) if path else "",
            "message": message,
        }

    def _report_from_checks(self, checks, message):
        status = "warning" if any(item.get("status") == "warning" for item in checks) else "pass"
        return {
            "status": status,
            "message": message,
            "checks": checks,
        }

    def _check(self, check_id, status, label, messages):
        return {
            "id": check_id,
            "label": label,
            "status": status or "warning",
            "messages": [message for message in messages if message],
        }

    def _messages(self, report):
        messages = []
        for field in ("warnings", "errors"):
            for item in report.get(field, []):
                if isinstance(item, dict):
                    message = item.get("message", "")
                    if message:
                        messages.append(message)
                elif item:
                    messages.append(str(item))
        if messages:
            return messages
        for item in report.get("checks", []):
            if item.get("status") in ("warning", "error") and item.get("message"):
                messages.append(item.get("message"))
        if report.get("issues"):
            messages.extend([str(item) for item in report.get("issues", [])])
        if report.get("messages"):
            messages.extend([str(item) for item in report.get("messages", [])])
        return messages

    def _summary(self, checks):
        errors = [item for item in checks if item.get("status") == "error"]
        warnings = [item for item in checks if item.get("status") == "warning"]
        summary = create_acceptance_summary(
            "error" if errors else ("warning" if warnings else "pass"),
            self._summary_messages(warnings),
            self._summary_messages(errors),
            self._summary_next_action(errors, warnings),
        )
        summary.update({
            "error_count": len(errors),
            "warning_count": len(warnings),
            "blocking_checks": [item["id"] for item in errors],
            "warning_checks": [item["id"] for item in warnings],
        })
        return summary

    def _summary_messages(self, checks):
        messages = []
        for item in checks:
            for message in item.get("messages", []):
                messages.append({"source": item.get("id", ""), "message": message})
        return messages

    def _summary_next_action(self, errors, warnings):
        error_ids = [item.get("id", "") for item in errors]
        if "manifest" in error_ids:
            return "确认资产包目录内存在 DCC AssetForge manifest 后重新执行验收"
        if "parent_materials" in error_ids:
            return "先确认 AssetForge 插件内容已挂载，并执行默认材质 Bootstrap 后重新检查母材质"
        if errors:
            return "修复阻断项后重新执行包验收"
        if warnings:
            return "检查警告项后可进入 UE 导入"
        return "可以进入 UE 导入"

    def _import_strategy_summary(self, manifest, texture_plan, material_plan):
        return {
            "existing_mesh_strategy": manifest.get("existing_mesh_strategy", "overwrite"),
            "existing_texture_strategy": texture_plan.get("existing_texture_strategy", "overwrite"),
            "existing_material_strategy": material_plan.get("existing_material_strategy", "reuse"),
        }

    def _import_policy_summary(self, manifest, texture_plan, material_asset_validation):
        return {
            "status": "manual_validation_required",
            "static_mesh_import_policy": dict(manifest.get("static_mesh_import_policy", {}) or {}),
            "texture_import_policy": dict(texture_plan.get("texture_import_policy", manifest.get("texture_import_policy", {}) or {})),
            "material_network_status": material_asset_validation.get("material_network_status", ""),
            "material_network_message": material_asset_validation.get("material_network_message", ""),
            "manual_validation_required": self._manual_validation_required(),
            "next_action": "包验收已记录导入策略；真实 UE 导入后逐项确认 Static Mesh、Texture 与母材质网络。",
        }

    def _manual_validation_required(self):
        return [
            "真实 UE 5.6：确认 Static Mesh Nanite、LODGroup、LOD 导入结果。",
            "真实 UE 5.6：确认 Texture Virtual Texture、Streaming、Texture Group 属性。",
            "真实 UE 5.6：确认母材质网络节点、参数、连接和保存结果。",
        ]


def validate_asset_forge_package(manifest_or_package_path, report_path=None, strict=False, block_warnings=None, require_import=False, command_args=None):
    return UnrealPackageAcceptanceValidator().validate(manifest_or_package_path, report_path, strict, block_warnings, require_import, command_args)


def validate_all_asset_forge_packages(export_root, report_path=None, strict=False, block_warnings=None, require_import=False, command_args=None):
    validator = UnrealPackageAcceptanceValidator()
    manifests = []
    for root, _, file_names in os.walk(export_root):
        for file_name in file_names:
            if file_name.endswith("_manifest.json"):
                manifests.append(os.path.join(root, file_name))
    reports = [validator.validate(path, strict=strict, block_warnings=block_warnings, require_import=require_import) for path in sorted(manifests)]
    warnings = []
    errors = []
    for report in reports:
        warnings.extend(report.get("warnings", []))
        errors.extend(report.get("errors", []))
    summary = create_acceptance_summary(
        "error" if errors else ("warning" if warnings else "pass"),
        warnings,
        errors,
        "修复阻断包后重新执行批量验收" if errors else ("检查警告包后可继续" if warnings else "批量包验收通过"),
    )
    summary.update(
        {
            "can_accept": all(report.get("summary", {}).get("can_accept", False) for report in reports) if reports else False,
            "warning_count": sum(report.get("summary", {}).get("warning_count", 0) for report in reports),
            "error_count": sum(report.get("summary", {}).get("error_count", 0) for report in reports),
        }
    )
    batch_report = {
        "version": "0.1",
        "stage": "batch_package_acceptance",
        "export_root": normalize_path(export_root),
        "total": len(reports),
        "counts": {
            "pass": len([report for report in reports if report.get("status") == "pass"]),
            "warning": len([report for report in reports if report.get("status") == "warning"]),
            "error": len([report for report in reports if report.get("status") == "error"]),
        },
        "summary": summary,
        "reports": reports,
    }
    attach_acceptance_summary(batch_report, summary)
    apply_acceptance_gate(batch_report, create_gate_policy(strict, block_warnings, require_import))
    active_report_path = normalize_path(report_path or default_report_path(export_root, "batch_package_acceptance"))
    attach_report_artifact_metadata(batch_report, active_report_path, command_args)
    attach_report_schema_validation(batch_report, require_gate=True)
    write_report(active_report_path, batch_report)
    return batch_report
