from __future__ import absolute_import

import unittest

from asset_forge.shared.report_schema import create_acceptance_summary, create_batch_report, create_end_to_end_report, next_action_for


class ReportSchemaNextActionTest(unittest.TestCase):
    def test_next_action_strategy_table_covers_common_reasons(self):
        self.assertIn("UE 5.6", next_action_for(reason="not_in_unreal"))
        self.assertIn("manifest", next_action_for(reason="missing_manifest"))
        self.assertIn("母材质", next_action_for(reason="missing_parent_material"))

    def test_acceptance_summary_uses_stable_chinese_next_action(self):
        summary = create_acceptance_summary(
            "error",
            errors=[{"source": "manifest", "message": "未找到 manifest"}],
            next_action_reason="missing_manifest",
        )

        self.assertFalse(summary["can_accept"])
        self.assertEqual(summary["next_action"], "确认资产包目录内存在 DCC AssetForge manifest 后重新执行验收")

    def test_acceptance_summary_exposes_user_guidance_fields(self):
        summary = create_acceptance_summary(
            "error",
            errors=[{"source": "manifest", "message": "missing manifest"}],
            next_action="Fix manifest and rerun.",
        )

        self.assertFalse(summary["can_import"])
        self.assertEqual(summary["decision"], "blocked")
        self.assertTrue(summary["why"])
        self.assertEqual(summary["next_steps"][0]["id"], "fix_error_1")

    def test_end_to_end_and_batch_reports_keep_guidance_structured(self):
        import_report = {
            "status": "success",
            "asset_name": "SM_Table",
            "summary": create_acceptance_summary("pass"),
        }

        end_to_end = create_end_to_end_report(import_report=import_report)
        batch = create_batch_report("Exports", False, [import_report])

        self.assertEqual(end_to_end["user_guidance"]["decision"], "ready")
        self.assertEqual(batch["asset_decisions"][0]["decision"], "ready")
        self.assertTrue(batch["user_guidance"]["can_import"])

    def test_failed_import_without_issues_still_explains_blocker(self):
        end_to_end = create_end_to_end_report(import_report={"status": "failed", "message": "UE import crashed"})

        self.assertFalse(end_to_end["can_import"])
        self.assertEqual(end_to_end["user_guidance"]["decision"], "blocked")
        self.assertIn("UE import crashed", end_to_end["why"][0])


if __name__ == "__main__":
    unittest.main()
