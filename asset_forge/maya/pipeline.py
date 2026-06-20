"""Maya Static Prop MVP workflow orchestration."""

from __future__ import absolute_import

from asset_forge.maya.adapter import MayaAdapter
from asset_forge.maya.export_package import build_export_package
from asset_forge.maya.fbx_exporter import MayaFbxExporter
from asset_forge.maya.manifest_writer import MayaManifestWriter
from asset_forge.maya.texture_packager import MayaTexturePackager
from asset_forge.shared.ai_analysis import LocalChineseSuggestionClient, analyze_validation
from asset_forge.shared.asset_health_report import create_asset_health_report
from asset_forge.shared.constants import SOURCE_DCC_MAYA, TARGET_ENGINE_UNREAL, TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.material_profile_schema import get_project_material_profiles, resolve_material_profile, write_material_profiles
from asset_forge.shared.material_profile_validator import validate_material_texture_coverage
from asset_forge.shared.material_texture_set_mapping import (
    build_material_texture_set_mapping,
    infer_texture_set_token_from_materials,
    match_material_to_texture_set,
    material_texture_set_entry,
    selected_texture_set_infos,
    short_texture_set_name,
    texture_set_info,
    tokenize_for_binding,
)
from asset_forge.shared.material_texture_bindings import create_material_texture_bindings
from asset_forge.shared.manifest_schema import ASSET_FORGE_SCHEMA_VERSION
from asset_forge.shared.package_naming import resolve_package_naming
from asset_forge.shared.report_schema import REPORT_VERSION, create_acceptance_summary, create_export_report, summarize_validation, write_report
from asset_forge.shared.rule_validator import StaticPropRuleValidator
from asset_forge.shared.rules_schema import get_project_rules
from asset_forge.shared.texture_folder_scanner import TextureFolderScanner


class MayaStaticPropPipeline(object):
    """Run scan, validate, export, and manifest generation for one asset."""

    def __init__(
        self,
        adapter=None,
        exporter=None,
        validator=None,
        manifest_writer=None,
        rules=None,
        ai_client=None,
        texture_packager=None,
        texture_folder_scanner=None,
    ):
        self.rules = rules or get_project_rules()
        self.adapter = adapter or MayaAdapter()
        self.exporter = exporter or MayaFbxExporter()
        self.validator = validator or StaticPropRuleValidator(self.rules)
        self.manifest_writer = manifest_writer or MayaManifestWriter()
        self.ai_client = ai_client or LocalChineseSuggestionClient()
        self.texture_packager = texture_packager or MayaTexturePackager()
        self.texture_folder_scanner = texture_folder_scanner or TextureFolderScanner()

    def scan_selection(self):
        selection = self.adapter.get_current_selection()
        if not selection:
            raise RuntimeError("没有选中资产")
        return self.scan_assets(selection)

    def scan_asset(self, asset_root):
        return self.adapter.scan_asset(asset_root, self.rules)

    def scan_assets(self, asset_roots):
        if hasattr(self.adapter, "scan_assets"):
            return self.adapter.scan_assets(asset_roots, self.rules)
        return self.scan_asset(list(asset_roots)[0])

    def validate_scan(self, scan_result, target_platform=TARGET_PLATFORM_HIGH_END_MOBILE, rules=None):
        validator = self.validator if rules is None else StaticPropRuleValidator(rules)
        return validator.validate(scan_result, target_platform)

    def preflight_assets(
        self,
        asset_roots,
        target_platform=TARGET_PLATFORM_HIGH_END_MOBILE,
        material_profile="Props_Opaque_PainterUE_ARM",
        texture_folder="",
        texture_set_token="",
        target_path="",
        asset_name_override="",
        rules=None,
        texture_import_policy=None,
        static_mesh_import_policy=None,
        source_name_suffix="",
        package_name_override="",
        package_version_mode="overwrite",
        package_version_padding=3,
        package_version_start=1,
        project_preset=None,
    ):
        asset_roots = list(asset_roots or [])
        if not asset_roots:
            raise RuntimeError("没有选中资产")
        active_rules = rules or self.rules
        scan_result = self.scan_assets(asset_roots)
        scan_result = self._apply_texture_folder(scan_result, texture_folder, material_profile, texture_set_token)
        scan_result = self._apply_texture_profile_defaults(scan_result, material_profile)
        scan_result = self._apply_material_profile_validation(scan_result, material_profile)
        scan_result = self._apply_asset_name_override(scan_result, "", source_name_suffix)
        scan_result = self._attach_package_naming_policy(
            scan_result,
            package_name_override or asset_name_override,
            package_version_mode,
            package_version_padding,
            package_version_start,
            project_preset,
        )
        scan_result = self._attach_material_texture_bindings(scan_result, target_path)
        validation_result = self.validate_scan(scan_result, target_platform, active_rules)
        validation_result = self._attach_texture_set_selection_gate(scan_result, validation_result)
        health_report = create_asset_health_report(scan_result, validation_result)
        scan_result = dict(scan_result, asset_health_report=health_report)
        validation_result = dict(validation_result, asset_health_report=health_report)
        return {
            "scan": scan_result,
            "validation": validation_result,
            "texture_folder_scan": scan_result.get("texture_folder_scan", {}),
            "asset_health_report": health_report,
        }

    def export_asset(
        self,
        asset_root,
        output_dir,
        target_platform=TARGET_PLATFORM_HIGH_END_MOBILE,
        target_path="/Game/Props",
        use_asset_folder=True,
        material_profile="Props_Opaque_PainterUE_ARM",
        texture_folder="",
        texture_set_token="",
        asset_name_override="",
        rules=None,
        texture_import_policy=None,
        static_mesh_import_policy=None,
        source_name_suffix="",
        package_name_override="",
        package_version_mode="overwrite",
        package_version_padding=3,
        package_version_start=1,
        project_preset=None,
    ):
        return self.export_assets(
            [asset_root],
            output_dir,
            target_platform,
            target_path,
            use_asset_folder,
            material_profile,
            texture_folder,
            texture_set_token,
            asset_name_override,
            rules,
            texture_import_policy,
            static_mesh_import_policy,
            source_name_suffix,
            package_name_override,
            package_version_mode,
            package_version_padding,
            package_version_start,
            project_preset,
        )

    def export_assets(
        self,
        asset_roots,
        output_dir,
        target_platform=TARGET_PLATFORM_HIGH_END_MOBILE,
        target_path="/Game/Props",
        use_asset_folder=True,
        material_profile="Props_Opaque_PainterUE_ARM",
        texture_folder="",
        texture_set_token="",
        asset_name_override="",
        rules=None,
        texture_import_policy=None,
        static_mesh_import_policy=None,
        source_name_suffix="",
        package_name_override="",
        package_version_mode="overwrite",
        package_version_padding=3,
        package_version_start=1,
        project_preset=None,
    ):
        asset_roots = list(asset_roots or [])
        if not asset_roots:
            raise RuntimeError("没有选中资产")
        active_rules = rules or self.rules
        scan_result = self.scan_assets(asset_roots)
        scan_result = self._apply_texture_folder(scan_result, texture_folder, material_profile, texture_set_token)
        scan_result = self._apply_texture_profile_defaults(scan_result, material_profile)
        scan_result = self._apply_material_profile_validation(scan_result, material_profile)
        scan_result = self._apply_asset_name_override(scan_result, "", source_name_suffix)
        scan_result = self._attach_material_texture_bindings(scan_result, target_path)
        validation_result = self.validate_scan(scan_result, target_platform, active_rules)
        validation_result = self._attach_texture_set_selection_gate(scan_result, validation_result)
        validation_result = self._attach_material_texture_binding_gate(scan_result, validation_result)
        health_report = create_asset_health_report(scan_result, validation_result)
        scan_result = dict(scan_result, asset_health_report=health_report)
        validation_result = dict(validation_result, asset_health_report=health_report)
        if not validation_result.get("can_export", False):
            debug_report_path = self._write_blocked_export_report(output_dir, scan_result, validation_result, target_platform, target_path)
            raise ExportValidationError(
                "资产存在阻断级别验证错误，已停止导出。详情见 debug report：{0}".format(debug_report_path),
                validation_result,
                scan_result,
                debug_report_path,
            )

        scan_result = self._attach_package_naming_policy(
            scan_result,
            package_name_override or asset_name_override,
            package_version_mode,
            package_version_padding,
            package_version_start,
            project_preset,
            output_dir,
        )
        asset_name = scan_result.get("asset_name", "Asset")
        package_naming = scan_result.get("package_naming", {})
        export_package = build_export_package(output_dir, asset_name, use_asset_folder, package_name=package_naming.get("package_name"))
        fbx_path = export_package["fbx_path"]
        manifest_path = export_package["manifest_path"]
        rename_map = self._export_name_map(scan_result)

        if len(asset_roots) > 1 and hasattr(self.exporter, "export_assets"):
            self.exporter.export_assets(asset_roots, fbx_path, rename_map=rename_map)
        else:
            self.exporter.export_asset(asset_roots[0], fbx_path, rename_map=rename_map)
        self.texture_packager.package_scan_textures(scan_result, export_package["package_dir"])
        self._write_material_profiles_snapshot(export_package["material_profiles_snapshot_path"])
        manifest = self.manifest_writer.build(
            scan_result,
            validation_result,
            fbx_path,
            target_path,
            package_dir=export_package["package_dir"],
            material_profile=material_profile,
            material_profiles_snapshot_path=export_package["material_profiles_snapshot_path"],
            texture_import_policy=texture_import_policy or {},
            static_mesh_import_policy=static_mesh_import_policy or {},
        )
        self.manifest_writer.write(manifest_path, manifest)
        portfolio_capture_hint = _portfolio_capture_hint(
            True,
            scan_result,
            validation_result,
            export_package["export_report_path"],
        )
        export_report = create_export_report(scan_result, validation_result, manifest, export_package)
        export_report["portfolio_capture_hint"] = portfolio_capture_hint
        write_report(export_package["export_report_path"], export_report)

        return {
            "scan": scan_result,
            "validation": validation_result,
            "fbx_path": fbx_path,
            "manifest_path": manifest_path,
            "export_report_path": export_package["export_report_path"],
            "package_dir": export_package["package_dir"],
            "manifest": manifest,
            "export_report": export_report,
            "asset_health_report": health_report,
            "portfolio_capture_hint": portfolio_capture_hint,
        }

    def _export_name_map(self, scan_result):
        asset_name = _safe_publish_name((scan_result or {}).get("asset_name", ""))
        source_asset_name = _safe_publish_name((scan_result or {}).get("asset_name_original", ""))
        suffix = _publish_source_suffix(asset_name, source_asset_name)
        if not suffix:
            return {}
        result = {}
        for transform in (scan_result or {}).get("transforms", []) or []:
            short_name = str(transform or "").split("|")[-1]
            target = _append_publish_suffix(short_name, suffix)
            if target != short_name:
                result[transform] = target
                result[short_name] = target
        if result:
            return result
        for root in (scan_result or {}).get("asset_roots", []) or []:
            short_name = str(root or "").split("|")[-1]
            target = _append_publish_suffix(short_name, suffix)
            if target != short_name:
                result[root] = target
                result[short_name] = target
        return result

    def rename_selection_with_prefix(self, prefix="SM_"):
        selection = self.adapter.get_current_selection()
        if not selection:
            raise RuntimeError("没有选中资产")
        if not hasattr(self.adapter, "rename_with_prefix"):
            raise RuntimeError("当前 Maya Adapter 不支持重命名")
        return self.adapter.rename_with_prefix(selection, prefix)

    def rename_asset_root_with_prefix(self, prefix="SM_"):
        selection = self.adapter.get_current_selection()
        if not selection:
            raise RuntimeError("没有选中资产")
        if not hasattr(self.adapter, "rename_with_prefix"):
            raise RuntimeError("当前 Maya Adapter 不支持重命名")
        scan_result = self.scan_assets(selection)
        target_root = scan_result.get("asset_name_source_path")
        if not target_root:
            raise RuntimeError("无法安全判定当前导出资产名来源，请先扫描模型或手动重命名资产根节点。")
        return self.adapter.rename_with_prefix([target_root], prefix)

    def rename_mesh_transforms_with_prefix(self, prefix="SM_"):
        selection = self.adapter.get_current_selection()
        if not selection:
            raise RuntimeError("没有选中资产")
        if not hasattr(self.adapter, "rename_mesh_transforms_with_prefix"):
            return []
        return self.adapter.rename_mesh_transforms_with_prefix(selection, prefix)

    def scan_texture_folder(self, texture_folder, asset_name, material_profile="Props_Opaque_PainterUE_ARM", texture_set_token=""):
        profile = resolve_material_profile(material_profile)
        return self.texture_folder_scanner.scan(texture_folder, asset_name, profile, texture_set_token=texture_set_token)

    def plan_texture_prefix_renames(self, scan_result, texture_prefix="T_", require_selected_set=False):
        return self.texture_folder_scanner.plan_texture_prefix_renames(scan_result, texture_prefix, require_selected_set=require_selected_set)

    def execute_texture_prefix_renames(self, scan_result, texture_prefix="T_", require_selected_set=False):
        return self.texture_folder_scanner.execute_texture_prefix_renames(scan_result, texture_prefix, require_selected_set=require_selected_set)

    def _attach_material_texture_bindings(self, scan_result, target_path=""):
        binding_report = create_material_texture_bindings(scan_result, target_path)
        result = dict(scan_result)
        result["material_texture_bindings"] = binding_report["bindings"]
        result["material_texture_binding_risks"] = binding_report["risks"]
        return result

    def _attach_package_naming_policy(
        self,
        scan_result,
        package_name_override="",
        package_version_mode="overwrite",
        package_version_padding=3,
        package_version_start=1,
        project_preset=None,
        output_dir="",
    ):
        result = dict(scan_result or {})
        result["package_name_override"] = str(package_name_override or "").strip()
        result["package_version_mode"] = package_version_mode
        result["package_version_padding"] = package_version_padding
        result["package_version_start"] = package_version_start
        if project_preset:
            result["project_preset"] = project_preset
        if output_dir:
            naming = resolve_package_naming(
                output_dir,
                result.get("asset_name", "Asset"),
                package_name_override=package_name_override,
                version_mode=package_version_mode,
                version_padding=package_version_padding,
                version_start=package_version_start,
            )
            result["package_name"] = naming.get("package_name", "")
            result["package_naming"] = naming
        return result

    def _write_material_profiles_snapshot(self, snapshot_path):
        write_material_profiles(snapshot_path, get_project_material_profiles())
        return snapshot_path

    def _apply_texture_folder(self, scan_result, texture_folder, material_profile, texture_set_token=""):
        if not texture_folder:
            return scan_result

        profile = resolve_material_profile(material_profile)
        folder_scan = self.texture_folder_scanner.scan(texture_folder, scan_result.get("asset_name", ""), profile, texture_set_token=texture_set_token)
        if not texture_set_token:
            inferred_token = self._infer_texture_set_token_from_materials(scan_result.get("materials", []), folder_scan.get("texture_sets", []))
            if inferred_token and inferred_token != ",".join(folder_scan.get("selected_texture_set_short_names", [])):
                folder_scan = self.texture_folder_scanner.scan(texture_folder, scan_result.get("asset_name", ""), profile, texture_set_token=inferred_token)
                folder_scan["auto_selected_texture_sets"] = True
                folder_scan["auto_material_texture_set_token"] = inferred_token
        result = dict(scan_result)
        result["texture_selection_policy"] = {
            "primary": "texture_folder",
            "fallback": "maya_material_assignment",
            "reason": "explicit_texture_folder",
            "texture_folder": texture_folder.replace("\\", "/"),
        }
        if folder_scan.get("requires_texture_set_selection"):
            result["textures"] = []
            result["texture_folder_scan"] = folder_scan
            result["asset_name_candidates"] = folder_scan.get("asset_name_candidates", [])
            material_mapping = self._build_material_texture_set_mapping(scan_result.get("materials", []), [], folder_scan, scan_result.get("asset_name", ""))
            result["materials"] = material_mapping["materials"]
            result["material_texture_sets"] = material_mapping["material_texture_sets"]
            return result
        result["textures"] = list(folder_scan.get("textures", []))
        result["asset_name_candidates"] = folder_scan.get("asset_name_candidates", [])
        material_mapping = self._build_material_texture_set_mapping(scan_result.get("materials", []), folder_scan.get("textures", []), folder_scan, scan_result.get("asset_name", ""))
        result["texture_folder_scan"] = dict(folder_scan, material_texture_sets=material_mapping["material_texture_sets"])
        result["materials"] = material_mapping["materials"]
        result["material_texture_sets"] = material_mapping["material_texture_sets"]
        return result

    def _infer_texture_set_token_from_materials(self, materials, texture_sets):
        return infer_texture_set_token_from_materials(materials, texture_sets)

    def _apply_material_profile_validation(self, scan_result, material_profile):
        result = dict(scan_result)
        result["material_profile_validation"] = validate_material_texture_coverage(
            material_profile,
            result.get("textures", []),
        )
        return result

    def _apply_texture_profile_defaults(self, scan_result, material_profile):
        profile = resolve_material_profile(material_profile)
        rules_by_usage = dict((rule.get("usage", ""), rule) for rule in profile.get("texture_rules", []))
        for texture in _iter_scan_textures(scan_result):
            rule = rules_by_usage.get(texture.get("usage", ""), {})
            if not rule:
                continue
            if rule.get("parameter") and not texture.get("parameter"):
                texture["parameter"] = rule.get("parameter", "")
            if "srgb" not in texture:
                texture["srgb"] = bool(rule.get("srgb", False))
            if rule.get("compression") and not texture.get("compression"):
                texture["compression"] = rule.get("compression", "")
            if rule.get("channels") and not texture.get("channels"):
                texture["channels"] = dict(rule.get("channels", {}))
        return scan_result

    def _apply_asset_name_override(self, scan_result, asset_name_override="", source_name_suffix=""):
        active_name = str(asset_name_override or "").strip()
        source_suffix = _safe_publish_suffix(source_name_suffix)
        if not active_name and source_suffix:
            base_name = str(scan_result.get("asset_name", "") or "").strip()
            suffix = "_" + source_suffix
            active_name = base_name if base_name.endswith(suffix) else base_name + suffix
        if not active_name:
            return scan_result
        result = dict(scan_result)
        result["asset_name_original"] = result.get("asset_name", "")
        result["asset_name"] = active_name
        result["asset_name_source"] = "export_override"
        return result

    def _attach_texture_set_selection_gate(self, scan_result, validation_result):
        folder_scan = scan_result.get("texture_folder_scan", {})
        if not folder_scan.get("requires_texture_set_selection"):
            return validation_result
        result = dict(validation_result)
        checks = list(result.get("checks", []))
        checks.append(
            {
                "id": "texture_set_selection",
                "label": "贴图集选择",
                "status": "error",
                "severity": "error",
                "object": folder_scan.get("texture_folder", ""),
                "value": ", ".join([item.get("set_name", "") for item in folder_scan.get("texture_sets", [])]),
                "limit": "选择一个贴图集",
                "message": "贴图目录内存在多个完整贴图集，导出前需要确认本模型使用哪一套贴图。",
                "next_action": "在 UI 的“贴图集关键词”中填写 a1,d1 或完整贴图集名称片段，重新扫描后再导出。",
            }
        )
        result["checks"] = checks
        result["status"] = "error"
        result["can_export"] = False
        summary = dict(result.get("summary", {}))
        summary["errors"] = int(summary.get("errors", 0)) + 1
        result["summary"] = summary
        return result

    def _attach_material_texture_binding_gate(self, scan_result, validation_result):
        blocking = [item for item in scan_result.get("material_texture_binding_risks", []) or [] if item.get("severity") == "error"]
        if not blocking:
            return validation_result
        result = dict(validation_result)
        checks = list(result.get("checks", []))
        for item in blocking:
            checks.append(
                {
                    "id": item.get("id", "material_texture_binding"),
                    "label": "材质贴图绑定",
                    "status": "error",
                    "severity": "error",
                    "object": item.get("material_name", "") or item.get("texture_set", ""),
                    "value": item.get("slot_name", "") or item.get("texture_count", 0),
                    "limit": "每个 Maya 材质必须匹配对应贴图集",
                    "message": item.get("message", "材质贴图绑定失败"),
                    "next_action": "检查“贴图详情”中的候选贴图集，补齐缺失贴图集或填写正确贴图集关键词后重新扫描。",
                }
            )
        result["checks"] = checks
        result["status"] = "error"
        result["can_export"] = False
        summary = dict(result.get("summary", {}))
        summary["errors"] = int(summary.get("errors", 0)) + len(blocking)
        result["summary"] = summary
        return result

    def _merged_textures(self, existing, incoming):
        result = list(existing or [])
        seen = set(texture.get("path", "") for texture in result)
        for texture in incoming:
            if texture.get("path", "") in seen:
                continue
            result.append(texture)
            seen.add(texture.get("path", ""))
        return result

    def _attach_folder_textures_to_materials(self, materials, textures, asset_name):
        return self._build_material_texture_set_mapping(materials, textures, {}, asset_name)["materials"]

    def _build_material_texture_set_mapping(self, materials, textures, folder_scan, asset_name):
        return build_material_texture_set_mapping(materials, textures, folder_scan, asset_name)

    def _selected_texture_set_infos(self, folder_scan, textures_by_set):
        return selected_texture_set_infos(folder_scan, textures_by_set)

    def _texture_set_info(self, texture_sets, set_name):
        return texture_set_info(texture_sets, set_name)

    def _match_material_to_texture_set(self, material_name, selected_sets, assigned_sets, allow_assigned=False):
        return match_material_to_texture_set(material_name, selected_sets, assigned_sets, allow_assigned=allow_assigned)

    def _material_texture_set_entry(self, material, binding, textures, status):
        return material_texture_set_entry(material, binding, textures, status)

    def analyze(self, scan_result, validation_result):
        return analyze_validation(scan_result, validation_result, self.rules, self.ai_client)

    def _write_blocked_export_report(self, output_dir, scan_result, validation_result, target_platform, target_path):
        asset_name = scan_result.get("asset_name", "Asset")
        export_package = build_export_package(output_dir, asset_name, True)
        validation_summary = summarize_validation(validation_result)
        texture_scan = scan_result.get("texture_folder_scan", {})
        errors = list(validation_summary.get("errors", []))
        warnings = list(validation_summary.get("warnings", [])) + list(texture_scan.get("issues", []))
        repair_actions = _repair_actions_for_report(scan_result, validation_result, texture_scan)
        summary = create_acceptance_summary(
            "error",
            warnings,
            errors,
            "查看阻断项 id、对象和修复建议，修复后重新导出。",
        )
        summary["repair_action_count"] = len(repair_actions)
        report_path = export_package["export_report_path"].replace("_export_report.json", "_export_blocked_report.json")
        repair_actions = _repair_actions_with_report_path(repair_actions, report_path)
        portfolio_capture_hint = _portfolio_capture_hint(False, scan_result, validation_result, report_path, repair_actions)
        report = {
            "version": REPORT_VERSION,
            "schema_version": ASSET_FORGE_SCHEMA_VERSION,
            "asset_forge_schema_version": ASSET_FORGE_SCHEMA_VERSION,
            "stage": "maya_export_blocked",
            "status": "error",
            "asset_name": asset_name,
            "source_dcc": SOURCE_DCC_MAYA,
            "target_engine": TARGET_ENGINE_UNREAL,
            "target_platform": target_platform,
            "target_path": target_path,
            "scan": scan_result,
            "texture_folder_scan": texture_scan,
            "asset_health_report": scan_result.get("asset_health_report", {}),
            "validation": validation_result,
            "summary": summary,
            "can_accept": False,
            "report_path": report_path,
            "portfolio_capture_hint": portfolio_capture_hint,
            "repair_actions": repair_actions,
            "warnings": warnings,
            "errors": errors,
            "next_action": summary.get("next_action", ""),
        }
        write_report(report_path, report)
        return report_path


class ExportValidationError(RuntimeError):
    """Raised when Maya validation blocks export, with structured report context."""

    def __init__(self, message, validation=None, scan=None, debug_report_path=""):
        RuntimeError.__init__(self, message)
        self.validation = validation or {}
        self.scan = scan or {}
        self.debug_report_path = debug_report_path


def _safe_publish_suffix(value):
    text = str(value or "").strip().replace(" ", "_")
    return "".join(ch for ch in text if ch.isalnum() or ch == "_").strip("_")


def _safe_publish_name(value):
    return _safe_publish_suffix(value) or "Asset"


def _publish_source_suffix(asset_name, source_asset_name):
    asset_name = _safe_publish_name(asset_name)
    source_asset_name = _safe_publish_name(source_asset_name)
    prefix = source_asset_name + "_"
    if not source_asset_name or not asset_name.startswith(prefix):
        return ""
    return asset_name[len(prefix) :]


def _append_publish_suffix(name, suffix):
    clean_name = _safe_publish_name(name)
    clean_suffix = _safe_publish_suffix(suffix)
    if not clean_suffix or clean_name.endswith("_" + clean_suffix):
        return clean_name
    return clean_name + "_" + clean_suffix


def _repair_actions_for_report(scan_result, validation_result, texture_scan):
    try:
        from asset_forge.maya.ui import repair_actions_for_state

        return repair_actions_for_state(scan_result or {}, validation_result or {}, texture_scan or {})
    except Exception:
        return []


def _repair_actions_with_report_path(repair_actions, report_path):
    result = []
    normalized_report_path = (report_path or "").replace("\\", "/")
    for action in repair_actions or []:
        item = dict(action)
        if normalized_report_path:
            item["report_path"] = normalized_report_path
        result.append(item)
    return result


def _portfolio_capture_hint(can_export, scan_result, validation_result, report_path="", repair_actions=None):
    asset_name = (scan_result or {}).get("asset_name", "Asset")
    normalized_report_path = (report_path or "").replace("\\", "/")
    if can_export:
        return "录制前看这里：资产 {0} 已可导出；打开导出报告 {1}；下一步在 UE Gate 选择该 Package，做预检、导入预演、批准导入。".format(
            asset_name,
            normalized_report_path or "待生成报告",
        )
    first_action = ((repair_actions or [{}])[0] or {}).get("label") or _first_blocker(validation_result)
    return "录制前看这里：资产 {0} 还不能导出；先展示第一个修复项“{1}”；打开阻断报告 {2}；下一步点对应入口后重新检查。".format(
        asset_name,
        first_action or "修复阻断项",
        normalized_report_path or "阻断调试报告",
    )


def _first_blocker(validation_result):
    for item in (validation_result or {}).get("checks", []):
        if item.get("status") == "error":
            return item.get("message") or item.get("label") or item.get("id", "")
    return ""


def _short_texture_set_name(value):
    return short_texture_set_name(value)


def _tokenize_for_binding(value):
    return tokenize_for_binding(value)


def _iter_scan_textures(scan_result):
    seen = set()
    for texture in (scan_result or {}).get("textures", []) or []:
        if isinstance(texture, dict) and id(texture) not in seen:
            seen.add(id(texture))
            yield texture
    for material in (scan_result or {}).get("materials", []) or []:
        for texture in material.get("textures", []) or []:
            if isinstance(texture, dict) and id(texture) not in seen:
                seen.add(id(texture))
                yield texture
