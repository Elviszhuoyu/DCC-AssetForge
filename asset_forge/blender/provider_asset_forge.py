# -*- coding: utf-8 -*-
"""Asset Forge provider actions for Blender MCP bridge."""

from __future__ import absolute_import

import json
import os
import time

from asset_forge.blender.fbx_exporter import BlenderFbxExporter
from asset_forge.blender.scanner import BlenderStaticPropScanner
from asset_forge.maya.export_package import build_export_package
from asset_forge.maya.manifest_writer import IMPORT_PRESET_BY_PLATFORM
from asset_forge.shared.constants import SOURCE_DCC_BLENDER, TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.manifest_schema import create_manifest, write_manifest
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.rule_validator import StaticPropRuleValidator, checks_to_manifest_dict
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
        scan = self._scan(params)
        target_platform = params.get("target_platform") or TARGET_PLATFORM_HIGH_END_MOBILE
        validation = self.validator.validate(scan, target_platform)
        return {
            "status": "success" if validation.get("can_export") else "blocked",
            "can_accept": True,
            "can_export": bool(validation.get("can_export")),
            "can_continue_to_package_contract": bool(validation.get("can_export")),
            "scan": scan,
            "validation": validation,
            "next_action": "生成 package contract；真实 UE 导入仍需 Blender FBX exporter。",
        }

    def build_static_prop_package_contract(self, params=None):
        params = params or {}
        export_root = params.get("export_root") or params.get("output_root")
        if not export_root:
            raise RuntimeError("缺少 export_root，无法写出 Blender package contract")
        target_path = sanitize_unreal_package_path(params.get("target_path") or "/Game/Props")
        material_profile = params.get("material_profile") or "Props_Opaque_PainterUE_ARM"
        target_platform = params.get("target_platform") or TARGET_PLATFORM_HIGH_END_MOBILE
        use_asset_folder = params.get("use_asset_folder", True)
        scan = self._scan(params)
        validation = self.validator.validate(scan, target_platform)
        package = build_export_package(export_root, scan.get("asset_name", "Asset"), use_asset_folder)
        manifest = self._build_manifest(scan, validation, package, target_path, target_platform, material_profile)
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
            "manifest": manifest,
            "validation": validation,
            "next_action": report["next_action"],
        }

    def export_static_prop_package(self, params=None):
        params = params or {}
        export_root = params.get("export_root") or params.get("output_root")
        if not export_root:
            raise RuntimeError("缺少 export_root，无法导出 Blender package")
        target_path = sanitize_unreal_package_path(params.get("target_path") or "/Game/Props")
        material_profile = params.get("material_profile") or "Props_Opaque_PainterUE_ARM"
        target_platform = params.get("target_platform") or TARGET_PLATFORM_HIGH_END_MOBILE
        use_asset_folder = params.get("use_asset_folder", True)
        scan = self._scan(params)
        validation = self.validator.validate(scan, target_platform)
        package = build_export_package(export_root, scan.get("asset_name", "Asset"), use_asset_folder)
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
                "validation": validation,
                "next_action": "修复 Blender Static Prop preflight 阻断项后再导出。",
            }
        exported_fbx = self.exporter.export_objects(scan.get("asset_roots", []), package["fbx_path"])
        fbx_exists = os.path.exists(exported_fbx)
        manifest = self._build_manifest(scan, validation, package, target_path, target_platform, material_profile)
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
            "manifest": manifest,
            "validation": validation,
            "next_action": "运行 UE accept-flow 导入 Blender package。" if fbx_exists else "检查 Blender FBX exporter 输出文件。",
        }

    def _build_manifest(self, scan, validation, package, target_path, target_platform, material_profile):
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
            textures=scan.get("textures", []),
            material_profile=material_profile,
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
            "next_action": "运行 UE accept-flow 导入 Blender package。" if can_continue_to_ue else "检查 Blender preflight 或 FBX exporter 输出。",
        }

    def _scan(self, params):
        selection = params.get("selection") or []
        if selection:
            return self.scanner.scan_by_names(selection)
        return self.scanner.scan_selection()


def _write_json(path, payload):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return normalize_path(path)