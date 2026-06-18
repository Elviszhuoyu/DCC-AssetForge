"""Bootstrap default Asset Forge material assets inside the UE plugin mount."""

from __future__ import absolute_import

import binascii
import os
import struct
import zlib

from asset_forge.unreal.material_package_schema import get_default_material_package_plan
from asset_forge.unreal.material_library import (
    GRAPH_COMMENT_BLOCKS,
    PARAMETER_DESCRIPTIONS,
    PARAMETER_GROUPS,
    PARAMETER_SORT_PRIORITIES,
)
from asset_forge.unreal.material_showcase import (
    UnrealMaterialShowcaseBuilder,
    build_material_showcase_report,
    get_default_material_showcase_plan,
)
from asset_forge.unreal.property_utils import get_unreal_property, set_unreal_property
from asset_forge.unreal.unreal_bridge import get_unreal


ASSET_KIND_MATERIAL = "material"
ASSET_KIND_FUNCTION = "material_function"
ASSET_KIND_MATERIAL_INSTANCE = "material_instance"
ASSET_KIND_PARAMETER_COLLECTION = "parameter_collection"
ASSET_KIND_TEXTURE = "texture"

MATERIAL_STATUS_GENERATED = "generated_pbr"

OBSOLETE_MATERIAL_ASSETS = (
    "/AssetForge/Materials/M_AF_HardSurface_Master",
    "/AssetForge/Materials/M_AF_HardSurface_Master_VT",
    "/AssetForge/Materials/M_AF_HardSurface_Masked",
    "/AssetForge/Materials/M_AF_HardSurface_Masked_VT",
    "/AssetForge/Materials/M_AF_HardSurface_Emissive",
    "/AssetForge/Materials/M_AF_HardSurface_Emissive_VT",
    "/AssetForge/Materials/M_AF_HardSurface_DirtyWear",
    "/AssetForge/Materials/M_AF_HardSurface_DirtyWear_VT",
    "/AssetForge/Materials/M_AF_HardSurface_WorldAligned",
    "/AssetForge/Materials/M_AF_HardSurface_POM",
    "/AssetForge/Materials/M_AF_Environment_Master_VT",
    "/AssetForge/Materials/M_AF_Environment_Masked",
    "/AssetForge/Materials/M_AF_Environment_Masked_VT",
    "/AssetForge/Materials/M_AF_Environment_Emissive",
    "/AssetForge/Materials/M_AF_Environment_Emissive_VT",
    "/AssetForge/Materials/M_AF_Character_Basic",
    "/AssetForge/Materials/M_AF_Character_Basic_VT",
    "/AssetForge/Materials/M_AF_Character_Masked",
    "/AssetForge/Materials/M_AF_Character_Masked_VT",
    "/AssetForge/Materials/M_AF_Emissive_Surface",
    "/AssetForge/Materials/M_AF_Emissive_Surface_VT",
    "/AssetForge/Materials/M_AF_Decal_Surface",
    "/AssetForge/Materials/M_AF_Glass_Translucent",
    "/AssetForge/Materials/M_AF_Props_Opaque",
    "/AssetForge/Materials/M_AF_Props_Opaque_VT",
    "/AssetForge/Materials/M_AF_Props_Masked",
    "/AssetForge/Materials/M_AF_Props_Masked_VT",
    "/AssetForge/Materials/M_AF_Props_Translucent",
    "/AssetForge/Materials/M_AF_Props_Translucent_VT",
    "/AssetForge/MaterialInstances/MI_AF_HardSurface_Default",
    "/AssetForge/MaterialInstances/MI_AF_HardSurface_DirtyWear",
    "/AssetForge/MaterialInstances/MI_AF_HardSurface_Emissive",
    "/AssetForge/MaterialInstances/MI_AF_HardSurface_Masked",
    "/AssetForge/MaterialInstances/MI_AF_HardSurface_POM",
    "/AssetForge/MaterialInstances/MI_AF_HardSurface_WorldAligned",
    "/AssetForge/MaterialInstances/MI_AF_Character_Basic",
    "/AssetForge/MaterialInstances/MI_AF_Character_Masked",
    "/AssetForge/MaterialInstances/MI_AF_Emissive_Surface",
    "/AssetForge/MaterialInstances/MI_AF_Decal_Surface",
    "/AssetForge/MaterialInstances/MI_AF_Glass_Translucent",
    "/AssetForge/MaterialFunctions/MF_AF_ApplyEmissive",
    "/AssetForge/MaterialFunctions/MF_AF_DecalSurface",
    "/AssetForge/MaterialFunctions/MF_AF_Emissive",
    "/AssetForge/MaterialFunctions/MF_AF_Imperfections",
    "/AssetForge/MaterialFunctions/MF_AF_NormalStrength",
    "/AssetForge/MaterialFunctions/MF_AF_OpacityMask",
    "/AssetForge/MaterialFunctions/MF_AF_POM",
    "/AssetForge/MaterialFunctions/MF_AF_RoughnessRemap",
    "/AssetForge/MaterialFunctions/MF_AF_TriplanarProjection",
    "/AssetForge/MaterialFunctions/MF_AF_UnpackARM",
    "/AssetForge/MaterialFunctions/MF_AF_UVControls",
    "/AssetForge/MaterialFunctions/MF_AF_Wear",
    "/AssetForge/ParameterCollections/MPC_AF_Global",
)


class UnrealMaterialAssetBootstrap(object):
    """Create or repair UE assets required by material binding plans."""

    def __init__(self, unreal_module=None, package_plan=None):
        self.unreal = unreal_module or get_unreal()
        self.package_plan = package_plan or get_default_material_package_plan()
        self._asset_cache = {}

    def plan(self):
        assets = []
        assets.extend(self._planned_placeholder_textures(self._active_placeholder_textures()))
        assets.extend(self._planned_assets(self._active_materials(), ASSET_KIND_MATERIAL))
        assets.extend(self._planned_material_instances(self.package_plan.get("material_instances", [])))
        assets.extend(self._planned_assets(self._active_functions(), ASSET_KIND_FUNCTION))
        assets.extend(self._planned_assets(self._active_parameter_collections(), ASSET_KIND_PARAMETER_COLLECTION))
        network_plans = [asset.get("material_network_plan", {}) for asset in assets if asset.get("kind") == ASSET_KIND_MATERIAL]
        showcase_plan = get_default_material_showcase_plan(self.package_plan)
        return {
            "status": "ready",
            "content_mount": self.package_plan.get("content_mount", ""),
            "directories": list(self.package_plan.get("directories", [])),
            "asset_count": len(assets),
            "assets": assets,
            "showcase_plan": showcase_plan,
            "showcase_report": build_material_showcase_report(self.package_plan),
            "material_network_status": MATERIAL_STATUS_GENERATED,
            "material_network_message": "UE Python bootstrap 将创建参数化 PBR 母材质网络：BaseColor、Normal、Packed ARM/ORM。",
            "material_network_plans": network_plans,
        }

    def _active_materials(self):
        return [item for item in self.package_plan.get("materials", []) if item.get("required_for_import", True)]

    def _active_functions(self):
        return [item for item in self.package_plan.get("functions", []) if item.get("required_for_import", True)]

    def _active_parameter_collections(self):
        return [item for item in self.package_plan.get("parameter_collections", []) if item.get("required_for_import", True)]

    def _active_placeholder_textures(self):
        return [item for item in self.package_plan.get("placeholder_textures", []) if item.get("required_for_import", True)]

    def inspect_assets(self):
        """Report which default plugin material assets already exist."""
        bootstrap_plan = self.plan()
        assets = []
        for asset_plan in bootstrap_plan.get("assets", []):
            exists = self._asset_exists(asset_plan.get("path", ""))
            assets.append(dict(asset_plan, status="existing" if exists else "missing"))

        existing_assets = [asset["path"] for asset in assets if asset["status"] == "existing"]
        missing_assets = [asset["path"] for asset in assets if asset["status"] == "missing"]
        if self.unreal is None:
            status = "warning"
            message = "当前不在 Unreal Python 环境，无法确认默认材质资产是否存在。"
        elif missing_assets:
            status = "warning"
            message = "默认材质资产不完整。"
        else:
            status = "pass"
            message = "默认材质资产已就绪。"

        return {
            "status": status,
            "message": message,
            "content_mount": bootstrap_plan.get("content_mount", ""),
            "planned_count": len(assets),
            "existing_count": len(existing_assets),
            "missing_count": len(missing_assets),
            "existing_assets": existing_assets,
            "missing_assets": missing_assets,
            "assets": assets,
            "material_network_status": bootstrap_plan.get("material_network_status", ""),
            "material_network_message": bootstrap_plan.get("material_network_message", ""),
        }

    def validate_parent_materials(self, material_binding_plan):
        """Validate that planned Material Instances can resolve their UE parent materials."""
        materials = list((material_binding_plan or {}).get("materials", []))
        if not materials:
            return {
                "status": "skipped",
                "can_create_material_instances": True,
                "message": "没有需要创建的材质实例，跳过母材质检查。",
                "checks": [],
                "missing_parent_materials": [],
                "next_action": "步骤已跳过，按需执行下一步。",
            }

        if self.unreal is None:
            checks = [
                self._parent_check(
                    "warning",
                    item.get("parent_material", ""),
                    item.get("target_asset_path", ""),
                    "当前不在 Unreal Python 环境中，无法真实检查母材质资产。",
                )
                for item in materials
                if item.get("parent_material", "")
            ]
            return {
                "status": "warning",
                "can_create_material_instances": False,
                "message": "未执行 UE 真实母材质检查。",
                "checks": checks,
                "missing_parent_materials": [],
                "next_action": "请在真实 UE 5.6 Editor Python 环境中重新执行该步骤。",
            }

        checks = []
        for item in materials:
            parent = item.get("parent_material", "")
            target = item.get("target_asset_path", "")
            if not parent:
                checks.append(self._parent_check("error", parent, target, "Material Profile 未提供母材质路径，无法创建材质实例。"))
            elif self._asset_exists(parent):
                checks.append(self._parent_check("pass", parent, target, "母材质存在，可以创建材质实例。"))
            else:
                checks.append(self._parent_check("error", parent, target, "缺少母材质：{0}，材质实例将没有 parent。".format(parent)))

        missing = [item.get("parent_material", "") for item in checks if item.get("status") == "error" and item.get("parent_material")]
        return {
            "status": "error" if missing else "pass",
            "can_create_material_instances": not missing,
            "message": "母材质检查通过。" if not missing else "母材质缺失，无法安全创建材质实例。",
            "checks": checks,
            "missing_parent_materials": missing,
            "next_action": "" if not missing else "先确认 AssetForge 插件内容已挂载，并执行默认材质 Bootstrap 后重新检查母材质。",
        }

    def bootstrap(self, dry_run=False, build_showcase=False, cleanup_obsolete_assets=False):
        bootstrap_plan = self.plan()
        self._scan_asset_registry_paths([self.package_plan.get("content_mount", "/AssetForge"), "/Engine/BasicShapes"])
        asset_validation = self.inspect_assets()
        dry_run_reports = self._dry_run_material_network_reports(bootstrap_plan, self.unreal is None)
        report = {
            "status": "skipped" if dry_run else "failed",
            "message": "材质资产预检完成，未创建真实资产。" if dry_run else "材质资产 Bootstrap 失败。",
            "plan": bootstrap_plan,
            "asset_validation": asset_validation,
            "material_network_status": bootstrap_plan.get("material_network_status", MATERIAL_STATUS_GENERATED),
            "material_network_message": bootstrap_plan.get("material_network_message", ""),
            "material_network_reports": dry_run_reports,
            "created_assets": [],
            "updated_assets": [],
            "existing_assets": [],
            "obsolete_assets_planned_for_cleanup": [],
            "obsolete_asset_cleanup_enabled": bool(cleanup_obsolete_assets),
            "deleted_obsolete_assets": [],
            "obsolete_asset_cleanup_issues": [],
            "configured_textures": [],
            "showcase_report": bootstrap_plan.get("showcase_report", {}),
            "issues": [],
            "next_action": "",
        }
        if self.unreal is None:
            report["issues"].append("当前不在 Unreal Python 环境，未创建真实资产。")
            report["next_action"] = "请在真实 UE 5.6 Editor Python 环境中执行 Bootstrap 以创建或修复母材质资产。"
            return report
        if dry_run:
            report["obsolete_assets_planned_for_cleanup"] = self._existing_obsolete_assets()
            report["next_action"] = "dry-run 只输出母材质节点与连接计划；如需创建资产，请在 UE Python 中关闭 dry-run 后执行。"
            return report

        report["material_network_reports"] = []
        report["obsolete_assets_planned_for_cleanup"] = self._existing_obsolete_assets()
        if cleanup_obsolete_assets:
            self._cleanup_obsolete_assets(report)
        self._ensure_directories(bootstrap_plan.get("directories", []))
        for asset_plan in bootstrap_plan.get("assets", []):
            self._ensure_asset(asset_plan, report)
        if build_showcase:
            report["showcase_report"] = self._ensure_material_showcase(bootstrap_plan)
            if report["showcase_report"].get("status") == "error":
                report["issues"].extend(report["showcase_report"].get("issues", []))
        else:
            report["showcase_report"] = self._skipped_material_showcase_report(bootstrap_plan)

        report["asset_validation"] = self.inspect_assets()
        report["status"] = "warning" if report["issues"] else "success"
        report["message"] = "默认材质资产 Bootstrap 完成。" if not report["issues"] else "默认材质资产 Bootstrap 完成，但存在警告。"
        if report["issues"]:
            report["next_action"] = "打开母材质检查 BaseColor、Normal、ARM 参数节点和连接，必要时手动修复后重新验收。"
        return report

    def _ensure_material_showcase(self, bootstrap_plan):
        builder = UnrealMaterialShowcaseBuilder(
            unreal_module=self.unreal,
            material_plan=self.package_plan,
            showcase_plan=bootstrap_plan.get("showcase_plan"),
        )
        return builder.build()

    def _skipped_material_showcase_report(self, bootstrap_plan):
        report = dict(bootstrap_plan.get("showcase_report", {}) or {})
        report["status"] = "skipped"
        report["message"] = "Material showcase is opt-in; default import/bootstrap must not open or create a level."
        return report

    def _planned_assets(self, items, kind):
        assets = []
        for item in items:
            asset_path = item.get("path", "")
            package_path, asset_name = asset_path.rsplit("/", 1)
            asset = {
                "kind": kind,
                "name": asset_name,
                "path": asset_path,
                "package_path": package_path,
                "render_mode": item.get("render_mode", ""),
                "asset_family": item.get("asset_family", ""),
                "factory": self._factory_name(kind),
                "asset_class": self._asset_class_name(kind),
            }
            if kind == ASSET_KIND_MATERIAL:
                asset["material_network_plan"] = self._material_network_plan(item)
            if kind == ASSET_KIND_FUNCTION:
                asset["function_interface_plan"] = {
                    "inputs": list(item.get("inputs", [])),
                    "outputs": list(item.get("outputs", [])),
                    "purpose": item.get("purpose", ""),
                    "status": item.get("material_function_interface_status", "generated_interface"),
                }
            assets.append(asset)
        return assets

    def _planned_placeholder_textures(self, items):
        assets = []
        for item in items:
            asset_path = item.get("path", "")
            package_path, asset_name = asset_path.rsplit("/", 1)
            assets.append(
                {
                    "kind": ASSET_KIND_TEXTURE,
                    "name": asset_name,
                    "path": asset_path,
                    "package_path": package_path,
                    "usage": item.get("usage", ""),
                    "rgba": list(item.get("rgba", [128, 128, 128, 255])),
                    "srgb": bool(item.get("srgb", True)),
                    "compression": item.get("compression", "default"),
                    "pattern": item.get("pattern", "solid"),
                    "factory": self._factory_name(ASSET_KIND_TEXTURE),
                    "asset_class": self._asset_class_name(ASSET_KIND_TEXTURE),
                }
            )
        return assets

    def _planned_material_instances(self, items):
        assets = []
        for item in items:
            asset_path = item.get("path", "")
            package_path, asset_name = asset_path.rsplit("/", 1)
            assets.append(
                {
                    "kind": ASSET_KIND_MATERIAL_INSTANCE,
                    "name": asset_name,
                    "path": asset_path,
                    "package_path": package_path,
                    "parent_material": item.get("parent_material", ""),
                    "scalar_overrides": dict(item.get("scalar_overrides", {}) or {}),
                    "vector_overrides": dict(item.get("vector_overrides", {}) or {}),
                    "static_switch_overrides": dict(item.get("static_switch_overrides", {}) or {}),
                    "texture_overrides": dict(item.get("texture_overrides", {}) or {}),
                    "factory": self._factory_name(ASSET_KIND_MATERIAL_INSTANCE),
                    "asset_class": self._asset_class_name(ASSET_KIND_MATERIAL_INSTANCE),
                }
            )
        return assets

    def _material_network_plan(self, item):
        parameters = list(item.get("texture_parameters", []))
        supports_vt = bool(item.get("supports_virtual_texture_sampling", False))
        nodes = []
        if "BaseColor" in parameters:
            nodes.append(self._texture_node("BaseColor", "color", "rgb", "base_color", supports_vt))
        if "Normal" in parameters:
            nodes.append(self._texture_node("Normal", "normal", "rgb", "normal", supports_vt))
        packed_name = "ARM" if "ARM" in parameters else ("ORM" if "ORM" in parameters else "")
        if packed_name:
            nodes.append(self._texture_node(packed_name, "masks", "rgb", "packed_arm", supports_vt))
        if "Emissive" in parameters:
            nodes.append(self._texture_node("Emissive", "color", "rgb", "emissive", supports_vt))
        if "ImperfectionMask" in parameters:
            nodes.append(self._texture_node("ImperfectionMask", "masks", "rgba", "imperfection_mask", supports_vt))
        if "Height" in parameters:
            nodes.append(self._texture_node("Height", "masks", "r", "height", supports_vt))
        if "OpacityMask" in parameters:
            nodes.append(self._texture_node("OpacityMask", "masks", "r", "opacity_mask", supports_vt))
        if "Opacity" in parameters:
            nodes.append(self._texture_node("Opacity", "masks", "r", "opacity", supports_vt))

        connections = []
        for node in nodes:
            name = node["parameter"]
            if name == "BaseColor":
                connections.append(_connection(name, "RGB", "base_color"))
            elif name == "Normal":
                connections.append(_connection(name, "RGB", "normal"))
            elif name in ("ARM", "ORM"):
                connections.extend(
                    [
                        _connection(name, "R", "ambient_occlusion", "ao"),
                        _connection(name, "G", "roughness", "roughness"),
                        _connection(name, "B", "metallic", "metallic"),
                    ]
                )
            elif name == "Emissive":
                connections.append(_connection(name, "RGB", "emissive_color"))
            elif name == "OpacityMask":
                connections.append(_connection(name, "R", "opacity_mask", "separate_opacity_mask"))
            elif name == "Opacity":
                connections.append(_connection(name, "R", "opacity"))

        if "UseOpacityMask" in (item.get("static_switches", {}) or {}) and "BaseColor" in parameters:
            connections.append(_connection("BaseColor", "A", "opacity_mask", "base_color_alpha"))

        return {
            "material_path": item.get("path", ""),
            "status": MATERIAL_STATUS_GENERATED,
            "texture_parameters": parameters,
            "master_family": item.get("master_family", ""),
            "parameter_api_mapping": dict(item.get("parameter_api_mapping", {}) or {}),
            "static_switches": dict(item.get("static_switches", {}) or {}),
            "scalar_parameters": list(item.get("scalar_parameters", [])),
            "vector_parameters": dict(item.get("vector_parameters", {}) or {}),
            "nodes": nodes,
            "connections": connections,
            "channel_semantics": {"R": "ambient_occlusion", "G": "roughness", "B": "metallic"},
            "supports_virtual_texture_sampling": supports_vt,
        }

    def _texture_node(self, parameter, sampler_type, output, usage, supports_virtual_texture_sampling=False):
        active_sampler_type = self._virtual_sampler_type(sampler_type) if supports_virtual_texture_sampling else sampler_type
        return {
            "node_type": "TextureSampleParameter2D",
            "parameter": parameter,
            "sampler_type": active_sampler_type,
            "default_asset_path": self._default_texture_asset_path(usage, active_sampler_type),
            "default_output": output,
            "usage": usage,
            "supports_virtual_texture_sampling": bool(supports_virtual_texture_sampling),
        }

    def _dry_run_material_network_reports(self, bootstrap_plan, unreal_missing=False):
        reports = []
        for plan in bootstrap_plan.get("material_network_plans", []):
            issues = []
            if unreal_missing:
                issues.append("当前不在 Unreal Python 环境，未创建真实资产。")
            reports.append(
                {
                    "status": "dry_run",
                    "material_path": plan.get("material_path", ""),
                    "material_network_status": plan.get("status", MATERIAL_STATUS_GENERATED),
                    "api_usage": {
                        "create_node": "MaterialEditingLibrary.create_material_expression",
                        "connect_property": "MaterialEditingLibrary.connect_material_property",
                        "connect_expression": "MaterialEditingLibrary.connect_material_expressions（仅用于表达式间连接；材质属性连接仍优先 connect_material_property）",
                        "recompile": "MaterialEditingLibrary.recompile_material",
                        "save": "EditorAssetLibrary.save_asset",
                    },
                    "parameters": list(plan.get("texture_parameters", [])),
                    "scalar_parameters": list(plan.get("scalar_parameters", [])),
                    "vector_parameters": dict(plan.get("vector_parameters", {})),
                    "nodes": list(plan.get("nodes", [])),
                    "connections": list(plan.get("connections", [])),
                    "channel_semantics": dict(plan.get("channel_semantics", {})),
                    "supports_virtual_texture_sampling": bool(plan.get("supports_virtual_texture_sampling", False)),
                    "created_nodes": [],
                    "connected": [],
                    "issues": issues,
                    "next_action": "在真实 UE 5.6 Editor Python 环境中执行 Bootstrap 后确认节点和连接已创建。",
                }
            )
        return reports

    def _ensure_directories(self, directories):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if not library or not hasattr(library, "make_directory"):
            return
        for directory in directories:
            library.make_directory(directory)

    def _existing_obsolete_assets(self):
        return [asset_path for asset_path in OBSOLETE_MATERIAL_ASSETS if self._asset_exists(asset_path)]

    def _cleanup_obsolete_assets(self, report):
        for asset_path in self._existing_obsolete_assets():
            if asset_path not in report["obsolete_assets_planned_for_cleanup"]:
                report["obsolete_assets_planned_for_cleanup"].append(asset_path)
            if self._delete_asset(asset_path):
                report["deleted_obsolete_assets"].append(asset_path)
            else:
                issue = "Obsolete material cleanup failed: {0}".format(asset_path)
                report["obsolete_asset_cleanup_issues"].append(issue)
                report["issues"].append(issue)

    def _ensure_asset(self, asset_plan, report):
        asset_path = asset_plan.get("path", "")
        asset = None
        if asset_plan.get("kind") == ASSET_KIND_TEXTURE:
            asset = self._ensure_placeholder_texture(asset_plan, report)
            if asset:
                if asset_path not in report["created_assets"] and asset_path not in report["existing_assets"]:
                    if self._asset_exists(asset_path):
                        report["existing_assets"].append(asset_path)
                    else:
                        report["updated_assets"].append(asset_path)
                self._configure_texture_asset(asset, asset_plan)
                report["configured_textures"].append(
                    {
                        "path": asset_path,
                        "usage": asset_plan.get("usage", ""),
                        "srgb": bool(asset_plan.get("srgb", True)),
                        "compression": asset_plan.get("compression", "default"),
                    }
                )
                self._save_asset(asset_path)
            return
        if self._asset_exists(asset_path):
            report["existing_assets"].append(asset_path)
            asset = self._load_asset(asset_path)
        else:
            asset = self._load_asset(asset_path)
            if asset:
                report["existing_assets"].append(asset_path)
            else:
                asset = self._create_asset(asset_plan, report)
                if asset:
                    report["created_assets"].append(asset_path)
        if not asset:
            return

        if asset_plan.get("kind") == ASSET_KIND_MATERIAL:
            self._configure_material(asset, asset_plan)
            network_report = self._configure_material_network(asset, asset_plan)
            report["material_network_reports"].append(network_report)
            if network_report.get("status") in ("success", "warning"):
                if asset_path not in report["created_assets"]:
                    report["updated_assets"].append(asset_path)
            report["issues"].extend(network_report.get("issues", []))
        elif asset_plan.get("kind") == ASSET_KIND_MATERIAL_INSTANCE:
            self._configure_material_instance(asset, asset_plan, report)
        elif asset_plan.get("kind") == ASSET_KIND_FUNCTION:
            self._configure_material_function(asset, asset_plan, report)
        self._save_asset(asset_path)

    def _ensure_placeholder_texture(self, asset_plan, report):
        asset_path = asset_plan.get("path", "")
        if self._asset_exists(asset_path):
            asset = self._import_placeholder_texture(asset_plan, report) or self._load_asset(asset_path)
            if asset:
                self._asset_cache[asset_path] = asset
            return asset

        asset = self._import_placeholder_texture(asset_plan, report)
        if not asset:
            asset = self._create_asset(asset_plan, report)
        if asset:
            self._asset_cache[asset_path] = asset
            report["created_assets"].append(asset_path)
        return asset

    def _import_placeholder_texture(self, asset_plan, report):
        task_class = getattr(self.unreal, "AssetImportTask", None)
        if task_class is None:
            return None
        source_path = self._write_placeholder_png(asset_plan, report)
        if not source_path:
            return None
        task = task_class()
        set_unreal_property(task, "filename", source_path)
        set_unreal_property(task, "destination_path", asset_plan.get("package_path", ""))
        set_unreal_property(task, "destination_name", asset_plan.get("name", ""))
        set_unreal_property(task, "replace_existing", True)
        set_unreal_property(task, "automated", True)
        set_unreal_property(task, "save", True)
        try:
            self.unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        except Exception as exc:
            report["issues"].append("Placeholder texture import failed: {0}: {1}".format(asset_plan.get("path", ""), exc))
            return None
        return self._load_asset(asset_plan.get("path", ""))

    def _write_placeholder_png(self, asset_plan, report):
        saved_dir = self._project_saved_dir()
        if not saved_dir:
            return None
        folder = os.path.join(saved_dir, "AssetForge", "PlaceholderTextures")
        try:
            if not os.path.isdir(folder):
                os.makedirs(folder)
            path = os.path.join(folder, asset_plan.get("name", "Texture") + ".png")
            self._write_pattern_rgba_png(path, asset_plan.get("rgba", [128, 128, 128, 255]), 64, 64, asset_plan.get("pattern", "solid"))
            return path
        except Exception as exc:
            report["issues"].append("Placeholder texture file write failed: {0}: {1}".format(asset_plan.get("path", ""), exc))
            return None

    def _project_saved_dir(self):
        paths = getattr(self.unreal, "Paths", None)
        if paths is not None:
            for name in ("project_saved_dir", "ProjectSavedDir"):
                method = getattr(paths, name, None)
                if method is not None:
                    try:
                        return method()
                    except Exception:
                        pass
        return os.path.join(os.getcwd(), "Saved")

    def _write_solid_rgba_png(self, path, rgba, width, height):
        color = [max(0, min(255, int(value))) for value in (list(rgba) + [255, 255, 255, 255])[:4]]
        self._write_rgba_png(path, [[color for _x in range(width)] for _y in range(height)])

    def _write_pattern_rgba_png(self, path, rgba, width, height, pattern):
        base = [max(0, min(255, int(value))) for value in (list(rgba) + [255, 255, 255, 255])[:4]]
        pixels = []
        for y in range(height):
            row = []
            for x in range(width):
                row.append(self._preview_pixel(base, x, y, width, height, pattern))
            pixels.append(row)
        self._write_rgba_png(path, pixels)

    def _preview_pixel(self, base, x, y, width, height, pattern):
        if pattern == "alpha_grid":
            checker = ((x // 8) + (y // 8)) % 2
            shade = 188 if checker else 92
            alpha = 255 if (x // 16 + y // 16) % 3 else 32
            return [shade, min(255, shade + 16), min(255, shade + 28), alpha]
        if pattern == "mask_stripes":
            value = 255 if ((x + y) // 10) % 2 == 0 else 0
            return [value, value, value, 255]
        if pattern == "emissive_panels":
            panel = (x // 12) % 2 == 0 and 18 < y < height - 18
            if panel:
                pulse = 190 + ((x * 7 + y * 3) % 66)
                return [255, pulse, 32, 255]
            return [0, 0, 0, 255]
        if pattern == "imperfection_wear":
            edge = min(x, y, width - 1 - x, height - 1 - y)
            scratches = 255 if (x * 5 + y * 11) % 37 < 4 else 0
            grime = 180 if (x * 3 + y * 7) % 29 < 6 else 24
            wear = 255 if edge < 8 or scratches else grime
            return [wear, grime, scratches, 255]
        if pattern == "metal_panel":
            seam = x % 16 == 0 or y % 16 == 0
            rivet = ((x - 8) % 32) ** 2 + ((y - 8) % 32) ** 2 < 10
            shade = 88 if seam else (178 if rivet else 132 + ((x * 3 + y * 5) % 18))
            return [shade, min(255, shade + 8), min(255, shade + 14), 255]
        if pattern == "rubber":
            grain = (x * 13 + y * 17) % 31
            shade = 18 + grain // 2
            return [shade, shade + 2, shade + 3, 255]
        if pattern == "tile_floor":
            grout = x % 16 in (0, 1) or y % 16 in (0, 1)
            shade = 64 if grout else 112 + ((x * 5 + y * 3) % 28)
            return [shade, min(255, shade + 6), min(255, shade + 2), 255]
        if pattern == "skin_warm":
            pore = (x * 19 + y * 23) % 41
            r = 198 + (pore % 18)
            g = 136 + (pore % 12)
            b = 108 + (pore % 10)
            return [r, g, b, 255]
        return list(base)

    def _write_rgba_png(self, path, pixels):
        height = len(pixels)
        width = len(pixels[0]) if height else 0
        raw = b"".join(b"\x00" + b"".join(bytes(pixel) for pixel in row) for row in pixels)
        chunks = [
            self._png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            self._png_chunk(b"IDAT", zlib.compress(raw)),
            self._png_chunk(b"IEND", b""),
        ]
        with open(path, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n" + b"".join(chunks))

    def _png_chunk(self, chunk_type, data):
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", binascii.crc32(chunk_type + data) & 0xFFFFFFFF)

    def _configure_texture_asset(self, texture_asset, asset_plan):
        set_unreal_property(texture_asset, "srgb", bool(asset_plan.get("srgb", True)))
        compression = self._texture_compression(asset_plan.get("compression", "default"))
        if compression is not None:
            set_unreal_property(texture_asset, "compression_settings", compression)
        set_unreal_property(texture_asset, "virtual_texture_streaming", False)

    def _texture_compression(self, compression):
        enum_class = getattr(self.unreal, "TextureCompressionSettings", None)
        if enum_class is None:
            return None
        candidates = {
            "default": ["TC_DEFAULT"],
            "normal": ["TC_NORMALMAP"],
            "masks": ["TC_MASKS", "TC_GRAYSCALE", "TC_DEFAULT"],
        }.get(compression, ["TC_DEFAULT"])
        for name in candidates:
            value = getattr(enum_class, name, None)
            if value is not None:
                return value
        return None

    def _create_asset(self, asset_plan, report):
        factory_class = getattr(self.unreal, asset_plan.get("factory", ""), None)
        asset_class = getattr(self.unreal, asset_plan.get("asset_class", ""), None)
        if factory_class is None or asset_class is None:
            report["issues"].append("当前 UE Python API 不支持创建资产：{0}".format(asset_plan.get("path", "")))
            return None

        asset = self.unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            asset_plan.get("name", ""),
            asset_plan.get("package_path", ""),
            asset_class,
            factory_class(),
        )
        if not asset:
            report["issues"].append("资产创建失败：{0}".format(asset_plan.get("path", "")))
        if asset:
            self._asset_cache[asset_plan.get("path", "")] = asset
        return asset

    def _configure_material(self, material_asset, asset_plan):
        domain = self._material_domain(asset_plan.get("render_mode", ""))
        if domain is not None:
            set_unreal_property(material_asset, "material_domain", domain)
        blend_mode = self._blend_mode(asset_plan.get("render_mode", ""))
        if blend_mode is not None:
            set_unreal_property(material_asset, "blend_mode", blend_mode)
        plan = asset_plan.get("material_network_plan", {}) or {}
        if asset_plan.get("render_mode") == "masked" and "OpacityClipValue" in plan.get("scalar_parameters", []):
            set_unreal_property(material_asset, "opacity_mask_clip_value", 0.333)

    def _configure_material_instance(self, material_instance, asset_plan, report):
        parent_path = asset_plan.get("parent_material", "")
        parent = self._load_asset(parent_path) if parent_path else None
        if parent:
            set_unreal_property(material_instance, "parent", parent)
        else:
            report["issues"].append("默认材质实例缺少可加载父材质：{0}".format(parent_path))
        editing = getattr(self.unreal, "MaterialEditingLibrary", None)
        if editing is None:
            return
        scalar_setter = getattr(editing, "set_material_instance_scalar_parameter_value", None)
        vector_setter = getattr(editing, "set_material_instance_vector_parameter_value", None)
        static_switch_setter = getattr(editing, "set_material_instance_static_switch_parameter_value", None)
        texture_setter = getattr(editing, "set_material_instance_texture_parameter_value", None)
        for name, value in asset_plan.get("scalar_overrides", {}).items():
            if scalar_setter is not None:
                result = scalar_setter(material_instance, name, value)
                self._record_material_instance_parameter_confirmation(editing, material_instance, asset_plan, report, "scalar_parameters", name, result)
        for name, value in asset_plan.get("vector_overrides", {}).items():
            if vector_setter is not None:
                result = vector_setter(material_instance, name, self._linear_color_value(value))
                self._record_material_instance_parameter_confirmation(editing, material_instance, asset_plan, report, "vector_parameters", name, result)
        for name, value in asset_plan.get("texture_overrides", {}).items():
            texture = self._load_asset(value)
            if texture and texture_setter is not None:
                result = texture_setter(material_instance, name, texture)
                self._record_material_instance_parameter_confirmation(editing, material_instance, asset_plan, report, "texture_parameters", name, result)
            elif texture_setter is None:
                report["issues"].append("当前 UE Python API 未暴露 Material Instance Texture 设置：{0}.{1}".format(asset_plan.get("path", ""), name))
            else:
                report["issues"].append("默认材质实例贴图覆盖缺少可加载纹理：{0}.{1} -> {2}".format(asset_plan.get("path", ""), name, value))
        for name, value in asset_plan.get("static_switch_overrides", {}).items():
            if scalar_setter is not None:
                scalar_result = scalar_setter(material_instance, name, 1.0 if bool(value) else 0.0)
                self._record_material_instance_parameter_confirmation(editing, material_instance, asset_plan, report, "scalar_parameters", name, scalar_result)
            if static_switch_setter is not None:
                result = static_switch_setter(material_instance, name, bool(value))
                self._record_material_instance_parameter_confirmation(editing, material_instance, asset_plan, report, "static_switch_parameters", name, result)
            else:
                report["issues"].append("当前 UE Python API 未暴露 Material Instance Static Switch 设置：{0}.{1}".format(asset_plan.get("path", ""), name))
        if hasattr(editing, "update_material_instance"):
            editing.update_material_instance(material_instance)

    def _record_material_instance_parameter_confirmation(self, editing, material_instance, asset_plan, report, category, name, result):
        if result is True or self._material_instance_parameter_readback(editing, material_instance, category, name):
            return
        report["issues"].append("默认材质实例参数未确认：{0}.{1}".format(asset_plan.get("path", ""), name))

    def _material_instance_parameter_readback(self, editing, material_instance, category, name):
        getter_name = {
            "texture_parameters": "get_material_instance_texture_parameter_value",
            "scalar_parameters": "get_material_instance_scalar_parameter_value",
            "vector_parameters": "get_material_instance_vector_parameter_value",
            "static_switch_parameters": "get_material_instance_static_switch_parameter_value",
        }.get(category, "")
        getter = getattr(editing, getter_name, None) if editing is not None else None
        if getter is not None:
            try:
                return getter(material_instance, name) is not None
            except Exception:
                pass
        property_names = {
            "texture_parameters": ["TextureParameterValues", "texture_parameter_values"],
            "scalar_parameters": ["ScalarParameterValues", "scalar_parameter_values"],
            "vector_parameters": ["VectorParameterValues", "vector_parameter_values"],
            "static_switch_parameters": ["StaticParameters", "static_parameters"],
        }.get(category, [])
        for property_name in property_names:
            text = str(get_unreal_property(material_instance, property_name, ""))
            if 'Name="{0}"'.format(name) in text or "Name={0}".format(name) in text:
                return True
        return False

    def _configure_material_function(self, function_asset, asset_plan, report):
        editing_library = getattr(self.unreal, "MaterialEditingLibrary", None)
        input_class = getattr(self.unreal, "MaterialExpressionFunctionInput", None)
        output_class = getattr(self.unreal, "MaterialExpressionFunctionOutput", None)
        interface = asset_plan.get("function_interface_plan", {}) or {}
        if editing_library is None:
            report["issues"].append("当前 UE Python API 不支持创建 Material Function 输入/输出节点：{0}".format(asset_plan.get("path", "")))
            return
        if input_class is None or output_class is None:
            report["issues"].append("当前 UE Python API 缺少 MaterialExpressionFunctionInput/Output：{0}".format(asset_plan.get("path", "")))
            return
        create_expression = self._material_function_expression_creator(editing_library, function_asset, report, asset_plan.get("path", ""))
        if create_expression is None:
            return
        self._reset_generated_material_function(function_asset, editing_library, report)
        inputs = {}
        outputs = {}
        for index, input_name in enumerate(interface.get("inputs", [])):
            expression = create_expression(input_class, -420, index * 120)
            set_unreal_property(expression, "input_name", input_name)
            set_unreal_property(expression, "description", interface.get("purpose", ""))
            self._configure_function_input_type(expression, input_name)
            inputs[input_name] = expression
        for index, output_name in enumerate(interface.get("outputs", [])):
            expression = create_expression(output_class, 240, index * 120)
            set_unreal_property(expression, "output_name", output_name)
            set_unreal_property(expression, "description", interface.get("purpose", ""))
            outputs[output_name] = expression
        self._connect_material_function_body(function_asset, create_expression, editing_library, inputs, outputs, asset_plan, report)

    def _connect_material_function_body(self, function_asset, create_expression, editing_library, inputs, outputs, asset_plan, report):
        if not hasattr(editing_library, "connect_material_expressions"):
            report["issues"].append("当前 UE Python API 缺少 Material Function 内部连线接口：{0}".format(asset_plan.get("path", "")))
            return
        name = asset_plan.get("name", "")
        if name == "MF_AF_UVControls":
            output = self._function_multiply(function_asset, create_expression, editing_library, inputs.get("UV"), "", inputs.get("UVTiling"), "", -80, 0, report)
            self._connect_function_output(editing_library, output, "", outputs.get("UVOut"), report)
        elif name == "MF_AF_UnpackARM":
            packed = inputs.get("PackMapRGB")
            self._connect_function_output(editing_library, packed, "R", outputs.get("AO"), report)
            self._connect_function_output(editing_library, packed, "G", outputs.get("Roughness"), report)
            self._connect_function_output(editing_library, packed, "B", outputs.get("Metallic"), report)
        elif name == "MF_AF_NormalStrength":
            normal = inputs.get("NormalRGB")
            strength = inputs.get("NormalStrength")
            output = self._function_normal_strength(function_asset, create_expression, editing_library, normal, strength, -80, 0, report)
            self._connect_function_output(editing_library, output, "", outputs.get("NormalOut"), report)
        elif name == "MF_AF_OpacityMask":
            output = self._function_multiply(function_asset, create_expression, editing_library, inputs.get("OpacityMask"), "", inputs.get("MaskContrast"), "", -80, 0, report)
            self._connect_function_output(editing_library, output, "", outputs.get("MaskOut"), report)
        elif name == "MF_AF_Emissive":
            tinted = self._function_multiply(function_asset, create_expression, editing_library, inputs.get("EmissiveRGB"), "", inputs.get("EmissiveTint"), "", -80, 0, report)
            output = self._function_multiply(function_asset, create_expression, editing_library, tinted, "", inputs.get("EmissiveIntensity"), "", 80, 0, report)
            self._connect_function_output(editing_library, output, "", outputs.get("EmissiveOut"), report)

    def _connect_function_output(self, editing_library, expression, output_name, function_output, report):
        if expression is None or function_output is None:
            return
        editing_library.connect_material_expressions(expression, output_name, function_output, "Result")
        self._set_expression_input(function_output, ("a", "A", "result", "Result"), expression, output_name)
        report.setdefault("material_function_connections", []).append(
            {
                "source": getattr(expression, "input_name", getattr(expression, "parameter_name", "")),
                "output": output_name,
                "target": getattr(function_output, "output_name", ""),
                "target_input": "Result",
            }
        )

    def _function_multiply(self, function_asset, create_expression, editing_library, left, left_output, right, right_output, x, y, report):
        if left is None or right is None:
            return left or right
        multiply_class = getattr(self.unreal, "MaterialExpressionMultiply", None)
        if multiply_class is None:
            report["issues"].append("当前 UE Python API 缺少 Multiply 节点，Material Function 将退化为直连。")
            return left
        node = create_expression(multiply_class, x, y)
        editing_library.connect_material_expressions(left, left_output, node, "A")
        editing_library.connect_material_expressions(right, right_output, node, "B")
        return node

    def _function_normal_strength(self, function_asset, create_expression, editing_library, normal, strength, x, y, report):
        if normal is None or strength is None:
            return normal
        flatten_class = getattr(self.unreal, "MaterialExpressionFlattenNormal", None)
        one_minus_class = getattr(self.unreal, "MaterialExpressionOneMinus", None)
        if flatten_class is None or one_minus_class is None:
            return self._function_multiply(function_asset, create_expression, editing_library, normal, "", strength, "", x, y, report)
        one_minus = create_expression(one_minus_class, x - 120, y)
        editing_library.connect_material_expressions(strength, "", one_minus, "")
        flatten = create_expression(flatten_class, x, y)
        editing_library.connect_material_expressions(normal, "", flatten, "Normal")
        editing_library.connect_material_expressions(one_minus, "", flatten, "Flatness")
        return flatten

    def _material_function_expression_creator(self, editing_library, function_asset, report, asset_path):
        function_creator = getattr(editing_library, "create_material_expression_in_function", None)
        if function_creator is not None:
            return lambda expression_class, x, y: function_creator(function_asset, expression_class, x, y)
        fallback_creator = getattr(editing_library, "create_material_expression", None)
        if fallback_creator is None:
            report["issues"].append("当前 UE Python API 缺少 Material Function 表达式创建接口：{0}".format(asset_path))
            return None
        report["issues"].append("当前 UE Python API 缺少 create_material_expression_in_function，已使用通用节点 API 作为兼容兜底：{0}".format(asset_path))
        return lambda expression_class, x, y: fallback_creator(function_asset, expression_class, x, y)

    def _configure_function_input_type(self, expression, input_name):
        input_type = self._function_input_type(input_name)
        if input_type is not None:
            set_unreal_property(expression, "input_type", input_type)

    def _function_input_type(self, input_name):
        enum_class = getattr(self.unreal, "FunctionInputType", None)
        if enum_class is None:
            return None
        scalar_names = {"UVTiling", "NormalStrength", "MaskContrast", "EmissiveIntensity"}
        vector2_names = {"UV"}
        vector4_names = {"EmissiveTint"}
        if input_name in scalar_names:
            candidates = ["FUNCTION_INPUT_SCALAR", "FUNCTION_INPUT_SCALAR1"]
        elif input_name in vector2_names:
            candidates = ["FUNCTION_INPUT_VECTOR2"]
        elif input_name in vector4_names:
            candidates = ["FUNCTION_INPUT_VECTOR4"]
        else:
            candidates = ["FUNCTION_INPUT_VECTOR3"]
        for name in candidates:
            value = getattr(enum_class, name, None)
            if value is not None:
                return value
        return None

    def _reset_generated_material_function(self, function_asset, editing_library, report):
        function_reset = getattr(editing_library, "delete_all_material_expressions_in_function", None)
        if function_reset is not None:
            function_reset(function_asset)
            return
        fallback_reset = getattr(editing_library, "delete_all_material_expressions", None)
        if fallback_reset is not None:
            fallback_reset(function_asset)
            report["issues"].append("当前 UE Python API 缺少 delete_all_material_expressions_in_function，已使用通用清理 API 作为兼容兜底。")
            return
        report["issues"].append("当前 UE Python API 缺少 Material Function 节点清理 API，旧接口节点可能仍留在资产中。")

    def _configure_material_network(self, material_asset, asset_plan):
        plan = asset_plan.get("material_network_plan", {})
        report = {
            "status": "skipped",
            "material_path": asset_plan.get("path", ""),
            "material_network_status": plan.get("status", MATERIAL_STATUS_GENERATED),
            "api_usage": {
                "create_node": "",
                "delete_nodes": "",
                "connect_property": "",
                "connect_expression": "",
                "recompile": "",
                "save": "EditorAssetLibrary.save_asset",
            },
            "parameters": list(plan.get("texture_parameters", [])),
            "scalar_parameters": list(plan.get("scalar_parameters", [])),
            "vector_parameters": dict(plan.get("vector_parameters", {})),
            "nodes": list(plan.get("nodes", [])),
            "connections": list(plan.get("connections", [])),
            "channel_semantics": dict(plan.get("channel_semantics", {})),
            "supports_virtual_texture_sampling": bool(plan.get("supports_virtual_texture_sampling", False)),
            "created_nodes": [],
            "comment_layout_validation": {
                "status": "skipped",
                "blocks": [],
                "blocks_overlap": False,
                "issues": [],
            },
            "connected": [],
            "deleted_expression_count": 0,
            "issues": [],
            "next_action": "",
        }
        editing_library = getattr(self.unreal, "MaterialEditingLibrary", None)
        if editing_library is None:
            report["status"] = "warning"
            report["issues"].append("当前 UE Python API 不可用 MaterialEditingLibrary，无法自动生成母材质节点网络。")
            report["next_action"] = "请在真实 UE 5.6 中确认 Python 插件和 MaterialEditingLibrary 可用后重新执行 Bootstrap。"
            return report

        self._reset_generated_material_network(material_asset, editing_library, report)

        created_by_parameter = {}
        for index, node in enumerate(plan.get("nodes", [])):
            expression_class = self._texture_expression_class(node, report)
            if expression_class is None:
                continue
            if not hasattr(editing_library, "create_material_expression"):
                report["issues"].append("当前 UE Python API 缺少 create_material_expression，无法创建参数节点。")
                continue
            node_x, node_y = self._texture_node_position(node.get("parameter", ""), index)
            expression = editing_library.create_material_expression(material_asset, expression_class, node_x, node_y)
            report["api_usage"]["create_node"] = "MaterialEditingLibrary.create_material_expression"
            self._configure_texture_expression(expression, node, report)
            created_by_parameter[node.get("parameter", "")] = expression
            report["created_nodes"].append(
                {
                    "parameter": node.get("parameter", ""),
                    "node_type": node.get("node_type", ""),
                    "expression_class": "MaterialExpressionTextureSampleParameter2D",
                    "sampler_type": node.get("sampler_type", ""),
                    "group": self._parameter_group(node.get("parameter", "")),
                    "sort_priority": self._parameter_sort_priority(node.get("parameter", "")),
                    "x": node_x,
                    "y": node_y,
                }
            )
        self._add_material_graph_comments(material_asset, editing_library, report, plan)

        if self._connect_enhanced_pbr_network(material_asset, editing_library, created_by_parameter, report, plan):
            self._finalize_comment_layout_validation(report)
            if hasattr(editing_library, "recompile_material"):
                editing_library.recompile_material(material_asset)
                report["api_usage"]["recompile"] = "MaterialEditingLibrary.recompile_material"
            report["status"] = "warning" if report["issues"] else "success"
            if report["issues"]:
                report["next_action"] = "打开母材质检查参数化 PBR 节点、VT 采样节点和连接。"
            return report

        for connection in plan.get("connections", []):
            expression = created_by_parameter.get(connection.get("parameter", ""))
            if not expression:
                report["issues"].append("缺少材质节点，无法连接参数：{0}".format(connection.get("parameter", "")))
                continue
            material_property = self._material_property(connection.get("material_property", ""))
            if material_property is None:
                report["issues"].append("当前 UE Python API 缺少材质属性枚举：{0}".format(connection.get("material_property", "")))
                continue
            if hasattr(editing_library, "connect_material_property"):
                editing_library.connect_material_property(expression, connection.get("output", ""), material_property)
                report["api_usage"]["connect_property"] = "MaterialEditingLibrary.connect_material_property"
                report["connected"].append(connection)
            elif hasattr(editing_library, "connect_material_expressions"):
                report["api_usage"]["connect_expression"] = "MaterialEditingLibrary.connect_material_expressions"
                report["issues"].append(
                    "当前 UE Python API 只有 connect_material_expressions，缺少 connect_material_property；无法把 {0}.{1} 直接连接到 {2}。".format(
                        connection.get("parameter", ""),
                        connection.get("output", ""),
                        connection.get("material_property", ""),
                    )
                )
            else:
                report["issues"].append("当前 UE Python API 不支持 connect_material_property / connect_material_expressions。")

        if hasattr(editing_library, "recompile_material"):
            editing_library.recompile_material(material_asset)
            report["api_usage"]["recompile"] = "MaterialEditingLibrary.recompile_material"
        self._finalize_comment_layout_validation(report)
        report["status"] = "warning" if report["issues"] else "success"
        if report["issues"]:
            report["next_action"] = "打开母材质检查 BaseColor、Normal、ARM 参数节点和连接，必要时手动修复后重新验收。"
        return report

    def _connect_enhanced_pbr_network(self, material_asset, editing_library, textures, report, plan=None):
        if not hasattr(editing_library, "connect_material_expressions"):
            return False
        multiply_class = getattr(self.unreal, "MaterialExpressionMultiply", None)
        scalar_class = getattr(self.unreal, "MaterialExpressionScalarParameter", None)
        vector_class = getattr(self.unreal, "MaterialExpressionVectorParameter", None)
        if multiply_class is None or scalar_class is None:
            return False

        handled = False
        self._connect_shared_uvs(material_asset, editing_library, textures, scalar_class, report)

        base_color = textures.get("BaseColor")
        imperfection = textures.get("ImperfectionMask")
        imperfection_intensity = None
        if base_color:
            output = base_color
            tint = self._create_parameter_expression(material_asset, editing_library, vector_class, "BaseColorTint", -620, -380, report, "VectorParameter", [1.0, 1.0, 1.0, 1.0]) if vector_class else None
            if tint:
                output = self._multiply(material_asset, editing_library, output, "RGB", tint, "", -380, -350, report)
            intensity = self._create_parameter_expression(material_asset, editing_library, scalar_class, "BaseColorIntensity", -620, -260, report, "ScalarParameter", 1.0)
            if intensity:
                output = self._multiply(material_asset, editing_library, output, "", intensity, "", -120, -300, report)
            if imperfection:
                imperfection_intensity = self._create_parameter_expression(material_asset, editing_library, scalar_class, "ImperfectionIntensity", -620, 1040, report, "ScalarParameter", 0.0)
                grime = self._multiply(material_asset, editing_library, imperfection, "R", imperfection_intensity, "", -360, 1040, report) if imperfection_intensity else None
                clean = self._one_minus(material_asset, editing_library, grime, "", -120, 1040, report) if grime else None
                if clean:
                    output = self._multiply(material_asset, editing_library, output, "", clean, "", 180, -260, report)
            self._connect_property(editing_library, output, "", "base_color", report)
            handled = True

        normal = textures.get("Normal")
        if normal:
            strength = self._create_parameter_expression(material_asset, editing_library, scalar_class, "NormalStrength", -620, 120, report, "ScalarParameter", 1.0)
            normal_output, normal_output_name = self._normal_strength(material_asset, editing_library, normal, strength, -360, 120, report)
            self._connect_property(editing_library, normal_output, normal_output_name, "normal", report)
            handled = True

        packed = textures.get("ARM") or textures.get("ORM")
        if packed:
            ao_intensity = self._create_parameter_expression(material_asset, editing_library, scalar_class, "AOIntensity", -620, 500, report, "ScalarParameter", 1.0)
            roughness_intensity = self._create_parameter_expression(material_asset, editing_library, scalar_class, "RoughnessIntensity", -620, 610, report, "ScalarParameter", 1.0)
            metallic_intensity = self._create_parameter_expression(material_asset, editing_library, scalar_class, "MetallicIntensity", -620, 720, report, "ScalarParameter", 1.0)
            specular = self._create_parameter_expression(material_asset, editing_library, scalar_class, "Specular", -620, 830, report, "ScalarParameter", 0.5)
            ao = self._multiply(material_asset, editing_library, packed, "R", ao_intensity, "", -360, 500, report) if ao_intensity else packed
            roughness = self._multiply(material_asset, editing_library, packed, "G", roughness_intensity, "", -360, 610, report) if roughness_intensity else packed
            metallic = self._multiply(material_asset, editing_library, packed, "B", metallic_intensity, "", -360, 720, report) if metallic_intensity else packed
            self._connect_property(editing_library, ao, "" if ao is not packed else "R", "ambient_occlusion", report)
            self._connect_property(editing_library, roughness, "" if roughness is not packed else "G", "roughness", report)
            self._connect_property(editing_library, metallic, "" if metallic is not packed else "B", "metallic", report)
            if specular:
                self._connect_property(editing_library, specular, "", "specular", report)
            handled = True

        if imperfection:
            if imperfection_intensity is None:
                self._create_parameter_expression(material_asset, editing_library, scalar_class, "ImperfectionIntensity", -620, 1040, report, "ScalarParameter", 0.0)
            handled = True

        height = textures.get("Height")
        if height:
            self._create_parameter_expression(material_asset, editing_library, scalar_class, "HeightScale", -620, 2500, report, "ScalarParameter", 0.03)
            self._create_parameter_expression(material_asset, editing_library, scalar_class, "POMMinSteps", -620, 2580, report, "ScalarParameter", 8.0)
            self._create_parameter_expression(material_asset, editing_library, scalar_class, "POMMaxSteps", -620, 2660, report, "ScalarParameter", 32.0)
            self._create_parameter_expression(material_asset, editing_library, scalar_class, "POMTemporalAAStepMultiplier", -620, 2740, report, "ScalarParameter", 1.0)
            handled = True

        emissive = textures.get("Emissive")
        if emissive:
            output = emissive
            tint = self._create_parameter_expression(material_asset, editing_library, vector_class, "EmissiveTint", -620, 1420, report, "VectorParameter", [1.0, 1.0, 1.0, 1.0]) if vector_class else None
            if tint:
                output = self._multiply(material_asset, editing_library, output, "RGB", tint, "", -360, 1420, report)
            intensity = self._create_parameter_expression(material_asset, editing_library, scalar_class, "EmissiveIntensity", -620, 1540, report, "ScalarParameter", 1.0)
            if intensity:
                output = self._multiply(material_asset, editing_library, output, "", intensity, "", -100, 1480, report)
            off = self._constant(material_asset, editing_library, 0.0, -100, 1620, report, "UseEmissiveOffValue")
            output = self._static_switch_parameter(
                material_asset,
                editing_library,
                "UseEmissive",
                output,
                "",
                off,
                "",
                bool((plan or {}).get("static_switches", {}).get("UseEmissive", False)),
                180,
                1580,
                report,
            )
            self._connect_property(editing_library, output, "", "emissive_color", report)
            handled = True

        opacity_switches = (plan or {}).get("static_switches", {}) or {}
        separate_opacity_mask = textures.get("OpacityMask")
        if base_color and "UseOpacityMask" in opacity_switches:
            contrast = self._create_parameter_expression(material_asset, editing_library, scalar_class, "MaskContrast", -620, 1880, report, "ScalarParameter", 1.0)
            alpha_mask = self._multiply(material_asset, editing_library, base_color, "A", contrast, "", -360, 1880, report) if contrast else base_color
            on = alpha_mask
            on_output = "" if alpha_mask is not base_color else "A"
            if separate_opacity_mask:
                separate_mask = self._multiply(material_asset, editing_library, separate_opacity_mask, "R", contrast, "", -360, 2000, report) if contrast else separate_opacity_mask
                on = self._static_switch_parameter(
                    material_asset,
                    editing_library,
                    "UseSeparateOpacityMask",
                    separate_mask,
                    "" if separate_mask is not separate_opacity_mask else "R",
                    alpha_mask,
                    on_output,
                    bool(opacity_switches.get("UseSeparateOpacityMask", False)),
                    -80,
                    2000,
                    report,
                )
                on_output = ""
            off = self._constant(material_asset, editing_library, 1.0, -360, 2180, report, "UseOpacityMaskOffValue")
            output = self._static_switch_parameter(
                material_asset,
                editing_library,
                "UseOpacityMask",
                on,
                on_output,
                off,
                "",
                bool(opacity_switches.get("UseOpacityMask", False)),
                180,
                2180,
                report,
            )
            self._connect_property(editing_library, output, "", "opacity_mask", report)
            handled = True

        opacity = textures.get("Opacity")
        if opacity:
            output = opacity
            intensity = self._create_parameter_expression(material_asset, editing_library, scalar_class, "OpacityIntensity", -620, 2300, report, "ScalarParameter", 1.0)
            if intensity:
                output = self._multiply(material_asset, editing_library, output, "R", intensity, "", -360, 2300, report)
                self._connect_property(editing_library, output, "", "opacity", report)
            else:
                self._connect_property(editing_library, output, "R", "opacity", report)
            handled = True

        if "UseSubsurface" in (plan or {}).get("static_switches", {}):
            tint = self._create_parameter_expression(material_asset, editing_library, vector_class, "SubsurfaceTint", -620, 2540, report, "VectorParameter", [1.0, 0.78, 0.65, 1.0]) if vector_class else None
            intensity = self._create_parameter_expression(material_asset, editing_library, scalar_class, "SubsurfaceIntensity", -620, 2660, report, "ScalarParameter", 0.25)
            output = self._multiply(material_asset, editing_library, tint, "", intensity, "", -360, 2600, report) if tint and intensity else tint
            off = self._constant(material_asset, editing_library, 0.0, -360, 2780, report, "UseSubsurfaceOffValue")
            output = self._static_switch_parameter(
                material_asset,
                editing_library,
                "UseSubsurface",
                output,
                "",
                off,
                "",
                bool((plan or {}).get("static_switches", {}).get("UseSubsurface", False)),
                -80,
                2720,
                report,
            )
            if output:
                self._connect_property(editing_library, output, "", "subsurface_color", report)
            handled = True

        return handled

    def _connect_shared_uvs(self, material_asset, editing_library, textures, scalar_class, report):
        texture_coordinate_class = getattr(self.unreal, "MaterialExpressionTextureCoordinate", None)
        if texture_coordinate_class is None:
            return None
        texture_nodes = [node for node in textures.values() if node is not None]
        if not texture_nodes:
            return None
        texcoord = editing_library.create_material_expression(material_asset, texture_coordinate_class, -1120, -780)
        tiling = self._create_parameter_expression(material_asset, editing_library, scalar_class, "UVTiling", -900, -760, report, "ScalarParameter", 1.0)
        uv_output = texcoord
        if tiling:
            uv_output = self._multiply(material_asset, editing_library, texcoord, "", tiling, "", -700, -760, report)
        for texture in texture_nodes:
            editing_library.connect_material_expressions(uv_output, "", texture, "UVs")
        report["api_usage"]["connect_expression"] = "MaterialEditingLibrary.connect_material_expressions"
        report["created_nodes"].append({"parameter": "", "node_type": "TextureCoordinate", "x": -1120, "y": -780})
        return uv_output

    def _texture_node_position(self, parameter, index):
        positions = {
            "BaseColor": (-980, -340),
            "Normal": (-980, 80),
            "ARM": (-980, 500),
            "ORM": (-980, 500),
            "ImperfectionMask": (-980, 1020),
            "Emissive": (-980, 1420),
            "OpacityMask": (-980, 1900),
            "Opacity": (-980, 2260),
            "Height": (-980, 2500),
        }
        return positions.get(parameter, (-980, -240 + index * 260))

    def _add_material_graph_comments(self, material_asset, editing_library, report, plan):
        comment_class = getattr(self.unreal, "MaterialExpressionComment", None)
        if comment_class is None or not hasattr(editing_library, "create_material_expression"):
            return
        comments = list(GRAPH_COMMENT_BLOCKS)
        if "UseSubsurface" in (plan.get("static_switches", {}) or {}):
            comments.append(
                {
                    "id": "AF_08_Subsurface",
                    "x": -700,
                    "y": 1960,
                    "size_x": 1560,
                    "size_y": 400,
                    "font_size": 16,
                    "text": "AF 08 次表面 / Subsurface\n角色皮肤预览；硬表面默认关闭。",
                    "color": (0.98, 0.58, 0.72, 0.40),
                    "parameters": ["SubsurfaceTint", "SubsurfaceIntensity", "UseSubsurface", "UseSubsurfaceOffValue"],
                }
            )
            comments[-1].update(
                {
                    "x": -1080,
                    "y": 2460,
                    "size_x": 1600,
                    "size_y": 420,
                    "font_size": 20,
                    "text": "AF 08 次表面",
                    "color": (0.98, 0.58, 0.72, 0.30),
                }
            )
        comment_readbacks = []
        native_comment_repair_available = self._material_comment_library() is not None
        for comment in comments:
            x, y, size_x, size_y, text, color = self._comment_block_values(comment)
            comment_id, covered_parameters = self._comment_block_metadata(comment)
            font_size = self._comment_block_font_size(comment)
            expression = editing_library.create_material_expression(material_asset, comment_class, x, y)
            written_properties = {}
            self._set_comment_property(expression, ("text", "Text"), text, report, text, written_properties=written_properties, key="text")
            self._set_comment_property(expression, ("desc", "Desc"), text, report, text, written_properties=written_properties, key="desc")
            self._set_comment_property(
                expression,
                ("SizeX", "size_x"),
                size_x,
                report,
                text,
                required=not native_comment_repair_available,
                written_properties=written_properties,
                key="size_x",
            )
            self._set_comment_property(
                expression,
                ("SizeY", "size_y"),
                size_y,
                report,
                text,
                required=not native_comment_repair_available,
                written_properties=written_properties,
                key="size_y",
            )
            self._set_comment_property(expression, ("font_size", "FontSize"), font_size, report, text, written_properties=written_properties, key="font_size")
            self._set_comment_property(expression, ("comment_color", "CommentColor"), self._linear_color_value(color), report, text, written_properties=written_properties, key="comment_color")
            self._set_comment_property(expression, ("material_expression_editor_x", "MaterialExpressionEditorX"), x, report, text, required=False, written_properties=written_properties, key="x")
            self._set_comment_property(expression, ("material_expression_editor_y", "MaterialExpressionEditorY"), y, report, text, required=False, written_properties=written_properties, key="y")
            self._set_comment_property(expression, ("comment_bubble_visible", "bCommentBubbleVisible"), False, report, text, required=False, written_properties=written_properties, key="comment_bubble_visible")
            self._set_comment_property(
                expression,
                ("comment_bubble_visible_in_details_panel", "bCommentBubbleVisible_InDetailsPanel"),
                False,
                report,
                text,
                required=False,
                written_properties=written_properties,
                key="comment_bubble_visible_in_details_panel",
            )
            self._set_comment_property(expression, ("color_comment_bubble", "bColorCommentBubble"), False, report, text, required=False, written_properties=written_properties, key="color_comment_bubble")
            self._set_comment_property(expression, ("group_mode", "bGroupMode"), True, report, text, required=False, written_properties=written_properties, key="group_mode")
            visible_text = self._first_comment_property(expression, ("text", "Text"), "")
            if not visible_text:
                report["issues"].append("母材质注释块写入失败：{0}".format(text.splitlines()[0]))
            parameter_groups = self._comment_parameter_groups(covered_parameters)
            readback = self._comment_readback(expression)
            node_report = {
                "parameter": "",
                "node_type": "MaterialExpressionComment",
                "expression_class": "MaterialExpressionComment",
                "description": text,
                "comment_text": text,
                "comment_id": comment_id,
                "comment_color": list(color),
                "font_size": font_size,
                "x": x,
                "y": y,
                "size_x": size_x,
                "size_y": size_y,
                "bounds": {"x": x, "y": y, "width": size_x, "height": size_y},
                "covered_parameters": covered_parameters,
                "covered_parameter_groups": sorted(set(parameter_groups.values())),
                "parameter_groups": parameter_groups,
                "comment_bubble_visible": False,
                "group_mode": True,
                "written_properties": written_properties,
                "readback": readback,
            }
            report["created_nodes"].append(node_report)
            layout_report = {
                "id": comment_id,
                "bounds": {"x": x, "y": y, "width": size_x, "height": size_y},
                "font_size": font_size,
                "covered_parameters": covered_parameters,
                "covered_parameter_groups": sorted(set(parameter_groups.values())),
                "parameter_groups": parameter_groups,
                "readback": readback,
            }
            report.setdefault("comment_layout_validation", {}).setdefault("blocks", []).append(layout_report)
            comment_readbacks.append((expression, node_report, layout_report))
        self._repair_material_graph_comments_with_native_library(material_asset, report)
        self._refresh_comment_readbacks(comment_readbacks)

    def _repair_material_graph_comments_with_native_library(self, material_asset, report):
        library = self._material_comment_library()
        repair = getattr(library, "repair_asset_forge_comment_blocks", None) if library else None
        if repair is None:
            report.setdefault("native_comment_repair", {"status": "not_available", "repaired_count": 0})
            return 0
        try:
            repaired_count = int(repair(material_asset) or 0)
        except Exception as exc:
            report.setdefault("native_comment_repair", {"status": "error", "repaired_count": 0, "message": str(exc)})
            report.setdefault("issues", []).append("Native material comment repair failed: {0}".format(exc))
            return 0
        report.setdefault("native_comment_repair", {"status": "success", "repaired_count": repaired_count})
        return repaired_count

    def _material_comment_library(self):
        for name in ("AssetForgeEditorMaterialCommentLibrary", "AssetForgeMaterialCommentLibrary"):
            library = getattr(self.unreal, name, None)
            if library is not None:
                return library
        return None

    def _refresh_comment_readbacks(self, comment_readbacks):
        for expression, node_report, layout_report in comment_readbacks:
            readback = self._comment_readback(expression)
            node_report["readback"] = readback
            layout_report["readback"] = readback
            size_x = int(readback.get("size_x") or node_report.get("size_x") or 0)
            size_y = int(readback.get("size_y") or node_report.get("size_y") or 0)
            if size_x > 0:
                node_report["size_x"] = size_x
                node_report.setdefault("bounds", {})["width"] = size_x
                layout_report.setdefault("bounds", {})["width"] = size_x
            if size_y > 0:
                node_report["size_y"] = size_y
                node_report.setdefault("bounds", {})["height"] = size_y
                layout_report.setdefault("bounds", {})["height"] = size_y

    def _comment_block_values(self, comment):
        if isinstance(comment, dict):
            return (
                int(comment.get("x", 0)),
                int(comment.get("y", 0)),
                int(comment.get("size_x", 600)),
                int(comment.get("size_y", 220)),
                comment.get("text", ""),
                tuple(comment.get("color", (0.2, 0.45, 0.95, 0.35))),
            )
        values = list(comment)
        if len(values) == 5:
            values.append((0.2, 0.45, 0.95, 0.35))
        return values[0], values[1], values[2], values[3], values[4], tuple(values[5])

    def _comment_block_metadata(self, comment):
        if isinstance(comment, dict):
            return comment.get("id", ""), list(comment.get("parameters", []))
        return "", []

    def _comment_block_font_size(self, comment):
        if isinstance(comment, dict):
            return int(comment.get("font_size", 18))
        return 18

    def _finalize_comment_layout_validation(self, report):
        layout = report.setdefault(
            "comment_layout_validation",
            {"status": "skipped", "blocks": [], "blocks_overlap": False, "issues": []},
        )
        blocks = list(layout.get("blocks", []))
        issues = []
        blocks_overlap = False
        for index, block in enumerate(blocks):
            for other in blocks[index + 1 :]:
                if self._bounds_overlap(block.get("bounds", {}), other.get("bounds", {})):
                    blocks_overlap = True
                    issues.append("Comment blocks overlap: {0} / {1}".format(block.get("id", ""), other.get("id", "")))

        parameter_nodes = {}
        for node in report.get("created_nodes", []):
            parameter = node.get("parameter", "")
            if parameter and "x" in node and "y" in node:
                parameter_nodes[parameter] = node
        for block in blocks:
            present = []
            outside = []
            bounds = block.get("bounds", {})
            for parameter in block.get("covered_parameters", []):
                node = parameter_nodes.get(parameter)
                if not node:
                    continue
                present.append(parameter)
                if not self._point_inside_bounds(node.get("x", 0), node.get("y", 0), bounds):
                    outside.append(parameter)
            block["covered_parameters_present"] = present
            if outside:
                issues.append("Comment block {0} does not cover: {1}".format(block.get("id", ""), ", ".join(outside)))

        layout["blocks"] = blocks
        layout["blocks_overlap"] = blocks_overlap
        layout["issues"] = issues
        layout["status"] = "pass" if not issues and blocks else "skipped" if not blocks else "error"
        for issue in issues:
            report.setdefault("issues", []).append("Comment layout validation: {0}".format(issue))

    def _bounds_overlap(self, left, right):
        return (
            int(left.get("x", 0)) < int(right.get("x", 0)) + int(right.get("width", 0))
            and int(left.get("x", 0)) + int(left.get("width", 0)) > int(right.get("x", 0))
            and int(left.get("y", 0)) < int(right.get("y", 0)) + int(right.get("height", 0))
            and int(left.get("y", 0)) + int(left.get("height", 0)) > int(right.get("y", 0))
        )

    def _point_inside_bounds(self, x, y, bounds):
        return (
            int(bounds.get("x", 0)) <= int(x) <= int(bounds.get("x", 0)) + int(bounds.get("width", 0))
            and int(bounds.get("y", 0)) <= int(y) <= int(bounds.get("y", 0)) + int(bounds.get("height", 0))
        )

    def _comment_parameter_groups(self, parameters):
        return dict((parameter, self._parameter_group(parameter)) for parameter in parameters)

    def _comment_readback(self, expression):
        return {
            "text": self._first_comment_property(expression, ("text", "Text"), ""),
            "size_x": self._first_comment_property(expression, ("size_x", "SizeX"), 0),
            "size_y": self._first_comment_property(expression, ("size_y", "SizeY"), 0),
            "font_size": self._first_comment_property(expression, ("font_size", "FontSize"), 0),
            "comment_color": self._first_comment_property(expression, ("comment_color", "CommentColor"), None),
            "group_mode": self._first_comment_property(expression, ("group_mode", "bGroupMode"), False),
        }

    def _first_comment_property(self, expression, names, default=None):
        for name in names:
            value = get_unreal_property(expression, name, None)
            if value is not None:
                return value
        return default

    def _set_comment_property(self, expression, names, value, report=None, comment_text="", required=True, written_properties=None, key=""):
        for name in names:
            if self._set_editor_property_verified(expression, name, value):
                if written_properties is not None:
                    written_properties[key or name] = name
                return True
        if required and report is not None:
            report["issues"].append("母材质注释属性写入失败：{0} -> {1}".format((comment_text or "").splitlines()[0], "/".join(names)))
        return False

    def _set_editor_property_verified(self, expression, name, value):
        setter = getattr(expression, "set_editor_property", None)
        getter = getattr(expression, "get_editor_property", None)
        if setter is not None:
            try:
                setter(name, value)
                if getter is None:
                    return True
                try:
                    if self._editor_property_matches(getter(name), value):
                        return True
                except Exception:
                    return True
            except Exception:
                pass
        try:
            setattr(expression, name, value)
            actual = getattr(expression, name)
            return self._editor_property_matches(actual, value)
        except Exception:
            pass
        if set_unreal_property(expression, name, value):
            try:
                return self._editor_property_matches(get_unreal_property(expression, name, None), value)
            except Exception:
                return True
        return False

    def _editor_property_matches(self, actual, expected):
        if isinstance(expected, bool):
            return bool(actual) is expected
        if isinstance(expected, int) and not isinstance(expected, bool):
            try:
                return int(actual) == expected
            except Exception:
                return False
        if isinstance(expected, float):
            try:
                return abs(float(actual) - expected) < 0.0001
            except Exception:
                return False
        if isinstance(expected, str):
            return actual == expected
        return actual is not None

    def _create_parameter_expression(self, material_asset, editing_library, expression_class, name, x, y, report, node_type, default_value=None):
        if expression_class is None:
            return None
        expression = editing_library.create_material_expression(material_asset, expression_class, x, y)
        set_unreal_property(expression, "parameter_name", name)
        group = self._parameter_group(name)
        self._set_parameter_group(expression, group)
        self._set_parameter_sort_priority(expression, self._parameter_sort_priority(name))
        self._annotate_expression(expression, self._parameter_description(name))
        if default_value is not None:
            set_unreal_property(expression, "default_value", self._parameter_default_value(node_type, default_value))
        report["created_nodes"].append(
            {
                "parameter": name,
                "node_type": node_type,
                "group": group,
                "sort_priority": self._parameter_sort_priority(name),
                "x": x,
                "y": y,
            }
        )
        return expression

    def _parameter_default_value(self, node_type, value):
        if node_type == "VectorParameter":
            return self._linear_color_value(value)
        return value

    def _linear_color_value(self, value):
        color_class = getattr(self.unreal, "LinearColor", None)
        if color_class is None:
            return value
        if isinstance(value, dict):
            return color_class(
                float(value.get("r", value.get("R", 1.0))),
                float(value.get("g", value.get("G", 1.0))),
                float(value.get("b", value.get("B", 1.0))),
                float(value.get("a", value.get("A", 1.0))),
            )
        if isinstance(value, (list, tuple)):
            values = list(value) + [1.0, 1.0, 1.0, 1.0]
            return color_class(float(values[0]), float(values[1]), float(values[2]), float(values[3]))
        return value

    def _multiply(self, material_asset, editing_library, left, left_output, right, right_output, x, y, report):
        multiply_class = getattr(self.unreal, "MaterialExpressionMultiply", None)
        if multiply_class is None or right is None:
            return left
        node = editing_library.create_material_expression(material_asset, multiply_class, x, y)
        self._annotate_expression(node, "数学节点：将贴图数据与可暴露参数相乘，用于强度、染色或遮罩调节。")
        editing_library.connect_material_expressions(left, left_output, node, "A")
        editing_library.connect_material_expressions(right, right_output, node, "B")
        report["api_usage"]["connect_expression"] = "MaterialEditingLibrary.connect_material_expressions"
        report["created_nodes"].append({"parameter": "", "node_type": "Multiply", "x": x, "y": y})
        return node

    def _one_minus(self, material_asset, editing_library, expression, output_name, x, y, report):
        one_minus_class = getattr(self.unreal, "MaterialExpressionOneMinus", None)
        if one_minus_class is None or expression is None:
            return None
        node = editing_library.create_material_expression(material_asset, one_minus_class, x, y)
        self._annotate_expression(node, "数学节点：反转瑕疵遮罩，让白色脏污区域能压暗预览表面。")
        editing_library.connect_material_expressions(expression, output_name, node, "")
        self._set_expression_input(node, ("input", "Input"), expression, output_name)
        report["api_usage"]["connect_expression"] = "MaterialEditingLibrary.connect_material_expressions"
        report["created_nodes"].append({"parameter": "", "node_type": "OneMinus", "x": x, "y": y})
        return node

    def _constant(self, material_asset, editing_library, value, x, y, report, name="AFConstantValue"):
        scalar_class = getattr(self.unreal, "MaterialExpressionScalarParameter", None)
        if scalar_class is None:
            return None
        node = self._create_parameter_expression(material_asset, editing_library, scalar_class, name, x, y, report, "ScalarParameter", float(value))
        self._annotate_expression(node, "可连接的安全默认值，用于关闭可选分支时保持材质输出稳定。")
        return node

    def _static_switch_parameter(self, material_asset, editing_library, name, true_expr, true_output, false_expr, false_output, default_value, x, y, report):
        lerp_class = getattr(self.unreal, "MaterialExpressionLinearInterpolate", None)
        scalar_class = getattr(self.unreal, "MaterialExpressionScalarParameter", None)
        if lerp_class is None or scalar_class is None or true_expr is None or false_expr is None:
            return true_expr if default_value else false_expr
        alpha = self._create_parameter_expression(
            material_asset,
            editing_library,
            scalar_class,
            name,
            x,
            y - 120,
            report,
            "ScalarParameter",
            1.0 if bool(default_value) else 0.0,
        )
        node = editing_library.create_material_expression(material_asset, lerp_class, x, y)
        if node is None:
            return true_expr if default_value else false_expr
        self._annotate_expression(node, "0/1 分支开关。用 Lerp 保持 UE Python 生成稳定，实例参数仍可控制开关效果。")
        editing_library.connect_material_expressions(false_expr, false_output, node, "A")
        editing_library.connect_material_expressions(true_expr, true_output, node, "B")
        if alpha is not None:
            editing_library.connect_material_expressions(alpha, "", node, "Alpha")
        report["api_usage"]["connect_expression"] = "MaterialEditingLibrary.connect_material_expressions"
        report["created_nodes"].append({"parameter": "", "node_type": "LinearInterpolate", "x": x, "y": y})
        return node

    def _set_expression_input(self, target_expression, property_names, source_expression, source_output, input_name=""):
        for property_name in property_names:
            expression_input = None
            if hasattr(target_expression, "get_editor_property"):
                try:
                    expression_input = target_expression.get_editor_property(property_name)
                except Exception:
                    expression_input = None
            if expression_input is None:
                expression_input = getattr(target_expression, property_name, None)
            if expression_input is None:
                continue
            set_ok = set_unreal_property(expression_input, "expression", source_expression)
            set_ok = set_unreal_property(expression_input, "output_index", self._expression_output_index(source_output)) and set_ok
            if input_name:
                set_unreal_property(expression_input, "input_name", input_name)
            set_ok = set_unreal_property(target_expression, property_name, expression_input) and set_ok
            if set_ok:
                return True
        return False

    def _expression_output_index(self, output_name):
        output_key = str(output_name or "").strip().lower()
        return {
            "": 0,
            "rgb": 0,
            "rgba": 0,
            "r": 1,
            "g": 2,
            "b": 3,
            "a": 4,
        }.get(output_key, 0)

    def _normal_strength(self, material_asset, editing_library, normal, strength, x, y, report):
        if strength is None:
            return normal, "RGB"
        flatten_class = getattr(self.unreal, "MaterialExpressionFlattenNormal", None)
        one_minus_class = getattr(self.unreal, "MaterialExpressionOneMinus", None)
        if flatten_class is None or one_minus_class is None:
            return self._multiply(material_asset, editing_library, normal, "RGB", strength, "", x, y, report), ""
        one_minus = editing_library.create_material_expression(material_asset, one_minus_class, x - 120, y)
        editing_library.connect_material_expressions(strength, "", one_minus, "")
        flatten = editing_library.create_material_expression(material_asset, flatten_class, x, y)
        editing_library.connect_material_expressions(normal, "RGB", flatten, "Normal")
        editing_library.connect_material_expressions(one_minus, "", flatten, "Flatness")
        report["api_usage"]["connect_expression"] = "MaterialEditingLibrary.connect_material_expressions"
        report["created_nodes"].append({"parameter": "", "node_type": "OneMinus"})
        report["created_nodes"].append({"parameter": "", "node_type": "FlattenNormal"})
        return flatten, ""

    def _connect_property(self, editing_library, expression, output, property_name, report):
        material_property = self._material_property(property_name)
        if material_property is None:
            report["issues"].append("当前 UE Python API 缺少材质属性枚举：{0}".format(property_name))
            return
        editing_library.connect_material_property(expression, output, material_property)
        report["api_usage"]["connect_property"] = "MaterialEditingLibrary.connect_material_property"
        report["connected"].append({"parameter": "", "output": output, "material_property": property_name})

    def _reset_generated_material_network(self, material_asset, editing_library, report):
        existing_expressions = self._material_expressions(material_asset)
        if hasattr(editing_library, "delete_all_material_expressions"):
            editing_library.delete_all_material_expressions(material_asset)
            report["api_usage"]["delete_nodes"] = "MaterialEditingLibrary.delete_all_material_expressions"
            report["deleted_expression_count"] = len(existing_expressions)
            self._delete_stale_material_expressions(material_asset, editing_library, existing_expressions, report)
            return
        report["issues"].append("当前 UE Python API 缺少 delete_all_material_expressions，旧的 Asset Forge 材质节点可能仍需手动清理。")

    def _material_expressions(self, material_asset):
        if not material_asset:
            return []
        if hasattr(material_asset, "get_editor_property"):
            try:
                expressions = list(material_asset.get_editor_property("expressions") or [])
                if expressions:
                    return expressions
            except Exception:
                pass
        expressions = list(getattr(material_asset, "expressions", []) or [])
        if expressions:
            return expressions
        return self._material_expressions_from_object_iterator(material_asset)

    def _material_expressions_from_object_iterator(self, material_asset):
        object_iterator = getattr(self.unreal, "ObjectIterator", None)
        if object_iterator is None:
            return []
        material_path = self._object_path_name(material_asset)
        if not material_path:
            return []
        expressions = []
        try:
            iterator = object_iterator()
        except Exception:
            return []
        for candidate in iterator:
            try:
                candidate_class = candidate.get_class().get_name()
            except Exception:
                candidate_class = candidate.__class__.__name__
            if not str(candidate_class).startswith("MaterialExpression"):
                continue
            outer = getattr(candidate, "get_outer", lambda: None)()
            if self._object_path_name(outer) == material_path:
                expressions.append(candidate)
        return expressions

    def _object_path_name(self, obj):
        if obj is None:
            return ""
        method = getattr(obj, "get_path_name", None)
        if method is not None:
            try:
                return str(method())
            except Exception:
                pass
        return str(getattr(obj, "path_name", ""))

    def _delete_stale_material_expressions(self, material_asset, editing_library, expressions, report):
        delete_one = getattr(editing_library, "delete_material_expression", None)
        if delete_one is None or not expressions:
            return
        deleted = 0
        for expression in expressions:
            try:
                delete_one(material_asset, expression)
                deleted += 1
            except Exception:
                pass
        if deleted:
            report["api_usage"]["delete_nodes"] = "MaterialEditingLibrary.delete_all_material_expressions + delete_material_expression"

    def _texture_expression_class(self, node, report):
        expression_class = getattr(self.unreal, "MaterialExpressionTextureSampleParameter2D", None)
        if expression_class is None:
            report["issues"].append("当前 UE Python API 缺少 TextureSampleParameter2D 节点类。")
        return expression_class

    def _configure_texture_expression(self, expression, node, report):
        set_unreal_property(expression, "parameter_name", node.get("parameter", ""))
        self._set_parameter_group(expression, self._parameter_group(node.get("parameter", "")))
        self._set_parameter_sort_priority(expression, self._parameter_sort_priority(node.get("parameter", "")))
        self._annotate_expression(expression, self._texture_description(node))
        sampler = self._sampler_type(node.get("sampler_type", ""))
        if sampler is None:
            report["issues"].append("当前 UE Python API 缺少 sampler type: {0}".format(node.get("sampler_type", "")))
            return
        set_unreal_property(expression, "sampler_type", sampler)
        default_asset_path = node.get("default_asset_path", "")
        if default_asset_path:
            texture = self._load_asset(default_asset_path)
            if texture:
                set_unreal_property(expression, "texture", texture)
                return
            report["issues"].append("未能加载安全默认贴图：{0}；请在 UE 中确认 sampler 默认资源。".format(default_asset_path))

    def _annotate_expression(self, expression, description):
        if not expression or not description:
            return
        set_unreal_property(expression, "desc", description)
        set_unreal_property(expression, "Desc", description)
        set_unreal_property(expression, "description", description)

    def _set_parameter_group(self, expression, group):
        if not expression or not group:
            return
        set_unreal_property(expression, "group", group)
        set_unreal_property(expression, "Group", group)

    def _set_parameter_sort_priority(self, expression, priority):
        if not expression:
            return
        set_unreal_property(expression, "sort_priority", priority)
        set_unreal_property(expression, "SortPriority", priority)

    def _parameter_group(self, name):
        return PARAMETER_GROUPS.get(name, "99 其他 / Advanced")

    def _parameter_sort_priority(self, name):
        return int(PARAMETER_SORT_PRIORITIES.get(name, 999))

    def _texture_description(self, node):
        parameter = node.get("parameter", "")
        usage = node.get("usage", "")
        sampler = node.get("sampler_type", "")
        fallback = "{0} 贴图采样。语义={1}；采样器={2}。".format(parameter or usage, usage, sampler)
        return PARAMETER_DESCRIPTIONS.get(parameter, fallback)

    def _parameter_description(self, name):
        return PARAMETER_DESCRIPTIONS.get(name, "Asset Forge 暴露材质参数：{0}。".format(name))

    def _default_texture_asset_path(self, usage, sampler_type):
        by_usage = {
            "base_color": "/AssetForge/Textures/T_AF_Default_BaseColor",
            "normal": "/AssetForge/Textures/T_AF_Default_Normal",
            "packed_arm": "/AssetForge/Textures/T_AF_Default_ARM",
            "opacity_mask": "/AssetForge/Textures/T_AF_Default_OpacityMask",
            "opacity": "/AssetForge/Textures/T_AF_Default_OpacityMask",
            "imperfection_mask": "/AssetForge/Textures/T_AF_Default_ImperfectionMask",
            "emissive": "/AssetForge/Textures/T_AF_Default_Emissive",
        }
        if usage in by_usage:
            return by_usage[usage]
        if sampler_type in ("normal", "virtual_normal"):
            return "/AssetForge/Textures/T_AF_Default_Normal"
        if sampler_type in ("masks", "virtual_masks"):
            return "/AssetForge/Textures/T_AF_Default_ImperfectionMask"
        return "/AssetForge/Textures/T_AF_Default_BaseColor"

    def _sampler_type(self, sampler_type):
        sampler_enum = getattr(self.unreal, "MaterialSamplerType", None)
        if sampler_enum is None:
            return None
        candidates = {
            "color": ["SAMPLERTYPE_COLOR"],
            "normal": ["SAMPLERTYPE_NORMAL"],
            "masks": ["SAMPLERTYPE_MASKS", "SAMPLERTYPE_LINEAR_COLOR", "SAMPLERTYPE_COLOR"],
            "virtual_color": ["SAMPLERTYPE_VIRTUAL_COLOR", "SAMPLERTYPE_COLOR"],
            "virtual_normal": ["SAMPLERTYPE_VIRTUAL_NORMAL", "SAMPLERTYPE_NORMAL"],
            "virtual_masks": ["SAMPLERTYPE_VIRTUAL_MASKS", "SAMPLERTYPE_VIRTUAL_LINEAR_COLOR", "SAMPLERTYPE_MASKS", "SAMPLERTYPE_LINEAR_COLOR"],
        }.get(sampler_type, [])
        for enum_name in candidates:
            value = getattr(sampler_enum, enum_name, None)
            if value is not None:
                return value
        return None

    def _virtual_sampler_type(self, sampler_type):
        return {
            "color": "virtual_color",
            "normal": "virtual_normal",
            "masks": "virtual_masks",
        }.get(sampler_type, sampler_type)

    def _material_domain(self, render_mode):
        domain_enum = getattr(self.unreal, "MaterialDomain", None)
        if domain_enum is None:
            return None
        if render_mode == "decal":
            return getattr(domain_enum, "MD_DEFERRED_DECAL", None)
        return getattr(domain_enum, "MD_SURFACE", None)

    def _material_property(self, name):
        material_property = getattr(self.unreal, "MaterialProperty", None)
        if material_property is None:
            return None
        lookup = {
            "base_color": "MP_BASE_COLOR",
            "normal": "MP_NORMAL",
            "ambient_occlusion": "MP_AMBIENT_OCCLUSION",
            "roughness": "MP_ROUGHNESS",
            "metallic": "MP_METALLIC",
            "specular": "MP_SPECULAR",
            "emissive_color": "MP_EMISSIVE_COLOR",
            "opacity_mask": "MP_OPACITY_MASK",
            "opacity": "MP_OPACITY",
            "subsurface_color": "MP_SUBSURFACE_COLOR",
        }
        enum_name = lookup.get(name)
        return getattr(material_property, enum_name, None) if enum_name else None

    def _blend_mode(self, render_mode):
        blend_enum = getattr(self.unreal, "BlendMode", None)
        if blend_enum is None:
            return None
        lookup = {
            "opaque": "BLEND_OPAQUE",
            "masked": "BLEND_MASKED",
            "translucent": "BLEND_TRANSLUCENT",
            "additive": "BLEND_ADDITIVE",
        }
        enum_name = lookup.get(render_mode)
        return getattr(blend_enum, enum_name, None) if enum_name else None

    def _asset_exists(self, asset_path):
        if self.unreal is None:
            return False
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "does_asset_exist"):
            if bool(library.does_asset_exist(asset_path)):
                return True
        disk_path = self._asset_disk_path(asset_path)
        if disk_path:
            self._scan_asset_registry_paths([self._asset_registry_path(asset_path)])
            if library and hasattr(library, "does_asset_exist"):
                if bool(library.does_asset_exist(asset_path)):
                    return True
            return True
        global_finder = getattr(self.unreal, "find_object", None)
        if global_finder is not None:
            try:
                if global_finder(None, asset_path):
                    return True
            except Exception:
                pass
        return False

    def _scan_asset_registry_paths(self, paths):
        if self.unreal is None:
            return
        clean_paths = sorted(set(path for path in paths if path))
        if not clean_paths:
            return
        registry_helpers = getattr(self.unreal, "AssetRegistryHelpers", None)
        if registry_helpers is None or not hasattr(registry_helpers, "get_asset_registry"):
            return
        try:
            registry = registry_helpers.get_asset_registry()
            if hasattr(registry, "scan_paths_synchronous"):
                registry.scan_paths_synchronous(clean_paths, True)
            if hasattr(registry, "wait_for_completion"):
                registry.wait_for_completion()
        except Exception:
            return

    def _asset_registry_path(self, asset_path):
        if not asset_path:
            return ""
        parts = asset_path.split("/")
        if len(parts) <= 2:
            return asset_path
        return "/".join(parts[:-1])

    def _can_safely_load_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "does_asset_exist") and library.does_asset_exist(asset_path):
            return True
        if self._asset_disk_path(asset_path):
            self._scan_asset_registry_paths([self._asset_registry_path(asset_path)])
            return bool(library and hasattr(library, "does_asset_exist") and library.does_asset_exist(asset_path))
        if asset_path.startswith("/Engine/"):
            return True
        return False

    def _load_asset(self, asset_path):
        if asset_path in self._asset_cache:
            return self._asset_cache[asset_path]
        if not self._can_safely_load_asset(asset_path):
            return None
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "load_asset"):
            asset = library.load_asset(asset_path)
            if asset:
                self._asset_cache[asset_path] = asset
                return asset
        global_loader = getattr(self.unreal, "load_asset", None)
        if global_loader is not None:
            asset = global_loader(asset_path)
            if asset:
                self._asset_cache[asset_path] = asset
                return asset
        return None

    def _asset_disk_path(self, asset_path):
        if not asset_path:
            return ""
        paths = getattr(self.unreal, "Paths", None)
        roots = []
        if paths is not None and asset_path.startswith("/AssetForge/"):
            plugins_dir_method = getattr(paths, "project_plugins_dir", None) or getattr(paths, "ProjectPluginsDir", None)
            if plugins_dir_method is not None:
                try:
                    roots.append(os.path.join(plugins_dir_method(), "AssetForge", "Content"))
                except Exception:
                    pass
        if paths is not None and asset_path.startswith("/Game/"):
            content_dir_method = getattr(paths, "project_content_dir", None) or getattr(paths, "ProjectContentDir", None)
            if content_dir_method is not None:
                try:
                    roots.append(content_dir_method())
                except Exception:
                    pass
        if not roots:
            return ""
        if asset_path.startswith("/AssetForge/"):
            relative_path = asset_path[len("/AssetForge/") :]
        elif asset_path.startswith("/Game/"):
            relative_path = asset_path[len("/Game/") :]
        else:
            return ""
        package_path = relative_path.replace("/", os.sep) + ".uasset"
        for root in roots:
            candidate = os.path.normpath(os.path.join(root, package_path))
            if os.path.isfile(candidate):
                return candidate
        return ""

    def _delete_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        self._close_asset_editors(asset_path)
        if library and hasattr(library, "delete_asset"):
            return bool(library.delete_asset(asset_path))
        return False

    def _close_asset_editors(self, asset_path):
        if self.unreal is None:
            return
        asset = self._load_asset(asset_path)
        if asset is None:
            return
        subsystem_class = getattr(self.unreal, "AssetEditorSubsystem", None)
        get_editor_subsystem = getattr(self.unreal, "get_editor_subsystem", None)
        if subsystem_class is None or get_editor_subsystem is None:
            return
        try:
            subsystem = get_editor_subsystem(subsystem_class)
        except Exception:
            return
        if subsystem and hasattr(subsystem, "close_all_editors_for_asset"):
            try:
                subsystem.close_all_editors_for_asset(asset)
            except Exception:
                pass

    def _save_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "save_asset"):
            library.save_asset(asset_path)

    def _parent_check(self, status, parent_material, target_asset_path, message):
        return {
            "id": "parent_material_exists",
            "label": "母材质",
            "status": status,
            "path": parent_material,
            "parent_material": parent_material,
            "target_asset_path": target_asset_path,
            "message": message,
        }

    def _factory_name(self, kind):
        return {
            ASSET_KIND_MATERIAL: "MaterialFactoryNew",
            ASSET_KIND_FUNCTION: "MaterialFunctionFactoryNew",
            ASSET_KIND_MATERIAL_INSTANCE: "MaterialInstanceConstantFactoryNew",
            ASSET_KIND_PARAMETER_COLLECTION: "MaterialParameterCollectionFactoryNew",
            ASSET_KIND_TEXTURE: "TextureFactory",
        }[kind]

    def _asset_class_name(self, kind):
        return {
            ASSET_KIND_MATERIAL: "Material",
            ASSET_KIND_FUNCTION: "MaterialFunction",
            ASSET_KIND_MATERIAL_INSTANCE: "MaterialInstanceConstant",
            ASSET_KIND_PARAMETER_COLLECTION: "MaterialParameterCollection",
            ASSET_KIND_TEXTURE: "Texture2D",
        }[kind]


def _connection(parameter, output, material_property, channel_semantic=""):
    return {
        "parameter": parameter,
        "output": output,
        "material_property": material_property,
        "channel_semantic": channel_semantic,
    }


def plan_default_material_assets():
    return UnrealMaterialAssetBootstrap().plan()


def inspect_default_material_assets():
    return UnrealMaterialAssetBootstrap().inspect_assets()


def bootstrap_default_material_assets(dry_run=False, build_showcase=False, cleanup_obsolete_assets=False):
    return UnrealMaterialAssetBootstrap().bootstrap(
        dry_run=dry_run,
        build_showcase=build_showcase,
        cleanup_obsolete_assets=cleanup_obsolete_assets,
    )
