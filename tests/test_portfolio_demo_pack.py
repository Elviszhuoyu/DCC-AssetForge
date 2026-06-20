from __future__ import absolute_import

import json
import os
import subprocess
import sys
import tempfile
import unittest

from asset_forge.shared.report_schema import write_report
from asset_forge.unreal.portfolio_demo_pack import create_portfolio_demo_pack


class PortfolioDemoPackTest(unittest.TestCase):
    def test_demo_pack_turns_evidence_into_short_storyboard(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = os.path.join(temp_dir, "evidence.json")
            write_report(evidence_path, _evidence(temp_dir))

            report = create_portfolio_demo_pack(evidence_path)
            steps = dict((item["id"], item) for item in report["steps"])

            self.assertEqual(report["stage"], "portfolio_demo_pack")
            self.assertEqual(report["demo_duration_minutes"], 3)
            self.assertEqual(steps["maya_scan"]["status"], "pass")
            self.assertEqual(steps["package_export"]["status"], "pass")
            self.assertEqual(steps["ue_gate_review"]["status"], "warning")
            self.assertEqual(steps["clean_install"]["status"], "manual_validation_required")
            self.assertIn("关闭 UE Editor", steps["clean_install"]["missing_action"])
            self.assertTrue(report["can_show_as_portfolio_wip"])
            self.assertFalse(report["can_claim_production_ready"])

    def test_demo_pack_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = os.path.join(temp_dir, "evidence.json")
            report_path = os.path.join(temp_dir, "portfolio_demo_pack.json")
            write_report(evidence_path, _evidence(temp_dir))

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/unreal_import_manifest.py",
                    "--portfolio-demo-pack",
                    evidence_path,
                    report_path,
                ],
                cwd=os.getcwd(),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            report = json.loads(result.stdout)
            self.assertEqual(report["stage"], "portfolio_demo_pack")
            self.assertTrue(os.path.exists(report_path))
            self.assertEqual(json.load(open(report_path, encoding="utf-8"))["stage"], "portfolio_demo_pack")

    def test_file_evidence_keeps_comment_box_persistence_boundary_in_material_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence = _evidence(temp_dir)
            evidence["material_graph_evidence_report"] = {
                "status": "pass",
                "ta_visual_review": {
                    "comment_box_persistence_status": "needs_on_site_review",
                },
            }
            evidence_path = os.path.join(temp_dir, "evidence.json")
            write_report(evidence_path, evidence)

            report = create_portfolio_demo_pack(evidence_path)
            steps = dict((item["id"], item) for item in report["steps"])
            material_result = steps["material_result"]

            self.assertEqual(material_result["status"], "warning")
            self.assertIn("当前会话读回不等于冷启动持久化通过", material_result["missing_action"])
            self.assertIn("当前会话读回不等于冷启动持久化通过", material_result["operator_checklist"][0])
            self.assertIn(
                "material_graph_evidence_report:ta_visual_review.comment_box_persistence_status=needs_on_site_review",
                material_result["evidence_refs"],
            )


def _evidence(temp_dir):
    return {
        "stage": "offline_evidence_bundle",
        "stages": {
            "maya_ui_flow": {
                "status": "pass",
                "report_path": os.path.join(temp_dir, "maya_ui_flow.json"),
                "repair_actions": [{"id": "fix_asset_name_prefix", "label": "修复资产名前缀"}],
            },
            "contract_check": {"status": "pass", "report_path": os.path.join(temp_dir, "contract.json")},
            "package_acceptance": {"status": "pass", "report_path": os.path.join(temp_dir, "acceptance.json")},
            "ue_gate_visual_review": {
                "status": "warning",
                "report_path": os.path.join(temp_dir, "ue_gate_review.json"),
                "notes": ["HandleOpenReportClicked", "打开报告"],
            },
            "material_graph_evidence": {"status": "pass", "report_path": os.path.join(temp_dir, "material.json")},
            "clean_install_validation": {"status": "manual_validation_required"},
        },
        "report_paths": {
            "accept_flow": os.path.join(temp_dir, "accept_flow.json"),
        },
    }


if __name__ == "__main__":
    unittest.main()
