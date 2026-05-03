from __future__ import absolute_import

import unittest

from asset_forge.shared.ai_analysis import analyze_validation, build_analysis_input
from asset_forge.shared.constants import CHECK_STATUS_PASS, CHECK_STATUS_WARNING


class Phase3AiAnalysisTest(unittest.TestCase):
    def test_analysis_input_is_serializable(self):
        scan = {"asset_name": "SM_Crate_01", "triangles": 1200}
        validation = {
            "asset_type": "static_prop",
            "target_platform": "pc",
            "score": 92,
            "status": "warning",
            "can_export": True,
            "checks": [],
        }

        data = build_analysis_input(scan, validation).to_dict()

        self.assertEqual(data["asset_name"], "SM_Crate_01")
        self.assertEqual(data["target_platform"], "pc")
        self.assertIn("project_rules", data)

    def test_warning_result_outputs_chinese_suggestion(self):
        scan = {"asset_name": "SM_Crate_01"}
        validation = {
            "asset_type": "static_prop",
            "target_platform": "high_end_mobile",
            "score": 84,
            "status": CHECK_STATUS_WARNING,
            "can_export": True,
            "checks": [
                {
                    "id": "lightmap_uv",
                    "label": "Lightmap UV",
                    "status": CHECK_STATUS_WARNING,
                    "message": "缺少 Lightmap UV",
                }
            ],
        }

        suggestion = analyze_validation(scan, validation)

        self.assertIn("缺少 Lightmap UV", suggestion)
        self.assertIn("第二套", suggestion)
        self.assertIn("不参与通过 / 失败判定", suggestion)
        self.assertTrue(validation["can_export"])

    def test_pass_result_outputs_pass_message(self):
        scan = {"asset_name": "SM_Crate_01"}
        validation = {
            "asset_type": "static_prop",
            "target_platform": "pc",
            "score": 100,
            "status": CHECK_STATUS_PASS,
            "can_export": True,
            "checks": [],
        }

        suggestion = analyze_validation(scan, validation)

        self.assertIn("检查结果为通过", suggestion)
        self.assertIn("Unreal 导入流程", suggestion)


if __name__ == "__main__":
    unittest.main()
