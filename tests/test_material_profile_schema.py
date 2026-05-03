from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.constants import ASSET_TYPE_PROPS, RENDER_MODE_OPAQUE
from asset_forge.shared.manifest_schema import create_manifest, validate_manifest
from asset_forge.shared.material_profile_schema import (
    create_material_profile,
    get_default_material_profile,
    get_default_material_profiles,
    read_material_profiles,
    validate_material_profile,
    validate_material_profiles,
    write_material_profiles,
)


class MaterialProfileSchemaTest(unittest.TestCase):
    def test_default_profiles_define_props_render_modes(self):
        profiles = get_default_material_profiles()
        profile_names = [profile["name"] for profile in profiles["profiles"]]

        self.assertEqual(validate_material_profiles(profiles), [])
        self.assertIn("Props_Opaque_PainterUE_ARM", profile_names)
        self.assertIn("Props_Masked_PainterUE_ARM", profile_names)
        self.assertIn("Props_Translucent_PainterUE_ARM", profile_names)

    def test_props_opaque_profile_contains_painter_ue_arm_rules(self):
        profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")
        rules_by_usage = dict((rule["usage"], rule) for rule in profile["texture_rules"])

        self.assertEqual(profile["asset_family"], ASSET_TYPE_PROPS)
        self.assertEqual(profile["render_mode"], RENDER_MODE_OPAQUE)
        self.assertEqual(profile["master_material"], "/Game/AssetForge/Materials/M_AF_Props_Opaque")
        self.assertTrue(profile["supports"]["emissive"])
        self.assertFalse(profile["supports"]["opacity_mask"])
        self.assertEqual(rules_by_usage["packed_arm"]["channels"]["r"], "ao")
        self.assertEqual(rules_by_usage["packed_arm"]["channels"]["g"], "roughness")
        self.assertEqual(rules_by_usage["packed_arm"]["channels"]["b"], "metallic")
        self.assertFalse(rules_by_usage["normal"]["srgb"])

    def test_profile_validation_reports_missing_fields(self):
        profile = create_material_profile(
            "Broken_Profile",
            ASSET_TYPE_PROPS,
            RENDER_MODE_OPAQUE,
            "/Game/Materials/M_Broken",
            texture_rules=[{"usage": "base_color"}],
        )

        issues = validate_material_profile(profile)

        self.assertIn("texture_rules[0] missing field: parameter", issues)
        self.assertIn("texture_rules[0] missing field: suffixes", issues)
        self.assertIn("texture_rules[0] missing field: srgb", issues)

    def test_profile_collection_round_trips_json(self):
        temp_dir = tempfile.mkdtemp()
        try:
            path = os.path.join(temp_dir, "material_profiles.json")
            profiles = get_default_material_profiles()

            write_material_profiles(path, profiles)
            loaded = read_material_profiles(path)

            self.assertEqual(validate_material_profiles(loaded), [])
            self.assertEqual(loaded["profiles"][0]["name"], profiles["profiles"][0]["name"])
        finally:
            shutil.rmtree(temp_dir)

    def test_config_material_profiles_file_is_valid(self):
        loaded = read_material_profiles(os.path.join("config", "material_profiles.json"))

        self.assertEqual(validate_material_profiles(loaded), [])
        self.assertEqual(loaded["profiles"][0]["name"], "Props_Opaque_PainterUE_ARM")

    def test_manifest_can_reference_material_profile_without_breaking_compatibility(self):
        manifest = create_manifest(
            "SM_Crate_01",
            "C:/Exports/SM_Crate_01.fbx",
            "/Game/Props",
            material_profile="Props_Opaque_PainterUE_ARM",
        )

        self.assertEqual(validate_manifest(manifest), [])
        self.assertEqual(manifest["material_profile"], "Props_Opaque_PainterUE_ARM")


if __name__ == "__main__":
    unittest.main()
