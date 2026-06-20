from __future__ import absolute_import

import os
import json
import subprocess
import sys
import tempfile
import unittest

from asset_forge.shared.report_schema import write_report
from asset_forge.shared.portfolio_evidence_manifest import create_portfolio_evidence_manifest


class PortfolioEvidenceManifestTest(unittest.TestCase):
    def test_manifest_turns_demo_steps_into_capture_checklist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = create_portfolio_evidence_manifest(_demo_pack(), temp_dir)
            captures = dict((item["step_id"], item) for item in report["captures"])

            self.assertEqual(report["stage"], "portfolio_evidence_manifest")
            self.assertEqual(report["status"], "warning")
            self.assertEqual(report["ready_capture_count"], 1)
            self.assertEqual(report["missing_capture_count"], 2)
            self.assertEqual(report["next_capture"], "maya_scan_capture")
            self.assertEqual(
                report["capture_summary"],
                {
                    "total_capture_count": 3,
                    "ready_capture_count": 1,
                    "missing_capture_count": 2,
                    "captured_capture_count": 0,
                    "screenshot_capture_count": 1,
                    "recording_capture_count": 2,
                    "next_capture": "maya_scan_capture",
                },
            )
            self.assertEqual(captures["package_export"]["status"], "pass")
            self.assertEqual(captures["maya_scan"]["status"], "manual_validation_required")
            self.assertIn("Maya", captures["maya_scan"]["portfolio_use"])
            self.assertEqual(captures["maya_scan"]["capture_type"], "recording")
            self.assertEqual(captures["maya_scan"]["gap"], "补真实 Maya UI 截图或录屏。")
            self.assertIn("建议保存到", captures["maya_scan"]["next_step"])
            self.assertEqual(captures["ue_gate_review"]["status"], "warning")
            self.assertTrue(captures["ue_gate_review"]["suggested_capture_path"].endswith("03_ue_gate_review.mp4"))
            self.assertTrue(captures["ue_gate_review"]["suggested_capture_path"].startswith(temp_dir.replace("\\", "/")))
            self.assertEqual(captures["package_export"]["capture_type"], "screenshot")
            self.assertFalse(captures["package_export"]["capture_file_exists"])
            self.assertEqual(captures["package_export"]["capture_file_size"], 0)
            self.assertEqual(captures["package_export"]["capture_file_status"], "missing")
            self.assertIn("最终作品集剪辑", captures["package_export"]["next_step"])

            self.assertEqual(len(report["capture_tasks"]), 3)
            self.assertEqual(
                report["capture_tasks"][0],
                {
                    "step_id": "maya_scan",
                    "capture_type": "recording",
                    "suggested_capture_path": captures["maya_scan"]["suggested_capture_path"],
                    "capture_file_status": "missing",
                    "next_step": captures["maya_scan"]["next_step"],
                },
            )
            self.assertNotIn("status", report["capture_tasks"][0])
            self.assertNotIn("title", report["capture_tasks"][0])

            shooting_cards = dict((item["step_id"], item) for item in report["capture_shooting_cards"])
            self.assertEqual(len(shooting_cards), 3)
            self.assertIn("Maya 发布工作台", shooting_cards["maya_scan"]["scene_focus"])
            self.assertIn("修复队列可见", shooting_cards["maya_scan"]["verify_points"])
            self.assertIn("打开报告入口可见", shooting_cards["ue_gate_review"]["verify_points"])
            self.assertEqual(shooting_cards["package_export"]["capture_file_status"], "missing")
            self.assertEqual(shooting_cards["package_export"]["suggested_capture_path"], captures["package_export"]["suggested_capture_path"])

    def test_pass_step_without_refs_still_requires_visual_capture(self):
        report = create_portfolio_evidence_manifest(
            {
                "stage": "portfolio_demo_pack",
                "steps": [
                    {"id": "maya_scan", "title": "Maya", "status": "pass", "evidence_refs": [], "missing_action": ""},
                ],
            }
        )

        self.assertEqual(report["captures"][0]["status"], "manual_validation_required")
        self.assertEqual(report["captures"][0]["gap"], "补真实截图或录屏证据。")
        self.assertEqual(report["captures"][0]["suggested_capture_path"], "01_maya_scan.mp4")

    def test_missing_demo_pack_steps_is_not_false_pass(self):
        report = create_portfolio_evidence_manifest({})

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["captures"], [])
        self.assertEqual(report["next_capture"], "demo_pack_steps")
        self.assertEqual(
            report["capture_summary"],
            {
                "total_capture_count": 0,
                "ready_capture_count": 0,
                "missing_capture_count": 0,
                "captured_capture_count": 0,
                "screenshot_capture_count": 0,
                "recording_capture_count": 0,
                "next_capture": "demo_pack_steps",
            },
        )
        self.assertIn("--portfolio-demo-pack", report["next_action"])
        self.assertIn("作品集演示包", report["next_action"])
        self.assertEqual(report["warnings"][0]["id"], "missing_demo_pack_steps")
        self.assertIn("作品集演示包", report["warnings"][0]["message"])
        self.assertIn("作品集演示包", report["capture_review_index"]["next_review"]["prompt"])

    def test_empty_evidence_root_keeps_capture_file_missing(self):
        report = create_portfolio_evidence_manifest(_demo_pack(), "")
        captures = dict((item["step_id"], item) for item in report["captures"])

        self.assertEqual(
            report["capture_directory_plan"],
            {
                "evidence_root": "",
                "needs_directory_create": False,
                "missing_task_count": 3,
                "captured_task_count": 0,
            },
        )
        self.assertEqual(report["capture_summary"]["captured_capture_count"], 0)
        self.assertEqual(
            report["capture_review_index"]["states"],
            {
                "captured": {"total": 0, "screenshot": 0, "recording": 0},
                "missing": {"total": 3, "screenshot": 1, "recording": 2},
                "ready": {"total": 1, "screenshot": 1, "recording": 0},
            },
        )
        self.assertEqual(report["capture_review_index"]["next_review"]["step_id"], "maya_scan")
        self.assertEqual(report["capture_review_index"]["next_review"]["capture_type"], "recording")
        self.assertEqual(report["capture_review_index"]["next_review"]["capture_file_status"], "missing")
        self.assertIn("证据目录", report["capture_review_index"]["next_review"]["prompt"])
        self.assertIn("evidence_root", report["capture_review_index"]["next_review"]["prompt"])
        self.assertEqual(captures["maya_scan"]["suggested_capture_path"], "01_maya_scan.mp4")
        self.assertFalse(captures["maya_scan"]["capture_file_exists"])
        self.assertEqual(captures["maya_scan"]["capture_file_size"], 0)
        self.assertEqual(captures["maya_scan"]["capture_file_status"], "missing")

    def test_missing_evidence_root_is_planned_without_creating_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_root = os.path.join(temp_dir, "captures")

            report = create_portfolio_evidence_manifest(_demo_pack(), capture_root)

            self.assertFalse(os.path.exists(capture_root))
            self.assertEqual(
                report["capture_directory_plan"],
                {
                    "evidence_root": capture_root.replace("\\", "/"),
                    "needs_directory_create": True,
                    "missing_task_count": 3,
                    "captured_task_count": 0,
                },
            )

    def test_existing_screenshot_file_is_marked_captured_without_changing_step_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_path = os.path.join(temp_dir, "02_package_export.png")
            with open(capture_path, "wb") as stream:
                stream.write(b"png-capture")

            report = create_portfolio_evidence_manifest(_demo_pack(), temp_dir)
            captures = dict((item["step_id"], item) for item in report["captures"])

            self.assertEqual(report["capture_summary"]["captured_capture_count"], 1)
            self.assertEqual(
                report["capture_directory_plan"],
                {
                    "evidence_root": temp_dir.replace("\\", "/"),
                    "needs_directory_create": False,
                    "missing_task_count": 2,
                    "captured_task_count": 1,
                },
            )
            self.assertEqual(captures["package_export"]["status"], "pass")
            self.assertTrue(captures["package_export"]["capture_file_exists"])
            self.assertEqual(captures["package_export"]["capture_file_size"], len(b"png-capture"))
            self.assertEqual(captures["package_export"]["capture_file_status"], "captured")
            self.assertEqual(
                report["capture_review_index"]["states"],
                {
                    "captured": {"total": 1, "screenshot": 1, "recording": 0},
                    "missing": {"total": 2, "screenshot": 0, "recording": 2},
                    "ready": {"total": 1, "screenshot": 1, "recording": 0},
                },
            )
            self.assertEqual(report["capture_review_index"]["next_review"]["step_id"], "maya_scan")
            self.assertIn("下一步采集 maya_scan", report["capture_review_index"]["next_review"]["prompt"])

            tasks = dict((item["step_id"], item) for item in report["capture_tasks"])
            self.assertEqual(tasks["package_export"]["capture_file_status"], "captured")
            self.assertEqual(tasks["package_export"]["suggested_capture_path"], captures["package_export"]["suggested_capture_path"])
            self.assertNotIn("status", tasks["package_export"])
            cards = dict((item["step_id"], item) for item in report["capture_shooting_cards"])
            self.assertEqual(cards["package_export"]["capture_file_status"], "captured")
            self.assertIn("Package 路径可见", cards["package_export"]["verify_points"])

    def test_existing_recording_file_is_marked_captured_without_hiding_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_path = os.path.join(temp_dir, "03_ue_gate_review.mp4")
            with open(capture_path, "wb") as stream:
                stream.write(b"mp4-capture")

            report = create_portfolio_evidence_manifest(_demo_pack(), temp_dir)
            captures = dict((item["step_id"], item) for item in report["captures"])

            self.assertEqual(report["status"], "warning")
            self.assertEqual(report["capture_summary"]["captured_capture_count"], 1)
            self.assertEqual(captures["ue_gate_review"]["status"], "warning")
            self.assertTrue(captures["ue_gate_review"]["capture_file_exists"])
            self.assertEqual(captures["ue_gate_review"]["capture_file_size"], len(b"mp4-capture"))
            self.assertEqual(captures["ue_gate_review"]["capture_file_status"], "captured")
            self.assertEqual(
                report["capture_review_index"]["states"],
                {
                    "captured": {"total": 1, "screenshot": 0, "recording": 1},
                    "missing": {"total": 2, "screenshot": 1, "recording": 1},
                    "ready": {"total": 1, "screenshot": 1, "recording": 0},
                },
            )
            self.assertEqual(report["capture_review_index"]["next_review"]["step_id"], "maya_scan")
            self.assertEqual(report["capture_review_index"]["next_review"]["capture_file_status"], "missing")

    def test_cli_writes_capture_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            demo_path = os.path.join(temp_dir, "demo_pack.json")
            capture_root = os.path.join(temp_dir, "captures")
            report_path = os.path.join(temp_dir, "capture_manifest.json")
            write_report(demo_path, _demo_pack())

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/unreal_import_manifest.py",
                    "--portfolio-evidence-manifest",
                    demo_path,
                    capture_root,
                    report_path,
                ],
                cwd=os.getcwd(),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            report = json.loads(result.stdout)
            with open(report_path, encoding="utf-8") as stream:
                written_report = json.load(stream)
            self.assertEqual(report["stage"], "portfolio_evidence_manifest")
            self.assertEqual(report["next_capture"], "maya_scan_capture")
            self.assertTrue(os.path.exists(report_path))
            self.assertEqual(report["report_path"], report_path.replace("\\", "/"))
            self.assertEqual(report["report_artifact"]["file_name"], "capture_manifest.json")
            self.assertEqual(written_report["report_artifact"], report["report_artifact"])
            self.assertIn("--portfolio-evidence-manifest", report["command_args"])
            self.assertIn(demo_path, report["command_args"])


def _demo_pack():
    return {
        "stage": "portfolio_demo_pack",
        "steps": [
            {
                "id": "maya_scan",
                "title": "Maya 扫描",
                "status": "manual_validation_required",
                "evidence_refs": [],
                "missing_action": "补真实 Maya UI 截图或录屏。",
            },
            {
                "id": "package_export",
                "title": "AF Package",
                "status": "pass",
                "evidence_refs": ["package_acceptance:report.json"],
                "missing_action": "",
            },
            {
                "id": "ue_gate_review",
                "title": "UE Gate",
                "status": "warning",
                "evidence_refs": ["source:HandleOpenReportClicked"],
                "missing_action": "补真实 UE Gate 点击截图。",
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
