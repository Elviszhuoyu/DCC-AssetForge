# -*- coding: utf-8 -*-
"""Asset Forge provider actions for Blender MCP bridge."""

from __future__ import absolute_import

import json
import os
import re
import struct
import time
import zlib

from asset_forge.blender.fbx_exporter import BlenderFbxExporter
from asset_forge.blender.scanner import BlenderStaticPropScanner
from asset_forge.maya.export_package import build_export_package
from asset_forge.maya.manifest_writer import IMPORT_PRESET_BY_PLATFORM
from asset_forge.shared.constants import SOURCE_DCC_BLENDER, TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.manifest_schema import create_manifest, write_manifest
from asset_forge.shared.material_texture_bindings import create_material_texture_bindings
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.rule_validator import StaticPropRuleValidator, checks_to_manifest_dict
from asset_forge.shared.texture_metadata import apply_texture_metadata
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
        scan = self._prepare_package_textures(scan, package, target_path)
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
        exported_fbx = self.exporter.export_objects(scan.get("asset_roots", []), package["fbx_path"], rename_map=self._export_name_map(scan))
        fbx_exists = os.path.exists(exported_fbx)
        scan = self._prepare_package_textures(scan, package, target_path)
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
            material_texture_sets=scan.get("material_texture_sets", []),
            material_texture_bindings=scan.get("material_texture_bindings", []),
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

    def _export_name_map(self, scan):
        asset_name = scan.get("asset_name", "SM_Asset")
        result = {}
        source_asset_name = scan.get("source_asset_name", "")
        if source_asset_name and source_asset_name != asset_name:
            result[source_asset_name] = asset_name
        for mesh_name in scan.get("meshes", []) or []:
            result[mesh_name] = self._static_mesh_export_name(asset_name, mesh_name)
        return result

    def _static_mesh_export_name(self, asset_name, mesh_name):
        clean_mesh = self._safe_name(mesh_name)
        if clean_mesh.startswith("SM_"):
            return clean_mesh
        clean_asset = self._safe_name(asset_name)
        asset_stem = clean_asset[3:] if clean_asset.startswith("SM_") else clean_asset
        if clean_mesh.startswith(asset_stem + "_"):
            return "SM_" + clean_mesh
        return clean_asset + "_" + clean_mesh
    def _prepare_package_textures(self, scan, package, target_path):
        scan = json.loads(json.dumps(scan or {}, ensure_ascii=False))
        materials = list(scan.get("materials", []) or [])
        texture_dir = os.path.join(package["package_dir"], "Textures")
        if not os.path.isdir(texture_dir):
            os.makedirs(texture_dir)

        all_textures = []
        texture_sets = []
        for material in materials:
            material_name = material.get("name", "") or material.get("material_name", "") or "Material"
            existing = list(material.get("textures", []) or [])
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
            material["texture_set"] = self._texture_set_name(scan.get("asset_name", "SM_Asset"), material_name)
            material["texture_set_short_name"] = material_name
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