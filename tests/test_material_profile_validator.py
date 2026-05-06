from __future__ import absolute_import

import unittest

from asset_forge.shared.material_profile_schema import get_default_material_profile
from asset_forge.shared.material_profile_validator import validate_material_texture_coverage, validate_packed_texture_channel_rules


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

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["checks"][0]["usage"], "packed_arm")

    def test_warns_when_packed_arm_channels_are_remapped_unexpectedly(self):
        profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")
        profile = dict(profile, texture_rules=[dict(rule) for rule in profile["texture_rules"]])
        for rule in profile["texture_rules"]:
            if rule["usage"] == "packed_arm":
                rule["channels"] = {"r": "metallic", "g": "roughness", "b": "ao"}

        report = validate_packed_texture_channel_rules(profile)

        self.assertEqual(report["status"], "warning")
        self.assertIn("packed_arm", report["warning_usages"])


if __name__ == "__main__":
    unittest.main()
