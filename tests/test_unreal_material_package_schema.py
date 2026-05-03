from __future__ import absolute_import

import unittest

from asset_forge.shared.material_profile_schema import get_default_material_profiles
from asset_forge.unreal.material_package_schema import (
    get_default_material_package_plan,
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
        self.assertIn("/AssetForge/Materials/M_AF_Props_Opaque", material_paths)
        self.assertIn("/AssetForge/Materials/M_AF_Props_Masked", material_paths)
        self.assertIn("/AssetForge/Materials/M_AF_Props_Translucent", material_paths)

    def test_default_profiles_reference_planned_master_materials(self):
        issues = profile_master_material_issues(
            get_default_material_profiles(),
            get_default_material_package_plan(),
        )

        self.assertEqual(issues, [])

    def test_props_opaque_includes_emissive_as_base_capability(self):
        plan = get_default_material_package_plan()
        opaque = self._find_material(plan, "M_AF_Props_Opaque")

        self.assertEqual(opaque["render_mode"], "opaque")
        self.assertIn("Emissive", opaque["texture_parameters"])
        self.assertIn("EmissiveIntensity", opaque["scalar_parameters"])
        self.assertNotIn("OpacityMask", opaque["texture_parameters"])

    def test_masked_and_translucent_are_render_mode_specific(self):
        plan = get_default_material_package_plan()
        masked = self._find_material(plan, "M_AF_Props_Masked")
        translucent = self._find_material(plan, "M_AF_Props_Translucent")

        self.assertEqual(masked["render_mode"], "masked")
        self.assertIn("OpacityMask", masked["texture_parameters"])
        self.assertEqual(translucent["render_mode"], "translucent")
        self.assertIn("Opacity", translucent["texture_parameters"])

    def test_mpc_is_global_only(self):
        plan = get_default_material_package_plan()
        mpc = plan["parameter_collections"][0]

        self.assertEqual(mpc["name"], "MPC_AF_Global")
        self.assertIn("Global", mpc["purpose"])
        self.assertNotIn("BaseColor", mpc["parameters"])

    def _find_material(self, plan, name):
        for material in plan["materials"]:
            if material["name"] == name:
                return material
        raise AssertionError("missing material: {0}".format(name))


if __name__ == "__main__":
    unittest.main()
