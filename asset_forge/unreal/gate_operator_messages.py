"""Chinese workbench wording projected from raw gate evidence."""

import re

from asset_forge.unreal.material_texture_binding_validator import texture_binding_check_status


_LABELS = {
    "manifest": "包体清单",
    "manifest_lint": "包体字段检查",
    "interface_contract": "DCC 与 UE 交付约定",
    "package": "导出包资源",
    "plugin_mount": "插件挂载",
    "plugin_content": "UE 插件内容",
    "material_assets": "默认材质资产",
    "parent_materials": "母材质",
    "material_binding_contract": "材质绑定规则",
    "material_graph_evidence": "材质图验证",
    "material_profile_reference": "材质预设引用",
    "material_profile_snapshot": "材质预设快照",
    "material_profile": "材质预设",
    "material_profile_contract": "材质参数规则",
    "material_texture_requirements": "必需贴图槽",
    "texture_quality": "贴图质量",
    "packed_channels": "打包贴图通道",
    "release_dependency_audit": "交付依赖",
    "same_name_strategy": "同名资产策略",
    "slot_binding_preflight": "网格材质槽",
    "static_mesh_lod_policy": "网格 LOD 策略",
    "static_mesh_import_policy": "网格导入设置",
    "engine_version_preflight": "UE 版本",
    "package_acceptance": "包体核验",
    "dry_run": "导入预演",
    "import": "导入",
}
_FIELDS = {
    "build_reversed_index_buffer": "反向索引缓冲区",
    "build_nanite": "构建 Nanite",
    "generate_lightmap_uvs": "生成光照贴图 UV",
    "import_mesh_lods": "导入网格 LOD",
    "remove_degenerates": "去除退化几何",
    "compute_weighted_normals": "计算加权法线",
    "one_convex_hull_per_ucx": "每个碰撞网格使用一个凸包",
    "import_materials": "导入材质",
    "import_textures": "导入贴图",
    "report-only": "仅记录",
    "report_only": "仅记录",
    "project_default": "使用项目默认值",
    "enable": "开启",
    "disable": "关闭",
    "true": "开启",
    "false": "关闭",
}
_FIELD_PATTERN = re.compile(r"(?<![\w])(" + "|".join(re.escape(key) for key in _FIELDS) + r")(?![\w])", re.I)
_CJK = re.compile(r"[\u3400-\u9fff]")
_COVERAGE_AGGREGATE = re.compile(r"^缺少必需贴图(?:数量|类型)?[：:]\s*([a-z_]+)$", re.I)
_USAGE_LABELS = {
    "base_color": "基础色",
    "normal": "法线",
    "packed_arm": "ARM/ORM 打包贴图",
    "packed_orm": "ARM/ORM 打包贴图",
    "opacity_mask": "镂空遮罩",
    "emissive": "自发光",
    "imperfection_mask": "瑕疵遮罩",
    "opacity": "透明度",
    "height": "高度",
}


def _value(row):
    return row.get("message", "") if isinstance(row, dict) else row


def localized_message(message, label="门禁检查", severity="warning"):
    message = str(message or "").strip()
    if not message:
        return ""
    aggregate = _COVERAGE_AGGREGATE.fullmatch(message)
    if aggregate:
        label = _USAGE_LABELS.get(aggregate.group(1).casefold(), "当前材质规则指定的贴图")
        return "包体缺少必需的{0}，请按材质槽核对后重新导出。".format(label)
    if message.startswith("母材质网络状态："):
        return "请在导入后打开材质实例，核对母材质的 PBR 参数和显示效果。"
    if "build_reversed_index_buffer" in message.casefold():
        value = re.search(r"\b(enable|enabled|true|disable|disabled|false|project_default)\b", message, re.I)
        state = {
            "enable": "开启", "enabled": "开启", "true": "开启",
            "disable": "关闭", "disabled": "关闭", "false": "关闭", "project_default": "使用项目默认值",
        }.get(value.group(1).casefold(), "") if value else ""
        if "report-only" in message or "report_only" in message:
            return "反向索引缓冲区{0}。本次导入仅记录此设置，请在 UE 网格详情中复核。".format("设为" + state if state else "设置已记录")
    for check_id, name in _LABELS.items():
        message = re.sub(r"\b" + re.escape(check_id.replace("_", " ")) + r"\b", name, message, flags=re.I)
        message = re.sub(r"(?<![\w])" + re.escape(check_id) + r"(?![\w])", name, message, flags=re.I)
    message = _FIELD_PATTERN.sub(lambda match: _FIELDS[match.group(1).casefold()], message)
    if _CJK.search(message):
        return message
    return "{0}有{1}，请打开完整报告核对。".format(label, "阻断项" if severity == "error" else "待复核项")


def _graph_detail(report, acceptance):
    labels = {
        "parent_material_exists": "母材质",
        "material_sampler_policy_validation": "贴图采样类型",
        "mi_texture_overrides": "材质实例贴图参数",
        "slot_binding": "网格材质槽",
        "compile_log_evidence": "材质编译结果",
        "real_ue_material_graph": "实际材质图",
        "material_comment_box_persistence": "材质图注释在重开后的保留情况",
    }
    rows = [
        row for section in (acceptance, report.get("import", {}))
        for row in section.get("material_graph_evidence_report", {}).get("checks", [])
        if row.get("status") == "warning"
    ]
    rows.extend(row for row in report.get("warnings", []) if isinstance(row, dict)
                and row.get("source") == "material_graph_evidence")
    details = [labels[row["id"]] for row in rows if row.get("id") in labels]
    detail = "、".join(dict.fromkeys(details)) or "实际材质图、材质参数和网格材质槽"
    return "请在 UE 中复核{0}。".format(detail)


_INVENTORY_CHECKS = {"plugin_content": "plugin_content_validation", "material_assets": "material_asset_validation"}


def _shared_preview_inventory(acceptance):
    inventories = []
    for key in _INVENTORY_CHECKS.values():
        validation = acceptance.get(key) or {}
        missing = validation.get("missing_assets") or []
        if not missing or not all(isinstance(path, str) and path.casefold().startswith("/assetforge/") for path in missing):
            return False
        inventory = {path.casefold() for path in missing}
        if validation.get("missing_count", len(inventory)) != len(inventory):
            return False
        inventories.append(inventory)
    return inventories[0] == inventories[1] and any(
        path.rsplit("/", 1)[-1].startswith("t_af_preview_") for path in inventories[0])


def _warning_detail(check_id, report, acceptance):
    if check_id in _INVENTORY_CHECKS:
        key = _INVENTORY_CHECKS[check_id]
        validation = acceptance.get(key, {})
        missing = list(dict.fromkeys(validation.get("missing_assets", [])))
        if missing:
            names = "、".join(path.rsplit("/", 1)[-1].split(".")[0] for path in missing[:2])
            return "缺少 {0} 项，含 {1}{2}。请核对插件内容安装。".format(
                validation.get("missing_count", len(missing)), names, " 等" if len(missing) > 2 else "")
    if check_id == "material_graph_evidence":
        return _graph_detail(report, acceptance)
    if check_id == "release_dependency_audit":
        return "交付工程需要启用 AssetForge 插件，保留包体使用的插件材质。"
    return ""


def _required_slot_details(report, acceptance, severity):
    details, related, covered_usages = {}, set(), set()
    for stage in (acceptance, report.get("dry_run") or {}, report.get("import") or {}):
        validation = stage.get("material_texture_binding_validation") or {}
        for row in validation.get("checks", []):
            if row.get("id") != "required_texture_parameter_missing" or texture_binding_check_status(validation, row) != severity:
                continue
            name = row.get("material_name") or row.get("material_instance_path")
            message = str(row.get("message") or "")
            if name and message:
                details[(name, row.get("parameter"))] = localized_message(message, "必需贴图槽", severity)
                related.add(message)
                covered_usages.add(row.get("usage"))
    return list(details.values()), related, covered_usages


def _covered_texture_summary(message, covered_usages):
    match = _COVERAGE_AGGREGATE.fullmatch(str(message or "").strip())
    return match is not None and match.group(1).casefold() in covered_usages


def operator_messages(report, level):
    """Project the same operator lines from a live flow, a legacy flow or a standalone report."""
    severity = "warning" if level == "warnings" else "error"
    acceptance = report.get("package_acceptance") or report
    checks = [row for row in acceptance.get("checks", []) if row.get("status") == severity]
    slot_details, covered, covered_usages = _required_slot_details(report, acceptance, severity)
    messages = ["必需贴图槽：" + line for line in slot_details]
    owners = set()
    shared_inventory = severity == "warning" and _shared_preview_inventory(acceptance)
    for row in checks:
        check_id = row.get("id")
        if check_id == "material_texture_requirements" and slot_details:
            continue
        if shared_inventory and check_id in _INVENTORY_CHECKS and check_id in owners:
            continue
        label = _LABELS.get(check_id) or row.get("label", "")
        if shared_inventory and check_id in _INVENTORY_CHECKS:
            label = "UE 插件预览与示例资源"
        label = label if _CJK.search(label) else "包体检查"
        detail = _warning_detail(check_id, report, acceptance) if severity == "warning" else ""
        if not detail:
            details = [
                localized_message(_value(item), label, severity) for item in row.get("messages", [])
                if not _covered_texture_summary(_value(item), covered_usages)
            ]
            detail = "；".join(dict.fromkeys(item for item in details if item))
        if detail:
            messages.append(label + "：" + detail)
            owners.add(check_id)
            if shared_inventory and check_id in _INVENTORY_CHECKS:
                owners.update(_INVENTORY_CHECKS)

    rows = report.get(level) or report.get("summary", {}).get(level) or []
    for row in rows:
        source = row.get("source", "") if isinstance(row, dict) else ""
        message = _value(row)
        if (source in owners or source == "pre_import_gate" or str(message or "") in covered
                or _covered_texture_summary(message, covered_usages)):
            continue
        label = _LABELS.get(source, "门禁检查")
        detail = _warning_detail(source, report, acceptance) if severity == "warning" else ""
        if detail:
            if shared_inventory and source in _INVENTORY_CHECKS:
                label = "UE 插件预览与示例资源"
                owners.update(_INVENTORY_CHECKS)
            messages.append(label + "：" + detail)
            owners.add(source)
        else:
            messages.append(localized_message(_value(row), label, severity))
    if not any(messages) and severity == "error":
        messages.extend(localized_message(row, severity=severity) for row in report.get("blocking_reasons", []))
    if not any(messages):
        messages.extend(localized_message(row, severity=severity) for row in report.get("operator_" + level, []))
    return list(dict.fromkeys(item for item in messages if item))
