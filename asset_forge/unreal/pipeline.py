"""Unreal import pipeline orchestration."""

from __future__ import absolute_import

import os

from asset_forge.shared.constants import UNREAL_IMPORT_STATUS_FAILED
from asset_forge.shared.material_profile_validator import validate_material_texture_coverage, validate_material_texture_quality
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.report_schema import attach_acceptance_summary, create_batch_report, create_end_to_end_report, read_report, summarize_pipeline, write_report
from asset_forge.unreal.engine_version_preflight import UnrealEngineVersionPreflight
from asset_forge.unreal.fbx_importer import UnrealStaticMeshFbxImporter
from asset_forge.unreal.import_logger import UnrealImportLogger
from asset_forge.unreal.material_asset_bootstrap import UnrealMaterialAssetBootstrap
from asset_forge.unreal.material_binding_planner import UnrealMaterialBindingPlanner
from asset_forge.unreal.material_evidence_collector import UnrealMaterialEvidenceCollector
from asset_forge.unreal.material_graph_evidence import build_material_graph_evidence_report
from asset_forge.unreal.material_instance_creator import UnrealMaterialInstanceCreator
from asset_forge.unreal.material_slot_assigner import UnrealMaterialSlotAssigner
from asset_forge.unreal.material_texture_binding_validator import validate_material_texture_bindings
from asset_forge.unreal.manifest_finder import find_latest_manifest, find_manifest_files
from asset_forge.unreal.manifest_reader import UnrealManifestReader
from asset_forge.unreal.operation_logger import UnrealOperationLogger
from asset_forge.unreal.package_validator import UnrealPackageValidator
from asset_forge.unreal.plugin_content_bootstrap import UnrealPluginContentBootstrap
from asset_forge.unreal.post_import_validator import UnrealPostImportValidator
from asset_forge.unreal.texture_import_planner import UnrealTextureImportPlanner
from asset_forge.unreal.texture_importer import UnrealTextureImporter, preview_texture_import_policy_report


class UnrealStaticMeshImportPipeline(object):
    """Read manifest, resolve preset, import FBX, and return a report."""

    def __init__(
        self,
        reader=None,
        importer=None,
        logger=None,
        post_import_validator=None,
        package_validator=None,
        texture_import_planner=None,
        texture_importer=None,
        material_binding_planner=None,
        material_instance_creator=None,
        material_slot_assigner=None,
        material_evidence_collector=None,
        plugin_content_bootstrap=None,
        material_asset_bootstrap=None,
        engine_version_preflight=None,
        auto_bootstrap_material_assets=False,
        import_options=None,
    ):
        self.reader = reader or UnrealManifestReader()
        self.importer = importer or UnrealStaticMeshFbxImporter()
        self.logger = logger or UnrealImportLogger()
        self.post_import_validator = post_import_validator or UnrealPostImportValidator()
        self.package_validator = package_validator or UnrealPackageValidator()
        self.texture_import_planner = texture_import_planner or UnrealTextureImportPlanner()
        self.texture_importer = texture_importer or UnrealTextureImporter()
        self.material_binding_planner = material_binding_planner or UnrealMaterialBindingPlanner()
        self.material_instance_creator = material_instance_creator or UnrealMaterialInstanceCreator()
        self.material_slot_assigner = material_slot_assigner or UnrealMaterialSlotAssigner()
        self.material_evidence_collector = material_evidence_collector or UnrealMaterialEvidenceCollector()
        self.plugin_content_bootstrap = plugin_content_bootstrap or UnrealPluginContentBootstrap()
        self.material_asset_bootstrap = material_asset_bootstrap or UnrealMaterialAssetBootstrap()
        self.engine_version_preflight = engine_version_preflight or UnrealEngineVersionPreflight()
        self.auto_bootstrap_material_assets = bool(auto_bootstrap_material_assets)
        self.import_options = dict(import_options or {})

    def dry_run_manifest(self, manifest_path, log_path=None):
        prepared = self._apply_import_options_override(self.reader.load(manifest_path, require_fbx_exists=True))
        manifest = prepared["manifest"]
        active_log_path = log_path or self._default_import_report_path(manifest, manifest_path)
        if not prepared["can_import"]:
            report = self.logger.failed(manifest, prepared["issues"], "Manifest 校验失败", prepared.get("preset"))
            report["manifest_path"] = normalize_path(manifest_path)
            self._attach_common_preflight(report, manifest)
            self._log_texture_policy_preview_events(report, active_log_path)
            self._finalize_report(report)
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        report = self.logger.skipped(manifest, prepared["preset"], "预检查通过，未执行导入")
        report["manifest_path"] = normalize_path(manifest_path)
        self._attach_common_preflight(report, manifest)
        self._log_texture_policy_preview_events(report, active_log_path)
        self._finalize_report(report)
        self._write_log(active_log_path, report)
        self._write_end_to_end_report(manifest, manifest_path, report)
        return report

    def import_from_manifest(self, manifest_path, log_path=None):
        prepared = self._apply_import_options_override(self.reader.load(manifest_path, require_fbx_exists=True))
        manifest = prepared["manifest"]
        active_log_path = log_path or self._default_import_report_path(manifest, manifest_path)
        self._log_operation(
            "unreal_import_entry",
            "started",
            inputs={"manifest_path": normalize_path(manifest_path), "asset_name": manifest.get("asset_name", "")},
            report_path=active_log_path,
        )
        if not prepared["can_import"]:
            report = self.logger.failed(manifest, prepared["issues"], "Manifest 校验失败", prepared.get("preset"))
            report["manifest_path"] = normalize_path(manifest_path)
            self._attach_common_preflight(report, manifest)
            self._finalize_report(report)
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        engine_version_preflight = self.engine_version_preflight.check(manifest)
        if not engine_version_preflight.get("can_write_assets", False):
            issues = [item.get("message", "") for item in engine_version_preflight.get("errors", [])]
            report = self.logger.failed(manifest, issues, "UE engine version preflight failed", prepared["preset"])
            report["manifest_path"] = normalize_path(manifest_path)
            self._attach_common_preflight(report, manifest)
            report["engine_version_preflight"] = engine_version_preflight
            self._finalize_report(report)
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        try:
            imported_assets = self.importer.import_static_mesh(manifest, prepared["preset"])
        except Exception as exc:
            report = self.logger.failed(manifest, [str(exc)], "Unreal 导入失败", prepared["preset"])
            report["manifest_path"] = normalize_path(manifest_path)
            self._attach_common_preflight(report, manifest)
            self._finalize_report(report)
            self._write_log(active_log_path, report)
            self._write_end_to_end_report(manifest, manifest_path, report)
            return report

        report = self.logger.success(manifest, imported_assets, preset=prepared["preset"])
        report["manifest_path"] = normalize_path(manifest_path)
        report["static_mesh_import_policy_report"] = getattr(
            self.importer,
            "last_import_policy_report",
            {"status": "skipped", "existing_mesh_strategy": "", "actions": [], "issues": []},
        )
        importer_options_report = getattr(self.importer, "last_fbx_import_options_report", None)
        if importer_options_report:
            report["fbx_import_options_report"] = importer_options_report
        self._attach_common_preflight(report, manifest)
        self._auto_bootstrap_material_assets(report)
        self._import_planned_textures(report)
        self._select_material_variants_for_imported_textures(report)
        self._attach_material_sampler_policy_validation(report)
        self._create_material_instances(report)
        self._attach_material_texture_binding_validation(report, manifest)
        self._assign_material_slots(report)
        self._collect_material_graph_evidence(report)
        self._attach_material_graph_evidence(report)
        report = self._attach_post_import_validation(report, manifest, imported_assets)
        self._finalize_report(report)
        self._write_log(active_log_path, report)
        self._write_end_to_end_report(manifest, manifest_path, report)
        return report

    def _apply_import_options_override(self, prepared):
        if not self.import_options:
            return prepared

        prepared = dict(prepared)
        manifest = dict(prepared.get("manifest") or {})
        preset = dict(prepared.get("preset") or {})
        policy = dict(manifest.get("static_mesh_import_policy") or {})
        options = dict(self.import_options)

        for key in [
            "import_mesh",
            "import_materials",
            "import_textures",
            "fbx_import_materials",
            "fbx_import_textures",
            "combine_meshes",
            "generate_lightmap_uvs",
            "normal_import_method",
            "normal_generation_method",
            "vertex_color_import_option",
            "vertex_override_color",
            "convert_scene",
            "force_front_x_axis",
            "convert_scene_unit",
            "transform_vertex_to_absolute",
            "bake_pivot_in_vertex",
            "import_translation",
            "import_rotation",
            "import_uniform_scale",
        ]:
            if key in options:
                preset[key] = options[key]
        if "auto_generate_collision" in options:
            preset["generate_missing_collision"] = bool(options["auto_generate_collision"])
        if "build_nanite" in options:
            policy["nanite_policy"] = "enable" if options["build_nanite"] else "disable"
        if "import_mesh_lods" in options:
            policy["import_lod_policy"] = "import_existing" if options["import_mesh_lods"] else "ignore_lods"
        if "static_mesh_lod_group" in options:
            policy["lod_group"] = options["static_mesh_lod_group"] or "project_default"
        if "build_reversed_index_buffer" in options:
            policy["build_reversed_index_buffer"] = "enable" if options["build_reversed_index_buffer"] else "disable"
        for key in ["one_convex_hull_per_ucx", "remove_degenerates", "compute_weighted_normals"]:
            if key in options:
                preset[key] = options[key]

        manifest["static_mesh_import_policy"] = policy
        prepared["manifest"] = manifest
        prepared["preset"] = preset
        prepared["gate_import_options_override"] = options
        return prepared

    def _attach_common_preflight(self, report, manifest):
        report["gate_import_options_override"] = dict(self.import_options or {})
        self._attach_engine_version_preflight(report, manifest)
        self._attach_package_validation(report, manifest)
        self._attach_plugin_content_validation(report)
        self._attach_texture_import_plan(report, manifest)
        self._attach_material_binding_plan(report, manifest)
        self._attach_material_texture_binding_validation(report, manifest)
        self._attach_material_network_preflight(report)
        self._attach_fbx_import_options(report, manifest)
        self._attach_static_mesh_lod_policy(report, manifest)
        self._attach_material_profile_validation(report, manifest)
        self._attach_texture_quality_validation(report, manifest)
        self._attach_import_policy_summary(report, manifest)
        self._attach_material_graph_evidence(report)
        return report

    def _attach_engine_version_preflight(self, report, manifest):
        report["engine_version_preflight"] = self.engine_version_preflight.check(manifest)
        return report

    def _write_log(self, log_path, report):
        if log_path:
            report["report_path"] = normalize_path(log_path)
            self.logger.write(log_path, report)

    def _default_import_report_path(self, manifest, manifest_path):
        package_dir = manifest.get("package_dir") or os.path.dirname(os.path.abspath(manifest_path))
        asset_name = manifest.get("asset_name", "asset")
        return os.path.join(package_dir, asset_name + "_import_report.json")

    def _default_export_report_path(self, manifest, manifest_path):
        package_dir = manifest.get("package_dir") or os.path.dirname(os.path.abspath(manifest_path))
        asset_name = manifest.get("asset_name", "asset")
        return os.path.join(package_dir, asset_name + "_export_report.json")

    def _default_end_to_end_report_path(self, manifest, manifest_path):
        package_dir = manifest.get("package_dir") or os.path.dirname(os.path.abspath(manifest_path))
        asset_name = manifest.get("asset_name", "asset")
        return os.path.join(package_dir, asset_name + "_end_to_end_report.json")

    def _write_end_to_end_report(self, manifest, manifest_path, import_report):
        export_report_path = self._default_export_report_path(manifest, manifest_path)
        export_report = read_report(export_report_path) if os.path.exists(export_report_path) else {}
        report = create_end_to_end_report(export_report, import_report)
        write_report(self._default_end_to_end_report_path(manifest, manifest_path), report)

    def _attach_post_import_validation(self, report, manifest, imported_assets):
        validation = self.post_import_validator.validate(manifest, imported_assets, report.get("fbx_import_options_report", {}))
        report["post_import_validation"] = validation
        self._log_operation(
            "unreal_post_import_validation",
            validation.get("status", "skipped"),
            inputs={"asset_name": manifest.get("asset_name", "")},
            outputs={"can_accept": validation.get("can_accept", None), "check_count": len(validation.get("checks", []))},
            warnings=[item for item in validation.get("checks", []) if item.get("status") == "warning"],
            errors=[item for item in validation.get("checks", []) if item.get("status") == "error"],
            report_path=report.get("report_path", ""),
        )
        if not validation.get("can_accept", False):
            issues = [item["message"] for item in validation.get("checks", []) if item.get("status") == "error"]
            report["status"] = UNREAL_IMPORT_STATUS_FAILED
            report["message"] = "导入完成，但导入后校验存在错误"
            report["issues"] = report.get("issues", []) + issues
        return report

    def _attach_package_validation(self, report, manifest):
        report["package_validation"] = self.package_validator.validate(manifest)
        return report

    def _attach_plugin_content_validation(self, report):
        report["plugin_content_validation"] = self.plugin_content_bootstrap.validate()
        return report

    def _attach_texture_import_plan(self, report, manifest):
        try:
            report["texture_import_plan"] = self.texture_import_planner.plan(manifest)
            report["texture_import_policy_report"] = preview_texture_import_policy_report(report["texture_import_plan"])
        except ValueError as exc:
            report["texture_import_plan"] = {
                "status": "error",
                "target_dir": "",
                "count": 0,
                "textures": [],
                "issues": [str(exc)],
            }
            report["texture_import_policy_report"] = preview_texture_import_policy_report(report["texture_import_plan"])
        return report

    def _attach_material_binding_plan(self, report, manifest):
        try:
            report["material_binding_plan"] = self.material_binding_planner.plan(
                manifest,
                report.get("texture_import_plan", {}),
                manifest.get("material_profile"),
            )
        except ValueError as exc:
            report["material_binding_plan"] = {
                "status": "error",
                "target_dir": "",
                "count": 0,
                "materials": [],
                "issues": [str(exc)],
            }
        return report

    def _attach_material_network_preflight(self, report):
        try:
            plan = self.material_asset_bootstrap.plan()
            report["material_network_summary"] = {
                "status": "manual_validation_required",
                "material_network_status": plan.get("material_network_status", ""),
                "material_network_message": plan.get("material_network_message", ""),
                "content_mount": plan.get("content_mount", ""),
                "asset_count": plan.get("asset_count", 0),
                "next_action": "在真实 UE 5.6 中执行材质 Bootstrap，并打开母材质确认节点和连接。",
            }
        except Exception as exc:
            report["material_network_summary"] = {
                "status": "warning",
                "material_network_status": "",
                "material_network_message": "无法生成母材质网络摘要：{0}".format(exc),
                "content_mount": "",
                "asset_count": 0,
                "next_action": "检查 Material Profile 和 material asset bootstrap 后重新执行 dry-run。",
            }
        return report

    def _attach_fbx_import_options(self, report, manifest):
        if report.get("fbx_import_options_report"):
            return report
        try:
            preset = report.get("resolved_preset") or report.get("preset") or report.get("import_preset") or {}
            if not isinstance(preset, dict):
                preset = {}
            if hasattr(self.importer, "plan_fbx_import_options"):
                report["fbx_import_options_report"] = self.importer.plan_fbx_import_options(manifest, preset)
            else:
                report["fbx_import_options_report"] = {
                    "status": "warning",
                    "api": {},
                    "policy": dict(manifest.get("static_mesh_import_policy", {}) or {}),
                    "options": {},
                    "warnings": ["当前 importer 不支持 FBX 导入选项计划报告。"],
                    "next_action": "更新 UE importer 后重新执行 dry-run。",
                }
        except Exception as exc:
            report["fbx_import_options_report"] = {
                "status": "warning",
                "api": {},
                "policy": {},
                "options": {},
                "warnings": ["生成 FBX 导入选项计划失败：{0}".format(exc)],
                "next_action": "检查 manifest static_mesh_import_policy 与 import preset。",
            }
        return report

    def _attach_static_mesh_lod_policy(self, report, manifest):
        policy = dict(manifest.get("static_mesh_import_policy", {}) or {})
        if not policy:
            policy = {"lod_group": "project_default", "import_lod_policy": "import_existing"}
        report["static_mesh_lod_policy_report"] = {
            "status": "warning",
            "policy": policy,
            "message": "已记录 Static Mesh Nanite / LOD 策略；Nanite 是虚拟化几何系统，不等同传统 LOD。当前报告不假装完成生产级自动 LOD。",
            "next_action": "在真实 UE 5.6 中导入后，打开 Static Mesh 资产确认 Nanite、LODGroup 与 LOD 导入结果。",
        }
        return report

    def _attach_material_profile_validation(self, report, manifest):
        report["material_profile_validation"] = validate_material_texture_coverage(
            manifest.get("material_profile"),
            manifest.get("textures", []),
        )
        return report

    def _attach_texture_quality_validation(self, report, manifest):
        report["texture_quality_validation"] = validate_material_texture_quality(
            manifest.get("material_profile"),
            manifest.get("textures", []),
        )
        return report

    def _attach_import_policy_summary(self, report, manifest):
        texture_plan = report.get("texture_import_plan", {}) or {}
        resolved_preset = report.get("resolved_preset") or {}
        if not isinstance(resolved_preset, dict):
            resolved_preset = {}
        report["import_policy_summary"] = {
            "status": "manual_validation_required",
            "content_import_policy": self._content_import_policy_summary(report, resolved_preset),
            "static_mesh_import_policy": dict(manifest.get("static_mesh_import_policy", {}) or {}),
            "texture_import_policy": dict(texture_plan.get("texture_import_policy", manifest.get("texture_import_policy", {}) or {})),
            "texture_policy_report_shape": "请求策略 / 实际应用 / 需要人工确认",
            "material_network_status": report.get("material_network_summary", {}).get("material_network_status", ""),
            "manual_validation_required": [
                "Static Mesh Nanite、LODGroup、LOD 导入结果必须在真实 UE Static Mesh 资产中确认。",
                "Texture Virtual Texture、Streaming、Texture Group 必须在真实 UE 贴图资产中确认。",
                "母材质网络节点、参数和连接必须在真实 UE Material Editor 中确认。",
            ],
            "next_action": "dry-run 已记录导入策略；真实 UE 导入后按 manual_validation_required 逐项确认。",
        }
        report["manual_validation_required"] = list(report["import_policy_summary"]["manual_validation_required"])
        return report

    def _content_import_policy_summary(self, report, resolved_preset):
        overrides = report.get("gate_import_options_override") or {}
        summary = {}
        for key in ("import_mesh", "import_materials", "import_textures"):
            summary[key] = {
                "enabled": bool(resolved_preset.get(key, True)),
                "source": "gate_override" if key in overrides else "resolved_preset",
            }
        return summary

    def _auto_bootstrap_material_assets(self, report):
        report["material_asset_bootstrap_report"] = {
            "status": "skipped",
            "message": "未启用自动材质资产 Bootstrap",
            "created_assets": [],
            "existing_assets": [],
            "issues": [],
        }
        if not self.auto_bootstrap_material_assets:
            return report

        bootstrap_report = self.material_asset_bootstrap.bootstrap(dry_run=False, repair_existing_assets=False)
        report["material_asset_bootstrap_report"] = bootstrap_report
        if bootstrap_report.get("status") in ("success", "warning"):
            self._attach_plugin_content_validation(report)
        return report

    def _import_planned_textures(self, report):
        plan = report.get("texture_import_plan", {})
        report["imported_textures"] = []
        report["texture_import_issues"] = []
        if not self._content_import_enabled(report, "import_textures"):
            report["texture_configuration_report"] = {"status": "skipped", "configured": [], "issues": []}
            report["texture_import_policy_report"] = {
                "status": "skipped",
                "existing_texture_strategy": "",
                "actions": [],
                "issues": [],
                "skip_reason": "import_textures=false；UE Gate 内容导入策略要求跳过贴图导入。",
            }
            return report
        if not plan.get("count", 0):
            return report

        try:
            report["imported_textures"] = self.texture_importer.import_textures(plan)
            report["texture_configuration_report"] = getattr(
                self.texture_importer,
                "last_configuration_report",
                {"status": "skipped", "configured": [], "issues": []},
            )
            report["texture_import_policy_report"] = getattr(
                self.texture_importer,
                "last_import_policy_report",
                {"status": "skipped", "existing_texture_strategy": "", "actions": [], "issues": []},
            )
            self._log_texture_policy_events(report)
        except Exception as exc:
            report["texture_import_issues"].append("贴图导入失败：{0}".format(exc))
            report["texture_configuration_report"] = {"status": "skipped", "configured": [], "issues": []}
            report["texture_import_policy_report"] = {"status": "skipped", "existing_texture_strategy": "", "actions": [], "issues": []}
        return report

    def _log_texture_policy_events(self, report):
        for item in report.get("texture_configuration_report", {}).get("configured", []):
            policy_report = item.get("policy_report", {}) or {}
            self._log_operation(
                "unreal_texture_policy_application",
                "warning" if policy_report.get("warnings") else "success",
                inputs={
                    "asset_path": item.get("asset_path", ""),
                    "usage": item.get("usage", ""),
                    "requested_policy": policy_report.get("requested_policy", {}),
                },
                outputs={
                    "applied": policy_report.get("applied", []),
                    "actual_policy": policy_report.get("actual_policy", {}),
                    "resolved_virtual_texture_policy": policy_report.get("resolved_virtual_texture_policy", ""),
                    "user_message": policy_report.get("user_message", ""),
                },
                warnings=policy_report.get("warnings", []),
                report_path=report.get("report_path", ""),
            )

    def _log_texture_policy_preview_events(self, report, report_path=""):
        for item in report.get("texture_import_policy_report", {}).get("actions", []):
            policy_report = item.get("policy_report", {}) or {}
            self._log_operation(
                "unreal_texture_policy_preview",
                "warning" if policy_report.get("warnings") else "success",
                inputs={
                    "asset_path": item.get("target_asset_path", ""),
                    "requested_policy": policy_report.get("requested_policy", {}),
                    "mode": policy_report.get("mode", "offline_preview"),
                },
                outputs={
                    "applied": policy_report.get("applied", []),
                    "actual_policy": policy_report.get("actual_policy", {}),
                    "actual_policy_source": policy_report.get("actual_policy_source", ""),
                    "resolved_virtual_texture_policy": policy_report.get("resolved_virtual_texture_policy", ""),
                    "user_message": policy_report.get("user_message", ""),
                },
                warnings=policy_report.get("warnings", []),
                report_path=report_path or report.get("report_path", ""),
            )

    def _select_material_variants_for_imported_textures(self, report):
        plan = report.get("material_binding_plan", {}) or {}
        materials = plan.get("materials", [])
        if not materials:
            return report

        vt_capable_parents = self._vt_capable_parent_materials()
        vt_assets = set()
        for item in report.get("texture_configuration_report", {}).get("configured", []):
            policy_report = item.get("policy_report", {}) or {}
            actual = policy_report.get("actual_policy", {}) or {}
            requested = policy_report.get("requested_policy", {}) or {}
            if self._policy_reports_virtual_texture(policy_report):
                vt_assets.add(item.get("asset_path", ""))

        decisions = []
        for material in materials:
            slots = material.get("slots", {}) or {}
            texture_parameter_paths = set((material.get("texture_parameters", {}) or {}).values())
            slot_paths = set(slots.values())
            material_texture_paths = texture_parameter_paths.union(slot_paths)
            requires_vt = any(path in vt_assets for path in material_texture_paths)
            original_parent = material.get("parent_material", "")
            vt_candidate = self._vt_material_variant(original_parent)
            uses_vt = requires_vt and vt_candidate in vt_capable_parents
            selected_parent = vt_candidate if uses_vt else original_parent
            material["requires_virtual_texture_sampling"] = requires_vt
            material["uses_virtual_texture_sampling"] = uses_vt
            material["parent_material"] = selected_parent
            material["parent_material_path"] = selected_parent
            if uses_vt:
                material["material_sampler_variant"] = "virtual_texture"
                material["parent_material_reason"] = "真实 UE 导入后检测到绑定贴图为 Virtual Texture，切换到 VT 采样母材质变体。"
            if requires_vt and not uses_vt:
                material["material_sampler_variant"] = "virtual_texture_required_unavailable"
                material["parent_material_reason"] = "Detected VT texture input, but DCC AssetForge has no verified VT-capable parent material yet."
            decisions.append(
                {
                    "material_instance_path": material.get("target_asset_path", ""),
                    "requires_virtual_texture_sampling": requires_vt,
                    "uses_virtual_texture_sampling": uses_vt,
                    "original_parent_material": original_parent,
                    "selected_parent_material": selected_parent,
                    "vt_capable_parent_available": uses_vt,
                    "vt_texture_assets": sorted(path for path in material_texture_paths if path in vt_assets),
                }
            )

        requires_unavailable = any(item["requires_virtual_texture_sampling"] and not item["uses_virtual_texture_sampling"] for item in decisions)
        report["material_variant_selection"] = {
            "status": "vt_sampler_required_unavailable" if requires_unavailable else ("vt_variant_selected" if any(item["uses_virtual_texture_sampling"] for item in decisions) else "standard_variant_selected"),
            "vt_asset_count": len(vt_assets),
            "decisions": decisions,
        }
        return report

    def _vt_capable_parent_materials(self):
        try:
            if hasattr(self.material_asset_bootstrap, "plan"):
                plan = self.material_asset_bootstrap.plan()
            else:
                plan = UnrealMaterialAssetBootstrap().plan()
        except Exception:
            return set()
        return set(
            item.get("material_path", "")
            for item in plan.get("material_network_plans", [])
            if item.get("supports_virtual_texture_sampling")
        )

    def _vt_material_variant(self, parent_material):
        if not parent_material or parent_material.endswith("_VT"):
            return parent_material
        if not parent_material.startswith("/AssetForge/Materials/"):
            return parent_material
        return parent_material + "_VT"

    def _policy_reports_virtual_texture(self, policy_report):
        policy_report = policy_report or {}
        requested = policy_report.get("requested_policy", {}) or {}
        if requested.get("virtual_texture_policy") == "force_on":
            return True
        return False

    def _attach_material_sampler_policy_validation(self, report):
        texture_configuration = report.get("texture_configuration_report", {}) or {}
        if hasattr(self.material_asset_bootstrap, "plan"):
            material_plan = self.material_asset_bootstrap.plan()
        else:
            material_plan = UnrealMaterialAssetBootstrap().plan()
        selected_materials = report.get("material_binding_plan", {}).get("materials", [])
        network_by_path = dict((item.get("material_path", ""), item) for item in material_plan.get("material_network_plans", []))
        selected_networks = [network_by_path.get(item.get("parent_material", ""), {}) for item in selected_materials]
        supports_vt = any(item.get("supports_virtual_texture_sampling") for item in selected_networks)
        if not selected_materials:
            selected_networks = material_plan.get("material_network_plans", [])
            supports_vt = any(plan.get("supports_virtual_texture_sampling") for plan in selected_networks)
        ordinary_nodes = []
        for plan in selected_networks:
            ordinary_nodes.extend([node for node in plan.get("nodes", []) if node.get("node_type") == "TextureSampleParameter2D"])

        checks = []
        effective_vt_assets = []
        unknown_vt_assets = []
        for item in texture_configuration.get("configured", []):
            policy_report = item.get("policy_report", {}) or {}
            requested = policy_report.get("requested_policy", {})
            actual = policy_report.get("actual_policy", {})
            effective = actual.get("effective_virtual_texture")
            asset_path = item.get("asset_path", "")
            if self._policy_reports_virtual_texture(policy_report):
                effective_vt_assets.append(asset_path)
            elif effective is True or effective in ("auto_project_default", "project_default", "unsupported", None):
                unknown_vt_assets.append(asset_path)
            elif isinstance(effective, str) and effective.lower() in ("true", "enabled", "on", "virtual_texture"):
                unknown_vt_assets.append(asset_path)

        if effective_vt_assets and not supports_vt:
            checks.append(
                {
                    "id": "vt_sampler_mismatch",
                    "label": "材质采样策略",
                    "status": "warning",
                    "asset_paths": effective_vt_assets,
                    "message": "有效贴图为 Virtual Texture，但当前母材质计划仍使用普通 TextureSampleParameter2D。",
                    "next_action": "只有显式 force_on 才应使用 VT sampler/VT material variant；请切换支持 VT 的母材质，或关闭这些贴图的 VT 后重新验收。",
                }
            )
        elif effective_vt_assets:
            checks.append(
                {
                    "id": "vt_sampler_compatible",
                    "label": "材质采样策略",
                    "status": "pass",
                    "asset_paths": effective_vt_assets,
                    "message": "有效 VT 贴图与支持 VT 采样的母材质计划一致。",
                }
            )

        if unknown_vt_assets:
            checks.append(
                {
                    "id": "vt_sampler_manual_confirm",
                    "label": "材质采样策略",
                    "status": "warning",
                    "asset_paths": unknown_vt_assets,
                    "message": "部分贴图使用 auto/project_default/unsupported VT 结果，无法离线确认采样器是否完全自洽。",
                    "next_action": "在真实 UE 中打开贴图和母材质，确认 Virtual Texture 状态与采样节点类型一致。",
                }
            )

        if not checks:
            checks.append(
                {
                    "id": "vt_sampler_not_required",
                    "label": "材质采样策略",
                    "status": "pass",
                    "asset_paths": [],
                    "message": "当前未发现有效 Virtual Texture 贴图，普通 TextureSampleParameter2D 可继续使用。",
                }
            )

        warnings = [item for item in checks if item.get("status") == "warning"]
        errors = [item for item in checks if item.get("status") == "error"]
        report["material_sampler_policy_validation"] = {
            "status": "error" if errors else ("warning" if warnings else "pass"),
            "supports_virtual_texture_sampling": supports_vt,
            "ordinary_sampler_node_count": len(ordinary_nodes),
            "checks": checks,
            "warnings": warnings,
            "errors": errors,
            "next_action": "检查材质采样策略 warning 后继续；真实 UE 中必须确认贴图 VT 状态和母材质采样节点一致。" if warnings else "材质采样策略与当前贴图策略一致。",
        }
        self._log_operation(
            "unreal_material_sampler_policy_validation",
            report["material_sampler_policy_validation"].get("status", ""),
            outputs={
                "supports_virtual_texture_sampling": supports_vt,
                "warning_count": len(warnings),
                "error_count": len(errors),
            },
            warnings=warnings,
            errors=errors,
            report_path=report.get("report_path", ""),
        )
        return report

    def _is_vt_material_path(self, path):
        return bool(path and path.endswith("_VT"))

    def _create_material_instances(self, report):
        report["created_material_instances"] = []
        report["material_instance_issues"] = []
        if not self._content_import_enabled(report, "import_materials"):
            report["material_parameter_report"] = {"status": "skipped", "texture_parameters": [], "scalar_parameters": [], "vector_parameters": [], "static_switch_parameters": [], "issues": []}
            report["material_instance_policy_report"] = {
                "status": "skipped",
                "existing_material_strategy": "",
                "actions": [],
                "issues": [],
                "skip_reason": "import_materials=false；UE Gate 内容导入策略要求跳过材质实例创建。",
            }
            return report
        plan = report.get("material_binding_plan", {})
        if not plan.get("count", 0):
            return report
        if hasattr(self.material_instance_creator, "is_available") and not self.material_instance_creator.is_available():
            return report
        blockers = self._material_instance_blockers(report)
        if blockers:
            report["material_instance_issues"].extend(blockers)
            return report
        if hasattr(self.material_instance_creator, "is_available"):
            if hasattr(self.material_asset_bootstrap, "validate_parent_materials"):
                report["parent_material_validation"] = self.material_asset_bootstrap.validate_parent_materials(plan)
                if report["parent_material_validation"].get("status") == "error" or not report["parent_material_validation"].get("can_create_material_instances", True):
                    report["material_instance_issues"].extend(
                        [item.get("message", "") for item in report["parent_material_validation"].get("checks", []) if item.get("status") in ("error", "warning")]
                    )
                    return report

        try:
            report["created_material_instances"] = self.material_instance_creator.create_from_plan(plan)
            report["material_parameter_report"] = self._material_parameter_report()
            report["material_instance_policy_report"] = self._material_instance_policy_report()
        except Exception as exc:
            report["material_instance_issues"].append("材质实例创建失败：{0}".format(exc))
            report["material_parameter_report"] = {"status": "skipped", "texture_parameters": [], "scalar_parameters": [], "vector_parameters": [], "static_switch_parameters": [], "issues": []}
            report["material_instance_policy_report"] = {"status": "skipped", "existing_material_strategy": "", "actions": [], "issues": []}
        return report

    def _material_parameter_report(self):
        report = getattr(
            self.material_instance_creator,
            "last_parameter_report",
            {"status": "skipped", "texture_parameters": [], "scalar_parameters": [], "vector_parameters": [], "static_switch_parameters": [], "issues": []},
        )
        if report.get("issues"):
            report["status"] = "warning"
        elif report.get("texture_parameters") or report.get("scalar_parameters") or report.get("vector_parameters") or report.get("static_switch_parameters"):
            report["status"] = "success"
        else:
            report["status"] = "skipped"
        return report

    def _material_instance_policy_report(self):
        return getattr(
            self.material_instance_creator,
            "last_creation_report",
            {"status": "skipped", "existing_material_strategy": "", "actions": [], "issues": []},
        )

    def _attach_material_texture_binding_validation(self, report, manifest):
        report["material_texture_binding_validation"] = validate_material_texture_bindings(
            report.get("material_binding_plan", {}),
            texture_import_plan=report.get("texture_import_plan", {}),
            material_parameter_report=report.get("material_parameter_report", {}),
            imported_textures=report.get("imported_textures", []),
            material_profile=manifest.get("material_profile"),
            unreal_module=getattr(self.material_instance_creator, "unreal", None),
        )
        if report.get("status") == "success":
            report["material_texture_binding_validation"]["blocks_acceptance"] = False
        return report

    def _content_import_enabled(self, report, key):
        preset = report.get("resolved_preset") or {}
        if not isinstance(preset, dict):
            return True
        return bool(preset.get(key, True))

    def _log_operation(self, operation, status, inputs=None, outputs=None, errors=None, warnings=None, report_path=""):
        try:
            return UnrealOperationLogger().log(
                operation,
                status,
                inputs=inputs or {},
                outputs=outputs or {},
                errors=errors or [],
                warnings=warnings or [],
                report_path=report_path or "",
            )
        except Exception:
            return {}

    def _material_instance_blockers(self, report):
        plugin_validation = report.get("plugin_content_validation", {})
        missing_assets = set(plugin_validation.get("missing_assets", []))
        plan = report.get("material_binding_plan", {})
        blockers = []
        checks = []
        parent_check_materials = plan.get("materials", []) if hasattr(self.material_instance_creator, "is_available") else []
        for material in parent_check_materials:
            parent = material.get("parent_material", "")
            if parent and parent in missing_assets:
                target = material.get("target_asset_path", "")
                message = "缺少母材质：{0}；已跳过材质实例：{1}".format(parent, target)
                blockers.append(message)
                checks.append(
                    {
                        "id": "parent_material_exists",
                        "label": "母材质",
                        "status": "error",
                        "path": parent,
                        "parent_material": parent,
                        "target_asset_path": target,
                        "message": message,
                    }
                )
        for check in report.get("material_sampler_policy_validation", {}).get("checks", []):
            if check.get("id") == "vt_sampler_mismatch":
                message = "VT 贴图需要 VT 采样母材质，但当前材质库没有已验证的 VT 采样链路；已跳过材质实例创建。"
                blockers.append(message)
                checks.append(
                    {
                        "id": "vt_sampler_mismatch",
                        "label": "材质采样策略",
                        "status": "error",
                        "asset_paths": check.get("asset_paths", []),
                        "message": message,
                    }
                )
        if checks:
            report["parent_material_validation"] = {
                "status": "error",
                "can_create_material_instances": False,
                "message": "母材质缺失，无法安全创建材质实例",
                "checks": checks,
                "missing_parent_materials": [item.get("parent_material", "") for item in checks],
                "next_action": "在真实 UE 5.6 项目中确认 AssetForge 插件内容挂载，并执行默认材质 Bootstrap 后重试",
            }
        return blockers

    def _finalize_report(self, report):
        summary = summarize_pipeline(import_report=report)
        report["summary"] = summary
        attach_acceptance_summary(report, summary)
        return report

    def _assign_material_slots(self, report):
        report["material_assignment_report"] = {
            "status": "skipped",
            "planned_count": len(report.get("material_binding_plan", {}).get("materials", [])),
            "assigned_count": 0,
            "assigned": [],
            "unassigned_materials": [],
            "issues": [],
        }
        if not self._content_import_enabled(report, "import_materials"):
            report["material_assignment_report"]["issues"].append("import_materials=false；已跳过材质槽绑定")
            return report
        if hasattr(self.material_slot_assigner, "is_available") and not self.material_slot_assigner.is_available():
            report["material_assignment_report"]["issues"].append("当前环境不可用 Unreal Python 模块，已跳过材质槽绑定")
            return report

        try:
            report["material_assignment_report"] = self.material_slot_assigner.assign_from_report(report)
        except Exception as exc:
            report["material_assignment_report"]["status"] = "warning"
            report["material_assignment_report"]["issues"].append("材质槽绑定失败：{0}".format(exc))
        return report

    def _attach_material_graph_evidence(self, report):
        report["material_graph_evidence_report"] = build_material_graph_evidence_report(
            material_binding_plan=report.get("material_binding_plan", {}),
            parent_material_validation=report.get("parent_material_validation", {}),
            material_network_reports=self._material_network_reports_for_evidence(report),
            material_parameter_report=report.get("material_parameter_report", {}),
            material_assignment_report=report.get("material_assignment_report", {}),
            material_sampler_policy_validation=report.get("material_sampler_policy_validation", {}),
            compile_log_evidence=report.get("material_compile_log_evidence", {}),
            real_ue_material_graph=report.get("real_ue_material_graph", {}),
        )
        return report

    def _collect_material_graph_evidence(self, report):
        if hasattr(self.material_evidence_collector, "is_available") and not self.material_evidence_collector.is_available():
            return report
        try:
            evidence = self.material_evidence_collector.collect(report)
        except Exception as exc:
            evidence = {
                "material_compile_log_evidence": {
                    "status": "error",
                    "source": "material_evidence_collector",
                    "messages": [{"severity": "error", "text": str(exc)}],
                },
                "real_ue_material_graph": {
                    "status": "error",
                    "source": "material_evidence_collector",
                    "issues": [str(exc)],
                },
            }
        for key in ("material_compile_log_evidence", "real_ue_material_graph"):
            if evidence.get(key):
                report[key] = evidence[key]
        return report

    def _material_network_reports_for_evidence(self, report):
        bootstrap_reports = report.get("material_asset_bootstrap_report", {}).get("material_network_reports", [])
        if bootstrap_reports:
            return list(bootstrap_reports)
        return self._material_network_plans_for_evidence()

    def _material_network_plans_for_evidence(self):
        try:
            if hasattr(self.material_asset_bootstrap, "plan"):
                plan = self.material_asset_bootstrap.plan()
            else:
                plan = UnrealMaterialAssetBootstrap().plan()
            return list(plan.get("material_network_plans", []) or [])
        except Exception:
            return []


class UnrealBatchImportPipeline(object):
    """Batch dry-run or import every manifest under an export root."""

    def __init__(self, item_pipeline=None):
        self.item_pipeline = item_pipeline or UnrealStaticMeshImportPipeline()

    def run(self, export_root, dry_run=False, report_path=None):
        manifests = find_manifest_files(export_root)
        reports = []
        for manifest_path in manifests:
            if dry_run:
                reports.append(self.item_pipeline.dry_run_manifest(manifest_path))
            else:
                reports.append(self.item_pipeline.import_from_manifest(manifest_path))

        batch_report = create_batch_report(export_root, dry_run, reports)
        write_report(report_path or self._default_batch_report_path(export_root, dry_run), batch_report)
        return batch_report

    def _default_batch_report_path(self, export_root, dry_run):
        file_name = "batch_dry_run_report.json" if dry_run else "batch_import_report.json"
        return normalize_path(os.path.join(export_root, file_name))


def import_manifest(manifest_path, log_path=None):
    """Convenience entry point for Unreal Python Script Editor."""
    return UnrealStaticMeshImportPipeline().import_from_manifest(manifest_path, log_path)


def dry_run_manifest(manifest_path, log_path=None):
    """Validate a manifest and resolve preset without importing."""
    return UnrealStaticMeshImportPipeline().dry_run_manifest(manifest_path, log_path)


def import_latest_manifest(export_root, log_path=None, dry_run=False):
    """Find and import the newest manifest under an export root."""
    manifest_path = find_latest_manifest(export_root)
    if not manifest_path:
        raise RuntimeError("未找到 DCC AssetForge manifest：{0}".format(export_root))
    pipeline = UnrealStaticMeshImportPipeline()
    if dry_run:
        return pipeline.dry_run_manifest(manifest_path, log_path)
    return pipeline.import_from_manifest(manifest_path, log_path)


def import_asset_forge_package(package_dir, dry_run=False, report_path=None, import_options=None):
    """Import or dry-run the newest manifest in one DCC AssetForge package folder."""
    manifest_path = find_latest_manifest(package_dir)
    if not manifest_path:
        raise RuntimeError("资产包内未找到 DCC AssetForge manifest：{0}".format(package_dir))

    active_report_path = report_path or os.path.join(os.path.abspath(package_dir), "package_import_report.json")
    pipeline = UnrealStaticMeshImportPipeline(import_options=import_options)
    if dry_run:
        return pipeline.dry_run_manifest(manifest_path, active_report_path)
    return pipeline.import_from_manifest(manifest_path, active_report_path)


def import_all_manifests(export_root, report_path=None, dry_run=False):
    """Import or dry-run every manifest under an export root."""
    return UnrealBatchImportPipeline().run(export_root, dry_run, report_path)
