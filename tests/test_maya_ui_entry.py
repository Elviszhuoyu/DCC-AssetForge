from __future__ import absolute_import

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from asset_forge.maya.pipeline import MayaStaticPropPipeline
import asset_forge.maya.ui as maya_ui
from asset_forge.maya.ui import (
    AssetForgeMayaWindow,
    BUILD_LABEL,
    _asset_card_state,
    _export_log_outputs,
    _export_card_state,
    _format_log_entry,
    _issue_card_state,
    _overview_panel_state,
    _polish_next_action_text,
    _polish_status_text,
    _texture_card_state,
    format_asset_card,
    format_empty_preflight_details,
    format_empty_selection_guidance,
    format_empty_texture_details,
    format_asset_identity,
    format_export_card,
    format_export_stage,
    format_issue_card,
    format_issue_locator,
    format_overview_panel,
    format_blocking_validation_summary,
    format_check_stage,
    format_preflight_summary,
    format_scan_stage,
    format_texture_card,
    repair_actions_for_state,
)


class MayaUiEntryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_build_label_is_visible_for_user_verification(self):
        self.assertIn("v0.1.8", BUILD_LABEL)
        self.assertIn("Build 2026-06-03-R10", BUILD_LABEL)

    def test_maya_icon_assets_are_pre_scaled_for_maya_controls(self):
        resource_dir = Path(__file__).resolve().parents[1] / "Plugins" / "AssetForge" / "Resources"

        expected_sizes = {"IconMayaHeader.png": (48, 48), "IconMayaShelf.png": (32, 32), "IconMayaMcpShelf.png": (32, 32)}
        for filename, expected_size in expected_sizes.items():
            with Image.open(resource_dir / filename) as image:
                self.assertEqual(image.size, expected_size)

        expected_accents = {
            "IconMayaShelf.png": (49, 211, 132, 255),
            "IconMayaMcpShelf.png": (54, 186, 230, 255),
        }
        for filename, accent in expected_accents.items():
            with Image.open(resource_dir / filename) as image:
                rgba = image.convert("RGBA")
                for x in range(32):
                    for y in range(29, 32):
                        self.assertEqual(rgba.getpixel((x, y)), accent)
                large_letter_pixels = self._bright_pixel_count(rgba, 4, 8, 18, 27)
                suffix_pixels = self._bright_pixel_count(rgba, 18, 3, 29, 14)
                self.assertGreaterEqual(large_letter_pixels, 45)
                self.assertGreaterEqual(suffix_pixels, 8)

    def _bright_pixel_count(self, image, x0, y0, x1, y1):
        return sum(
            1
            for y in range(y0, y1)
            for x in range(x0, x1)
            if min(image.getpixel((x, y))[:3]) >= 190
        )

    def test_target_path_strips_trailing_newline(self):
        window = AssetForgeMayaWindow(cmds_module=FakeUiCmds("/Game/Props/Test01\n"), pipeline=FakePipeline(), log_root=self.temp_dir)
        window.controls["target_path"] = "target_path"

        self.assertEqual(window._target_path(), "/Game/Props/Test01")

    def test_target_path_rejects_internal_control_character(self):
        window = AssetForgeMayaWindow(cmds_module=FakeUiCmds("/Game/Props/Te\nst"), pipeline=FakePipeline(), log_root=self.temp_dir)
        window.controls["target_path"] = "target_path"

        with self.assertRaises(RuntimeError):
            window._target_path()

    def test_asset_identity_and_name_prefix_blocker_are_actionable(self):
        scan = _blocked_scan()
        validation = _blocked_validation()

        identity = format_asset_identity(scan)
        summary = format_preflight_summary(scan, validation, {})

        self.assertIn("当前导出资产名：zuti", identity)
        self.assertIn("来源：所选父组/共同父节点", identity)
        self.assertIn("当前资产根节点：|zuti|SM_B_a", identity)
        self.assertIn("资产名来源节点：|zuti", identity)
        self.assertIn("当前选择根节点：2 个，将作为一个资产包导出。", identity)
        self.assertIn("- |zuti|SM_B_a", identity)
        self.assertIn("命名说明：多个选择共享同一父节点，资产名来自共同父节点。", identity)
        self.assertIn("Mesh 数量：2", identity)
        self.assertIn("三角面：1200", identity)
        self.assertIn("当前导出资产名：zuti", summary)
        self.assertIn("导出资产名缺少 SM_ 前缀", summary)
        self.assertIn("当前导出资产名 zuti 来自所选父组/共同父节点；它缺少 SM_ 前缀，因此不能导出。", summary)
        self.assertIn("手动把导出资产名改成 SM_zuti", summary)
        self.assertIn("一键修复资产名前缀", summary)
        self.assertIn("修复队列", summary)
        self.assertNotIn("id=fix_asset_name_prefix", summary)
        self.assertIn("问题=导出资产名缺少 SM_ 前缀", summary)
        self.assertIn("入口=点击“修复资产名前缀”按钮", summary)
        self.assertNotIn("_rename_prefix", summary)
        self.assertIn("报告=预检阶段不写报告；导出被阻断时会写调试报告。", summary)
        self.assertNotIn("mesh_exists", summary)

    def test_asset_identity_guides_empty_selection_and_first_selection_naming(self):
        empty_identity = format_asset_identity({})
        first_selection_identity = format_asset_identity(_first_selection_scan())

        self.assertIn("当前资产根节点：未扫描", empty_identity)
        self.assertIn("场景唯一可导出资产", empty_identity)
        self.assertIn("自动兜底", empty_identity)
        self.assertIn("多个候选资产，它不会猜测", empty_identity)
        self.assertIn("当前资产根节点：|SM_A", first_selection_identity)
        self.assertIn("资产名来源节点：|SM_A", first_selection_identity)
        self.assertIn("当前选择没有共同父节点", first_selection_identity)
        self.assertIn("请选择共同父组", first_selection_identity)

    def test_empty_selection_error_explains_auto_fallback_boundary(self):
        cmds = FakeFullUiCmds(os.path.join(self.temp_dir, "settings.json"))
        pipeline = FakePipeline()
        pipeline.selection = []
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=pipeline, log_root=self.temp_dir)
        window.controls = _fake_full_controls()

        window._export()

        self.assertIn(format_empty_selection_guidance(), cmds.results)
        self.assertIn("多个候选资产，它不会猜测", cmds.results)
        self.assertFalse(pipeline.export_called)

    def test_blocking_validation_summary_excludes_pass_checks(self):
        text = format_blocking_validation_summary(_blocked_validation(), _blocked_scan(), "D:/Reports/zuti_export_blocked_report.json")

        self.assertIn("name_prefix", text)
        self.assertNotIn("mesh_exists", text)
        self.assertIn("调试报告", text)

    def test_repair_actions_are_structured_for_blockers_and_texture_fixes(self):
        actions = repair_actions_for_state(
            _blocked_scan(),
            _blocked_validation(),
            {
                "issues": [{"id": "texture_set_auto_selected"}],
                "rename_suggestions": [{"suggested_name": "T_HK416_D_B_a1_BaseColor.png"}],
            },
        )

        by_id = dict((item["id"], item) for item in actions)
        self.assertEqual(by_id["fix_asset_name_prefix"]["ui_callback"], "_rename_prefix")
        self.assertEqual(by_id["fix_asset_name_prefix"]["expected_asset_name"], "SM_zuti")
        self.assertEqual(by_id["fix_asset_name_prefix"]["label"], "修复资产名前缀")
        self.assertEqual(by_id["fix_asset_name_prefix"]["button_label"], "修复资产名前缀")
        self.assertEqual(by_id["fix_asset_name_prefix"]["target_label"], "修复资产名前缀按钮")
        self.assertEqual(by_id["fix_asset_name_prefix"]["problem"], "导出资产名缺少 SM_ 前缀")
        self.assertIn("SM_zuti", by_id["fix_asset_name_prefix"]["next_step"])
        self.assertTrue(by_id["fix_asset_name_prefix"]["can_run_from_ui_flow"])
        self.assertEqual(by_id["review_texture_set_issues"]["label"], "检查贴图集问题")
        self.assertEqual(by_id["review_texture_set_issues"]["problem"], "texture_set_auto_selected")
        self.assertEqual(by_id["review_texture_set_issues"]["field_label"], "贴图集关键词")
        self.assertEqual(by_id["review_texture_set_issues"]["field"], "texture_set_token")
        self.assertEqual(by_id["review_texture_set_issues"]["example"], "a1,d1")
        self.assertEqual(by_id["fix_texture_prefix"]["label"], "修复贴图前缀")
        self.assertEqual(by_id["fix_texture_prefix"]["button_label"], "修复贴图前缀")
        self.assertEqual(by_id["fix_texture_prefix"]["ui_callback"], "_rename_texture_prefix")
        self.assertEqual(by_id["fix_texture_prefix"]["planned_count"], 1)

    def test_latest_log_entry_summary_shows_repair_actions(self):
        text = _format_log_entry(
            {
                "timestamp": "2026-06-01T15:00:00",
                "operation": "export_preflight_blocked",
                "status": "error",
                "outputs": {
                    "can_export": False,
                    "error_count": 1,
                    "repair_actions": [
                        {
                            "id": "fix_asset_name_prefix",
                            "label": "修复资产名前缀",
                            "problem": "导出资产名缺少 SM_ 前缀",
                            "button_label": "修复资产名前缀",
                            "ui_callback": "_rename_prefix",
                            "next_action": "点击修复资产名前缀。",
                        }
                    ],
                    "report_path": "D:/Reports/zuti_export_blocked_report.json",
                    "portfolio_capture_hint": "录制前看这里：资产 zuti 还不能导出；先展示第一个修复项“修复资产名前缀”；打开阻断报告 D:/Reports/zuti_export_blocked_report.json；下一步点对应入口后重新检查。",
                },
            }
        )

        self.assertIn("导出前检查未通过 | 错误", text)
        self.assertIn("修复项=1", text)
        self.assertIn("首个修复=修复资产名前缀", text)
        self.assertIn("问题=导出资产名缺少 SM_ 前缀", text)
        self.assertIn("修复入口=点击“修复资产名前缀”按钮", text)
        self.assertNotIn("_rename_prefix", text)
        self.assertIn("修复下一步=点击修复资产名前缀。", text)
        self.assertIn("录制提示=录制前看这里：资产 zuti 还不能导出", text)
        self.assertIn("报告=D:/Reports/zuti_export_blocked_report.json", text)

    def test_texture_folder_scan_summary_uses_short_sections_and_no_legacy_wording(self):
        window = AssetForgeMayaWindow(cmds_module=FakeUiCmds("/Game/Props"), pipeline=FakePipeline(), log_root=self.temp_dir)

        text = window._format_texture_folder_scan(
            {
                "directory_status": "valid",
                "selected_texture_set_short_names": ["a1", "d1"],
                "selected_texture_sets": ["HK416_D_B_a1", "HK416_D_B_d1"],
                "matched_count": 6,
                "matched_usages": ["base_color", "normal", "orm", "base_color", "normal", "orm"],
                "texture_sets": [{"short_name": "a1", "set_name": "HK416_D_B_a1", "completeness": 1.0, "usages": ["base_color", "normal"], "missing_usages": []}],
                "issues": [],
                "rename_suggestions": [],
            }
        )

        self.assertIn("状态：", text)
        self.assertIn("候选贴图集：", text)
        self.assertIn("当前选择：", text)
        self.assertIn("已选贴图集：HK416_D_B_a1, HK416_D_B_d1", text)
        self.assertIn("将导出贴图数量：", text)
        self.assertIn("将导出用途：", text)
        self.assertIn("已按当前关键词选择贴图集", text)
        self.assertIn("下一步建议：", text)
        self.assertNotIn("贴图集 " + "Token", text)

    def test_status_cards_are_compact_operator_summaries(self):
        scan = _successful_scan()
        validation = _successful_validation()
        texture_scan = scan["texture_folder_scan"]

        self.assertEqual(format_asset_card(scan), "资产 | SM_B · Mesh 1 · Tri 1.2k")
        self.assertEqual(format_texture_card(texture_scan, scan), "贴图 | 就绪 · 3 张 · 问题 0")
        self.assertEqual(format_issue_card(validation), "风险 | 通过 · 阻断 0 · 警告 0")
        self.assertEqual(format_export_card(scan, validation, texture_scan), "发布 | 可导出 · 贴图 3 张")
        self.assertEqual(format_scan_stage(scan), "01 扫描资产 · 已识别 SM_B")
        self.assertEqual(format_check_stage(scan, validation), "02 检查风险 · 通过")
        self.assertEqual(format_export_stage(scan, validation), "03 导出 Package · 可导出")
        overview = format_overview_panel(scan, validation, texture_scan)
        self.assertIn("通过 | 预检完成，可以导出 Package 给 UE Gate", overview)
        self.assertIn("资产 SM_B / Mesh 1 / Tri 1.2k", overview)
        self.assertIn("贴图 3 张 / 问题 0", overview)
        self.assertIn("风险 通过", overview)

    def test_status_and_next_action_text_are_polished_for_cards(self):
        self.assertEqual(_polish_status_text("状态：模型扫描完成"), "状态 | 模型扫描完成")
        self.assertEqual(_polish_next_action_text("下一步：点击检查"), "下一步 | 点击检查")
        self.assertEqual(format_asset_card({}), "资产 | 未扫描 · 选择后扫描")
        self.assertEqual(format_texture_card({}), "贴图 | 未扫描 · 选择目录")
        self.assertEqual(format_issue_card({}), "风险 | 未预检 · 扫描后检查")
        self.assertEqual(format_export_card({}, {}), "发布 | 等待扫描 · 资产和预检")

    def test_status_cards_have_semantic_visual_states(self):
        scan = _successful_scan()
        validation = _successful_validation()
        texture_scan = scan["texture_folder_scan"]

        self.assertEqual(_asset_card_state(scan), "ok")
        self.assertEqual(_texture_card_state(texture_scan, scan), "ok")
        self.assertEqual(_issue_card_state(validation), "ok")
        self.assertEqual(_export_card_state(scan, validation, texture_scan), "ok")
        self.assertEqual(_asset_card_state({}), "waiting")
        self.assertEqual(_texture_card_state({}, {}), "waiting")
        self.assertEqual(_issue_card_state({}), "waiting")
        self.assertEqual(_export_card_state({}, {}, {}), "waiting")
        self.assertEqual(_overview_panel_state({}, {}, {}), "panel")
        self.assertEqual(_overview_panel_state(scan, {}, {}), "info")
        self.assertEqual(_overview_panel_state(scan, validation, texture_scan), "ok")
        self.assertEqual(_overview_panel_state(scan, _blocked_validation(), texture_scan), "error")
        self.assertEqual(_issue_card_state(_blocked_validation()), "error")
        self.assertEqual(_export_card_state(scan, _blocked_validation(), texture_scan), "error")
        self.assertEqual(_texture_card_state({"issues": [{"message": "多套贴图待确认"}]}, scan), "warning")

    def test_log_operation_refreshes_last_maya_log_control(self):
        cmds = FakeFullUiCmds(os.path.join(self.temp_dir, "settings.json"))
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=FakePipeline(), log_root=self.temp_dir)
        window.controls = _fake_full_controls()

        window._log_operation("scan_model", "success", outputs={"asset_name": "SM_Test"})

        self.assertIn("扫描资产", cmds.scroll_values["last_maya_log"])
        self.assertNotIn("scan_model", cmds.scroll_values["last_maya_log"])
        self.assertIn("日志路径：", cmds.scroll_values["last_maya_log"])

    def test_export_debug_bundle_writes_ai_readable_snapshot(self):
        cmds = FakeFullUiCmds(os.path.join(self.temp_dir, "settings.json"))
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=FakePipeline(), log_root=self.temp_dir)
        window.controls = _fake_full_controls()
        window.last_scan = _successful_scan()
        window.last_validation = _successful_validation()
        window.last_texture_scan = _successful_scan()["texture_folder_scan"]
        window.last_package_dir = "D:/Exports/SM_B"
        window.last_selection = ["|SM_B"]

        window._export_debug_bundle()

        self.assertIn("调试信息已导出", cmds.results)
        debug_path = cmds.results.split("调试信息已导出：", 1)[1].split("\n", 1)[0].replace("/", os.sep)
        self.assertTrue(os.path.exists(debug_path))
        with open(debug_path, "r", encoding="utf-8") as stream:
            text = stream.read()
        self.assertIn("Asset Forge v0.1.8", text)
        self.assertIn("[settings]", text)
        self.assertIn("[scan]", text)

    def test_export_log_outputs_include_debuggable_package_summary(self):
        outputs = _export_log_outputs(
            {
                "scan": {
                    "asset_name": "SM_zuti",
                    "mesh_count": 2,
                    "textures": [{}, {}, {}, {}, {}, {}],
                    "texture_folder_scan": {
                        "matched_count": 6,
                        "texture_set_token": "a1,d1",
                        "selected_texture_sets": ["HK416_D_B_a1", "HK416_D_B_d1"],
                    },
                },
                "validation": {"status": "warning", "can_export": True, "summary": {"warnings": 1, "errors": 0}},
                "manifest": {"texture_import_policy": {"virtual_texture_policy": "auto", "texture_streaming_policy": "never_stream"}},
                "manifest_path": "D:/exp/SM_zuti/SM_zuti_manifest.json",
                "package_dir": "D:/exp/SM_zuti",
            }
        )

        self.assertEqual(outputs["asset_name"], "SM_zuti")
        self.assertEqual(outputs["mesh_count"], 2)
        self.assertEqual(outputs["matched_count"], 6)
        self.assertEqual(outputs["texture_set_token"], "a1,d1")
        self.assertEqual(outputs["warning_count"], 1)
        self.assertEqual(outputs["error_count"], 0)
        self.assertEqual(outputs["can_import"], "pending_ue_dry_run")
        self.assertEqual(outputs["report_path"], "")
        self.assertIn("录制前看这里：资产 SM_zuti 已可导出", outputs["portfolio_capture_hint"])
        self.assertIn("下一步在 UE Gate 选择该 Package，生成入审报告、预演导入计划、正式导入", outputs["portfolio_capture_hint"])
        self.assertEqual(outputs["operator_action"], "UE Gate: 选择该 Package -> 生成入审报告 -> 预演导入计划 -> 正式导入")
        self.assertIn("选择该 Package", outputs["next_step"])
        self.assertEqual(outputs["texture_import_policy"]["texture_streaming_policy"], "never_stream")

    def test_export_result_summary_is_operator_readable(self):
        summary = maya_ui.format_export_result_summary(
            {
                "scan": _successful_scan(),
                "validation": _successful_validation(),
                "manifest_path": "D:/Exports/SM_B/SM_B_manifest.json",
                "package_dir": "D:/Exports/SM_B",
                "export_report_path": "D:/Exports/SM_B/SM_B_export_report.json",
            }
        )

        self.assertIn("导出完成 | Package 已生成，等待 UE Gate", summary)
        self.assertIn("发布包：D:/Exports/SM_B", summary)
        self.assertIn("报告：D:/Exports/SM_B/SM_B_export_report.json", summary)
        self.assertIn("状态：可导出=true | UE Gate=待生成入审报告 | 警告/阻断=0/0", summary)
        self.assertIn("UE Gate: 选择该 Package -> 生成入审报告 -> 预演导入计划 -> 正式导入", summary)
        self.assertIn("录制前看这里：资产 SM_B 已可导出；打开导出报告 D:/Exports/SM_B/SM_B_export_report.json", summary)
        self.assertIn("下一步：在 UE Gate 里选择该 Package，按清单生成入审报告、预演导入计划、正式导入", summary)

    def test_blocked_export_result_summary_reuses_validation_counts(self):
        summary = maya_ui.format_export_blocked_result(
            _blocked_scan(),
            _blocked_validation(),
            "D:/Reports/zuti_export_blocked_report.json",
        )

        self.assertIn("导出阻断 | Package 未生成", summary)
        self.assertIn("发布包：未生成", summary)
        self.assertIn("报告：D:/Reports/zuti_export_blocked_report.json", summary)
        self.assertIn("状态：可导出=false | UE Gate=false | 警告/阻断=0/1", summary)
        self.assertIn("修复：先处理第一阻断项 -> 重新检查 -> 再导出", summary)
        self.assertIn("第一阻断：导出资产名缺少 SM_ 前缀", summary)
        self.assertIn("录制前看这里：资产 zuti 还不能导出；先展示第一个修复项“修复资产名前缀”", summary)
        self.assertIn("打开阻断报告 D:/Reports/zuti_export_blocked_report.json；下一步点对应入口后重新检查", summary)
        self.assertIn("下一步：先修复第一阻断项：导出资产名缺少 SM_ 前缀；然后重新检查并重试导出", summary)
        self.assertIn("修复队列：", summary)
        self.assertIn("修复资产名前缀：问题=导出资产名缺少 SM_ 前缀", summary)
        self.assertNotIn("id=fix_asset_name_prefix", summary)
        self.assertIn("问题=导出资产名缺少 SM_ 前缀", summary)
        self.assertIn("入口=点击“修复资产名前缀”按钮", summary)
        self.assertNotIn("_rename_prefix", summary)
        self.assertIn("报告=D:/Reports/zuti_export_blocked_report.json", summary)

    def test_save_project_settings_handler_writes_json_with_suffix(self):
        target = os.path.join(self.temp_dir, "asset_forge_project")
        cmds = FakeFullUiCmds(target)
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=FakePipeline(), log_root=self.temp_dir)
        window.controls = _fake_full_controls()

        window._save_project_settings()

        saved = target + ".json"
        self.assertTrue(os.path.exists(saved))
        with open(saved, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        self.assertEqual(data["mesh_prefix"], "SM_")
        self.assertEqual(data["texture_prefix"], "T_")
        self.assertIn(saved.replace("\\", "/"), cmds.results)
        self.assertIn("已保存", cmds.settings_label)
        self.assertIn("保存项目设置", cmds.scroll_values["last_maya_log"])
        self.assertNotIn("save_project_settings", cmds.scroll_values["last_maya_log"])

    def test_save_project_settings_handler_normalizes_wildcard_path(self):
        target = os.path.join(self.temp_dir, "test01_config.*")
        cmds = FakeFullUiCmds(target)
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=FakePipeline(), log_root=self.temp_dir)
        window.controls = _fake_full_controls()

        window._save_project_settings()

        saved = os.path.join(self.temp_dir, "test01_config.json")
        self.assertTrue(os.path.exists(saved))
        self.assertFalse(os.path.exists(target))

    def test_scan_apply_save_logs_include_settings_snapshot(self):
        target = os.path.join(self.temp_dir, "settings.json")
        cmds = FakeFullUiCmds(target)
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=FakePipeline(), log_root=self.temp_dir)
        window.controls = _fake_full_controls()

        window._save_project_settings()

        latest = os.path.join(self.temp_dir, "AssetForgeReports", "logs", "latest_maya.log")
        with open(latest, "r", encoding="utf-8") as stream:
            data = json.loads(stream.readlines()[-1])
        self.assertIn("settings", data["inputs"])
        self.assertEqual(data["inputs"]["settings"]["export_root"], "D:/Exports")

    def test_applied_project_settings_preserve_unicode_paths_when_ui_field_degrades(self):
        cmds = FakeUnicodePathCmds(os.path.join(self.temp_dir, "settings.json"))
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=FakePipeline(), log_root=self.temp_dir)
        window.controls = _fake_full_controls()
        settings = {
            "export_root": "E:/Repo/导出",
            "texture_root": "E:/Repo/测试/Test01/Tex",
            "ue_target_path": "/Game/Props/HK416D_UI",
            "mesh_prefix": "SM_",
            "texture_prefix": "T_",
            "texture_set_token": "a1,d1,b1",
            "asset_name_override": "SM_HK416D_Custom",
            "build_reversed_index_buffer": "enable",
            "generate_lightmap_uvs": "disable",
            "collision_complexity": "use_complex_as_simple",
        }

        window._apply_project_settings(settings)
        active = window._settings_from_ui()

        self.assertEqual(active["export_root"], "E:/Repo/导出")
        self.assertEqual(active["texture_root"], "E:/Repo/测试/Test01/Tex")
        self.assertEqual(active["asset_name_override"], "SM_HK416D_Custom")
        self.assertEqual(active["build_reversed_index_buffer"], "enable")
        self.assertEqual(active["generate_lightmap_uvs"], "disable")
        self.assertEqual(active["collision_complexity"], "use_complex_as_simple")

    def test_export_blocked_by_preflight_does_not_call_real_export(self):
        cmds = FakeFullUiCmds(os.path.join(self.temp_dir, "settings.json"))
        pipeline = FakePipeline()
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=pipeline, log_root=self.temp_dir)
        window.controls = _fake_full_controls()

        window._export()

        self.assertFalse(pipeline.export_called)
        self.assertTrue(pipeline.blocked_report_written)
        self.assertIn("导出阻断 | Package 未生成", cmds.results)
        self.assertIn("报告", cmds.results)
        self.assertIn("状态：可导出=false | UE Gate=false | 警告/阻断=0/1", cmds.results)
        self.assertIn("修复：先处理第一阻断项 -> 重新检查 -> 再导出", cmds.results)
        self.assertIn("第一阻断：导出资产名缺少 SM_ 前缀", cmds.results)
        self.assertIn("下一步：先修复第一阻断项：导出资产名缺少 SM_ 前缀；然后重新检查并重试导出", cmds.results)
        self.assertIn("问题=导出资产名缺少 SM_ 前缀", cmds.results)
        self.assertIn("报告=D:/Reports/zuti_export_blocked_report.json", cmds.results)
        self.assertIn("UE Gate=false", cmds.scroll_values["last_maya_log"])
        self.assertIn("警告=0", cmds.scroll_values["last_maya_log"])
        self.assertIn("阻断=1", cmds.scroll_values["last_maya_log"])
        self.assertIn("问题=导出资产名缺少 SM_ 前缀", cmds.scroll_values["last_maya_log"])
        self.assertIn("报告=D:/Reports/zuti_export_blocked_report.json", cmds.scroll_values["last_maya_log"])
        self.assertIn("导出资产名缺少 SM_ 前缀", cmds.scroll_values["preflight"])

    def test_export_auto_rescans_when_selection_changed(self):
        cmds = FakeFullUiCmds(os.path.join(self.temp_dir, "settings.json"))
        pipeline = FakePipeline()
        pipeline.selection = ["|zuti|SM_B_new"]
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=pipeline, log_root=self.temp_dir)
        window.controls = _fake_full_controls()
        window.last_selection = ["|old|SM_Old"]

        window._export()

        self.assertFalse(pipeline.export_called)
        self.assertIn("选择已变化", cmds.scroll_values["preflight"])
        self.assertEqual(pipeline.preflight_selection, ["|zuti|SM_B_new"])

    def test_real_window_export_success_passes_frontend_settings_to_pipeline(self):
        cmds = FakeEditableUiCmds(os.path.join(self.temp_dir, "settings.json"))
        pipeline = FakeExportSuccessPipeline()
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=pipeline, log_root=self.temp_dir)
        window.controls = _fake_full_controls()

        window._export()

        self.assertTrue(pipeline.export_called)
        self.assertEqual(pipeline.preflight_calls, 1)
        self.assertEqual(pipeline.export_args["selection"], ["|SM_B"])
        self.assertEqual(pipeline.export_args["output_dir"], "D:/Exports")
        self.assertEqual(pipeline.export_args["target_path"], "/Game/Props/HK416D")
        self.assertEqual(pipeline.export_args["material_profile"], "Props_Opaque_PainterUE_ARM")
        self.assertEqual(pipeline.export_args["texture_folder"], "D:/Textures")
        self.assertEqual(pipeline.export_args["texture_set_token"], "a1,d1")
        self.assertEqual(
            pipeline.export_args["texture_import_policy"],
            {"virtual_texture_policy": "force_off", "texture_streaming_policy": "streaming", "texture_group": "project_default"},
        )
        self.assertEqual(
            pipeline.export_args["static_mesh_import_policy"],
            {
                "nanite_policy": "disable",
                "lod_group": "SmallProp",
                "import_lod_policy": "report_only",
                "build_reversed_index_buffer": "report_only",
                "generate_lightmap_uvs": "report_only",
                "collision_complexity": "report_only",
            },
        )
        self.assertEqual(window.last_package_dir, "D:/Exports/SM_B")
        self.assertIn("清单：", cmds.results)
        self.assertIn("发布包：D:/Exports/SM_B", cmds.results)
        self.assertIn("报告：D:/Exports/SM_B/SM_B_export_report.json", cmds.results)
        self.assertIn("状态：可导出=true | UE Gate=待生成入审报告 | 警告/阻断=0/0", cmds.results)
        self.assertIn("UE Gate: 选择该 Package -> 生成入审报告 -> 预演导入计划 -> 正式导入", cmds.results)
        self.assertIn("下一步：在 UE Gate 里选择该 Package，按清单生成入审报告、预演导入计划、正式导入", cmds.results)
        self.assertIn("日志路径：", cmds.results)
        self.assertIn("导出成功", cmds.scroll_values["last_maya_log"])
        self.assertNotIn("export_success", cmds.scroll_values["last_maya_log"])
        self.assertIn("发布包=D:/Exports/SM_B", cmds.scroll_values["last_maya_log"])
        self.assertIn("可导出=true", cmds.scroll_values["last_maya_log"])
        self.assertIn("UE Gate=待生成入审报告", cmds.scroll_values["last_maya_log"])
        self.assertIn("警告=0", cmds.scroll_values["last_maya_log"])

    def test_texture_prefix_rename_cancel_does_not_touch_disk(self):
        cmds = FakeTexturePrefixCmds(os.path.join(self.temp_dir, "settings.json"), confirm_answer="取消")
        pipeline = FakeTexturePrefixPipeline()
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=pipeline, log_root=self.temp_dir)
        window.controls = _fake_full_controls()
        window.last_scan = _successful_scan()

        window._rename_texture_prefix()

        self.assertEqual(pipeline.plan_calls, 1)
        self.assertEqual(pipeline.execute_calls, 0)
        self.assertIn("planned rename", cmds.results)
        self.assertIn("修复贴图前缀", cmds.scroll_values["last_maya_log"])
        self.assertNotIn("add_texture_prefix", cmds.scroll_values["last_maya_log"])

    def test_texture_prefix_rename_confirm_executes_selected_texture_set_only(self):
        cmds = FakeTexturePrefixCmds(os.path.join(self.temp_dir, "settings.json"), confirm_answer="__default__")
        pipeline = FakeTexturePrefixPipeline()
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=pipeline, log_root=self.temp_dir)
        window.controls = _fake_full_controls()
        window.last_scan = _successful_scan()

        window._rename_texture_prefix()

        self.assertEqual(pipeline.plan_calls, 1)
        self.assertEqual(pipeline.execute_calls, 1)
        self.assertTrue(pipeline.execute_require_selected_set)
        self.assertEqual(pipeline.execute_prefix, "T_")
        self.assertIn("renamed texture", cmds.results)
        self.assertIn("修复贴图前缀", cmds.scroll_values["last_maya_log"])
        self.assertNotIn("add_texture_prefix", cmds.scroll_values["last_maya_log"])

    def test_texture_folder_scan_rescans_when_selection_changed(self):
        cmds = FakeFullUiCmds(os.path.join(self.temp_dir, "settings.json"))
        pipeline = FakeSelectionChangedTexturePipeline()
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=pipeline, log_root=self.temp_dir)
        window.controls = _fake_full_controls()
        window.last_scan = dict(_successful_scan(), asset_name="SM_Old")
        window.last_selection = ["|SM_Old"]

        window._scan_texture_folder()

        self.assertEqual(pipeline.scan_calls, 1)
        self.assertEqual(pipeline.texture_scan_asset_name, "SM_New")
        self.assertIn("选择已变化", cmds.scroll_values["texture_summary"])

    def test_asset_prefix_fix_uses_confirm_dialog_and_single_undo_chunk(self):
        cmds = FakePrefixFixCmds(os.path.join(self.temp_dir, "settings.json"), confirm_answer="__default__")
        pipeline = FakePrefixFixPipeline()
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=pipeline, log_root=self.temp_dir)
        window.controls = _fake_full_controls()

        window._rename_prefix()

        self.assertEqual(pipeline.rename_root_calls, 1)
        self.assertEqual(pipeline.rename_mesh_calls, 1)
        self.assertEqual(cmds.undo_calls, [("open", "Asset Forge 修复资产名前缀"), ("close", "")])
        self.assertIn("建议资产名：SM_zuti", cmds.confirm_messages[0])
        self.assertIn("修复资产名前缀", cmds.scroll_values["last_maya_log"])
        self.assertNotIn("fix_asset_name_prefix", cmds.scroll_values["last_maya_log"])

    def test_asset_prefix_fix_cancel_does_not_modify_scene(self):
        cmds = FakePrefixFixCmds(os.path.join(self.temp_dir, "settings.json"), confirm_answer="取消")
        pipeline = FakePrefixFixPipeline()
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=pipeline, log_root=self.temp_dir)
        window.controls = _fake_full_controls()

        window._rename_prefix()

        self.assertEqual(pipeline.rename_root_calls, 0)
        self.assertEqual(pipeline.rename_mesh_calls, 0)
        self.assertEqual(cmds.undo_calls, [])
        self.assertIn("未修改 Maya 场景", cmds.results)

    def test_choose_directory_buttons_write_back_to_frontend_fields(self):
        cmds = FakeDirectoryButtonCmds(os.path.join(self.temp_dir, "settings.json"))
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=FakePipeline(), log_root=self.temp_dir)
        window.controls = _fake_full_controls()

        window._choose_output_dir()
        window._choose_texture_folder()

        self.assertEqual(cmds.button_values["output_dir"], "D:/Picked/Export")
        self.assertEqual(cmds.button_values["texture_folder"], "D:/Picked/Textures")
        self.assertEqual(cmds.dialog_captions, ["选择导出", "选择贴图"])

    def test_open_last_package_button_uses_latest_export_directory(self):
        cmds = FakeEditableUiCmds(os.path.join(self.temp_dir, "settings.json"))
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=FakePipeline(), log_root=self.temp_dir)
        window.controls = _fake_full_controls()
        window.last_package_dir = "D:/Exports/SM_B"
        old_open_directory = maya_ui.open_directory
        try:
            maya_ui.open_directory = lambda path: path.replace("\\", "/")
            window._open_last_package()
        finally:
            maya_ui.open_directory = old_open_directory

        self.assertIn("D:/Exports/SM_B", cmds.results)
        self.assertIn("打开导出目录", cmds.scroll_values["last_maya_log"])
        self.assertNotIn("open_package_dir", cmds.scroll_values["last_maya_log"])

    def test_ai_analyze_button_scans_validates_and_writes_suggestion(self):
        cmds = FakeEditableUiCmds(os.path.join(self.temp_dir, "settings.json"))
        pipeline = FakeAnalyzePipeline()
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=pipeline, log_root=self.temp_dir)
        window.controls = _fake_full_controls()

        window._analyze()

        self.assertEqual(pipeline.scan_calls, 1)
        self.assertEqual(pipeline.validate_calls, 1)
        self.assertEqual(pipeline.analyze_calls, 1)
        self.assertIn("AI suggestion", cmds.results)
        self.assertIn("AI 分析", cmds.scroll_values["last_maya_log"])
        self.assertNotIn("ai_analyze", cmds.scroll_values["last_maya_log"])

    def test_frontend_preflight_callback_receives_asset_health_report(self):
        cmds = FakeFullUiCmds(os.path.join(self.temp_dir, "settings.json"))
        scan = _blocked_scan()
        scan["materials"] = [{"name": "B_missing", "shading_group": "B_missingSG", "textures": []}]
        pipeline = MayaStaticPropPipeline(adapter=HealthScanAdapter(scan))
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=pipeline, log_root=self.temp_dir)
        window.controls = _fake_full_controls()

        result = window._run_preflight()

        self.assertIn("asset_health_report", result)
        self.assertEqual(result["asset_health_report"]["status"], "blocked")
        self.assertTrue(result["asset_health_report"]["auto_fix_suggestions"])
        self.assertEqual(result["scan"]["material_texture_bindings"][0]["material_name"], "B_missing")
        self.assertTrue(any(item["id"] == "unmatched_material" for item in result["scan"]["material_texture_binding_risks"]))
        self.assertEqual(window.last_scan["asset_health_report"]["status"], "blocked")

    def test_show_builds_operator_console_controls(self):
        cmds = FakeBuildCmds(os.path.join(self.temp_dir, "settings.json"))
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=FakePipeline(), log_root=self.temp_dir)

        window.show()

        labels = "\n".join(cmds.labels)
        self.assertIn("Asset Forge Maya 发布工作台", labels)
        self.assertIn("MCP：未检查", labels)
        self.assertIn("启动", labels)
        self.assertIn("状态", labels)
        self.assertIn("发布状态", labels)
        self.assertIn("问题定位", labels)
        self.assertIn("发布动作", labels)
        self.assertIn("未扫描 | 选择资产根节点，然后扫描", labels)
        self.assertIn("资产 未扫描    贴图 未扫描    风险 未预检    发布 等待扫描", labels)
        self.assertIn("资产 | 未扫描 · 选择后扫描", labels)
        self.assertIn("贴图 | 未扫描 · 选择目录", labels)
        self.assertIn("风险 | 未预检 · 扫描后检查", labels)
        self.assertIn("发布 | 等待扫描 · 资产和预检", labels)
        self.assertIn("1 发布目标", labels)
        self.assertIn("2 资产概览", labels)
        self.assertIn("3 贴图匹配", labels)
        self.assertIn("4 风险检查", labels)
        self.assertIn("资产详情", labels)
        self.assertIn("贴图匹配", labels)
        self.assertIn("贴图详情", labels)
        self.assertIn("检查详情", labels)
        self.assertIn("结果 / 日志", labels)
        self.assertIn("导入策略（写入 Package，UE Gate 可复核）", labels)
        self.assertIn("基础导入", labels)
        self.assertIn("网格构建", labels)
        self.assertIn("材质贴图", labels)
        self.assertIn("高级设置", labels)
        self.assertIn("Maya 只生成 Package 和导入建议", labels)
        self.assertIn("这些值会写入 Package；UE Gate 导入前仍可复核和覆盖。", labels)
        self.assertIn("Virtual Texture 策略建议", labels)
        self.assertIn("Texture Streaming 策略建议", labels)
        self.assertIn("保持 Mesh / 独立 Mesh 关系清晰", labels)
        self.assertIn("Nanite 策略建议", labels)
        self.assertIn("Mesh LOD 导入策略建议", labels)
        self.assertIn("Maya 操作日志", labels)
        self.assertIn("1 扫描资产", labels)
        self.assertIn("2 检查风险", labels)
        self.assertIn("3 导出 Package 给 UE Gate", labels)
        self.assertIn("导出调试信息", labels)
        self.assertIn("修复资产名前缀", labels)
        self.assertIn("贴图集关键词", labels)
        self.assertIn("下一步", labels)
        self.assertTrue(any("IconMayaHeader.png" in image for image in cmds.images))
        scroll_text = "\n".join(cmds.scroll_values.values())
        self.assertIn(format_asset_identity({}), scroll_text)
        self.assertIn(format_empty_texture_details(), scroll_text)
        self.assertIn(format_empty_preflight_details(), scroll_text)
        self.assertIn("定位：等待扫描", scroll_text)
        self.assertEqual(cmds.scroll_layout_count, 1)
        self.assertEqual(cmds.scroll_layout_kwargs["verticalScrollBarThickness"], 16)
        self.assertIn(126, cmds.scroll_field_heights)
        self.assertIn(168, cmds.scroll_field_heights)
        self.assertIn(186, cmds.scroll_field_heights)
        self.assertIn(64, cmds.scroll_field_heights)
        self.assertIn(76, cmds.scroll_field_heights)

    def test_mcp_status_running_shows_port(self):
        cmds = FakeFullUiCmds(os.path.join(self.temp_dir, "settings.json"))
        window = AssetForgeMayaWindow(cmds_module=cmds, pipeline=FakePipeline(), log_root=self.temp_dir)
        window.controls = {"mcp_status": "mcp_status"}

        window._set_mcp_status({"status": "running", "port": 8766})

        self.assertEqual(cmds.summary, "MCP：8766 运行中")

    def test_issue_locator_points_to_material_texture_binding(self):
        validation = {
            "status": "error",
            "can_export": False,
            "checks": [
                {
                    "id": "unmatched_material",
                    "label": "材质贴图绑定",
                    "status": "error",
                    "object": "B_a1",
                    "message": "Maya material has no matching texture set; export is blocked to avoid default material textures.",
                    "next_action": "检查“贴图详情”中的候选贴图集，补齐缺失贴图集或填写正确贴图集关键词后重新扫描。",
                }
            ],
            "summary": {"warnings": 0, "errors": 1},
        }

        text = format_issue_locator(
            _successful_scan(),
            validation,
            {"matched_count": 6, "issues": []},
            preferred="risk",
        )

        self.assertIn("定位：风险检查详情", text)
        self.assertIn("[阻断] unmatched_material | 对象：B_a1", text)
        self.assertIn("位置：材质贴图绑定 -> 贴图详情 / 检查详情", text)
        self.assertIn("补齐缺失贴图集", text)


def _blocked_scan():
    return {
        "asset_name": "zuti",
        "asset_name_source": "common_parent",
        "asset_name_source_path": "|zuti",
        "asset_root": "|zuti|SM_B_a",
        "asset_roots": ["|zuti|SM_B_a", "|zuti|SM_B_e"],
        "mesh_count": 2,
        "triangles": 1200,
        "textures": [],
    }


def _blocked_validation():
    return {
        "status": "error",
        "can_export": False,
        "checks": [
            {"id": "name_prefix", "label": "命名规范", "status": "error", "severity": "error", "message": "资产名应以 SM_ 开头", "limit": "SM_"},
            {"id": "mesh_exists", "label": "Mesh 存在", "status": "pass", "severity": "error", "message": "通过"},
        ],
    }


def _first_selection_scan():
    scan = _blocked_scan()
    scan.update(
        {
            "asset_name": "SM_A",
            "asset_name_source": "first_selection",
            "asset_name_source_path": "|SM_A",
            "asset_root": "|SM_A",
            "asset_roots": ["|SM_A", "|SM_B"],
        }
    )
    return scan


def _successful_scan():
    return {
        "asset_name": "SM_B",
        "asset_name_source": "selected_root",
        "asset_name_source_path": "|SM_B",
        "asset_root": "|SM_B",
        "asset_roots": ["|SM_B"],
        "mesh_count": 1,
        "triangles": 1200,
        "textures": [],
        "texture_folder_scan": {
            "directory_status": "valid",
            "matched_count": 3,
            "texture_set_token": "a1,d1",
            "selected_texture_set_short_names": ["a1", "d1"],
            "selected_texture_sets": ["HK416_D_B_a1", "HK416_D_B_d1"],
        },
    }


def _successful_validation():
    return {"status": "pass", "can_export": True, "checks": [], "summary": {"warnings": 0, "errors": 0}}


class FakeUiCmds(object):
    def __init__(self, target_path):
        self.target_path = target_path

    def textFieldGrp(self, control, query=False, text=False, **kwargs):
        return self.target_path


class FakeFullUiCmds(object):
    def __init__(self, save_path):
        self.save_path = save_path
        self.summary = ""
        self.settings_label = ""
        self.results = ""
        self.scroll_values = {}

    def fileDialog2(self, **kwargs):
        return [self.save_path]

    def textFieldButtonGrp(self, control, query=False, text=False, edit=False, **kwargs):
        values = {"output_dir": "D:/Exports", "texture_folder": "D:/Textures"}
        return values.get(control, "")

    def textFieldGrp(self, control, query=False, text=False, edit=False, **kwargs):
        values = {"name_prefix": "SM_", "texture_prefix": "T_", "target_path": "/Game/Props", "texture_set_token": "a1,d1"}
        return values.get(control, "")

    def intFieldGrp(self, control, query=False, value1=False, edit=False, **kwargs):
        return 50000

    def optionMenu(self, control, query=False, value=False, edit=False, **kwargs):
        values = {"platform": "high_end_mobile", "material_profile": "Props_Opaque_PainterUE_ARM"}
        return values.get(control, "")

    def text(self, control=None, edit=False, label="", **kwargs):
        if control == "settings_path":
            self.settings_label = label
        self.summary = label

    def scrollField(self, control, edit=False, text="", **kwargs):
        self.scroll_values[control] = text
        if control == "results":
            self.results = text

    def warning(self, message):
        self.summary = message


class FakeEditableUiCmds(FakeFullUiCmds):
    def __init__(self, save_path):
        super(FakeEditableUiCmds, self).__init__(save_path)
        self.button_values = {"output_dir": "D:/Exports", "texture_folder": "D:/Textures"}
        self.text_values = {
            "name_prefix": "SM_",
            "texture_prefix": "T_",
            "target_path": "/Game/Props/HK416D",
            "texture_set_token": "a1,d1",
            "texture_group": "project_default",
            "static_mesh_lod_group": "SmallProp",
        }
        self.option_values = {
            "platform": "high_end_mobile",
            "material_profile": "Props_Opaque_PainterUE_ARM",
            "virtual_texture_policy": "force_off",
            "texture_streaming_policy": "streaming",
            "nanite_policy": "disable",
            "static_mesh_lod_import_policy": "report_only",
        }

    def textFieldButtonGrp(self, control, query=False, text=False, edit=False, **kwargs):
        if edit:
            self.button_values[control] = kwargs.get("text", text if isinstance(text, str) else "")
            return control
        return self.button_values.get(control, "")

    def textFieldGrp(self, control, query=False, text=False, edit=False, **kwargs):
        if edit:
            self.text_values[control] = kwargs.get("text", text if isinstance(text, str) else "")
            return control
        return self.text_values.get(control, "")

    def optionMenu(self, control, query=False, value=False, edit=False, **kwargs):
        if edit:
            self.option_values[control] = kwargs.get("value", "")
            return control
        return self.option_values.get(control, "")


class FakeTexturePrefixCmds(FakeEditableUiCmds):
    def __init__(self, save_path, confirm_answer):
        super(FakeTexturePrefixCmds, self).__init__(save_path)
        self.confirm_answer = confirm_answer
        self.confirm_messages = []

    def confirmDialog(self, **kwargs):
        self.confirm_messages.append(kwargs.get("message", ""))
        if self.confirm_answer == "__default__":
            return kwargs.get("defaultButton")
        return self.confirm_answer


class FakePrefixFixCmds(FakeTexturePrefixCmds):
    def __init__(self, save_path, confirm_answer):
        super(FakePrefixFixCmds, self).__init__(save_path, confirm_answer)
        self.undo_calls = []

    def undoInfo(self, openChunk=False, closeChunk=False, chunkName="", **kwargs):
        if openChunk:
            self.undo_calls.append(("open", chunkName))
        if closeChunk:
            self.undo_calls.append(("close", ""))


class FakeDirectoryButtonCmds(FakeEditableUiCmds):
    def __init__(self, save_path):
        super(FakeDirectoryButtonCmds, self).__init__(save_path)
        self.dialog_captions = []

    def fileDialog2(self, **kwargs):
        caption = kwargs.get("caption", "")
        if "贴图" in caption or "Painter" in caption:
            self.dialog_captions.append("选择贴图")
            return ["D:/Picked/Textures"]
        self.dialog_captions.append("选择导出")
        return ["D:/Picked/Export"]


class FakeUnicodePathCmds(FakeFullUiCmds):
    def __init__(self, save_path):
        super(FakeUnicodePathCmds, self).__init__(save_path)
        self.button_values = {"output_dir": "D:/Exports", "texture_folder": "D:/Textures"}

    def textFieldButtonGrp(self, control, query=False, text=False, edit=False, **kwargs):
        if edit:
            value = text if isinstance(text, str) else kwargs.get("text", "")
            self.button_values[control] = value.replace("导出", "??").replace("测试", "??")
            return control
        return self.button_values.get(control, "")


class FakeBuildCmds(FakeFullUiCmds):
    def __init__(self, save_path):
        super(FakeBuildCmds, self).__init__(save_path)
        self.labels = []
        self.images = []
        self.counter = 0
        self.scroll_layout_count = 0
        self.scroll_layout_kwargs = {}
        self.scroll_field_kwargs = {}
        self.scroll_field_heights = []

    def window(self, *args, **kwargs):
        if kwargs.get("exists"):
            return False
        return "window"

    def deleteUI(self, *args, **kwargs):
        pass

    def columnLayout(self, *args, **kwargs):
        return "column"

    def scrollLayout(self, *args, **kwargs):
        self.scroll_layout_count += 1
        self.scroll_layout_kwargs = dict(kwargs)
        return "main_scroll"

    def rowLayout(self, *args, **kwargs):
        return "row"

    def setParent(self, *args, **kwargs):
        pass

    def text(self, control=None, edit=False, label="", **kwargs):
        self.labels.append(label)
        self.summary = label
        return "text_{0}".format(len(self.labels))

    def optionMenu(self, control=None, query=False, value=False, edit=False, **kwargs):
        if query:
            return super(FakeBuildCmds, self).optionMenu(control, query=query, value=value, edit=edit, **kwargs)
        self.counter += 1
        self.labels.append(kwargs.get("label", ""))
        return kwargs.get("label", "option_{0}".format(self.counter))

    def menuItem(self, *args, **kwargs):
        self.labels.append(kwargs.get("label", ""))
        return "menuItem"

    def textFieldGrp(self, control=None, query=False, text=False, edit=False, **kwargs):
        if query or edit:
            return super(FakeBuildCmds, self).textFieldGrp(control, query=query, text=text, edit=edit, **kwargs)
        self.counter += 1
        self.labels.append(kwargs.get("label", ""))
        return kwargs.get("label", "textField_{0}".format(self.counter))

    def textFieldButtonGrp(self, control=None, query=False, text=False, edit=False, **kwargs):
        if query or edit:
            return super(FakeBuildCmds, self).textFieldButtonGrp(control, query=query, text=text, edit=edit, **kwargs)
        self.counter += 1
        self.labels.append(kwargs.get("label", ""))
        return kwargs.get("label", "textFieldButton_{0}".format(self.counter))

    def intFieldGrp(self, control=None, query=False, value1=False, edit=False, **kwargs):
        if query or edit:
            return super(FakeBuildCmds, self).intFieldGrp(control, query=query, value1=value1, edit=edit, **kwargs)
        self.counter += 1
        self.labels.append(kwargs.get("label", ""))
        return kwargs.get("label", "intField_{0}".format(self.counter))

    def button(self, *args, **kwargs):
        self.labels.append(kwargs.get("label", ""))
        return kwargs.get("label", "button")

    def image(self, *args, **kwargs):
        self.images.append(kwargs.get("image", ""))
        return kwargs.get("image", "image")

    def scrollField(self, control=None, edit=False, text="", **kwargs):
        if edit:
            self.scroll_values[control] = text
            if control == "results":
                self.results = text
            return control
        self.counter += 1
        name = "scroll_{0}".format(self.counter)
        self.scroll_values[name] = text if isinstance(text, str) else kwargs.get("text", "")
        self.scroll_field_kwargs[name] = dict(kwargs)
        self.scroll_field_heights.append(kwargs.get("height"))
        return name

    def showWindow(self, *args, **kwargs):
        pass


class FakePipeline(object):
    rules = {}

    def __init__(self):
        self.adapter = self
        self.selection = ["|zuti|SM_B_a", "|zuti|SM_B_e"]
        self.export_called = False
        self.blocked_report_written = False
        self.preflight_selection = []

    def get_current_selection(self):
        return list(self.selection)

    def preflight_assets(self, *args, **kwargs):
        self.preflight_selection = list(args[0])
        return {"scan": _blocked_scan(), "validation": _blocked_validation(), "texture_folder_scan": {}}

    def export_assets(self, *args, **kwargs):
        self.export_called = True
        return {}

    def _write_blocked_export_report(self, *args, **kwargs):
        self.blocked_report_written = True
        return "D:/Reports/zuti_export_blocked_report.json"


class FakeExportSuccessPipeline(object):
    rules = {}

    def __init__(self):
        self.adapter = self
        self.selection = ["|SM_B"]
        self.preflight_calls = 0
        self.export_called = False
        self.export_args = {}

    def get_current_selection(self):
        return list(self.selection)

    def preflight_assets(self, selection, target_platform=None, material_profile=None, texture_folder=None, texture_set_token=None, target_path=None, asset_name_override="", rules=None, texture_import_policy=None, static_mesh_import_policy=None):
        self.preflight_calls += 1
        return {"scan": _successful_scan(), "validation": _successful_validation(), "texture_folder_scan": _successful_scan()["texture_folder_scan"]}

    def export_assets(self, selection, output_dir, target_platform, target_path, *args, **kwargs):
        self.export_called = True
        self.export_args = {
            "selection": list(selection),
            "output_dir": output_dir,
            "target_platform": target_platform,
            "target_path": target_path,
            "material_profile": kwargs.get("material_profile"),
            "texture_folder": kwargs.get("texture_folder"),
            "texture_set_token": kwargs.get("texture_set_token"),
            "texture_import_policy": kwargs.get("texture_import_policy"),
            "static_mesh_import_policy": kwargs.get("static_mesh_import_policy"),
        }
        return {
            "scan": _successful_scan(),
            "validation": _successful_validation(),
            "manifest": {
                "texture_import_policy": kwargs.get("texture_import_policy"),
                "static_mesh_import_policy": kwargs.get("static_mesh_import_policy"),
            },
            "package_dir": "D:/Exports/SM_B",
            "manifest_path": "D:/Exports/SM_B/SM_B_manifest.json",
            "fbx_path": "D:/Exports/SM_B/SM_B.fbx",
            "export_report_path": "D:/Exports/SM_B/SM_B_export_report.json",
        }


class FakeTexturePrefixPipeline(object):
    rules = {}

    def __init__(self):
        self.adapter = self
        self.plan_calls = 0
        self.execute_calls = 0
        self.execute_prefix = ""
        self.execute_require_selected_set = False

    def get_current_selection(self):
        return ["|SM_B"]

    def scan_selection(self):
        return _successful_scan()

    def scan_texture_folder(self, folder, asset_name, material_profile, token):
        return _successful_scan()["texture_folder_scan"]

    def plan_texture_prefix_renames(self, scan, texture_prefix, require_selected_set=True):
        self.plan_calls += 1
        return {
            "status": "success",
            "texture_prefix": texture_prefix,
            "planned_count": 1,
            "skipped_count": 0,
            "actions": [{"status": "planned", "message": "planned rename"}],
        }

    def execute_texture_prefix_renames(self, scan, texture_prefix, require_selected_set=True):
        self.execute_calls += 1
        self.execute_prefix = texture_prefix
        self.execute_require_selected_set = require_selected_set
        return {
            "status": "success",
            "texture_prefix": texture_prefix,
            "renamed_count": 1,
            "skipped_count": 0,
            "actions": [{"status": "renamed", "message": "renamed texture"}],
        }


class FakeSelectionChangedTexturePipeline(object):
    rules = {}

    def __init__(self):
        self.adapter = self
        self.selection = ["|SM_New"]
        self.scan_calls = 0
        self.texture_scan_asset_name = ""

    def get_current_selection(self):
        return list(self.selection)

    def scan_selection(self):
        self.scan_calls += 1
        return dict(_successful_scan(), asset_name="SM_New", asset_roots=["|SM_New"])

    def scan_texture_folder(self, folder, asset_name, material_profile, token):
        self.texture_scan_asset_name = asset_name
        return _successful_scan()["texture_folder_scan"]


class FakePrefixFixPipeline(object):
    rules = {}

    def __init__(self):
        self.adapter = self
        self.rename_root_calls = 0
        self.rename_mesh_calls = 0

    def get_current_selection(self):
        return ["|zuti"]

    def scan_selection(self):
        return _blocked_scan()

    def rename_asset_root_with_prefix(self, prefix):
        self.rename_root_calls += 1
        return ["|SM_zuti"]

    def rename_mesh_transforms_with_prefix(self, prefix):
        self.rename_mesh_calls += 1
        return ["|SM_zuti|SM_B_a"]


class FakeAnalyzePipeline(object):
    rules = {}

    def __init__(self):
        self.adapter = self
        self.scan_calls = 0
        self.validate_calls = 0
        self.analyze_calls = 0

    def get_current_selection(self):
        return ["|SM_B"]

    def scan_selection(self):
        self.scan_calls += 1
        return _successful_scan()

    def validate_scan(self, scan, target_platform):
        self.validate_calls += 1
        return _successful_validation()

    def analyze(self, scan, validation):
        self.analyze_calls += 1
        return "AI suggestion: ready for export"


class HealthScanAdapter(object):
    def __init__(self, scan_result):
        self.scan_result = dict(scan_result)

    def get_current_selection(self):
        return list(self.scan_result.get("asset_roots", []))

    def scan_assets(self, asset_roots, rules):
        result = dict(self.scan_result)
        result["asset_roots"] = list(asset_roots)
        return result


def _fake_full_controls():
    return {
        "output_dir": "output_dir",
        "texture_folder": "texture_folder",
        "name_prefix": "name_prefix",
        "texture_prefix": "texture_prefix",
        "target_path": "target_path",
        "triangle_budget": "triangle_budget",
        "platform": "platform",
        "material_profile": "material_profile",
        "texture_set_token": "texture_set_token",
        "virtual_texture_policy": "virtual_texture_policy",
        "texture_streaming_policy": "texture_streaming_policy",
        "texture_group": "texture_group",
        "nanite_policy": "nanite_policy",
        "static_mesh_lod_group": "static_mesh_lod_group",
        "static_mesh_lod_import_policy": "static_mesh_lod_import_policy",
        "summary": "summary",
        "results": "results",
        "last_maya_log": "last_maya_log",
        "settings_path": "settings_path",
        "asset_identity": "asset_identity",
        "texture_summary": "texture_summary",
        "preflight": "preflight",
    }


if __name__ == "__main__":
    unittest.main()
