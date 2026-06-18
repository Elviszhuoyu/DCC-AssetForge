from __future__ import absolute_import

import unittest

from asset_forge.unreal.material_binding_contract import validate_material_binding_contract


class UnrealMaterialBindingContractTest(unittest.TestCase):
    def test_contract_passes_when_binding_table_matches_plan_and_slots(self):
        report = validate_material_binding_contract(
            {
                "material_slots": [{"name": "B_a1", "index": 0}],
                "material_texture_bindings": [
                    {
                        "material_name": "B_a1",
                        "slot_index": 0,
                        "texture_usages": ["base_color", "normal"],
                        "ue_material_instance_path": "/Game/Props/Materials/MI_B_a1",
                    }
                ],
            },
            {
                "materials": [
                    {
                        "material_name": "B_a1",
                        "target_asset_path": "/Game/Props/Materials/MI_B_a1",
                        "slots": {"base_color": "/Game/Props/Textures/T_B_a1_BaseColor", "normal": "/Game/Props/Textures/T_B_a1_Normal"},
                    }
                ]
            },
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["binding_count"], 1)

    def test_missing_binding_table_is_warning_not_blocker(self):
        report = validate_material_binding_contract(
            {"material_slots": [{"name": "B_a1", "index": 0}]},
            {"materials": [{"material_name": "B_a1", "target_asset_path": "/Game/Props/Materials/MI_B_a1"}]},
        )

        self.assertEqual(report["status"], "warning")
        self.assertTrue(any(item["id"] == "material_texture_bindings" for item in report["warnings"]))

    def test_path_slot_and_usage_mismatch_are_reported(self):
        report = validate_material_binding_contract(
            {
                "material_slots": [{"name": "B_d1", "index": 0}],
                "material_texture_bindings": [
                    {
                        "material_name": "B_a1",
                        "slot_index": 0,
                        "texture_usages": ["base_color", "normal"],
                        "ue_material_instance_path": "/Game/Props/Materials/MI_B_WRONG",
                    }
                ],
            },
            {
                "materials": [
                    {
                        "material_name": "B_a1",
                        "target_asset_path": "/Game/Props/Materials/MI_B_a1",
                        "slots": {"base_color": "/Game/Props/Textures/T_B_a1_BaseColor"},
                    }
                ]
            },
        )

        self.assertEqual(report["status"], "warning")
        warning_ids = [item["id"] for item in report["warnings"]]
        self.assertIn("binding_material_instance_path", warning_ids)
        self.assertIn("binding_slot_index", warning_ids)
        self.assertIn("binding_texture_usages", warning_ids)

    def test_empty_material_plan_is_error(self):
        report = validate_material_binding_contract({"material_texture_bindings": [{"material_name": "B_a1"}]}, {"materials": []})

        self.assertEqual(report["status"], "error")
        self.assertTrue(any(item["id"] == "material_binding_plan" for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()
