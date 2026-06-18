"""One-shot acceptance flow for a single Asset Forge package."""

from __future__ import absolute_import

import os

from asset_forge.shared.acceptance_gate import apply_acceptance_gate, create_gate_policy
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.report_artifacts import attach_report_artifact_metadata, default_report_path
from asset_forge.shared.report_schema import attach_acceptance_summary, attach_report_schema_validation, create_acceptance_summary, write_report
from asset_forge.unreal.manifest_finder import find_manifest_files
from asset_forge.unreal.package_acceptance import UnrealPackageAcceptanceValidator
from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline


class UnrealPackageAcceptanceFlow(object):
    """Run package acceptance, dry-run, optional import, and unified reporting."""

    def __init__(self, acceptance_validator=None, import_pipeline=None):
        self.acceptance_validator = acceptance_validator or UnrealPackageAcceptanceValidator()
        self.import_pipeline = import_pipeline

    def run(
        self,
        package_dir,
        report_path=None,
        run_import=False,
        auto_bootstrap_material_assets=False,
        strict=False,
        block_warnings=None,
        require_import=False,
        import_options=None,
        command_args=None,
    ):
        before_acceptance = self.acceptance_validator.validate(package_dir)
        material_bootstrap = self._run_auto_material_bootstrap(auto_bootstrap_material_assets)
        acceptance = self.acceptance_validator.validate(package_dir) if auto_bootstrap_material_assets else before_acceptance
        manifest_path = acceptance.get("manifest_path", "")
        pipeline = self.import_pipeline or UnrealStaticMeshImportPipeline(
            auto_bootstrap_material_assets=auto_bootstrap_material_assets,
            import_options=import_options,
        )

        dry_run_report = self._run_dry_run(pipeline, manifest_path)
        import_report = self._run_import(pipeline, manifest_path, acceptance, run_import)
        report = self._flow_report(
            package_dir,
            before_acceptance,
            acceptance,
            material_bootstrap,
            dry_run_report,
            import_report,
            run_import,
            auto_bootstrap_material_assets,
            import_options,
        )
        apply_acceptance_gate(report, create_gate_policy(strict, block_warnings, require_import))
        active_report_path = normalize_path(report_path or self._default_report_path(package_dir))
        attach_report_artifact_metadata(report, active_report_path, command_args)
        attach_report_schema_validation(report, require_gate=True)
        write_report(active_report_path, report)
        return report

    def _run_auto_material_bootstrap(self, enabled):
        if not enabled:
            return self._skipped_step("material_bootstrap", "未启用 --auto-materials，跳过默认材质 Bootstrap")
        bootstrapper = getattr(self.acceptance_validator, "material_asset_bootstrap", None)
        if not bootstrapper or not hasattr(bootstrapper, "bootstrap"):
            return self._skipped_step("material_bootstrap", "当前验收器不支持默认材质 Bootstrap")
        try:
            report = bootstrapper.bootstrap(dry_run=False)
        except Exception as exc:
            return self._failed_step("material_bootstrap", "材质母版 Bootstrap 执行异常：{0}".format(exc))
        if report.get("status") == "failed" and not report.get("next_action"):
            report["next_action"] = "请在真实 UE 5.6 Editor Python 环境中重新执行该步骤"
        return report

    def _run_dry_run(self, pipeline, manifest_path):
        if not manifest_path:
            return self._skipped_step("dry_run", "缺少 manifest，跳过 dry-run")
        try:
            return pipeline.dry_run_manifest(manifest_path)
        except Exception as exc:
            return self._failed_step("dry_run", "dry-run 执行异常：{0}".format(exc))

    def _run_import(self, pipeline, manifest_path, acceptance, run_import):
        if not run_import:
            return self._skipped_step("import", "未请求真实导入；如需 UE 真实验收，请在 UE Python 中使用 --run-import")
        if not manifest_path:
            return self._skipped_step("import", "缺少 manifest，跳过真实导入")
        if not acceptance.get("summary", {}).get("can_accept", False):
            return self._skipped_step("import", "包验收存在阻断项，跳过真实导入")
        try:
            return pipeline.import_from_manifest(manifest_path)
        except Exception as exc:
            return self._failed_step("import", "真实导入执行异常：{0}".format(exc))

    def _flow_report(
        self,
        package_dir,
        before_acceptance,
        acceptance,
        material_bootstrap,
        dry_run_report,
        import_report,
        run_import,
        auto_bootstrap_material_assets,
        import_options,
    ):
        warnings = []
        errors = []
        for source, report in [
            ("material_bootstrap", material_bootstrap),
            ("package_acceptance", acceptance),
            ("dry_run", dry_run_report),
            ("import", import_report),
        ]:
            warnings.extend(self._tag_messages(source, report.get("warnings", [])))
            errors.extend(self._tag_messages(source, report.get("errors", [])))
            if report.get("status") == "failed":
                errors.append({"source": source, "message": report.get("message", "步骤失败")})
            warnings.extend(self._issue_messages(source, report.get("issues", [])))

        if auto_bootstrap_material_assets and material_bootstrap.get("status") == "success":
            warnings = self._filter_confirmed_material_network_warnings(warnings)

        if material_bootstrap.get("status") == "failed":
            next_action = "请在真实 UE 5.6 Editor Python 环境中重新执行该步骤"
        elif not run_import:
            next_action = "在真实 UE 5.6 项目中使用 --run-import 执行真实导入与导入后验收"
        elif errors:
            next_action = "修复阻断项后重新执行一键验收"
        else:
            next_action = "检查 warnings，确认资产可验收"

        summary = create_acceptance_summary(
            "error" if errors else ("warning" if warnings else "pass"),
            warnings,
            errors,
            next_action,
        )
        report = {
            "version": "0.1",
            "stage": "package_acceptance_flow",
            "package_dir": normalize_path(package_dir),
            "run_import": bool(run_import),
            "auto_bootstrap_material_assets": bool(auto_bootstrap_material_assets),
            "gate_import_options_override": dict(import_options or {}),
            "asset_name": acceptance.get("asset_name", ""),
            "manifest_path": acceptance.get("manifest_path", ""),
            "status": summary.get("status", ""),
            "summary": summary,
            "auto_materials": self._auto_materials_report(before_acceptance, acceptance, material_bootstrap, auto_bootstrap_material_assets),
            "package_acceptance": acceptance,
            "dry_run": dry_run_report,
            "import": import_report,
            "import_result_summary": self._import_result_summary(import_report, run_import),
            "post_import_validation": import_report.get("post_import_validation", {}),
            "step_outcomes": self._step_outcomes(
                [
                    ("material_bootstrap", material_bootstrap),
                    ("package_acceptance", acceptance),
                    ("dry_run", dry_run_report),
                    ("import", import_report),
                ]
            ),
            "user_guidance": self._user_guidance(summary),
        }
        return attach_acceptance_summary(report, summary)

    def _import_result_summary(self, import_report, run_import):
        if not run_import:
            return {
                "status": "not_requested",
                "report_path": "",
                "imported_asset_count": 0,
                "imported_texture_count": 0,
                "created_material_instance_count": 0,
                "material_assignment_count": 0,
                "post_import_status": "",
            }
        summary = import_report.get("summary", {}) if isinstance(import_report, dict) else {}
        post_import = import_report.get("post_import_validation", {}) if isinstance(import_report, dict) else {}
        return {
            "status": import_report.get("status", "") if isinstance(import_report, dict) else "",
            "summary_status": summary.get("status", ""),
            "report_path": import_report.get("report_path", "") if isinstance(import_report, dict) else "",
            "imported_asset_count": len(import_report.get("imported_assets", [])) if isinstance(import_report, dict) else 0,
            "imported_texture_count": summary.get("imported_texture_count", 0),
            "created_material_instance_count": summary.get("created_material_instance_count", 0),
            "material_assignment_count": summary.get("material_assignment_count", 0),
            "post_import_status": post_import.get("status", summary.get("post_import_status", "")),
            "expected_static_mesh_count": post_import.get("expected_static_mesh_count", 0),
            "imported_static_mesh_count": post_import.get("imported_static_mesh_count", 0),
        }

    def _tag_messages(self, source, messages):
        result = []
        for item in messages:
            if isinstance(item, dict):
                tagged = dict(item)
                tagged.setdefault("source", source)
                result.append(tagged)
            else:
                result.append({"source": source, "message": str(item)})
        return result

    def _issue_messages(self, source, issues):
        return [{"source": source, "message": str(item)} for item in issues or []]

    def _filter_confirmed_material_network_warnings(self, warnings):
        filtered = []
        for warning in warnings:
            if warning.get("source") == "material_profile_contract" and "generated_pbr" in warning.get("message", ""):
                continue
            filtered.append(warning)
        return filtered

    def _auto_materials_report(self, before_acceptance, after_acceptance, material_bootstrap, enabled):
        return {
            "enabled": bool(enabled),
            "bootstrap_report": material_bootstrap,
            "before": self._material_state(before_acceptance),
            "after": self._material_state(after_acceptance),
        }

    def _step_outcomes(self, steps):
        outcomes = []
        for name, report in steps:
            summary = report.get("summary", {}) if isinstance(report, dict) else {}
            outcomes.append(
                {
                    "stage": name,
                    "status": report.get("status", "") if isinstance(report, dict) else "",
                    "can_accept": summary.get("can_accept", report.get("can_accept", False) if isinstance(report, dict) else False),
                    "decision": summary.get("decision", report.get("decision", "") if isinstance(report, dict) else ""),
                    "message": report.get("message", "") if isinstance(report, dict) else "",
                    "next_action": summary.get("next_action", report.get("next_action", "") if isinstance(report, dict) else ""),
                    "warning_count": summary.get("warning_count", len(report.get("warnings", [])) if isinstance(report, dict) else 0),
                    "error_count": summary.get("error_count", len(report.get("errors", [])) if isinstance(report, dict) else 0),
                }
            )
        return outcomes

    def _user_guidance(self, summary):
        return {
            "decision": summary.get("decision", ""),
            "decision_label": summary.get("decision_label", ""),
            "can_import": summary.get("can_import", summary.get("can_accept", False)),
            "why": list(summary.get("why", [])),
            "next_steps": list(summary.get("next_steps", [])),
        }

    def _material_state(self, acceptance):
        return {
            "status": acceptance.get("status", ""),
            "summary": acceptance.get("summary", {}),
            "material_asset_status": acceptance.get("material_asset_validation", {}).get("status", ""),
            "material_asset_message": acceptance.get("material_asset_validation", {}).get("message", ""),
            "parent_material_status": acceptance.get("parent_material_validation", {}).get("status", ""),
            "parent_material_message": acceptance.get("parent_material_validation", {}).get("message", ""),
            "missing_parent_materials": acceptance.get("parent_material_validation", {}).get("missing_parent_materials", []),
        }

    def _skipped_step(self, stage, message):
        summary = create_acceptance_summary("skipped", [], [], message)
        report = {
            "status": "skipped",
            "stage": stage,
            "message": message,
            "summary": summary,
        }
        return attach_acceptance_summary(report, summary)

    def _failed_step(self, stage, message):
        summary = create_acceptance_summary("error", [], [{"message": message}], "修复异常后重新执行一键导入。")
        report = {
            "status": "failed",
            "stage": stage,
            "message": message,
            "errors": [{"message": message}],
            "summary": summary,
        }
        return attach_acceptance_summary(report, summary)

    def _default_report_path(self, package_dir):
        return default_report_path(package_dir, "package_acceptance_flow")


def run_asset_forge_package_acceptance(
    package_dir,
    report_path=None,
    run_import=False,
    auto_bootstrap_material_assets=False,
    strict=False,
    block_warnings=None,
    require_import=False,
    import_options=None,
    command_args=None,
):
    return UnrealPackageAcceptanceFlow().run(
        package_dir,
        report_path,
        run_import,
        auto_bootstrap_material_assets,
        strict,
        block_warnings,
        require_import,
        import_options,
        command_args,
    )


class UnrealBatchPackageAcceptanceFlow(object):
    """Run the one-shot acceptance flow for every package under a root."""

    def __init__(self, item_flow=None):
        self.item_flow = item_flow or UnrealPackageAcceptanceFlow()

    def run(
        self,
        export_root,
        report_path=None,
        run_import=False,
        auto_bootstrap_material_assets=False,
        strict=False,
        block_warnings=None,
        require_import=False,
        import_options=None,
        command_args=None,
    ):
        manifests = find_manifest_files(export_root)
        reports = []
        policy = create_gate_policy(strict, block_warnings, require_import)
        for manifest_path in manifests:
            package_dir = os.path.dirname(os.path.abspath(manifest_path))
            reports.append(
                self.item_flow.run(
                    package_dir,
                    run_import=run_import,
                    auto_bootstrap_material_assets=auto_bootstrap_material_assets,
                    strict=strict,
                    block_warnings=block_warnings,
                    require_import=require_import,
                    import_options=import_options,
                )
            )
        report = self._batch_report(export_root, reports, run_import, auto_bootstrap_material_assets, import_options)
        apply_acceptance_gate(report, policy)
        active_report_path = normalize_path(report_path or self._default_report_path(export_root))
        attach_report_artifact_metadata(report, active_report_path, command_args)
        attach_report_schema_validation(report, require_gate=True)
        write_report(active_report_path, report)
        return report

    def _batch_report(self, export_root, reports, run_import, auto_bootstrap_material_assets, import_options):
        warnings = []
        errors = []
        blocked = []
        warning_packages = []
        for report in reports:
            warnings.extend(report.get("warnings", []))
            errors.extend(report.get("errors", []))
            package_dir = report.get("package_dir", "")
            if not report.get("summary", {}).get("can_accept", False):
                blocked.append(package_dir)
            elif report.get("summary", {}).get("warning_count", 0):
                warning_packages.append(package_dir)

        summary = create_acceptance_summary(
            "error" if errors else ("warning" if warnings else "pass"),
            warnings,
            errors,
            "修复阻断包后重新执行批量一键验收" if errors else ("检查警告包后可继续" if warnings else "批量一键验收通过"),
        )
        summary.update(
            {
                "blocked_packages": [normalize_path(path) for path in blocked],
                "warning_packages": [normalize_path(path) for path in warning_packages],
            }
        )
        report = {
            "version": "0.1",
            "stage": "batch_package_acceptance_flow",
            "export_root": normalize_path(export_root),
            "run_import": bool(run_import),
            "auto_bootstrap_material_assets": bool(auto_bootstrap_material_assets),
            "gate_import_options_override": dict(import_options or {}),
            "total": len(reports),
            "counts": {
                "pass": len([item for item in reports if item.get("status") == "pass"]),
                "warning": len([item for item in reports if item.get("status") == "warning"]),
                "error": len([item for item in reports if item.get("status") == "error"]),
            },
            "summary": summary,
            "reports": reports,
            "package_decisions": self._package_decisions(reports),
            "user_guidance": self._user_guidance(summary),
        }
        return attach_acceptance_summary(report, summary)

    def _package_decisions(self, reports):
        decisions = []
        for report in reports:
            summary = report.get("summary", {})
            decisions.append(
                {
                    "package_dir": normalize_path(report.get("package_dir", "")),
                    "asset_name": report.get("asset_name", ""),
                    "status": report.get("status", ""),
                    "decision": summary.get("decision", report.get("decision", "")),
                    "can_accept": summary.get("can_accept", report.get("can_accept", False)),
                    "can_import": summary.get("can_import", report.get("can_import", False)),
                    "warning_count": summary.get("warning_count", len(report.get("warnings", []))),
                    "error_count": summary.get("error_count", len(report.get("errors", []))),
                    "next_action": summary.get("next_action", report.get("next_action", "")),
                }
            )
        return decisions

    def _user_guidance(self, summary):
        return {
            "decision": summary.get("decision", ""),
            "decision_label": summary.get("decision_label", ""),
            "can_import": summary.get("can_import", summary.get("can_accept", False)),
            "why": list(summary.get("why", [])),
            "next_steps": list(summary.get("next_steps", [])),
        }

    def _default_report_path(self, export_root):
        return default_report_path(export_root, "batch_package_acceptance_flow")


def run_all_asset_forge_package_acceptance(
    export_root,
    report_path=None,
    run_import=False,
    auto_bootstrap_material_assets=False,
    strict=False,
    block_warnings=None,
    require_import=False,
    import_options=None,
    command_args=None,
):
    return UnrealBatchPackageAcceptanceFlow().run(
        export_root,
        report_path,
        run_import,
        auto_bootstrap_material_assets,
        strict,
        block_warnings,
        require_import,
        import_options,
        command_args,
    )
