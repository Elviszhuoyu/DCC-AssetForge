from __future__ import absolute_import

import unittest

from asset_forge.shared.material_profile_schema import get_default_material_profile
from asset_forge.shared.material_profile_validator import validate_material_texture_coverage


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


if __name__ == "__main__":
    unittest.main()
