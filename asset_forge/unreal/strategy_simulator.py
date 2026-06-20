"""Offline same-name asset strategy simulation for acceptance reports."""

from __future__ import absolute_import

from asset_forge.shared.report_schema import REPORT_VERSION, attach_acceptance_summary, create_acceptance_summary


TRACKED_STRATEGIES = set(["overwrite", "reuse", "skip", "error"])


def simulate_same_name_strategies(manifest, texture_import_plan, material_binding_plan):
    actions = []
    actions.append(_action("static_mesh", manifest.get("target_path", "") + "/" + manifest.get("asset_name", ""), manifest.get("existing_mesh_strategy", "overwrite")))
    for texture in texture_import_plan.get("textures", []):
        actions.append(_action("texture", texture.get("target_asset_path", ""), texture.get("existing_texture_strategy", texture_import_plan.get("existing_texture_strategy", "overwrite"))))
    for material in material_binding_plan.get("materials", []):
        actions.append(_action("material_instance", material.get("target_asset_path", ""), material.get("existing_material_strategy", material_binding_plan.get("existing_material_strategy", "reuse"))))

    warnings = []
    errors = []
    for item in actions:
        if item["strategy"] == "error":
            errors.append(_message(item, "error 策略遇到同名资产时将阻断导入"))
        elif item["strategy"] not in TRACKED_STRATEGIES:
            warnings.append(_message(item, "未知同名资产策略：{0}".format(item["strategy"])))

    summary = create_acceptance_summary(
        "error" if errors else ("warning" if warnings else "pass"),
        warnings,
        errors,
        "调整 error 同名资产策略或清理目标资产后重新验收" if errors else "同名资产策略可追踪",
    )
    report = {
        "version": REPORT_VERSION,
        "stage": "same_name_strategy_simulation",
        "status": summary.get("status", ""),
        "actions": actions,
        "summary": summary,
    }
    return attach_acceptance_summary(report, summary)


def _action(kind, target_asset_path, strategy):
    return {
        "kind": kind,
        "target_asset_path": target_asset_path.replace("\\", "/"),
        "strategy": strategy or "",
        "action": _action_name(strategy),
        "message": "同名 {0} 策略模拟：{1}".format(kind, strategy or "未指定"),
    }


def _action_name(strategy):
    return {
        "overwrite": "would_overwrite",
        "reuse": "would_reuse",
        "skip": "would_skip",
        "error": "would_block",
    }.get(strategy, "unknown")


def _message(action, message):
    return {
        "source": "same_name_strategy",
        "id": action.get("kind", ""),
        "path": action.get("target_asset_path", ""),
        "message": message,
    }
