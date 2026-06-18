from __future__ import absolute_import

import unittest

from asset_forge.shared.acceptance_gate import apply_acceptance_gate, create_gate_policy
from asset_forge.shared.report_schema import create_acceptance_summary, validate_report_schema


class ReportSchemaValidatorTest(unittest.TestCase):
    def test_validates_common_report_fields(self):
        summary = create_acceptance_summary("pass")
        report = {
            "version": "0.1",
            "stage": "sample",
            "status": "pass",
            "summary": summary,
            "can_accept": True,
            "warnings": [],
            "errors": [],
            "next_action": "可以验收",
        }

        validation = validate_report_schema(report)

        self.assertEqual(validation["status"], "pass")
        self.assertTrue(validation["can_accept"])

    def test_gate_report_requires_gate_fields(self):
        summary = create_acceptance_summary("warning", warnings=[{"message": "warn"}])
        report = {
            "version": "0.1",
            "stage": "sample_gate",
            "status": "warning",
            "summary": summary,
            "can_accept": True,
            "warnings": summary["warnings"],
            "errors": [],
            "next_action": "检查 warnings，确认可接受后继续",
        }
        apply_acceptance_gate(report, create_gate_policy(strict=True))

        validation = validate_report_schema(report, require_gate=True)

        self.assertEqual(validation["status"], "pass")
        self.assertTrue(any(item["path"] == "report.gate_status" for item in validation["checks"]))

    def test_reports_missing_schema_fields_in_chinese(self):
        validation = validate_report_schema({"stage": "broken"})

        self.assertEqual(validation["status"], "error")
        self.assertTrue(any("缺失" in item["message"] for item in validation["errors"]))

    def test_failed_status_blocks_acceptance_without_errors(self):
        summary = create_acceptance_summary("failed")

        self.assertEqual(summary["status"], "error")
        self.assertFalse(summary["can_accept"])


if __name__ == "__main__":
    unittest.main()
