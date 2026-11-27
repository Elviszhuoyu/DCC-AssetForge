import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch



class ReviewWorkbenchTest(unittest.TestCase):
    def setUp(self):
        from asset_forge.unreal.review_workbench import ReviewWorkbench

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ui = ReviewWorkbench(object(), Path(self.temp.name))
        self.row = {"asset_path": "/Game/B", "status": "needs_review", "fully_fixable": False,
                    "facts": {}, "asset_type": "StaticMesh", "incomplete": True, "issues": []}
        self.second = dict(self.row, asset_path="/Game/C")
        self.report = {"assets": [self.row, self.second], "review_id": "first", "revision": 1,
                       "created_at_utc": "2026-01-01", "policy": {}, "json_path": "original"}
        self.ui._set_report(self.report)

    def test_gate_handoff_scans_only_returned_meshes_and_selects_the_first(self):
        with patch("asset_forge.unreal.review_workbench.selected_paths") as selected, \
                patch("asset_forge.unreal.review_workbench.scan_assets") as scan, \
                patch("asset_forge.unreal.review_workbench.record_review", return_value=self.report) as record:
            self.ui.act("imported", json.dumps({"receipt": "import-1", "meshes": ["/Game/C.C", "/Game/B.B", "/Game/C"]}))
            scan.assert_called_once_with(["/Game/C", "/Game/B"], unreal_module=self.ui.ue)
            selected.assert_not_called()
            record.assert_called_once_with(scan.return_value, self.ui.root)
        self.assertEqual(self.ui.selected, "/Game/C")
        self.assertEqual(self.ui.view()["batch_id"], self.report["review_id"])

    def test_stock_rule_settings_show_enforced_limits_and_affect_only_a_new_stock_scan(self):
        self.assertIn("50,000", self.ui.view()["stock_policy"]["limits"])
        self.ui.act("rules_platform", "mobile")
        self.ui.act("rules_profile", "Props_Opaque_PainterUE_ARM")
        state = self.ui.view()
        self.assertEqual(state["stock_policy"]["platform"], "mobile")
        self.assertIn("8,000 三角面", state["stock_policy"]["limits"])
        self.assertIn("材质槽上限 2", state["stock_policy"]["limits"])
        self.assertEqual(state["stock_policy"]["profile"], "Props_Opaque_PainterUE_ARM")
        self.assertIs(self.ui.report, self.report)
        with patch("asset_forge.unreal.review_workbench.selected_paths", return_value=["/Game/B"]), \
                patch("asset_forge.unreal.review_workbench.scan_assets") as scan, \
                patch("asset_forge.unreal.review_workbench.record_review", return_value=self.report):
            self.ui.act("scan")
            policy = scan.call_args.kwargs["policy"]
            self.assertEqual(policy["platform"], "mobile")
            self.assertEqual(policy["max_triangles"], 8000)
            self.assertEqual(policy["max_material_slots"], 2)
            self.assertEqual(policy["material_profile"], "Props_Opaque_PainterUE_ARM")
        with self.assertRaisesRegex(ValueError, "选定规则已不可用"):
            self.ui.act("rules_platform", "missing")
        self.assertEqual(self.ui.view()["stock_policy"]["platform"], "mobile")

    def test_gate_handoff_supplies_the_package_rules_and_recheck_keeps_them(self):
        self.ui.act("rules_platform", "high_end_mobile")
        self.ui.act("rules_profile", "Props_Opaque_PainterUE_ARM")
        policy = {"material_profile": "Studio_ARM", "material_profile_snapshot": {"name": "Studio_ARM"}}
        handoff = {"receipt": "painter", "meshes": ["/Game/B.B"], "policy": policy}
        stored = dict(self.report, policy=policy)
        with patch("asset_forge.unreal.review_workbench.scan_assets") as scan, \
                patch("asset_forge.unreal.review_workbench.record_review", return_value=stored), \
                patch("asset_forge.unreal.review_workbench._rounds", return_value=[stored]):
            self.ui.act("imported", json.dumps(handoff))
            scan.assert_called_once_with(["/Game/B"], policy=policy, unreal_module=self.ui.ue)
            self.ui.act("recheck")
            scan.assert_called_with(["/Game/B"], policy, self.ui.ue)
        self.assertEqual(self.ui.view()["profile"], "Studio_ARM")

    def test_declared_250000_8_budget_persists_and_is_independent_of_stock(self):
        from asset_forge.unreal.asset_review import _policy
        from asset_forge.unreal.review_workbench import ReviewWorkbench

        self.ui.act("rules_triangles", "31000")
        self.ui.act("rules_material_slots", "3")
        self.ui.act("rules_profile", "Props_Opaque_PainterUE_ARM")
        stock = self.ui.view()["stock_policy"]
        self.assertEqual((stock["triangles"], stock["material_slots"]), (31000, 3))
        with self.assertRaisesRegex(ValueError, "大于 0"):
            self.ui.act("rules_material_slots", "0")
        handoff = {"receipt": "package-with-budgets", "meshes": ["/Game/B.B"],
                   "policy": {"material_profile": "Props_Opaque_PainterUE_ARM"},
                   "asset_budgets": {"triangles": 250000, "material_slots": 8}}

        def scan(paths, policy, unreal_module):
            effective, _ = _policy(policy)
            return {"policy": effective, "asset_paths": paths, "assets": [self.row], "fix_plan": []}

        with patch("asset_forge.unreal.review_workbench.scan_assets", side_effect=scan):
            self.ui.act("imported", json.dumps(handoff))
            self.assertEqual(self.ui.report["policy"]["max_triangles"], 250000)
            self.assertEqual(self.ui.report["policy"]["max_material_slots"], 8)
            self.assertEqual(self.ui.view()["budget_summary"], "250,000 三角面 / 8 个材质槽")
            self.assertEqual(self.ui.view()["budget_source"], "包体声明")
            reopened = ReviewWorkbench(self.ui.ue, self.ui.root)
            reopened.act("open")
            reopened.act("recheck")
            self.assertEqual(reopened.report["revision"], 2)
            self.assertEqual(reopened.report["policy"]["asset_budgets"], handoff["asset_budgets"])
            initial_report = Path(self.ui.report["json_path"])
            initial_copy = initial_report.read_bytes()

            reopened.act("rules_batch_budget", json.dumps({"triangles": 180000, "material_slots": 6}))
            self.assertEqual(reopened.report["revision"], 3)
            self.assertEqual(reopened.report["review_id"], self.ui.report["review_id"])
            self.assertEqual(reopened.report["policy"]["asset_budgets"], handoff["asset_budgets"])
            self.assertEqual(reopened.view()["budget_summary"], "180,000 三角面 / 6 个材质槽")
            self.assertEqual(reopened.view()["budget_source"], "手动调整")

            reopened.act("recheck")
            self.assertEqual(reopened.view()["batch_budget"], {"triangles": 180000, "material_slots": 6})
            reopened.act("rules_batch_budget", json.dumps(handoff["asset_budgets"]))
        self.assertEqual(reopened.report["revision"], 5)
        self.assertEqual(reopened.view()["budget_summary"], "250,000 三角面 / 8 个材质槽")
        self.assertEqual(reopened.view()["budget_source"], "包体声明")
        self.assertEqual(initial_report.read_bytes(), initial_copy)
        self.assertEqual((self.ui.view()["stock_policy"]["triangles"], self.ui.view()["stock_policy"]["material_slots"]), (31000, 3))

    def test_returning_to_one_receipt_reuses_its_batch_until_a_new_import(self):
        first = {"receipt": "import-1", "meshes": ["/Game/C.C", "/Game/B.B"]}
        second = dict(first, receipt="import-2")
        new_report = dict(self.report, review_id="second")
        with patch("asset_forge.unreal.review_workbench.scan_assets") as scan, \
                patch("asset_forge.unreal.review_workbench.record_review", side_effect=[self.report, new_report]), \
                patch("asset_forge.unreal.review_workbench._rounds", return_value=[self.report]):
            self.ui.act("imported", json.dumps(first))
            self.ui.act("select", "/Game/B")
            self.ui.preview = {"asset_paths": ["/Game/B"]}
            self.ui.act("imported", json.dumps(first))
            self.assertEqual(self.ui.selected, "/Game/B")
            self.assertIsNotNone(self.ui.preview)
            self.ui._set_report(dict(self.report, review_id="history"))
            self.ui.act("imported", json.dumps(first))
            self.assertEqual(self.ui.report["review_id"], "first")
            self.assertEqual(self.ui.selected, "/Game/C")
            self.assertEqual(scan.call_count, 1)
            self.ui.act("imported", json.dumps(second))
            self.assertEqual(self.ui.report["review_id"], "second")
            self.assertEqual(scan.call_count, 2)

    def test_empty_or_invalid_import_does_not_open_another_scope(self):
        with patch("asset_forge.unreal.review_workbench.scan_assets") as scan:
            invalid = [None, [], {}, {"receipt": "", "meshes": ["/Game/B"]},
                       {"receipt": "one", "meshes": []}, {"receipt": "one", "meshes": ["/Game/B", 1]},
                       {"receipt": "one", "meshes": ["/Game/B"], "policy": []}]
            for payload in map(json.dumps, invalid):
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    self.ui.act("imported", payload)
            scan.assert_not_called()
        self.assertIs(self.ui.report, self.report)

    def test_unverified_or_incomplete_empty_results_never_say_pass(self):
        self.assertNotIn("检查通过", self.ui.view()["empty_label"])
        self.row.update(status="pass")
        self.assertEqual(self.ui.view()["assets"][0]["status"], "needs_review")
        self.assertNotIn("检查通过", self.ui.view()["empty_label"])
        self.row.update(incomplete=False)
        self.assertIn("检查通过", self.ui.view()["empty_label"])

    def test_view_projects_recorded_time_profile_and_current_observations(self):
        from datetime import datetime, timezone

        self.report["created_at_utc"] = "2026-11-26T05:30:59Z"
        self.report["policy"]["material_profile"] = "Props_Opaque_PBR"
        self.ui.batches = [self.report]
        self.row["issues"] = [{"rule_id": "texture.srgb", "object_path": "/Game/T_B_ORM",
                               "actual": True, "expected": False}]
        view = self.ui.view()
        stamp = datetime(2026, 11, 26, 5, 30, tzinfo=timezone.utc).astimezone().strftime("%m-%d %H:%M")
        self.assertIn(stamp, view["summary"])
        self.assertIn(stamp, view["batches"][0]["label"])
        self.assertEqual([r["profile"] for r in view["assets"]], ["Props_Opaque_PBR"] * 2)
        self.assertEqual(view["issues"][0]["current"], "当前开启 sRGB")

    def test_missing_profile_and_timestamp_are_not_inferred(self):
        self.report.pop("created_at_utc")
        self.ui.batches = [self.report]
        self.assertEqual(self.ui.view()["assets"][0]["profile"], "")
        self.assertEqual(self.ui.view()["summary"], "2 件资产  ·  第 1 轮")

    def test_confirmation_feedback_cannot_override_the_asset_severity(self):
        self.row.update(status="blocked", fully_fixable=True, incomplete=False)
        self.row["issues"] = [{"rule_id": "texture.srgb", "object_path": "/Game/T_B_ORM",
                              "severity": "error", "actual": True, "expected": False}]
        self.ui.message = "已保存 0 张贴图，当前资产已复扫。"
        view = self.ui.view()
        self.assertIn("可修（1 项阻断）", view["facts"])
        self.assertEqual(view["issues"][0]["severity"], "blocked")
        self.assertEqual(view["assets"][0]["status"], "fixable")
        self.assertIn("已复扫", view["message"])

    def test_legacy_history_has_no_fabricated_pass_evidence(self):
        self.assertFalse(self.ui.view()["has_pass_evidence"])
        self.row["passed"] = [{"rule_id": "mesh.material_slots", "title": "材质槽数量"}]
        view = self.ui.view()
        self.assertTrue(view["has_pass_evidence"])
        self.assertEqual(view["passed"], self.row["passed"])
        self.assertEqual(view["assets"][0]["status"], "needs_review")

    def test_navigation_discards_uncommitted_preview_and_location_keeps_selection(self):
        self.ui.preview = {"asset_paths": ["/Game/B"]}
        self.row["issues"] = [{"object_path": "/Game/Texture", "rule_id": "texture.srgb"}]
        with patch("asset_forge.unreal.review_workbench.locate_issue", return_value="/Game/Texture"):
            self.ui.act("locate", "0")
        self.assertEqual(self.ui.selected, "/Game/B")
        self.ui.act("select", "/Game/C")
        self.assertIsNone(self.ui.preview)
        with patch("asset_forge.unreal.review_workbench._rounds", return_value=[self.report]):
            with self.assertRaisesRegex(ValueError, "预览"):
                self.ui.act("apply")

    def test_preview_actions_and_messages_follow_real_repair_eligibility(self):
        dirty = "存在尚未保存的包，磁盘注册表不能确认当前引用范围"
        shared = "贴图有选区以外的网格引用"
        indexing = "注册表尚未完成全项目扫描"
        base = {"texture_path": "/Game/T_B_ORM", "old": {"srgb": True, "compression": "TC_DEFAULT"},
                "new": {"srgb": False, "compression": "TC_MASKS"}, "referencers": [], "mesh_owners": []}
        with patch("asset_forge.unreal.review_workbench._rounds", return_value=[self.report]), \
                patch("asset_forge.unreal.review_workbench.scan_assets") as scan:
            for reasons, fix, detail in [
                    ([dirty], "preview", "保存相关改动"), ([shared], "preview", "人工核对"),
                    ([indexing], "preview", "等待资产注册表"), ([""], "confirm", "后确认"),
                    ([shared, ""], "confirm", "可修改 1 / 2"), ([], "", "没有可修复")]:
                with self.subTest(reasons=reasons):
                    plans = [dict(base, texture_path="/Game/T_{}".format(i), reason=r, can_apply=not r)
                             for i, r in enumerate(reasons)]
                    scan.return_value = {"asset_paths": [self.ui.selected], "fix_plan": plans}
                    self.ui.act("preview")
                    view = self.ui.view()
                    self.assertEqual(view["fix"], fix)
                    self.assertIn(detail, view["message"])
                    if fix == "preview":
                        self.assertIn(reasons[0], view["message"])
                        self.assertNotIn("后确认", view["message"])

    def test_newer_round_invalidates_approval_before_write(self):
        self.ui.preview = {"asset_paths": ["/Game/B"], "fix_plan": [{"texture_path": "/Game/T", "can_apply": True}]}
        latest = dict(self.report, revision=2)
        with patch("asset_forge.unreal.review_workbench._rounds", return_value=[latest]), \
                patch("asset_forge.unreal.review_workbench.apply_fixes") as apply:
            with self.assertRaisesRegex(ValueError, "新一轮"):
                self.ui.act("apply")
            apply.assert_not_called()
        self.assertIsNone(self.ui.preview)
        self.assertEqual(self.ui.report["revision"], 2)
