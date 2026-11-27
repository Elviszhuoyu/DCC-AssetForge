# -*- coding: utf-8 -*-
"""Artist-facing contracts for Maya static-prop checks."""


PACKED_TEXTURE_IMPACT = "缺少 ARM/ORM 贴图，导入 UE 后将回退为默认占位图，导致模型失去金属度与粗糙度变化。"
PACKED_TEXTURE_GUIDANCE = (
    "请从 Painter 重新导出 UE 打包贴图，或按 R=环境遮蔽、G=粗糙度、B=金属度打包。"
    "项目已配置分离贴图规则时，也可切换到该规则。完成后复检。"
)
TEXTURE_USAGE_LABELS = {
    "base_color": "基础色", "normal": "法线", "packed_arm": "ARM/ORM", "roughness": "粗糙度",
    "metallic": "金属度", "emissive": "自发光", "opacity": "透明度", "opacity_mask": "透明遮罩",
    "height": "高度贴图", "imperfection_mask": "磨损遮罩", "unknown": "用途未识别",
}


RULES = {
    "name_prefix": ("模型命名规范", "当前名称「{value}」，要求使用「{limit}」前缀及唯一的合法节点名。",
                    "补齐前缀。命名空间、非法字符和重名请在 Outliner 中调整。", "rename"),
    "mesh_exists": ("可导出网格", "当前包含 {value} 个网格，要求至少 1 个。",
                    "在 Outliner 选择包含多边形网格的资产根节点，再切换并检查。", "focus"),
    "empty_mesh": ("空网格", "检测到 {value} 个空网格，要求为 {limit} 个。",
                   "聚焦空网格，恢复有效几何或从待发布资产中移除它。", "focus"),
    "zero_area_triangles": ("零面积三角形", "检测到 {value} 个零面积三角形，期望为 {limit} 个。",
                            "查看标记的原始面和邻域，在 Maya 中手动修正拓扑。", "components"),
    "zero_length_edges": ("零长度边", "检测到 {value} 条零长度边，期望为 {limit} 条。",
                          "查看重合端点和邻域，在 Maya 中手动修正拓扑。", "components"),
    "frozen_transform": ("冻结变换", "当前 {value}，期望 {limit}。",
                         "冻结静态网格的平移、旋转和缩放，保留当前外观后复检。", "freeze"),
    "illegal_scale": ("非法缩放", "当前 {value}，期望 {limit}。",
                      "调整非正缩放或在确认镜像后的法线方向后冻结变换。", "freeze"),
    "triangle_budget": ("三角面预算", "当前 {value} 个三角面，预设上限为 {limit}。",
                        "检查几何密度。确有需要时在规则设置里切换目标平台或调整预算。", "budget"),
    "material_slots": ("材质槽预算", "当前 {value} 个材质槽，预设上限为 {limit}。",
                       "合并用途相同的材质，或采用适合的目标平台预设。", "budget"),
    "uv0": ("第 1 套 UV", "{value}。要求第 1 套 UV 有坐标。",
            "在 UV 编辑器创建第 1 套 UV、展开并保存坐标，然后复检。", "uv"),
    "lightmap_uv": ("第 2 套 Lightmap UV", "{value}。静态光照需要第 2 套 UV，且其中要有坐标。",
                    "在 UV 编辑器按通道顺序补充一套不重叠的光照 UV，然后复检。", "uv"),
    "hidden_objects": ("隐藏对象", "检测到 {value} 个隐藏对象，期望为 {limit} 个。",
                       "选中问题对象，在 Outliner 核对可见性和导出范围。", "focus"),
    "history_nodes": ("构造历史", "检测到 {value} 个构造历史节点，期望为 {limit} 个。",
                      "确认无需保留建模步骤后，清理构造历史并复检。", "history"),
    "collision_naming": ("碰撞体命名", "检测到 {value} 个命名不合规的碰撞体，期望为 {limit} 个。",
                         "检查选中的碰撞体，按照项目配置的 UE 碰撞前缀重命名。", "focus"),
    "material_assignment": ("表面材质分配", "检测到 {value} 个面缺少有效材质或仍使用 Maya 默认材质，要求为 {limit} 个。",
                            "选择受影响面，再用 Maya 的材质菜单分配项目材质。", "components"),
    "required_texture": ("必需贴图", "材质槽「{object}」缺少 {value}，当前规则要求 {limit}。",
                         "打开贴图设置检查材质规则与贴图目录，补齐必需贴图后复检。", "textures"),
    "missing_packed_texture": ("缺少 ARM/ORM 打包贴图", "材质槽「{object}」{value}，当前规则要求 {limit}。",
                               "如果只有分开的粗糙度与金属度贴图，" + PACKED_TEXTURE_GUIDANCE,
                               "external_texture"),
    "texture_set_selection": ("贴图集选择", "当前可用贴图集为「{value}」。需要确定本资产使用的贴图集。",
                              "在贴图设置填写贴图名筛选词，然后复检。", "textures"),
    "ambiguous_material_texture_set": ("材质贴图集歧义", "材质「{object}」命中 {count} 个候选贴图集，要求指定唯一的贴图集。",
                                       "从下方列表选择该材质对应的贴图集，工作台会自动复检。", "candidate"),
    "invalid_material_texture_set": ("指定贴图集不可用", "材质「{object}」之前指定的贴图集已不可用，要求选择 1 个有效贴图集。",
                                     "在下方重新选择，或检查贴图目录和关键词。", "candidate"),
    "unmatched_material": ("材质未匹配贴图集", "材质「{object}」匹配到 0 个贴图集，要求匹配 1 个。",
                           "核对材质名、贴图目录及贴图名筛选词，再复检。", "textures"),
    "unassigned_texture_set": ("贴图集未分配材质", "贴图集「{object}」分配给了 0 个材质，要求关联 1 个材质。",
                                "检查材质名和贴图名筛选词，保留本资产使用的贴图集。", "textures"),
    "material_texture_binding": ("材质贴图绑定", "当前材质绑定异常（{value}），期望 {limit}。",
                                 "在贴图设置检查材质与贴图集的对应关系，再复检。", "textures"),
    "shared_texture_set": ("材质共用贴图集", "贴图集「{object}」当前用于 {value}。期望每个材质有对应贴图集，或经项目确认后共享。",
                           "在贴图设置核对材质与贴图集的对应关系，再复检。", "textures"),
    "shared_texture_file": ("材质共用贴图文件", "贴图「{object}」由 {value} 共用。期望按材质用途分别绑定，或经项目确认后共享。",
                            "检查目录中重名、重复使用的贴图，再复检。", "textures"),
    "shared_material_instance": ("材质实例重名", "{value} 都映射到「{object}」。期望每个材质实例路径唯一。",
                                 "检查材质名称和贴图集命名，再复检。", "textures"),
    "shared_slot_index": ("材质槽索引冲突", "{value} 都映射到槽位 {object}。期望槽位与材质一一对应。",
                          "在 Maya 中检查网格的材质分配，再复检。", "textures"),
}

ACTIONS = {
    "rename": (("rename", "一键修复前缀"), ("rules", "调整前缀规则")),
    "focus": (("focus", "聚焦对象"),),
    "components": (),
    "freeze": (("freeze", "冻结变换"),),
    "budget": (("focus", "聚焦对象"), ("rules", "查看预设规则")),
    "uv": (("uv", "打开 UV 编辑器"), ("focus", "聚焦网格")),
    "history": (("history", "清理构造历史"),),
    "candidate": (),
    "textures": (("textures", "打开贴图设置"),),
    "external_texture": (("choose_textures", "选择外部贴图目录"),),
}

GATE_RULES = frozenset(RULES) - frozenset((
    "name_prefix", "mesh_exists", "empty_mesh", "zero_area_triangles", "zero_length_edges",
    "frozen_transform", "illegal_scale", "triangle_budget", "material_slots", "uv0",
    "lightmap_uv", "hidden_objects", "history_nodes", "collision_naming",
))


def _transform_values(scan, illegal):
    entries = []
    for node, values in scan.get("transform_data", {}).items():
        scale = values.get("scale", ())
        if illegal:
            if not any(value <= 0 for value in scale):
                continue
            display = "Scale {0}".format(scale)
        else:
            targets = {"translate": (0, 0, 0), "rotate": (0, 0, 0), "scale": (1, 1, 1)}
            parts = ["{0} {1}".format(key.title(), values[key]) for key, expected in targets.items()
                     if values.get(key) and any(abs(a - b) > 0.0001 for a, b in zip(values[key], expected))]
            if not parts:
                continue
            display = "，".join(parts)
        entries.append(node.rsplit("|", 1)[-1] + " " + display)
    return "；".join(entries[:3])


def describe(check, scan, validation, obj="", has_components=False):
    rule = check.get("id", "")
    title, template, guidance, kind = RULES.get(rule, RULES["material_texture_binding"])
    status = check.get("status")
    severity = {"error": "blocked", "warning": "warning", "pass": "pass"}.get(status, "needs_review")
    value, limit = check.get("value"), check.get("limit")
    if kind == "uv":
        sets = scan.get("uv_sets", {}).get(obj, [])
        counts = scan.get("uv_coordinate_counts", {}).get(obj, [])
        if obj in scan.get("uv_sets", {}):
            channels = "、".join("第 {0} 套 {1}（{2}）".format(index + 1, name,
                               "{0} 个坐标".format(counts[index]) if index < len(counts) and counts[index] is not None
                               else "坐标未核验") for index, name in enumerate(sets[:2]))
            value = "当前有 {0} 套 UV{1}".format(len(sets), "，" + channels if channels else "")
        else:
            value = "已读取所选网格的 UV 坐标" if status == "pass" else "当前通道缺失、为空或无法读取"
    elif kind == "freeze":
        illegal = rule == "illegal_scale"
        value = _transform_values(scan, illegal) or ("变换已冻结" if status == "pass" else "检测到异常变换")
        limit = "Scale 每项大于 0" if illegal else "Translate / Rotate = (0, 0, 0)，Scale = (1, 1, 1)"
    if kind == "candidate" and not check.get("candidates"):
        kind = "textures"
        guidance = "在贴图设置核对贴图目录和贴图名筛选词，再复检。"
    if kind == "components" and not has_components:
        kind = "focus"
        if status != "pass":
            template = "当前无法读取组件编号。该项要求成功读取几何，且异常数量为 {limit}。"
            guidance = "聚焦网格，确认对象仍存在并复检。"
    if rule == "required_texture":
        if isinstance(value, list):
            value = "、".join(TEXTURE_USAGE_LABELS.get(usage, "预设指定贴图") for usage in value)
        if isinstance(limit, list):
            limit = "、".join(TEXTURE_USAGE_LABELS.get(usage, "预设指定贴图") for usage in limit)
    if isinstance(value, list):
        value = "、".join(value)
    summary = template.format(value="未设上限" if limit is None and kind == "budget" else value,
                              limit="未设上限" if limit is None else limit, object=obj.replace("\\", "/").rsplit("/", 1)[-1].rsplit("|", 1)[-1],
                              count=len(check.get("candidates", [])))
    if rule == "name_prefix" and check.get("naming_issues"):
        summary += " " + "；".join(check["naming_issues"])
    blocking = severity == "blocked" and validation.get("block_export_on_error", True)
    blocking = blocking or severity == "warning" and not validation.get("allow_warning_export", True)
    if rule in GATE_RULES and severity == "blocked":
        blocking = True
    if rule == "missing_packed_texture":
        impact = ("此项阻断导出。" if blocking else "可继续导出。") + PACKED_TEXTURE_IMPACT
        if check.get("separate_texture_maps"):
            guidance = "已在这套贴图中找到分开的粗糙度与金属度贴图。" + PACKED_TEXTURE_GUIDANCE
    elif blocking:
        impact = "此项阻断导出。"
    elif severity == "warning" and rule == "lightmap_uv":
        impact = "可继续导出。仅使用 Lumen 动态光照且无需静态烘焙时，可以忽略。"
    elif severity == "warning":
        impact = "可继续导出。交付前按项目规范确认是否需要修复。"
    elif severity == "pass":
        impact = "此项符合当前预设，可继续导出。"
    else:
        impact = "当前预设允许带此项导出。"
    actions = ACTIONS[kind]
    if kind == "rename" and check.get("naming_issues"):
        actions = (("focus", "聚焦对象"), ("rules", "调整前缀规则"))
    return dict(title=title, severity=severity, summary=summary, export_impact=impact,
                fix_guidance=guidance, action_kind=kind,
                component_label="选中受影响面" if rule == "material_assignment" else "选原组件", actions=[dict(id=key, label=label) for key, label in actions])
