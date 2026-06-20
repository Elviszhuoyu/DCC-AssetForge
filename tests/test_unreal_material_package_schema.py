from __future__ import absolute_import

import unittest

from asset_forge.shared.material_profile_schema import get_default_material_profiles
from asset_forge.unreal.material_library_acceptance import validate_material_library_product_readiness
from asset_forge.unreal.material_package_schema import (
    get_default_material_package_plan,
    material_instance_package_paths,
    material_package_paths,
    profile_master_material_issues,
    validate_material_package_plan,
)


class UnrealMaterialPackageSchemaTest(unittest.TestCase):
    def test_default_plan_contains_props_render_mode_materials(self):
        plan = get_default_material_package_plan()
        material_paths = material_package_paths(plan)

        self.assertEqual(validate_material_package_plan(plan), [])
        self.assertEqual(plan["content_mount"], "/AssetForge")
        self.assertEqual(plan["disk_content_root"], "Plugins/AssetForge/Content")
        self.assertIn("/AssetForge/Textures", plan["directories"])
        self.assertIn("/AssetForge/Showcase", plan["directories"])
        self.assertEqual(
            material_paths,
            [
                "/AssetForge/Materials/M_AF_Props_Master",
                "/AssetForge/Materials/M_AF_Environment_Master",
                "/AssetForge/Materials/M_AF_Character_Master",
            ],
        )

    def test_default_profiles_reference_planned_master_materials(self):
        issues = profile_master_material_issues(
            get_default_material_profiles(),
            get_default_material_package_plan(),
        )

        self.assertEqual(issues, [])

    def test_props_opaque_uses_minimal_static_prop_pbr_parameters(self):
        plan = get_default_material_package_plan()
        opaque = self._find_material(plan, "M_AF_Props_Master")

        self.assertEqual(opaque["render_mode"], "masked")
        self.assertEqual(opaque["texture_parameters"], ["BaseColor", "Normal", "ARM", "OpacityMask", "Emissive", "ImperfectionMask"])
        self.assertIn("Emissive", opaque["texture_parameters"])
        self.assertIn("NormalStrength", opaque["scalar_parameters"])
        self.assertIn("UVTiling", opaque["scalar_parameters"])
        self.assertIn("Specular", opaque["scalar_parameters"])
        self.assertNotIn("RoughnessMin", opaque["scalar_parameters"])
        self.assertNotIn("RoughnessMax", opaque["scalar_parameters"])
        self.assertIn("BaseColorTint", opaque["vector_parameters"])
        self.assertEqual(opaque["master_family"], "MM_Surface_PBR")
        self.assertEqual(opaque["parameter_api_mapping"]["ARM"], "Pack Map")
        self.assertIn("EmissiveIntensity", opaque["scalar_parameters"])
        self.assertIn("EmissiveTint", opaque["vector_parameters"])
        self.assertIn("OpacityMask", opaque["texture_parameters"])
        self.assertFalse(opaque["static_switches"]["UseEmissive"])
        self.assertFalse(opaque["static_switches"]["UseOpacityMask"])
        self.assertFalse(opaque["static_switches"]["UseSeparateOpacityMask"])

    def test_virtual_texture_variants_are_not_generated_until_verified(self):
        plan = get_default_material_package_plan()
        props = self._find_material(plan, "M_AF_Props_Master")

        self.assertFalse(props["supports_virtual_texture_sampling"])
        self.assertNotIn("UseVirtualTextures", props["static_switches"])
        self.assertFalse(any(material["name"].endswith("_VT") for material in plan["materials"]))

    def test_masked_and_emissive_are_instance_states_on_category_master(self):
        plan = get_default_material_package_plan()
        masked = self._find_material_instance(plan, "MI_AF_Props_Masked")
        separate_mask = self._find_material_instance(plan, "MI_AF_Props_Masked_SeparateMask")
        emissive = self._find_material_instance(plan, "MI_AF_Props_Emissive")

        self.assertEqual(masked["parent_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertTrue(masked["static_switch_overrides"]["UseOpacityMask"])
        self.assertNotIn("UseSeparateOpacityMask", masked["static_switch_overrides"])
        self.assertEqual(separate_mask["parent_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertTrue(separate_mask["static_switch_overrides"]["UseOpacityMask"])
        self.assertTrue(separate_mask["static_switch_overrides"]["UseSeparateOpacityMask"])
        self.assertEqual(separate_mask["texture_overrides"]["OpacityMask"], "/AssetForge/Textures/T_AF_Preview_OpacityMask_Stripes")
        self.assertEqual(emissive["parent_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertTrue(emissive["static_switch_overrides"]["UseEmissive"])
        self.assertEqual(emissive["texture_overrides"]["Emissive"], "/AssetForge/Textures/T_AF_Preview_Emissive_Panels")

    def test_optional_controls_are_exposed_on_category_masters(self):
        plan = get_default_material_package_plan()
        props = self._find_material(plan, "M_AF_Props_Master")
        environment = self._find_material(plan, "M_AF_Environment_Master")

        self.assertIn("Emissive", props["texture_parameters"])
        self.assertIn("ImperfectionMask", props["texture_parameters"])
        self.assertIn("ImperfectionIntensity", props["scalar_parameters"])
        self.assertNotIn("EdgeWearIntensity", props["scalar_parameters"])
        self.assertNotIn("WorldAlignedScale", environment["scalar_parameters"])
        self.assertNotIn("ProjectionBlendSharpness", environment["scalar_parameters"])
        self.assertNotIn("MacroVariationScale", environment["scalar_parameters"])
        self.assertNotIn("MacroVariationIntensity", environment["scalar_parameters"])
        self.assertNotIn("UseWorldAligned", environment["static_switches"])
        self.assertNotIn("UseTriplanar", environment["static_switches"])

    def test_default_placeholder_textures_have_semantic_formats(self):
        plan = get_default_material_package_plan()
        textures = dict((item["name"], item) for item in plan["placeholder_textures"])

        self.assertEqual(textures["T_AF_Default_BaseColor"]["compression"], "default")
        self.assertTrue(textures["T_AF_Default_BaseColor"]["srgb"])
        self.assertEqual(textures["T_AF_Default_Normal"]["compression"], "normal")
        self.assertFalse(textures["T_AF_Default_Normal"]["srgb"])
        self.assertEqual(textures["T_AF_Default_ARM"]["compression"], "masks")
        self.assertEqual(textures["T_AF_Default_ARM"]["rgba"][:3], [255, 128, 0])
        self.assertEqual(textures["T_AF_Default_OpacityMask"]["compression"], "masks")
        self.assertFalse(textures["T_AF_Default_OpacityMask"]["srgb"])
        self.assertEqual(textures["T_AF_Default_OpacityMask"]["rgba"][:3], [255, 255, 255])
        self.assertEqual(textures["T_AF_Default_Emissive"]["rgba"][:3], [0, 0, 0])
        self.assertEqual(textures["T_AF_Preview_BaseColor_AlphaGrid"]["pattern"], "alpha_grid")
        self.assertEqual(textures["T_AF_Preview_OpacityMask_Stripes"]["pattern"], "mask_stripes")
        self.assertEqual(textures["T_AF_Preview_Emissive_Panels"]["pattern"], "emissive_panels")
        self.assertEqual(textures["T_AF_Preview_Imperfection_Wear"]["compression"], "masks")
        self.assertEqual(textures["T_AF_Preview_BaseColor_MetalPanel"]["pattern"], "metal_panel")
        self.assertEqual(textures["T_AF_Preview_BaseColor_Rubber"]["pattern"], "rubber")
        self.assertEqual(textures["T_AF_Preview_BaseColor_TileFloor"]["pattern"], "tile_floor")
        self.assertEqual(textures["T_AF_Preview_BaseColor_SkinWarm"]["pattern"], "skin_warm")
        self.assertEqual(textures["T_AF_Preview_ARM_Metal"]["compression"], "masks")
        self.assertFalse(textures["T_AF_Preview_ARM_Rough"]["srgb"])

    def test_default_material_instance_presets_are_planned(self):
        plan = get_default_material_package_plan()
        instance_paths = material_instance_package_paths(plan)

        self.assertIn("/AssetForge/MaterialInstances/MI_AF_Props_Default", instance_paths)
        self.assertIn("/AssetForge/MaterialInstances/MI_AF_Props_DirtyWear", instance_paths)
        self.assertIn("/AssetForge/MaterialInstances/MI_AF_Props_MetalPanel", instance_paths)
        self.assertIn("/AssetForge/MaterialInstances/MI_AF_Environment_TileFloor", instance_paths)
        self.assertIn("/AssetForge/MaterialInstances/MI_AF_Character_SkinPreview", instance_paths)
        self.assertNotIn("/AssetForge/MaterialInstances/MI_AF_HardSurface_POM", instance_paths)
        dirty_wear = self._find_material_instance(plan, "MI_AF_Props_DirtyWear")
        self.assertEqual(dirty_wear["parent_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertEqual(dirty_wear["scalar_overrides"]["ImperfectionIntensity"], 0.75)
        self.assertEqual(dirty_wear["texture_overrides"]["ImperfectionMask"], "/AssetForge/Textures/T_AF_Preview_Imperfection_Wear")
        metal = self._find_material_instance(plan, "MI_AF_Props_MetalPanel")
        self.assertEqual(metal["texture_overrides"]["ARM"], "/AssetForge/Textures/T_AF_Preview_ARM_Metal")
        tile = self._find_material_instance(plan, "MI_AF_Environment_TileFloor")
        self.assertEqual(tile["scalar_overrides"]["UVTiling"], 4.0)
        skin = self._find_material_instance(plan, "MI_AF_Character_SkinPreview")
        self.assertEqual(skin["texture_overrides"]["BaseColor"], "/AssetForge/Textures/T_AF_Preview_BaseColor_SkinWarm")

    def test_default_library_does_not_expose_unimplemented_controls(self):
        plan = get_default_material_package_plan()
        blocked = {
            "RoughnessMin",
            "RoughnessMax",
            "EdgeWearIntensity",
            "WorldAlignedScale",
            "ProjectionBlendSharpness",
            "MacroVariationScale",
            "MacroVariationIntensity",
            "SkinRoughnessBias",
            "MicroNormalStrength",
        }

        for material in plan["materials"]:
            self.assertFalse(blocked.intersection(material["scalar_parameters"]), material["name"])

    def test_instance_overrides_match_parent_parameters(self):
        plan = get_default_material_package_plan()
        parents = dict((material["path"], material) for material in plan["materials"])

        for material_instance in plan["material_instances"]:
            parent = parents[material_instance["parent_material"]]
            for parameter in material_instance.get("scalar_overrides", {}):
                self.assertIn(parameter, parent["scalar_parameters"])
            for parameter in material_instance.get("texture_overrides", {}):
                self.assertIn(parameter, parent["texture_parameters"])
            for parameter in material_instance.get("static_switch_overrides", {}):
                self.assertIn(parameter, parent["static_switches"])

    def test_product_readiness_acceptance_passes_for_default_library(self):
        report = validate_material_library_product_readiness()

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["issue_count"], 0)
        self.assertEqual(report["master_count"], 3)
        self.assertGreaterEqual(report["preset_count"], 15)
        self.assertGreaterEqual(report["preview_texture_count"], 10)
        self.assertEqual(report["showcase_level_path"], "/AssetForge/Showcase/LV_AF_Material_Showcase")
        self.assertEqual(report["showcase_category_count"], 3)
        self.assertGreaterEqual(report["showcase_entry_count"], 15)

    def test_default_material_functions_are_not_generated_until_called_by_masters(self):
        plan = get_default_material_package_plan()

        self.assertEqual(plan["functions"], [])

    def test_unused_mpc_is_not_declared_as_default_asset(self):
        plan = get_default_material_package_plan()

        self.assertEqual(plan["parameter_collections"], [])

    def _find_material(self, plan, name):
        for material in plan["materials"]:
            if material["name"] == name:
                return material
        raise AssertionError("missing material: {0}".format(name))

    def _find_material_instance(self, plan, name):
        for material_instance in plan["material_instances"]:
            if material_instance["name"] == name:
                return material_instance
        raise AssertionError("missing material instance: {0}".format(name))


if __name__ == "__main__":
    unittest.main()
