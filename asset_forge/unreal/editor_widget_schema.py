"""Unreal Gate UI schema and Python fallback layout."""

from __future__ import absolute_import

from copy import deepcopy

from asset_forge.unreal.editor_widget_actions import get_action_plan


REQUIRED_UI_REGIONS = [
    "brand_header",
    "global_search",
    "workflow_tabs",
    "package_history",
    "local_export_scan",
    "package_picker",
    "package_summary",
    "package_contents",
    "mesh_status",
    "texture_status",
    "material_status",
    "profile_status",
    "gate_status",
    "validation_summary",
    "issue_list",
    "package_detail",
    "target_and_overwrite",
    "import_history",
    "import_approval",
    "action_buttons",
    "report_output",
]


REQUIRED_WIDGETS = [
    "AFG_Workbench",
    "AFG_WorkflowTabs",
    "AFG_TabPackages",
    "AFG_TabReview",
    "AFG_TabApproval",
    "AFG_PackageSection",
    "AFG_ReviewSection",
    "AFG_ApprovalSection",
    "AFG_ReportSection",
    "AFG_BrandMark",
    "AFG_BrandName",
    "AFG_GlobalSearch",
    "AFG_SourceFilter",
    "AFG_RuleFilter",
    "AFG_RecentPackageList",
    "AFG_ScanExportDirectoryButton",
    "AFG_SelectedPackagePath",
    "AFG_SelectedPackageSummary",
    "AFG_PackageContents",
    "AFG_MeshStatus",
    "AFG_TextureStatus",
    "AFG_MaterialStatus",
    "AFG_ProfileStatus",
    "AFG_GateStatus",
    "AFG_ImportHistoryList",
    "AFG_ImportScopeSummary",
    "AFG_WarningList",
    "AFG_ErrorList",
    "AFG_ReportPath",
    "AFG_OpenReportButton",
    "AFG_NextAction",
    "AFG_RefreshButton",
    "AFG_ImportButton",
]


REQUIRED_SECTION_ORDER = [
    "AFG_PackageSection",
    "AFG_ReviewSection",
    "AFG_ApprovalSection",
    "AFG_ReportSection",
]


REQUIRED_DATA_SECTIONS = [
    "package_history",
    "package_gate",
    "selected_package",
    "import_history",
    "import_approval",
    "gate_report",
]


FORBIDDEN_DEBUG_TEXT = ["debug", "placeholder", "todo", "test widget", "sample panel", "lorem"]


REQUIRED_WIDGET_CLASSES = {
    "AFG_GlobalSearch": "EditableTextBox",
    "AFG_SourceFilter": "ComboBoxString",
    "AFG_RuleFilter": "ComboBoxString",
    "AFG_RecentPackageList": "ListView",
    "AFG_ImportHistoryList": "ListView",
}


def _text(name, cls, parent, text="", font_size=None, color=None, padding=None):
    item = {"name": name, "class": cls, "parent": parent}
    if text:
        item["text"] = text
    if font_size:
        item["font_size"] = font_size
    if color:
        item["color"] = color
    if padding:
        item["padding"] = padding
    return item


def _box(name, cls, parent, padding=None):
    item = {"name": name, "class": cls, "parent": parent}
    if padding:
        item["padding"] = padding
    return item


def _control(name, cls, parent, text="", padding=None):
    item = {"name": name, "class": cls, "parent": parent}
    if text:
        item["text"] = text
    if padding:
        item["padding"] = padding
    return item


def _row(row_name, parent, label_name, label, value_name, value, value_color=None, value_size=11):
    return [
        _box(row_name, "HorizontalBox", parent, (0, 1, 0, 1)),
        _text(label_name, "TextBlock", row_name, label, 10, (0.55, 0.60, 0.64, 1.0)),
        _text(value_name, "TextBlock", row_name, value, value_size, value_color or (0.84, 0.88, 0.90, 1.0)),
    ]


def _button(name, parent, label_name, label):
    return [
        {"name": name, "class": "Button", "parent": parent},
        _text(label_name, "TextBlock", name, label, 10, (0.86, 0.90, 0.92, 1.0), (6, 2, 6, 2)),
    ]


EDITOR_WIDGET_PLAN = {
    "widget_name": "EUW_AssetForgeGate",
    "asset_type": "EditorUtilityWidgetBlueprint",
    "content_mount": "/AssetForge",
    "asset_path": "/AssetForge/Editor/EUW_AssetForgeGate",
    "disk_directory": "Plugins/AssetForge/Content/Editor",
    "fallback_ui": "python_editor_dialog_gate",
    "ui_language": "zh-CN",
    "rebuild_tree": True,
    "debug_shell_policy": {
        "forbid_english_debug_shell": True,
        "forbidden_text": FORBIDDEN_DEBUG_TEXT,
    },
    "official_sources": [
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/editor-utility-widgets-in-unreal-engine",
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/details-panel-customizations-in-unreal-engine",
        "https://dev.epicgames.com/documentation/en-us/unreal-engine/modeling-mode-in-unreal-engine",
    ],
    "design_intent": {
        "name": "Asset Forge 导入门禁工作台",
        "tone": "贴近 UE Details Panel 的克制工具界面",
        "density": "紧凑、清晰、适合 TA 重复操作",
        "primary_flow": ["选择包体", "检查包体", "导入已放行包体"],
        "visual_rules": [
            "全中文文案，不使用英文调试壳",
            "采用 UE 官方 Details Panel 式分类、属性行和短标签",
            "搜索、包体历史、导入历史和导入动作必须使用语义控件，而不是调试占位文本",
            "每个阶段都有可折叠式 Category Header，不把大字说明堆满界面",
            "重要信息用左标签、右值或右控件呈现，减少自由文本段落",
            "包体列表、选中详情、历史记录和导入动作必须分区",
            "主按钮承担用户目标，辅助按钮只保留检查和已放行导入",
        ],
    },
    "layout_regions": REQUIRED_UI_REGIONS,
    "section_layout": [
        {
            "id": "package_history",
            "container": "AFG_PackageSection",
            "title": "1 包体来源",
            "role": "扫描 Maya、Blender 等 DCC 输出的 Asset Forge 包体，并选择一个待检查包。",
            "primary_action": "scan_export_directory",
            "collapsible": True,
        },
        {
            "id": "selected_package",
            "container": "AFG_ReviewSection",
            "title": "2 导入控制",
            "role": "核对资产名、来源 DCC、UE 目标路径、FBX、贴图、材质实例和材质规则，并导入已放行包体。",
            "primary_action": "preview_package_gate",
            "collapsible": True,
        },
        {
            "id": "import_history",
            "container": "AFG_ApprovalSection",
            "title": "3 包体内容",
            "role": "查看当前包体内网格、贴图、材质实例和项目预设。",
            "primary_action": "import_package",
            "collapsible": True,
        },
        {
            "id": "gate_report",
            "container": "AFG_ReportSection",
            "title": "4 导入策略",
            "role": "集中显示导入建议、覆盖策略、警告、阻断项、报告路径和下一步动作。",
            "primary_action": "preview_package_gate",
            "collapsible": True,
        },
    ],
    "action_bindings": [
        {"widget": "AFG_RefreshButton", "action": "refresh_packages", "purpose": "刷新最近导出包与导入记录。"},
        {"widget": "AFG_ScanExportDirectoryButton", "action": "scan_export_directory", "purpose": "扫描本地 Asset Forge 导出包目录。"},
        {"widget": "AFG_RecentPackageList", "action": "select_package", "purpose": "选择一个本地导出包体。"},
        {"widget": "AFG_PreviewGateButton", "action": "preview_package_gate", "purpose": "检查当前选中包体。"},
        {"widget": "AFG_DryRunButton", "action": "dry_run_package", "purpose": "检查当前设置下的导入计划，不创建 UE 资产。"},
        {"widget": "AFG_ImportButton", "action": "import_package", "purpose": "导入已放行的当前选中包体。"},
        {"widget": "AFG_OpenReportButton", "action": "open_report", "purpose": "打开当前包体已有的门禁或导入报告。"},
    ],
    "core_widgets": [
        _box("AFG_RootScroll", "ScrollBox", ""),
        _box("AFG_Root", "VerticalBox", "AFG_RootScroll", (8, 8, 8, 8)),
        _box("AFG_Header", "VerticalBox", "AFG_Root", (0, 0, 0, 6)),
        _box("AFG_BrandRow", "HorizontalBox", "AFG_Header", (0, 0, 0, 4)),
        _text("AFG_BrandMark", "TextBlock", "AFG_BrandRow", "AF 锻造", 16, (0.18, 0.78, 0.72, 1.0), (5, 1, 8, 1)),
        _text("AFG_BrandName", "TextBlock", "AFG_BrandRow", "Asset Forge 导入门禁工作台", 14, (0.92, 0.94, 0.95, 1.0)),
        _text("AFG_HeaderStatus", "TextBlock", "AFG_Header", "状态：等待扫描", 10, (0.58, 0.78, 0.62, 1.0)),
        _control("AFG_GlobalSearch", "EditableTextBox", "AFG_Header", "搜索包体名 / DCC / 目标路径 / 材质规则", (0, 2, 0, 2)),
        _box("AFG_WorkflowTabs", "HorizontalBox", "AFG_Header", (0, 4, 0, 4)),
        *_button("AFG_TabPackages", "AFG_WorkflowTabs", "AFG_TabPackagesLabel", "包体"),
        *_button("AFG_TabReview", "AFG_WorkflowTabs", "AFG_TabReviewLabel", "检查"),
        *_button("AFG_TabApproval", "AFG_WorkflowTabs", "AFG_TabApprovalLabel", "导入"),
        _box("AFG_Workbench", "VerticalBox", "AFG_Root", (0, 2, 0, 2)),
        _box("AFG_PackageSection", "VerticalBox", "AFG_Workbench", (0, 4, 0, 6)),
        *_button("AFG_PackageSectionHeader", "AFG_PackageSection", "AFG_PackageSectionTitle", "▾ 1 包体来源"),
        _box("AFG_FilterRow", "HorizontalBox", "AFG_PackageSection", (0, 1, 0, 1)),
        _control("AFG_SourceFilter", "ComboBoxString", "AFG_FilterRow", "来源：全部 DCC", (0, 0, 4, 0)),
        _control("AFG_RuleFilter", "ComboBoxString", "AFG_FilterRow", "规则：全部材质规则", (0, 0, 0, 0)),
        *_row("AFG_ExportRootRow", "AFG_PackageSection", "AFG_ExportRootLabel", "扫描目录", "AFG_ExportRootValue", "AssetForge/Exports 与用户指定目录"),
        *_row("AFG_SignalRow", "AFG_PackageSection", "AFG_SignalLabel", "识别信号", "AFG_PackageHint", "清单 manifest / 来源 source_dcc / schema_version / export_report"),
        _text("AFG_PackageHistoryTitle", "TextBlock", "AFG_PackageSection", "本地导出包", 10, (0.55, 0.60, 0.64, 1.0), (0, 2, 0, 0)),
        _control("AFG_RecentPackageList", "ListView", "AFG_PackageSection", "包体列表：未扫描到 AF 包体", (0, 1, 0, 2)),
        _box("AFG_ActionBar", "VerticalBox", "AFG_PackageSection", (0, 4, 0, 0)),
        *_button("AFG_RefreshButton", "AFG_ActionBar", "AFG_RefreshButtonLabel", "刷新最近包体"),
        *_button("AFG_ScanExportDirectoryButton", "AFG_ActionBar", "AFG_ScanExportDirectoryButtonLabel", "扫描导出目录"),
        *_button("AFG_PreviewGateButton", "AFG_ActionBar", "AFG_PreviewGateButtonLabel", "仅检查"),
        *_button("AFG_DryRunButton", "AFG_ActionBar", "AFG_DryRunButtonLabel", "仅检查导入计划"),
        *_button("AFG_ImportButton", "AFG_ActionBar", "AFG_ImportButtonLabel", "仅导入已放行"),
        _box("AFG_ReviewSection", "VerticalBox", "AFG_Workbench", (0, 4, 0, 6)),
        *_button("AFG_ReviewSectionHeader", "AFG_ReviewSection", "AFG_ReviewSectionTitle", "▾ 2 导入控制"),
        *_row("AFG_SelectedPackageRow", "AFG_ReviewSection", "AFG_SelectedPackageTitle", "选中包体", "AFG_SelectedPackagePath", "尚未选择包体"),
        *_row("AFG_TargetPathRow", "AFG_ReviewSection", "AFG_TargetPathLabel", "UE 目标路径", "AFG_SelectedPackageSummary", "选择包体后显示资产名、来源 DCC、目标路径和覆盖策略"),
        _box("AFG_StatusGrid", "VerticalBox", "AFG_ReviewSection", (0, 2, 0, 2)),
        *_row("AFG_MeshStatusRow", "AFG_StatusGrid", "AFG_MeshStatusLabel", "网格", "AFG_MeshStatus", "未检查"),
        *_row("AFG_TextureStatusRow", "AFG_StatusGrid", "AFG_TextureStatusLabel", "贴图", "AFG_TextureStatus", "未检查"),
        *_row("AFG_MaterialStatusRow", "AFG_StatusGrid", "AFG_MaterialStatusLabel", "材质实例", "AFG_MaterialStatus", "未检查"),
        *_row("AFG_ProfileStatusRow", "AFG_StatusGrid", "AFG_ProfileStatusLabel", "材质规则", "AFG_ProfileStatus", "未检查"),
        *_row("AFG_GateStatusRow", "AFG_StatusGrid", "AFG_GateStatusLabel", "门禁", "AFG_GateStatus", "等待包体", (0.58, 0.78, 0.62, 1.0)),
        *_row("AFG_PackageContentsRow", "AFG_ReviewSection", "AFG_PackageContentsTitle", "包内资产", "AFG_PackageContents", "Mesh：未检查 | Textures：未检查 | Materials：未检查"),
        _box("AFG_ApprovalSection", "VerticalBox", "AFG_Workbench", (0, 4, 0, 6)),
        *_button("AFG_ApprovalSectionHeader", "AFG_ApprovalSection", "AFG_ApprovalSectionTitle", "▾ 3 包体内容"),
        _text("AFG_ImportHistoryTitle", "TextBlock", "AFG_ApprovalSection", "导入历史", 11, (0.78, 0.84, 0.88, 1.0)),
        _control("AFG_ImportHistoryList", "ListView", "AFG_ApprovalSection", "导入历史：暂无记录", (0, 1, 0, 2)),
        *_row("AFG_ApprovalSummaryRow", "AFG_ApprovalSection", "AFG_ApprovalTitle", "导入策略分组", "AFG_ApprovalSummary", "基础导入 / 网格构建 / 材质贴图 / 高级设置"),
        *_row("AFG_ImportScopeRow", "AFG_ApprovalSection", "AFG_ImportScopeTitle", "导入说明", "AFG_ImportScopeSummary", "检查只写报告；导入只处理当前选中且已放行的包体"),
        _box("AFG_ReportSection", "VerticalBox", "AFG_Workbench", (0, 4, 0, 6)),
        *_button("AFG_ReportSectionHeader", "AFG_ReportSection", "AFG_ReportSectionTitle", "▾ 4 导入策略"),
        *_row("AFG_ReportPathRow", "AFG_ReportSection", "AFG_ReportPathLabel", "报告路径", "AFG_ReportPath", "等待检查报告"),
        *_button("AFG_OpenReportButton", "AFG_ReportSection", "AFG_OpenReportButtonLabel", "打开报告"),
        *_row("AFG_WarningRow", "AFG_ReportSection", "AFG_IssueTitle", "检查报告", "AFG_WarningList", "警告：无", (0.95, 0.75, 0.42, 1.0)),
        *_row("AFG_ErrorRow", "AFG_ReportSection", "AFG_ErrorLabel", "阻断项", "AFG_ErrorList", "阻断：无", (0.95, 0.45, 0.42, 1.0)),
        *_row("AFG_ReportOutputRow", "AFG_ReportSection", "AFG_ReportOutputLabel", "报告输出", "AFG_ReportOutput", "等待检查报告"),
        *_row("AFG_NextActionRow", "AFG_ReportSection", "AFG_NextActionLabel", "下一步", "AFG_NextAction", "先扫描并选择包体", (0.88, 0.90, 0.74, 1.0), 12),
    ],
    "obsolete_widgets": [
        "AFG_ApprovalChecklist",
        "AFG_ApproveMesh",
        "AFG_ApproveTextures",
        "AFG_ApproveMaterials",
    ],
    "data_sections": [
        {"id": "package_history", "source_action": "refresh_packages", "fields": ["latest_package_dir", "package_count", "packages", "status_label"]},
        {
            "id": "package_gate",
            "source_action": "preview_package_gate",
            "fields": [
                "asset_name",
                "target_path",
                "asset_count",
                "mesh_status",
                "texture_count",
                "texture_status",
                "material_count",
                "material_status",
                "profile_name",
                "profile_status",
                "profile_count",
                "can_accept",
                "gate_status",
                "warnings",
                "errors",
                "overwrite_strategy",
            ],
        },
        {"id": "selected_package", "source_action": "select_package", "fields": ["package_dir", "manifest_path", "asset_name", "source_dcc_label", "target_path", "contents"]},
        {"id": "import_history", "source_action": "refresh_packages", "fields": ["last_import_status", "last_import_report_path", "recent_imports", "recent_reports"]},
        {"id": "import_approval", "source_action": "import_package", "fields": ["can_accept", "import_scope", "approved_at", "import_status"]},
        {"id": "gate_report", "source_action": "preview_package_gate", "fields": ["report_path", "latest_report_path", "can_open_report", "warning_count", "error_count", "blocking_checks", "next_action"]},
    ],
}


def get_editor_widget_plan():
    plan = deepcopy(EDITOR_WIDGET_PLAN)
    plan["actions"] = get_action_plan()
    plan["action_count"] = len(plan["actions"])
    return plan


def validate_editor_widget_plan(plan=None):
    active_plan = plan or get_editor_widget_plan()
    issues = []
    asset_path = active_plan.get("asset_path", "")
    disk_directory = active_plan.get("disk_directory", "")
    action_ids = [item.get("id", "") for item in active_plan.get("actions", [])]
    widget_names = [item.get("name", "") for item in active_plan.get("core_widgets", [])]
    data_section_ids = [item.get("id", "") for item in active_plan.get("data_sections", [])]
    action_bindings = active_plan.get("action_bindings", [])
    binding_actions = [item.get("action", "") for item in action_bindings]

    if not asset_path.startswith("/AssetForge/"):
        issues.append("widget asset must live under /AssetForge")
    if asset_path.startswith("/Game/"):
        issues.append("widget asset must not live under project /Game content")
    if not disk_directory.startswith("Plugins/AssetForge/Content"):
        issues.append("widget disk directory must live under plugin Content")
    for required_action in ["refresh_packages", "scan_export_directory", "select_package", "preview_package_gate", "open_report", "dry_run_package", "import_package"]:
        if required_action not in action_ids:
            issues.append("missing widget action: {0}".format(required_action))
        if required_action not in binding_actions:
            issues.append("missing widget action binding: {0}".format(required_action))
    if active_plan.get("asset_type") != "EditorUtilityWidgetBlueprint":
        issues.append("widget asset type must be EditorUtilityWidgetBlueprint")
    if active_plan.get("ui_language") != "zh-CN":
        issues.append("widget UI language must be zh-CN")
    if not active_plan.get("debug_shell_policy", {}).get("forbid_english_debug_shell", False):
        issues.append("widget must forbid English debug shell copy")
    for required_region in REQUIRED_UI_REGIONS:
        if required_region not in active_plan.get("layout_regions", []):
            issues.append("missing widget layout region: {0}".format(required_region))
    for required_widget in REQUIRED_WIDGETS:
        if required_widget not in widget_names:
            issues.append("missing widget core control: {0}".format(required_widget))
    for required_section in REQUIRED_DATA_SECTIONS:
        if required_section not in data_section_ids:
            issues.append("missing widget data section: {0}".format(required_section))
    if _children_of(active_plan, "AFG_Workbench") != REQUIRED_SECTION_ORDER:
        issues.append("widget workbench must use vertical staged sections")
    if _class_by_widget(active_plan, "AFG_Workbench") != "VerticalBox":
        issues.append("widget workbench must be vertical, not a horizontal text strip")
    if _class_by_widget(active_plan, "AFG_ActionBar") != "VerticalBox":
        issues.append("widget action area must be a details-style vertical control group")
    if _parent_by_widget(active_plan, "AFG_ActionBar") != "AFG_PackageSection":
        issues.append("widget action area must live inside package section")
    for widget_name, expected_class in REQUIRED_WIDGET_CLASSES.items():
        if _class_by_widget(active_plan, widget_name) != expected_class:
            issues.append("widget semantic control must use {0}: {1}".format(expected_class, widget_name))
    textblock_count = sum(1 for item in active_plan.get("core_widgets", []) if item.get("class") == "TextBlock")
    widget_count = max(1, len(active_plan.get("core_widgets", [])))
    if float(textblock_count) / float(widget_count) > 0.70:
        issues.append("widget tree still looks like a text-only debug panel")
    if len(active_plan.get("section_layout", [])) != 4:
        issues.append("widget section layout must declare four staged sections")
    for item in active_plan.get("section_layout", []):
        if not item.get("collapsible", False):
            issues.append("widget staged section must be collapsible-ready: {0}".format(item.get("id", "")))
    for text in _visible_texts(active_plan):
        if not _has_chinese(text):
            issues.append("visible widget text must include Chinese copy: {0}".format(text))
        lowered = text.lower()
        for forbidden_text in active_plan.get("debug_shell_policy", {}).get("forbidden_text", FORBIDDEN_DEBUG_TEXT):
            if forbidden_text in lowered:
                issues.append("visible widget text must not use debug shell copy: {0}".format(text))
    return issues


def _children_of(plan, parent):
    return [
        item.get("name", "")
        for item in plan.get("core_widgets", [])
        if item.get("parent", "") == parent
    ]


def _class_by_widget(plan, widget_name):
    for item in plan.get("core_widgets", []):
        if item.get("name", "") == widget_name:
            return item.get("class", "")
    return ""


def _parent_by_widget(plan, widget_name):
    for item in plan.get("core_widgets", []):
        if item.get("name", "") == widget_name:
            return item.get("parent", "")
    return ""


def _visible_texts(plan):
    texts = []
    for item in plan.get("core_widgets", []):
        if item.get("text", ""):
            texts.append(item["text"])
    for item in plan.get("section_layout", []):
        texts.append(item.get("title", ""))
        texts.append(item.get("role", ""))
    for item in plan.get("action_bindings", []):
        texts.append(item.get("purpose", ""))
    return [text for text in texts if text]


def _has_chinese(value):
    return any("\u4e00" <= character <= "\u9fff" for character in value)
