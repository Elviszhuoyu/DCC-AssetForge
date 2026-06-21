from __future__ import absolute_import

from copy import deepcopy
import os
import unittest

from asset_forge.unreal.editor_widget_schema import get_editor_widget_plan, validate_editor_widget_plan


class UnrealEditorWidgetSchemaTest(unittest.TestCase):
    def test_editor_widget_plan_uses_plugin_content_path(self):
        plan = get_editor_widget_plan()

        self.assertEqual(validate_editor_widget_plan(plan), [])
        self.assertEqual(plan["asset_type"], "EditorUtilityWidgetBlueprint")
        self.assertEqual(plan["asset_path"], "/AssetForge/Editor/EUW_AssetForgeGate")
        self.assertFalse(plan["asset_path"].startswith("/Game/"))
        self.assertTrue(plan["disk_directory"].startswith("Plugins/AssetForge/Content"))
        self.assertTrue(os.path.isdir(plan["disk_directory"]))

    def test_editor_widget_plan_binds_package_actions(self):
        plan = get_editor_widget_plan()
        action_ids = [item["id"] for item in plan["actions"]]

        for action_id in [
            "select_package",
            "refresh_packages",
            "scan_export_directory",
            "ensure_widget_asset",
            "read_widget_tree",
            "preview_package_gate",
            "dry_run_package",
            "import_package",
        ]:
            self.assertIn(action_id, action_ids)
        self.assertEqual(plan["action_count"], len(action_ids))
        for region in [
            "workflow_tabs",
            "package_history",
            "local_export_scan",
            "package_contents",
            "mesh_status",
            "texture_status",
            "material_status",
            "profile_status",
            "gate_status",
            "target_and_overwrite",
            "import_history",
            "import_approval",
            "report_output",
        ]:
            self.assertIn(region, plan["layout_regions"])
        widget_names = [item["name"] for item in plan["core_widgets"]]
        for widget_name in [
            "AFG_Workbench",
            "AFG_WorkflowTabs",
            "AFG_PackageSection",
            "AFG_ReviewSection",
            "AFG_ApprovalSection",
            "AFG_ReportSection",
            "AFG_RecentPackageList",
            "AFG_SourceFilter",
            "AFG_RuleFilter",
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
        ]:
            self.assertIn(widget_name, widget_names)

    def test_editor_widget_plan_declares_chinese_vertical_gate_ui(self):
        plan = get_editor_widget_plan()

        self.assertEqual(plan["ui_language"], "zh-CN")
        self.assertTrue(plan["rebuild_tree"])
        self.assertTrue(plan["debug_shell_policy"]["forbid_english_debug_shell"])
        self.assertIn("全中文文案，不使用英文调试壳", plan["design_intent"]["visual_rules"])
        self.assertIn("采用 UE 官方 Details Panel 式分类、属性行和短标签", plan["design_intent"]["visual_rules"])
        self.assertEqual(
            [item["container"] for item in plan["section_layout"]],
            ["AFG_PackageSection", "AFG_ReviewSection", "AFG_ApprovalSection", "AFG_ReportSection"],
        )
        self.assertEqual(
            _children_of(plan, "AFG_Workbench"),
            ["AFG_PackageSection", "AFG_ReviewSection", "AFG_ApprovalSection", "AFG_ReportSection"],
        )
        self.assertEqual(_parent_of(plan, "AFG_ActionBar"), "AFG_PackageSection")
        self.assertEqual(_class_of(plan, "AFG_ActionBar"), "VerticalBox")
        self.assertEqual(_parent_of(plan, "AFG_GlobalSearch"), "AFG_Header")
        self.assertEqual(_class_of(plan, "AFG_GlobalSearch"), "EditableTextBox")
        self.assertEqual(_class_of(plan, "AFG_RecentPackageList"), "ListView")
        self.assertEqual(_class_of(plan, "AFG_ImportHistoryList"), "ListView")
        self.assertEqual(_class_of(plan, "AFG_SourceFilter"), "ComboBoxString")
        self.assertEqual(_class_of(plan, "AFG_RuleFilter"), "ComboBoxString")
        self.assertEqual(_class_of(plan, "AFG_ImportScopeSummary"), "TextBlock")
        self.assertNotIn("AFG_ApproveMesh", [item["name"] for item in plan["core_widgets"]])
        self.assertNotIn("AFG_ApproveTextures", [item["name"] for item in plan["core_widgets"]])
        self.assertNotIn("AFG_ApproveMaterials", [item["name"] for item in plan["core_widgets"]])
        self.assertIn("AFG_ApproveMesh", plan["obsolete_widgets"])
        self.assertIn("AFG_ApproveTextures", plan["obsolete_widgets"])
        self.assertIn("AFG_ApproveMaterials", plan["obsolete_widgets"])
        self.assertIn("Asset Forge 导入门禁工作台", _text_by_widget(plan, "AFG_BrandName"))
        self.assertEqual(
            [item["title"] for item in plan["section_layout"]],
            ["1 包体来源", "2 导入控制", "3 包体内容", "4 导入策略"],
        )
        self.assertTrue(all(item["collapsible"] for item in plan["section_layout"]))

    def test_editor_widget_plan_covers_gate_data_sections_and_bindings(self):
        plan = get_editor_widget_plan()
        sections = dict((item["id"], item) for item in plan["data_sections"])
        bindings = dict((item["action"], item["widget"]) for item in plan["action_bindings"])

        for section_id in [
            "package_history",
            "package_gate",
            "selected_package",
            "import_history",
            "import_approval",
            "gate_report",
        ]:
            self.assertIn(section_id, sections)
        self.assertEqual(sections["package_history"]["source_action"], "refresh_packages")
        self.assertEqual(sections["package_gate"]["source_action"], "preview_package_gate")
        self.assertEqual(sections["selected_package"]["source_action"], "select_package")
        self.assertEqual(sections["import_history"]["source_action"], "refresh_packages")
        self.assertEqual(sections["import_approval"]["source_action"], "import_package")
        self.assertEqual(sections["gate_report"]["source_action"], "preview_package_gate")
        self.assertIn("packages", sections["package_history"]["fields"])
        self.assertIn("contents", sections["selected_package"]["fields"])
        self.assertIn("recent_reports", sections["import_history"]["fields"])
        self.assertIn("import_scope", sections["import_approval"]["fields"])
        self.assertIn("can_open_report", sections["gate_report"]["fields"])
        self.assertIn("next_action", sections["gate_report"]["fields"])
        self.assertEqual(bindings["scan_export_directory"], "AFG_ScanExportDirectoryButton")
        self.assertEqual(bindings["select_package"], "AFG_RecentPackageList")
        self.assertEqual(bindings["open_report"], "AFG_OpenReportButton")
        self.assertEqual(bindings["import_package"], "AFG_ImportButton")

    def test_editor_widget_visible_copy_is_chinese_not_debug_shell(self):
        plan = get_editor_widget_plan()
        forbidden_text = plan["debug_shell_policy"]["forbidden_text"]

        for text in _visible_texts(plan):
            self.assertTrue(_has_chinese(text), text)
            self.assertFalse(any(item in text.lower() for item in forbidden_text), text)
        self.assertIn("扫描导出目录", _text_by_widget(plan, "AFG_ScanExportDirectoryButtonLabel"))
        self.assertIn("AF 锻造", _text_by_widget(plan, "AFG_BrandMark"))
        self.assertIn("选中包体", _text_by_widget(plan, "AFG_SelectedPackageTitle"))
        self.assertIn("包内资产", _text_by_widget(plan, "AFG_PackageContentsTitle"))
        self.assertIn("导入历史", _text_by_widget(plan, "AFG_ImportHistoryTitle"))
        self.assertIn("导入策略分组", _text_by_widget(plan, "AFG_ApprovalTitle"))
        self.assertIn("基础导入 / 网格构建 / 材质贴图 / 高级设置", _text_by_widget(plan, "AFG_ApprovalSummary"))
        self.assertIn("检查只写报告", _text_by_widget(plan, "AFG_ImportScopeSummary"))
        self.assertIn("检查报告", _text_by_widget(plan, "AFG_IssueTitle"))
        self.assertIn("打开报告", _text_by_widget(plan, "AFG_OpenReportButtonLabel"))

    def test_editor_widget_validation_rejects_schema_regressions(self):
        plan = get_editor_widget_plan()
        broken = deepcopy(plan)
        broken["ui_language"] = "en-US"
        broken["core_widgets"] = [
            item for item in broken["core_widgets"] if item["name"] != "AFG_ApprovalSection"
        ]
        broken["data_sections"] = [
            item for item in broken["data_sections"] if item["id"] != "gate_report"
        ]
        broken["core_widgets"].append(
            {"name": "AFG_DebugShellTitle", "class": "TextBlock", "parent": "AFG_Root", "text": "Debug Placeholder"}
        )

        issues = validate_editor_widget_plan(broken)

        self.assertIn("widget UI language must be zh-CN", issues)
        self.assertIn("missing widget core control: AFG_ApprovalSection", issues)
        self.assertIn("missing widget data section: gate_report", issues)
        self.assertTrue(any("vertical staged sections" in issue for issue in issues))
        self.assertTrue(any("debug shell copy" in issue for issue in issues))

    def test_editor_widget_validation_rejects_text_only_regressions(self):
        plan = get_editor_widget_plan()
        broken = deepcopy(plan)
        for item in broken["core_widgets"]:
            if item["name"] in ("AFG_GlobalSearch", "AFG_RecentPackageList", "AFG_ImportHistoryList"):
                item["class"] = "TextBlock"

        issues = validate_editor_widget_plan(broken)

        self.assertIn("widget semantic control must use EditableTextBox: AFG_GlobalSearch", issues)
        self.assertIn("widget semantic control must use ListView: AFG_RecentPackageList", issues)
        self.assertIn("widget semantic control must use ListView: AFG_ImportHistoryList", issues)

    def test_editor_widget_plan_records_official_sources(self):
        plan = get_editor_widget_plan()

        self.assertTrue(all(source.startswith("https://dev.epicgames.com/") for source in plan["official_sources"]))


def _children_of(plan, parent):
    return [
        item["name"]
        for item in plan["core_widgets"]
        if item.get("parent", "") == parent
    ]


def _parent_of(plan, widget_name):
    for item in plan["core_widgets"]:
        if item["name"] == widget_name:
            return item.get("parent", "")
    return ""


def _class_of(plan, widget_name):
    for item in plan["core_widgets"]:
        if item["name"] == widget_name:
            return item.get("class", "")
    return ""


def _visible_texts(plan):
    texts = []
    for item in plan["core_widgets"]:
        if item.get("text", ""):
            texts.append(item["text"])
    for item in plan["section_layout"]:
        texts.append(item["title"])
        texts.append(item["role"])
    for item in plan["action_bindings"]:
        texts.append(item["purpose"])
    return texts


def _text_by_widget(plan, widget_name):
    for item in plan["core_widgets"]:
        if item["name"] == widget_name:
            return item.get("text", "")
    return ""


def _has_chinese(value):
    return any("\u4e00" <= character <= "\u9fff" for character in value)


if __name__ == "__main__":
    unittest.main()
