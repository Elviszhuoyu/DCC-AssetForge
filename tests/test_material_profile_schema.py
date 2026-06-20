from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.constants import ASSET_TYPE_CHARACTER, ASSET_TYPE_ENVIRONMENT, ASSET_TYPE_FX, ASSET_TYPE_PROPS, RENDER_MODE_ADDITIVE, RENDER_MODE_OPAQUE
from asset_forge.shared.manifest_schema import create_manifest, validate_manifest
from asset_forge.shared.material_profile_schema import (
    create_material_profile,
    get_default_material_profile,
    get_default_material_profiles,
    get_material_profile,
    get_project_material_profiles,
    export_material_profiles_config,
    import_material_profiles_config,
    material_profile_names,
    read_material_profiles,
    resolve_material_profile,
    validate_material_profile,
    validate_material_profiles,
    validate_material_profiles_report,
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
        self.assertIn("Environment_Opaque_PainterUE_ARM", profile_names)
        self.assertIn("Character_Basic_PainterUE_ARM", profile_names)
        self.assertIn("Emissive_Surface_PainterUE", profile_names)

    def test_props_opaque_profile_contains_painter_ue_arm_rules(self):
        profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")
        rules_by_usage = dict((rule["usage"], rule) for rule in profile["texture_rules"])

        self.assertEqual(profile["asset_family"], ASSET_TYPE_PROPS)
        self.assertEqual(profile["render_mode"], RENDER_MODE_OPAQUE)
        self.assertEqual(profile["master_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertEqual(profile["master_family"], "MM_Surface_PBR")
        self.assertEqual(profile["material_variants"]["opaque"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertEqual(profile["material_variants"]["dirty_wear_vt"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertEqual(profile["parameter_api_mapping"]["BaseColor"], "Base Color")
        self.assertTrue(profile["supports"]["emissive"])
        self.assertFalse(profile["supports"]["opacity_mask"])
        self.assertTrue(profile["supports"]["imperfection_mask"])
        self.assertFalse(profile["supports"]["pom"])
        self.assertIn("emissive", rules_by_usage)
        self.assertIn("height", rules_by_usage)
        self.assertNotIn("EmissiveIntensity", profile["scalar_parameters"])
        self.assertNotIn("EmissiveTint", profile["vector_parameters"])
        self.assertEqual(rules_by_usage["packed_arm"]["channels"]["r"], "ao")
        self.assertEqual(rules_by_usage["packed_arm"]["channels"]["g"], "roughness")
        self.assertEqual(rules_by_usage["packed_arm"]["channels"]["b"], "metallic")
        self.assertFalse(rules_by_usage["normal"]["srgb"])
        self.assertEqual(rules_by_usage["imperfection_mask"]["parameter"], "ImperfectionMask")
        self.assertFalse(rules_by_usage["imperfection_mask"]["required"])
        self.assertEqual(rules_by_usage["imperfection_mask"]["channels"]["g"], "edge_wear")
        self.assertEqual(profile["scalar_parameters"]["RoughnessMin"], 0.05)
        self.assertEqual(profile["scalar_parameters"]["RoughnessMax"], 0.95)
        self.assertIn("dirty_wear", profile["material_variants"])
        self.assertEqual(profile["parameter_api_mapping"]["ImperfectionMask"], "Imperfection Mask")

    def test_masked_profiles_allow_base_color_alpha_without_separate_mask(self):
        props = get_default_material_profile("Props_Masked_PainterUE_ARM")
        environment = get_default_material_profile("Environment_Masked_PainterUE_ARM")

        self.assertFalse(dict((rule["usage"], rule) for rule in props["texture_rules"])["opacity_mask"]["required"])
        self.assertFalse(dict((rule["usage"], rule) for rule in environment["texture_rules"])["opacity_mask"]["required"])

    def test_default_profiles_cover_environment_character_and_emissive_surface(self):
        environment = get_default_material_profile("Environment_Opaque_PainterUE_ARM")
        character = get_default_material_profile("Character_Basic_PainterUE_ARM")
        emissive = get_default_material_profile("Emissive_Surface_PainterUE")
        translucent = get_default_material_profile("Props_Translucent_PainterUE_ARM")

        self.assertEqual(environment["asset_family"], ASSET_TYPE_ENVIRONMENT)
        self.assertEqual(environment["master_material"], "/AssetForge/Materials/M_AF_Environment_Master")
        self.assertFalse(environment["supports"]["pom"])
        self.assertEqual(character["asset_family"], ASSET_TYPE_CHARACTER)
        self.assertEqual(character["master_material"], "/AssetForge/Materials/M_AF_Character_Master")
        self.assertIn("SubsurfaceTint", character["vector_parameters"])
        self.assertEqual(emissive["asset_family"], ASSET_TYPE_FX)
        self.assertEqual(emissive["render_mode"], RENDER_MODE_ADDITIVE)
        self.assertEqual(emissive["master_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertIn("EmissiveTint", emissive["vector_parameters"])
        self.assertEqual(translucent["enabled_material_variants"], ["glass", "translucent"])
        self.assertFalse(translucent["default_import_profile"])

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

    def test_material_profile_config_import_and_export_reports(self):
        temp_dir = tempfile.mkdtemp()
        try:
            export_path = os.path.join(temp_dir, "Profiles", "material_profiles.json")
            target_path = os.path.join(temp_dir, "Project", "material_profiles.json")

            export_report = export_material_profiles_config(export_path, get_default_material_profiles())
            import_report = import_material_profiles_config(export_path, target_path)

            self.assertEqual(export_report["status"], "success")
            self.assertEqual(import_report["status"], "success")
            self.assertTrue(os.path.exists(target_path))
            self.assertEqual(read_material_profiles(target_path)["profiles"][0]["name"], "Props_Opaque_PainterUE_ARM")
        finally:
            shutil.rmtree(temp_dir)

    def test_material_profile_validation_report_uses_chinese_messages(self):
        report = validate_material_profiles_report({"profiles": [{"name": "Broken"}]})

        self.assertEqual(report["status"], "error")
        self.assertFalse(report["can_use"])
        self.assertTrue(any("缺少字段" in issue for issue in report["issues"]))

    def test_config_material_profiles_file_is_valid(self):
        loaded = read_material_profiles(os.path.join("config", "material_profiles.json"))
        opaque = get_material_profile("Props_Opaque_PainterUE_ARM", loaded)
        rules_by_usage = dict((rule["usage"], rule) for rule in opaque["texture_rules"])

        self.assertEqual(validate_material_profiles(loaded), [])
        self.assertEqual(loaded["profiles"][0]["name"], "Props_Opaque_PainterUE_ARM")
        self.assertEqual(opaque["master_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertEqual(opaque["master_family"], "MM_Surface_PBR")
        self.assertIn("imperfection_mask", rules_by_usage)
        self.assertEqual(rules_by_usage["imperfection_mask"]["parameter"], "ImperfectionMask")
        self.assertIn("material_variants", opaque)
        self.assertIn("parameter_api_mapping", opaque)
        self.assertEqual(opaque["parameter_api_mapping"]["RoughnessMin"], "Roughness Min")

    def test_project_material_profiles_load_from_config_file(self):
        profiles = get_project_material_profiles(os.path.join("config", "material_profiles.json"))

        self.assertIn("Props_Masked_PainterUE_ARM", material_profile_names(profiles))
        self.assertEqual(get_material_profile("Props_Translucent_PainterUE_ARM", profiles)["render_mode"], "translucent")

    def test_manifest_can_reference_material_profile_without_breaking_compatibility(self):
        manifest = create_manifest(
            "SM_Crate_01",
            "C:/Exports/SM_Crate_01.fbx",
            "/Game/Props",
            material_profile="Props_Opaque_PainterUE_ARM",
        )

        self.assertEqual(validate_manifest(manifest), [])
        self.assertEqual(manifest["material_profile"], "Props_Opaque_PainterUE_ARM")

    def test_resolve_material_profile_falls_back_to_props_opaque(self):
        profile = resolve_material_profile("Missing_Profile")

        self.assertEqual(profile["name"], "Props_Opaque_PainterUE_ARM")


if __name__ == "__main__":
    unittest.main()
