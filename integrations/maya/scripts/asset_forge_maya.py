"""Maya module entry points for DCC AssetForge."""

from __future__ import absolute_import

import importlib
import sys

from asset_forge.shared.constants import TARGET_PLATFORM_HIGH_END_MOBILE


RELOAD_PREFIXES = (
    "asset_forge.maya.",
    "asset_forge.shared.",
)


def reload_asset_forge_modules():
    """Reload DCC AssetForge Maya/shared modules inside the same Maya Python process."""
    for module_name in sorted(list(sys.modules.keys()), reverse=True):
        if module_name.startswith(RELOAD_PREFIXES):
            importlib.reload(sys.modules[module_name])


def reload_and_show():
    """Reload project modules and open the DCC AssetForge Maya UI."""
    reload_asset_forge_modules()
    from asset_forge.maya.ui import show as show_ui

    return show_ui()


def show():
    """Open the DCC AssetForge Maya UI, reloading code so repeated tests use the latest build."""
    return reload_and_show()


def scan_selection():
    """Scan the current Maya selection."""
    reload_asset_forge_modules()

    return _pipeline_class()().scan_selection()


def export_selected(
    output_dir,
    target_platform=TARGET_PLATFORM_HIGH_END_MOBILE,
    target_path="/Game/Props",
    material_profile="Props_Opaque_PainterUE_ARM",
    texture_folder="",
    texture_set_token="",
    project_settings_path="",
    asset_name_override="",
):
    """Export the current Maya selection as one DCC AssetForge package."""
    reload_asset_forge_modules()

    settings = _export_settings(
        output_dir,
        target_platform,
        target_path,
        material_profile,
        texture_folder,
        texture_set_token,
        project_settings_path,
        asset_name_override,
    )
    logger = _operation_logger_class()()
    pipeline = _pipeline_class()()
    selection = pipeline.adapter.get_current_selection()
    if not selection:
        raise RuntimeError("没有选中资产")
    logger.log("shelf_export_start", "running", inputs={"selection": selection, "settings": settings})
    try:
        result = pipeline.export_assets(
            selection,
            settings["export_root"],
            settings["target_platform"],
            settings["ue_target_path"],
            material_profile=settings["material_profile"],
            texture_folder=settings["texture_root"],
            texture_set_token=settings["texture_set_token"],
            asset_name_override=settings["asset_name_override"],
            rules=_active_rules(pipeline.rules, settings),
            texture_import_policy=_texture_import_policy(settings),
            static_mesh_import_policy=_static_mesh_import_policy(settings),
            source_name_suffix="Maya",
        )
    except Exception as exc:
        logger.log("shelf_export_failed", "error", inputs={"selection": selection, "settings": settings}, errors=[str(exc)])
        raise
    logger.log(
        "shelf_export_success",
        "success",
        inputs={"selection": selection, "settings": settings},
        outputs={
            "asset_name": (result.get("scan") or {}).get("asset_name", ""),
            "package_dir": result.get("package_dir", ""),
            "manifest_path": result.get("manifest_path", ""),
            "latest_maya_log": _latest_log_path(),
        },
        report_path=result.get("export_report_path", ""),
    )
    return result


def _export_settings(output_dir, target_platform, target_path, material_profile, texture_folder, texture_set_token, project_settings_path="", asset_name_override=""):
    data = _load_project_settings(project_settings_path) if project_settings_path else {}
    data.update(
        {
            "export_root": output_dir,
            "target_platform": target_platform,
            "ue_target_path": target_path,
            "material_profile": material_profile,
            "texture_root": texture_folder,
            "texture_set_token": texture_set_token,
        }
    )
    if asset_name_override:
        data["asset_name_override"] = asset_name_override
    return _normalize_project_settings(data)


def _texture_import_policy(settings):
    return {
        "virtual_texture_policy": settings.get("virtual_texture_policy", "project_default"),
        "texture_streaming_policy": settings.get("texture_streaming_policy", "project_default"),
        "texture_group": settings.get("texture_group", "project_default"),
    }


def _static_mesh_import_policy(settings):
    return {
        "nanite_policy": settings.get("nanite_policy", "project_default"),
        "lod_group": settings.get("static_mesh_lod_group", "project_default"),
        "import_lod_policy": settings.get("static_mesh_lod_import_policy", "import_existing"),
        "build_reversed_index_buffer": settings.get("build_reversed_index_buffer", "report_only"),
        "generate_lightmap_uvs": settings.get("generate_lightmap_uvs", "report_only"),
        "collision_complexity": settings.get("collision_complexity", "report_only"),
    }


def _active_rules(rules, settings):
    result = dict(rules or {})
    static_rules = dict(result.get("static_prop", {}))
    budgets = dict(static_rules.get("max_triangles", {}))
    if int(settings.get("triangle_budget") or 0) > 0:
        budgets[settings.get("target_platform") or TARGET_PLATFORM_HIGH_END_MOBILE] = int(settings.get("triangle_budget"))
    static_rules["max_triangles"] = budgets
    static_rules["name_prefix"] = settings.get("mesh_prefix") or "SM_"
    result["static_prop"] = static_rules
    return result


def _pipeline_class():
    from asset_forge.maya.pipeline import MayaStaticPropPipeline

    return MayaStaticPropPipeline


def _operation_logger_class():
    from asset_forge.maya.operation_logger import MayaOperationLogger

    return MayaOperationLogger


def _latest_log_path():
    from asset_forge.maya.operation_logger import latest_log_path

    return latest_log_path()


def _load_project_settings(path):
    from asset_forge.maya.project_settings import load_project_settings

    return load_project_settings(path)


def _normalize_project_settings(data):
    from asset_forge.maya.project_settings import normalize_project_settings

    return normalize_project_settings(data)
