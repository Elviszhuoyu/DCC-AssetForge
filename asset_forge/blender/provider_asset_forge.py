# -*- coding: utf-8 -*-
"""DCC AssetForge provider actions for the Blender MCP bridge."""

from __future__ import absolute_import

import importlib
import json
import os
import re
import shutil
import struct
import sys
import time
import zlib

from asset_forge.blender.fbx_exporter import BlenderFbxExporter
from asset_forge.blender.scanner import BlenderStaticPropScanner, clean_asset_name_prefix
from asset_forge.maya.manifest_writer import IMPORT_PRESET_BY_PLATFORM
from asset_forge.shared.constants import SOURCE_DCC_BLENDER, TARGET_PLATFORM_PC
from asset_forge.shared.material_profile_schema import resolve_material_profile


def _refresh_shared_texture_modules_for_hot_reload():
    for module_name in (
        "asset_forge.shared.package_naming",
        "asset_forge.shared.manifest_schema",
        "asset_forge.maya.export_package",
        "asset_forge.shared.texture_folder_scanner",
        "asset_forge.shared.material_texture_set_mapping",
        "asset_forge.shared.material_texture_bindings",
    ):
        module = sys.modules.get(module_name)
        if module is not None:
            importlib.reload(module)


_refresh_shared_texture_modules_for_hot_reload()

from asset_forge.maya.export_package import build_export_package
from asset_forge.shared.manifest_schema import create_manifest, write_manifest
from asset_forge.shared.material_texture_set_mapping import (
    build_material_texture_set_mapping,
    infer_texture_set_token_from_materials,
)
from asset_forge.shared.material_texture_bindings import create_material_texture_bindings
from asset_forge.shared.package_naming import resolve_package_naming
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.rule_validator import StaticPropRuleValidator, checks_to_manifest_dict
from asset_forge.shared.texture_metadata import apply_texture_metadata
from asset_forge.shared.texture_folder_scanner import TextureFolderScanner
from asset_forge.shared.unreal_path import sanitize_unreal_package_path


class BlenderAssetForgeProvider(object):
    def __init__(self, bpy_module=None, scanner=None, validator=None, exporter=None):
        self.scanner = scanner or BlenderStaticPropScanner(bpy_module=bpy_module)
        self.validator = validator or StaticPropRuleValidator()
        self.exporter = exporter or BlenderFbxExporter(bpy_module=bpy_module)

    def scan_static_prop(self, params=None):
        params = params or {}
        scan = self._scan(params)
        return {
            "status": "success",
            "can_accept": True,
            "scan": scan,
            "next_action": "运行 blender_preflight_static_prop。",
        }

    def preflight_static_prop(self, params=None):
        params = params or {}
        scan = self._scan_for_validation(params)
        target_platform = params.get("target_platform") or TARGET_PLATFORM_PC
        validation = self._validation(scan, target_platform, params)
        return {
            "status": "success" if validation.get("can_export") else "blocked",
            "can_accept": True,
            "can_export": bool(validation.get("can_export")),
            "can_continue_to_package_contract": bool(validation.get("can_export")),
            "scan": scan,
            "validation": validation,
            "texture_folder_scan": scan.get("texture_folder_scan", {}),
            "next_action": "生成 package contract；真实 UE 导入仍需 Blender FBX exporter。",
        }

    def build_static_prop_package_contract(self, params=None):
        params = params or {}
        export_root = params.get("export_root") or params.get("output_root")
        if not export_root:
            raise RuntimeError("缺少 export_root，无法写出 Blender package contract")
        target_path = sanitize_unreal_package_path(params.get("target_path") or "/Game/Props")
        material_profile = params.get("material_profile") or "Props_Opaque_PainterUE_ARM"
        target_platform = params.get("target_platform") or TARGET_PLATFORM_PC
        use_asset_folder = params.get("use_asset_folder", True)
        scan = self._scan_for_validation(dict(params, target_path=target_path))
        validation = self._validation(scan, target_platform, params)
        scan = self._attach_package_naming(scan, export_root, params)
        package = build_export_package(export_root, scan.get("asset_name", "Asset"), use_asset_folder, package_name=scan.get("package_name"))
        if validation.get("can_export"):
            scan = self._prepare_package_textures(scan, package, target_path, params)
        manifest = self._build_manifest(scan, validation, package, target_path, target_platform, material_profile, params)
        manifest.update(
            {
                "fbx_export_status": "planned",
                "can_continue_to_ue": False,
                "package_contract_status": "draft",
                "source_scene_path": scan.get("scene_path", ""),
            }
        )
        write_manifest(package["manifest_path"], manifest, pretty=True)
        report = self._build_export_report(scan, validation, manifest, package, "success" if validation.get("can_export") else "blocked", "planned", False)
        report["package_contract_status"] = "draft"
        report["next_action"] = "运行 blender_export_static_prop_package 写出真实 FBX。"
        _write_json(package["export_report_path"], report)
        return {
            "status": report["status"],
            "can_accept": True,
            "can_continue_to_ue": False,
            "fbx_export_status": "planned",
            "manifest_path": package["manifest_path"],
            "export_report_path": package["export_report_path"],
            "package_dir": package["package_dir"],
            "scan": scan,
            "manifest": manifest,
            "validation": validation,
            "can_export": bool(validation.get("can_export")),
            "next_action": report["next_action"],
        }

    def export_static_prop_package(self, params=None):
        params = params or {}
        export_root = params.get("export_root") or params.get("output_root")
        if not export_root:
            raise RuntimeError("缺少 export_root，无法导出 Blender package")
        target_path = sanitize_unreal_package_path(params.get("target_path") or "/Game/Props")
        material_profile = params.get("material_profile") or "Props_Opaque_PainterUE_ARM"
        target_platform = params.get("target_platform") or TARGET_PLATFORM_PC
        use_asset_folder = params.get("use_asset_folder", True)
        scan = self._scan_for_validation(dict(params, target_path=target_path))
        validation = self._validation(scan, target_platform, params)
        scan = self._attach_package_naming(scan, export_root, params)
        package = build_export_package(export_root, scan.get("asset_name", "Asset"), use_asset_folder, package_name=scan.get("package_name"))
        if not validation.get("can_export"):
            report = self._build_export_report(scan, validation, {}, package, "blocked", "blocked", False)
            _write_json(package["export_report_path"], report)
            return {
                "status": "blocked",
                "can_accept": True,
                "can_continue_to_ue": False,
                "fbx_export_status": "blocked",
                "export_report_path": package["export_report_path"],
                "package_dir": package["package_dir"],
                "scan": scan,
                "validation": validation,
                "can_export": False,
                "next_action": "修复 Blender Static Prop preflight 阻断项后再导出。",
            }
        exported_fbx = self.exporter.export_objects(scan.get("asset_roots", []), package["fbx_path"], rename_map=self._export_name_map(scan))
        fbx_exists = os.path.exists(exported_fbx)
        scan = self._prepare_package_textures(scan, package, target_path, params)
        manifest = self._build_manifest(scan, validation, package, target_path, target_platform, material_profile, params)
        manifest.update(
            {
                "fbx_export_status": "success" if fbx_exists else "missing_file",
                "can_continue_to_ue": bool(fbx_exists),
                "package_contract_status": "ready" if fbx_exists else "blocked",
                "source_scene_path": scan.get("scene_path", ""),
            }
        )
        write_manifest(package["manifest_path"], manifest, pretty=True)
        report = self._build_export_report(
            scan,
            validation,
            manifest,
            package,
            "success" if fbx_exists else "blocked",
            manifest["fbx_export_status"],
            bool(fbx_exists),
        )
        _write_json(package["export_report_path"], report)
        return {
            "status": report["status"],
            "can_accept": True,
            "can_continue_to_ue": bool(fbx_exists),
            "fbx_export_status": manifest["fbx_export_status"],
            "fbx_path": package["fbx_path"],
            "manifest_path": package["manifest_path"],
            "export_report_path": package["export_report_path"],
            "package_dir": package["package_dir"],
            "scan": scan,
            "manifest": manifest,
            "validation": validation,
            "can_export": bool(validation.get("can_export")),
            "next_action": "运行 UE accept-flow 导入 Blender package。" if fbx_exists else "检查 Blender FBX exporter 输出文件。",
        }

    def _build_manifest(self, scan, validation, package, target_path, target_platform, material_profile, params=None):
        params = params or {}
        return create_manifest(
            scan.get("asset_name", ""),
            package["fbx_path"],
            target_path,
            checks=checks_to_manifest_dict(validation),
            score=validation.get("score", 0),
            source_dcc=SOURCE_DCC_BLENDER,
            target_platform=target_platform,
            import_preset=IMPORT_PRESET_BY_PLATFORM.get(target_platform, "StaticProp_HighEndMobile"),
            package_dir=package["package_dir"],
            materials=scan.get("materials", []),
            material_slots=scan.get("material_slot_details", []),
            material_texture_sets=scan.get("material_texture_sets", []),
            material_texture_bindings=scan.get("material_texture_bindings", []),
            material_texture_binding_risks=scan.get("material_texture_binding_risks", []),
            textures=scan.get("textures", []),
            texture_selection_policy=scan.get("texture_selection_policy", {}),
            texture_folder_scan=scan.get("texture_folder_scan", {}),
            package_naming=scan.get("package_naming", {}),
            project_preset=params.get("project_preset", {}),
            material_profile=material_profile,
            texture_import_policy=params.get("texture_import_policy", {}) or {},
            static_mesh_import_policy=params.get("static_mesh_import_policy", {}) or {},
        )

    def _build_export_report(self, scan, validation, manifest, package, status, fbx_export_status, can_continue_to_ue):
        return {
            "status": status,
            "can_accept": True,
            "can_continue_to_ue": bool(can_continue_to_ue),
            "fbx_export_status": fbx_export_status,
            "package_contract_status": "ready" if can_continue_to_ue else "blocked",
            "created_at_epoch": time.time(),
            "scan": scan,
            "validation": validation,
            "manifest": manifest,
            "package": package,
            "package_naming": manifest.get("package_naming", {}),
            "project_preset": manifest.get("project_preset", {}),
            "next_action": "运行 UE accept-flow 导入 Blender package。" if can_continue_to_ue else "检查 Blender preflight 或 FBX exporter 输出。",
        }

    def _scan(self, params):
        selection = params.get("selection") or []
        name_prefix = clean_asset_name_prefix(params.get("mesh_prefix"))
        if selection:
            return self.scanner.scan_by_names(selection, name_prefix=name_prefix)
        return self.scanner.scan_selection(name_prefix=name_prefix)

    def _scan_for_validation(self, params):
        params = params or {}
        scan = self._scan(params)
        scan = self._apply_publish_asset_name(scan, params.get("asset_identity_override", ""), params.get("mesh_prefix", ""), params.get("source_name_suffix", ""))
        target_path = sanitize_unreal_package_path(params.get("target_path") or "/Game/Props")
        return self._prepare_validation_scan(scan, target_path, params)

    def _prepare_validation_scan(self, scan, target_path, params=None):
        params = params or {}
        scan = json.loads(json.dumps(scan or {}, ensure_ascii=False))
        scan = self._normalize_blender_material_names_for_ue(scan)
        scan = self._apply_texture_folder(scan, params)
        binding_report = create_material_texture_bindings(scan, target_path)
        scan["material_texture_bindings"] = binding_report.get("bindings", [])
        scan["material_texture_binding_risks"] = binding_report.get("risks", [])
        return scan

    def _attach_package_naming(self, scan, export_root, params):
        naming = resolve_package_naming(
            export_root,
            (scan or {}).get("asset_name", "Asset"),
            package_name_override=params.get("package_name_override") or params.get("asset_name_override") or "",
            version_mode=params.get("package_version_mode") or "overwrite",
            version_padding=params.get("package_version_padding") or 3,
            version_start=params.get("package_version_start") or 1,
        )
        result = dict(scan or {})
        result["package_name"] = naming.get("package_name", "")
        result["package_naming"] = naming
        if params.get("project_preset"):
            result["project_preset"] = params.get("project_preset")
        return result

    def _validation(self, scan, target_platform, params=None):
        validator = self._active_validator(target_platform, params or {})
        validation = validator.validate(scan, target_platform)
        validation = self._downgrade_blender_transform_warning(scan, validation)
        validation = self._attach_texture_set_selection_gate(scan, validation)
        validation = self._attach_material_texture_binding_gate(scan, validation)
        return validation

    def _active_validator(self, target_platform, params):
        rules = json.loads(json.dumps(getattr(self.validator, "rules", {}) or {}, ensure_ascii=False))
        if not rules:
            return self.validator
        rules["name_prefix"] = clean_asset_name_prefix(params.get("mesh_prefix"))
        triangle_budget = _safe_int(params.get("triangle_budget"), 0)
        if triangle_budget > 0:
            budgets = dict(rules.get("max_triangles", {}) or {})
            budgets[target_platform] = triangle_budget
            rules["max_triangles"] = budgets
        return StaticPropRuleValidator(rules)

    def _attach_texture_set_selection_gate(self, scan, validation):
        folder_scan = scan.get("texture_folder_scan", {}) or {}
        if not folder_scan.get("requires_texture_set_selection"):
            return validation
        result = dict(validation)
        checks = list(result.get("checks", []) or [])
        checks.append(
            {
                "id": "texture_set_selection",
                "label": "贴图集选择",
                "status": "error",
                "severity": "error",
                "object": folder_scan.get("texture_folder", ""),
                "value": ", ".join([item.get("set_name", "") for item in folder_scan.get("texture_sets", []) or []]),
                "limit": "选择一个贴图集",
                "message": "贴图目录内存在多个完整贴图集，导出前需要确认本模型使用哪一套贴图。",
                "next_action": "填写 texture_set_token，或把 Blender 材质命名为能匹配贴图集的短 token 后重新预检。",
            }
        )
        result["checks"] = checks
        return self._mark_validation_blocked(result, 1)

    def _attach_material_texture_binding_gate(self, scan, validation):
        blocking = [item for item in scan.get("material_texture_binding_risks", []) or [] if item.get("severity") == "error"]
        if not blocking:
            return validation
        result = dict(validation)
        checks = list(result.get("checks", []) or [])
        for item in blocking:
            checks.append(
                {
                    "id": item.get("id", "material_texture_binding"),
                    "label": "材质贴图绑定",
                    "status": "error",
                    "severity": "error",
                    "object": item.get("material_name", "") or item.get("texture_set", ""),
                    "value": item.get("slot_name", "") or item.get("texture_count", 0),
                    "limit": "每个 Blender 材质必须匹配对应贴图集",
                    "message": item.get("message", "材质贴图绑定失败"),
                    "next_action": "检查 texture_folder 与材质命名，或填写 texture_set_token 后重新预检。",
                }
            )
        result["checks"] = checks
        return self._mark_validation_blocked(result, len(blocking))

    def _mark_validation_blocked(self, validation, error_count):
        result = dict(validation)
        result["status"] = "error"
        result["can_export"] = False
        summary = dict(result.get("summary", {}) or {})
        summary["errors"] = int(summary.get("errors", 0)) + int(error_count)
        result["summary"] = summary
        return result

    def _downgrade_blender_transform_warning(self, scan, validation):
        if not isinstance(validation, dict) or scan.get("source_dcc") != SOURCE_DCC_BLENDER:
            return validation
        changed = False
        for check in validation.get("checks", []) or []:
            if check.get("id") != "frozen_transform" or check.get("status") != "error":
                continue
            check["status"] = "warning"
            check["severity"] = "warning"
            check["message"] = "Blender 对象 Transform 未归零；导出层会保留层级变换，UE Gate 需复核比例和朝向。"
            changed = True
        if not changed:
            return validation
        summary = {"errors": 0, "warnings": 0, "passes": 0}
        for check in validation.get("checks", []) or []:
            status = check.get("status")
            if status == "error":
                summary["errors"] += 1
            elif status == "warning":
                summary["warnings"] += 1
            elif status == "pass":
                summary["passes"] += 1
        validation["summary"] = summary
        validation["status"] = "error" if summary["errors"] else "warning" if summary["warnings"] else "pass"
        validation["can_export"] = summary["errors"] == 0
        return validation

    def _export_name_map(self, scan):
        asset_name = scan.get("asset_name", "SM_Asset")
        name_prefix = clean_asset_name_prefix(scan.get("asset_name_prefix"))
        result = {}
        source_asset_name = scan.get("source_asset_name", "")
        if source_asset_name and source_asset_name != asset_name:
            result[source_asset_name] = asset_name
        for mesh_name in scan.get("meshes", []) or []:
            result[mesh_name] = self._static_mesh_export_name(asset_name, mesh_name, name_prefix, source_asset_name)
        return result

    def _static_mesh_export_name(self, asset_name, mesh_name, name_prefix="SM_", source_asset_name=""):
        name_prefix = clean_asset_name_prefix(name_prefix)
        clean_mesh = self._safe_name(mesh_name)
        source_suffix = self._publish_source_suffix(asset_name, source_asset_name, name_prefix)
        if source_suffix:
            base_mesh = clean_mesh if clean_mesh.startswith(name_prefix) else name_prefix + clean_mesh
            return self._append_publish_suffix(base_mesh, source_suffix)
        if clean_mesh.startswith(name_prefix):
            return self._append_publish_suffix(clean_mesh, source_suffix)
        clean_asset = self._safe_name(asset_name)
        asset_stem = clean_asset[len(name_prefix) :] if clean_asset.startswith(name_prefix) else clean_asset
        if clean_mesh.startswith(asset_stem + "_"):
            return self._append_publish_suffix(name_prefix + clean_mesh, source_suffix)
        return self._append_publish_suffix(clean_asset + "_" + clean_mesh, source_suffix)

    def _prepare_package_textures(self, scan, package, target_path, params=None):
        params = params or {}
        scan = json.loads(json.dumps(scan or {}, ensure_ascii=False))
        scan = self._normalize_blender_material_names_for_ue(scan)
        scan = self._apply_texture_folder(scan, params)
        materials = list(scan.get("materials", []) or [])
        texture_dir = os.path.join(package["package_dir"], "Textures")
        if not os.path.isdir(texture_dir):
            os.makedirs(texture_dir)

        all_textures = []
        texture_sets = []
        for material in materials:
            material_name = material.get("name", "") or material.get("material_name", "") or "Material"
            existing = list(material.get("textures", []) or [])
            existing = [self._copy_existing_texture(texture_dir, scan.get("asset_name", "SM_Asset"), material_name, item) for item in existing]
            by_usage = dict((item.get("usage", ""), item) for item in existing)
            created = []
            for usage in ("base_color", "normal", "packed_arm"):
                texture = by_usage.get(usage)
                if texture:
                    created.append(texture)
                    continue
                texture = self._write_placeholder_texture(texture_dir, scan.get("asset_name", "SM_Asset"), material, usage)
                created.append(texture)
            material["textures"] = created
            material["texture_set"] = material.get("texture_set") or self._texture_set_name(scan.get("asset_name", "SM_Asset"), material_name)
            material["texture_set_short_name"] = material.get("texture_set_short_name") or material_name
            existing_binding_source = material.get("texture_set_binding_source", "")
            if existing_binding_source:
                material["texture_set_binding_source"] = existing_binding_source
            elif any(item.get("source_type") != "blender_placeholder" for item in created):
                material["texture_set_binding_source"] = "blender_image_node"
            else:
                material["texture_set_binding_source"] = "blender_material_placeholder"
            all_textures.extend(created)
            texture_sets.append(
                {
                    "status": "bound",
                    "material_name": material_name,
                    "shading_group": "",
                    "texture_set": material["texture_set"],
                    "texture_set_short_name": material["texture_set_short_name"],
                    "binding_source": material["texture_set_binding_source"],
                    "texture_count": len(created),
                    "usages": sorted([item.get("usage", "") for item in created]),
                    "textures": created,
                }
            )

        scan["materials"] = materials
        scan["textures"] = self._dedupe_textures(all_textures)
        scan["material_texture_sets"] = texture_sets
        binding_report = create_material_texture_bindings(scan, target_path)
        scan["material_texture_bindings"] = binding_report.get("bindings", [])
        scan["material_texture_binding_risks"] = binding_report.get("risks", [])
        return scan

    def _apply_texture_folder(self, scan, params):
        texture_folder = params.get("texture_folder") or params.get("texture_root") or params.get("texture_dir") or ""
        if not texture_folder:
            return scan
        profile = resolve_material_profile(params.get("material_profile") or "Props_Opaque_PainterUE_ARM")
        scanner = TextureFolderScanner(recursive=bool(params.get("texture_recursive", False)))
        folder_scan = scanner.scan(texture_folder, scan.get("asset_name", ""), profile, texture_set_token=params.get("texture_set_token", ""))
        if not params.get("texture_set_token"):
            inferred_token = infer_texture_set_token_from_materials(scan.get("materials", []), folder_scan.get("texture_sets", []))
            if inferred_token:
                folder_scan = scanner.scan(texture_folder, scan.get("asset_name", ""), profile, texture_set_token=inferred_token)
                folder_scan["auto_selected_texture_sets"] = True
                folder_scan["auto_material_texture_set_token"] = inferred_token
        result = dict(scan)
        result["texture_selection_policy"] = {
            "primary": "texture_folder",
            "fallback": "blender_image_node",
            "reason": "explicit_texture_folder",
            "texture_folder": normalize_path(texture_folder),
        }
        result["texture_folder_scan"] = folder_scan
        result["asset_name_candidates"] = folder_scan.get("asset_name_candidates", scan.get("asset_name_candidates", []))
        if folder_scan.get("requires_texture_set_selection"):
            mapping = build_material_texture_set_mapping(scan.get("materials", []), [], folder_scan, scan.get("asset_name", ""), allow_shared_texture_sets=True)
            result["materials"] = self._merge_material_texture_sources(scan.get("materials", []), mapping["materials"])
            result["material_texture_sets"] = mapping["material_texture_sets"]
            result["textures"] = []
            return result
        mapping = build_material_texture_set_mapping(scan.get("materials", []), folder_scan.get("textures", []), folder_scan, scan.get("asset_name", ""), allow_shared_texture_sets=True)
        result["materials"] = self._merge_material_texture_sources(scan.get("materials", []), mapping["materials"])
        result["textures"] = list(folder_scan.get("textures", []))
        result["material_texture_sets"] = mapping["material_texture_sets"]
        result["texture_folder_scan"] = dict(folder_scan, material_texture_sets=mapping["material_texture_sets"])
        return result

    def _merge_material_texture_sources(self, original_materials, folder_materials):
        originals = dict((item.get("name", "") or item.get("material_name", ""), item) for item in (original_materials or []))
        result = []
        for material in folder_materials or []:
            name = material.get("name", "") or material.get("material_name", "")
            original = originals.get(name, {})
            merged = dict(material)
            merged["textures"] = self._merge_textures_by_usage(original.get("textures", []), material.get("textures", []))
            if original.get("textures") and material.get("textures"):
                merged["texture_set_binding_source"] = "blender_image_node+texture_folder"
            result.append(merged)
        return result

    def _merge_textures_by_usage(self, primary, secondary):
        result = []
        seen = set()
        # When an explicit texture folder is provided, it is the publish source of truth.
        # Blender node textures remain useful only for usages the folder does not provide.
        for texture in list(secondary or []) + list(primary or []):
            usage = texture.get("usage", "")
            if usage in seen:
                continue
            result.append(texture)
            seen.add(usage)
        return result

    def _apply_publish_asset_name(self, scan, asset_name_override="", mesh_prefix="", source_name_suffix=""):
        override = self._safe_name(asset_name_override) if str(asset_name_override or "").strip() else ""
        source_suffix = self._safe_name(source_name_suffix) if str(source_name_suffix or "").strip() else ""
        if not override and source_suffix:
            base_name = self._safe_name((scan or {}).get("asset_name", ""))
            suffix = "_" + source_suffix
            override = base_name if base_name.endswith(suffix) else base_name + suffix
        if not override:
            return scan
        prefix = clean_asset_name_prefix(mesh_prefix)
        if not override.startswith(prefix):
            override = prefix + override
        result = dict(scan or {})
        result["asset_name_original"] = result.get("asset_name", "")
        result["asset_name"] = override
        result["asset_name_source"] = "export_override"
        candidates = list(result.get("asset_name_candidates", []) or [])
        if override not in candidates:
            candidates.insert(0, override)
        result["asset_name_candidates"] = candidates
        return result

    def _copy_existing_texture(self, texture_dir, asset_name, material_name, texture):
        texture = dict(texture or {})
        source = texture.get("source_path") or texture.get("path") or texture.get("package_path") or ""
        usage = texture.get("usage", "")
        if not source or not usage:
            return texture
        source_path = os.path.abspath(source)
        if not os.path.isfile(source_path):
            texture["copy_status"] = "missing_source"
            return texture
        target = texture.get("package_path") or self._packaged_texture_path(texture_dir, asset_name, material_name, usage, source_path)
        target_path = os.path.abspath(target)
        if os.path.abspath(source_path) != target_path:
            parent = os.path.dirname(target_path)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            shutil.copy2(source_path, target_path)
        texture["path"] = normalize_path(target_path)
        texture["package_path"] = normalize_path(target_path)
        texture["source_path"] = normalize_path(source_path)
        texture["copied"] = True
        texture["copy_status"] = "copied"
        texture.setdefault("selected_texture_set", self._texture_set_name(asset_name, material_name))
        return apply_texture_metadata(texture, target_path)

    def _packaged_texture_path(self, texture_dir, asset_name, material_name, usage, source_path):
        suffix = {"base_color": "BaseColor", "normal": "Normal", "packed_arm": "OcclusionRoughnessMetallic"}.get(usage, self._safe_name(usage))
        extension = os.path.splitext(source_path)[1] or ".png"
        file_name = "T_{0}_{1}_{2}{3}".format(self._safe_name(asset_name), self._safe_name(material_name), suffix, extension.lower())
        return os.path.join(texture_dir, file_name)

    def _normalize_blender_material_names_for_ue(self, scan):
        for material in scan.get("materials", []) or []:
            original = material.get("material_name") or material.get("name", "")
            safe = self._safe_name(original)
            if original and safe != original:
                material.setdefault("source_material_name", original)
                material.setdefault("blender_material_name", original)
            material["name"] = safe
            material["material_name"] = safe
        for slot in scan.get("material_slot_details", []) or []:
            original = slot.get("name", "")
            safe = self._safe_name(original)
            if original and safe != original:
                slot.setdefault("source_slot_name", original)
                slot.setdefault("blender_material_name", original)
            slot["name"] = safe
        return scan

    def _write_placeholder_texture(self, texture_dir, asset_name, material, usage):
        material_name = material.get("name", "") or material.get("material_name", "") or "Material"
        suffix = {"base_color": "BaseColor", "normal": "Normal", "packed_arm": "OcclusionRoughnessMetallic"}[usage]
        file_name = "T_{0}_{1}_{2}.png".format(self._safe_name(asset_name), self._safe_name(material_name), suffix)
        path = os.path.join(texture_dir, file_name)
        rgba = self._placeholder_rgba(material, usage)
        if not os.path.exists(path):
            _write_png_rgba(path, 1, 1, [rgba])
        texture = {
            "node": "",
            "path": normalize_path(path),
            "source_path": normalize_path(path),
            "package_path": normalize_path(path),
            "copied": True,
            "source_type": "blender_placeholder",
            "source_label": "Blender 占位贴图",
            "usage": usage,
            "parameter": {"base_color": "BaseColor", "normal": "Normal", "packed_arm": "ARM"}[usage],
            "srgb": usage == "base_color",
            "compression": {"base_color": "default", "normal": "normalmap", "packed_arm": "masks"}[usage],
            "match_mode": "blender_material_placeholder",
            "selected_texture_set": self._texture_set_name(asset_name, material_name),
            "width": 1,
            "height": 1,
        }
        if usage == "packed_arm":
            texture["channels"] = {"r": "ao", "g": "roughness", "b": "metallic"}
        return apply_texture_metadata(texture, path)

    def _placeholder_rgba(self, material, usage):
        if usage == "normal":
            return (128, 128, 255, 255)
        if usage == "packed_arm":
            return (255, 128, 0, 255)
        color = material.get("base_color", [0.72, 0.72, 0.72, 1.0])
        values = list(color or [0.72, 0.72, 0.72, 1.0])
        while len(values) < 4:
            values.append(1.0)
        return tuple(int(max(0.0, min(1.0, float(item))) * 255.0 + 0.5) for item in values[:4])

    def _texture_set_name(self, asset_name, material_name):
        return "{0}_{1}".format(self._safe_name(asset_name), self._safe_name(material_name))

    def _safe_name(self, value):
        clean = re.sub(r"[^0-9A-Za-z_]+", "_", value or "Asset").strip("_")
        return clean or "Asset"

    def _publish_source_suffix(self, asset_name, source_asset_name, name_prefix="SM_"):
        clean_asset = self._safe_name(asset_name)
        clean_source = self._safe_name(source_asset_name)
        candidates = [clean_source]
        if clean_source and not clean_source.startswith(name_prefix):
            candidates.append(name_prefix + clean_source)
        for candidate in candidates:
            prefix = candidate + "_"
            if candidate and clean_asset.startswith(prefix):
                return clean_asset[len(prefix) :]
        return ""

    def _append_publish_suffix(self, name, suffix):
        clean_name = self._safe_name(name)
        clean_suffix = self._safe_name(suffix) if str(suffix or "").strip() else ""
        if not clean_suffix or clean_name.endswith("_" + clean_suffix):
            return clean_name
        return clean_name + "_" + clean_suffix

    def _dedupe_textures(self, textures):
        result = []
        seen = set()
        for texture in textures:
            key = (texture.get("usage", ""), texture.get("package_path", ""))
            if key in seen:
                continue
            seen.add(key)
            result.append(texture)
        return result


def _write_png_rgba(path, width, height, pixels):
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            row.extend(bytearray(pixels[y * width + x]))
        rows.append(bytes(row))
    raw = b"".join(rows)
    payload = b"\x89PNG\r\n\x1a\n"
    payload += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    payload += _png_chunk(b"IDAT", zlib.compress(raw))
    payload += _png_chunk(b"IEND", b"")
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "wb") as stream:
        stream.write(payload)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _png_chunk(kind, data):
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _write_json(path, payload):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return normalize_path(path)
