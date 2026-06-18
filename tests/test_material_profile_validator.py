from __future__ import absolute_import

import unittest

from asset_forge.shared.material_profile_schema import get_default_material_profile
from asset_forge.shared.material_profile_validator import (
    validate_material_texture_coverage,
    validate_material_texture_quality,
    validate_packed_texture_channel_rules,
)


class MaterialProfileValidatorTest(unittest.TestCase):
    def test_reports_missing_required_texture_usages(self):
        profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")

        report = validate_material_texture_coverage(profile, [{"usage": "base_color"}])

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["missing_usages"], ["normal"])

    def test_passes_when_required_texture_usages_exist(self):
        profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")

        report = validate_material_texture_coverage(profile, [{"usage": "base_color"}, {"usage": "normal"}])

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["missing_usages"], [])

    def test_validates_default_arm_channel_rule(self):
        profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")

        report = validate_packed_texture_channel_rules(profile)
        usages = [check["usage"] for check in report["checks"]]

        self.assertEqual(report["status"], "pass")
        self.assertIn("packed_arm", usages)
        self.assertIn("imperfection_mask", usages)

    def test_warns_when_packed_arm_channels_are_remapped_unexpectedly(self):
        profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")
        profile = dict(profile, texture_rules=[dict(rule) for rule in profile["texture_rules"]])
        for rule in profile["texture_rules"]:
            if rule["usage"] == "packed_arm":
                rule["channels"] = {"r": "metallic", "g": "roughness", "b": "ao"}

        report = validate_packed_texture_channel_rules(profile)

        self.assertEqual(report["status"], "warning")
        self.assertIn("packed_arm", report["warning_usages"])

    def test_texture_quality_validates_manifest_metadata_without_image_dependency(self):
        profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")

        report = validate_material_texture_quality(
            profile,
            [
                {
                    "usage": "base_color",
                    "package_path": "D:/Pkg/Textures/SM_Crate_BaseColor.png",
                    "width": 1024,
                    "height": 1024,
                    "srgb": True,
                    "compression": "default",
                },
                {
                    "usage": "normal",
                    "package_path": "D:/Pkg/Textures/SM_Crate_N.jpg",
                    "width": 1000,
                    "height": 1024,
                    "srgb": True,
                    "compression": "default",
                },
            ],
        )

        self.assertEqual(report["status"], "warning")
        messages = [item["message"] for item in report["checks"] if item["status"] == "warning"]
        self.assertTrue(any("格式不在推荐列表" in message for message in messages))
        self.assertTrue(any("尺寸建议使用 2 的幂" in message for message in messages))
        self.assertTrue(any("sRGB 与 profile 不一致" in message for message in messages))

    def test_texture_quality_counts_usage_per_texture_set(self):
        profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")

        report = validate_material_texture_quality(
            profile,
            [
                {"usage": "base_color", "package_path": "D:/Pkg/T_A_BaseColor.png", "selected_texture_set": "A", "width": 1024, "height": 1024, "srgb": True, "compression": "default"},
                {"usage": "normal", "package_path": "D:/Pkg/T_A_Normal.png", "selected_texture_set": "A", "width": 1024, "height": 1024, "srgb": False, "compression": "normalmap"},
                {"usage": "base_color", "package_path": "D:/Pkg/T_B_BaseColor.png", "selected_texture_set": "B", "width": 1024, "height": 1024, "srgb": True, "compression": "default"},
                {"usage": "normal", "package_path": "D:/Pkg/T_B_Normal.png", "selected_texture_set": "B", "width": 1024, "height": 1024, "srgb": False, "compression": "normalmap"},
            ],
        )

        duplicate_warnings = [
            item for item in report["checks"]
            if item["status"] == "warning" and item["id"] == "texture_count" and "同一 usage" in item["message"]
        ]
        self.assertEqual(duplicate_warnings, [])


if __name__ == "__main__":
    unittest.main()
