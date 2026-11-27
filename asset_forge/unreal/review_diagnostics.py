"""Artist-facing diagnostics for the registered Unreal asset review rules."""


# The default describes when the rule is evaluated, rather than whether a given asset uses it.
REVIEW_RULES = {
    "asset.read": ("资产类型", "读取资产时", "读到 {actual}，要求 {expected}。",
                   "从内容浏览器选择静态网格或二维贴图后重新检查。", "selection"),
    "mesh.lod0_triangles": ("LOD0 三角面预算", "静态网格", "LOD0 实测 {actual} 个三角面，上限 {expected}。",
                            "打开静态网格编辑器查看 LOD0，减面或核对目标平台预算。", "open_mesh"),
    "mesh.material_slots": ("材质槽数量", "静态网格", "实测 {actual} 个材质槽，上限 {expected}。",
                            "打开静态网格编辑器，检查空槽、重复槽和可合并的材质分区。", "open_mesh"),
    "mesh.lod_count": ("LOD 数量", "预设启用", "实测 {actual} 个 LOD，至少需要 {expected}。",
                       "打开静态网格编辑器，按当前用途补齐 LOD 后复验。", "open_mesh"),
    "mesh.simple_collision": ("简单碰撞", "预设启用", "实测 {actual} 个简单碰撞体，至少需要 {expected}。",
                              "打开静态网格编辑器，按项目要求制作简单碰撞后复验。", "open_mesh"),
    "mesh.empty_lod0": ("LOD0 渲染几何", "静态网格", "实测 {actual} 个 LOD0 三角面，要求 {expected}。",
                        "打开静态网格编辑器核对 LOD0，补齐可渲染几何后重新交付。", "open_mesh"),
    "mesh.slot_material": ("材质槽绑定", "静态网格", "实测 {actual}，要求 {expected}。",
                           "打开静态网格编辑器，定位所列材质槽并指定实际交付材质。", "open_mesh"),
    "material.texture_bindings": ("材质贴图绑定", "已分配的材质", "实测 {actual}，要求 {expected}。",
                                   "打开材质编辑器检查实际引用的贴图及参数。", "open_material"),
    "material.required_texture": ("必需贴图槽", "匹配当前规则母材质",
                                  "{actual}，要求{expected}。",
                                  "打开该材质实例核对此槽，补齐真实贴图后重新交付。", "open_material"),
    "texture.role": ("贴图用途", "读取贴图时", "识别结果为 {actual}，要求 {expected}。",
                     "打开贴图，按命中规则核对母材质、纹理参数和实际用途。", "open_texture"),
    "texture.source_size": ("贴图源尺寸", "贴图，尺寸上限由预设启用", "实测 {actual}，要求 {expected}。",
                            "打开贴图编辑器查看导入源尺寸，按目标平台预算调整。", "open_texture"),
    "texture.srgb": ("色彩空间", "贴图用途明确时", "sRGB 实测 {actual}，期望 {expected}。",
                     "打开贴图编辑器核对 sRGB，调整后保存并复验。", "open_texture"),
    "texture.compression": ("纹理压缩", "贴图用途明确时", "压缩格式实测 {actual}，期望 {expected}。",
                            "打开贴图编辑器核对压缩设置，调整后保存并复验。", "open_texture"),
    "texture.repair_scope": ("贴图修复范围", "发现纹理设置差异时", "引用核对结果为 {actual}，要求 {expected}。",
                             "核对引用范围。保存未落盘改动后可重新预览，共享贴图由负责人处理。", "preview_fix"),
}

ACTIONS = {
    "selection": "",
    "open_mesh": "打开静态网格",
    "open_material": "打开材质",
    "open_texture": "打开贴图",
    "preview_fix": "预览修复影响",
}
EXPECTATIONS = {
    "assigned": "各槽分配实际交付材质",
    "readable": "能读取材质引用的贴图与参数",
    "unique profile rule": "当前材质规则命中唯一的贴图用途",
    "verified private texture": "能确认引用范围，且修改仅影响本次检查的资产",
}


def reading(value):
    if value is None:
        return "未能读取"
    if isinstance(value, bool):
        return "开启" if value else "关闭"
    if isinstance(value, (list, tuple)):
        return "、".join(str(item) for item in value) or "无"
    if value == "":
        return "空"
    return str(value)


def diagnostic(rule, actual, expected, severity, fix_guidance="", can_preview=False):
    title, _, template, guidance, action = REVIEW_RULES[rule]
    if rule == "texture.role":
        if actual in ([], ["unknown"]):
            actual = "当前规则没有匹配到可确认的贴图用途"
        elif isinstance(actual, list):
            actual = "候选用途为 " + "、".join(actual)
    elif rule == "texture.source_size":
        if isinstance(actual, (list, tuple)):
            actual = " × ".join(map(str, actual)) + " px"
        expected = "可读取源尺寸" if expected is None else "最长边不超过 {} px".format(expected)
    elif rule == "mesh.slot_material" and actual == []:
        actual = "没有材质槽"
    elif rule == "asset.read" and actual == "unknown":
        actual = None
    if isinstance(expected, str):
        expected = EXPECTATIONS.get(expected, expected)
    if can_preview:
        action = "preview_fix"
    return {
        "title": title,
        "severity": severity,
        "summary": template.format(actual=reading(actual), expected=reading(expected)),
        "export_impact": {
            "blocked": "此项阻断本轮 UE 批审放行。",
            "warning": "此项不阻断本轮 UE 批审放行。",
            "needs_review": "当前证据不足，核实前不能认定通过。",
            "pass": "此项符合当前检查要求。",
        }[severity],
        "fix_guidance": fix_guidance or guidance,
        "action_kind": action,
    }


def issue_diagnostic(issue):
    if "diagnostic" in issue:
        return issue["diagnostic"]
    rule = issue["rule_id"]
    severity = {"error": "blocked", "warning": "warning"}.get(issue.get("severity"), "needs_review")
    if rule not in REVIEW_RULES:
        return {
            "title": "旧批次检查项（{}）".format(rule), "severity": severity,
            "summary": "实测 {}，期望 {}。".format(reading(issue.get("actual")), reading(issue.get("expected"))),
            "export_impact": "按原批次结论处理。",
            "fix_guidance": issue.get("suggestion") or "复验当前资产以取得当前规则的诊断。",
            "action_kind": "selection",
        }
    return diagnostic(rule, issue.get("actual"), issue.get("expected"), severity, issue.get("suggestion") or "",
                      rule in ("texture.srgb", "texture.compression") and issue.get("severity") == "error")
