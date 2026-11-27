from __future__ import absolute_import

import unittest

from asset_forge.shared.material_texture_bindings import create_material_texture_bindings
from asset_forge.shared.material_texture_set_mapping import build_material_texture_set_mapping


class MaterialTextureBindingsTest(unittest.TestCase):
    def test_single_generic_material_needs_a_choice_between_competing_sets(self):
        slots = [{"name": "M_Generic"}]
        textures = [{"selected_texture_set": name, "usage": usage}
                    for name in ("Prop_Trim", "Prop_Body") for usage in ("base_color", "normal", "packed_arm")]
        for ordered in (textures, list(reversed(textures))):
            result = build_material_texture_set_mapping(slots, ordered)
            row = result["material_texture_sets"][0]
            self.assertEqual(row["status"], "ambiguous_material_texture_set")
            self.assertEqual(row["candidates"], ["Prop_Body", "Prop_Trim"])
            self.assertEqual(result["materials"][0]["textures"], [])
            chosen = build_material_texture_set_mapping(
                slots, ordered, material_texture_set_overrides={"M_Generic": "Prop_Trim"})
            self.assertEqual(chosen["material_texture_sets"][0]["binding_source"], "manual_override")
            self.assertEqual(chosen["materials"][0]["textures"],
                             [texture for texture in ordered if texture["selected_texture_set"] == "Prop_Trim"])

    def test_generic_slot_preserves_legacy_single_and_complementary_inputs(self):
        inputs = [
            [{"usage": "base_color"}, {"usage": "normal"}],
            [{"selected_texture_set": "Prop_Body", "usage": usage} for usage in ("base_color", "normal")],
            [{"selected_texture_set": "Albedo", "usage": "base_color"},
             {"selected_texture_set": "Details", "usage": "normal"}],
        ]
        for textures in inputs:
            with self.subTest(textures=textures):
                mapping = build_material_texture_set_mapping([{"name": "M_Generic"}], textures)
                self.assertEqual(mapping["material_texture_sets"][0]["status"], "bound")
                self.assertEqual(mapping["materials"][0]["textures"], textures)

    def test_empty_target_path_keeps_material_instance_name_without_path(self):
        report = create_material_texture_bindings(
            {
                "materials": [{"name": "B_a1"}],
                "material_texture_sets": [
                    {
                        "status": "bound",
                        "material_name": "B_a1",
                        "texture_set": "HK416_D_B_a1",
                        "texture_set_short_name": "a1",
                        "textures": [{"usage": "base_color", "source_path": "D:/Tex/T_B_a1_BaseColor.png"}],
                    }
                ],
            }
        )

        binding = report["bindings"][0]
        self.assertEqual(binding["ue_material_instance_name"], "MI_B_a1")
        self.assertEqual(binding["ue_material_instance_path"], "")
        self.assertEqual(binding["texture_usages"], ["base_color"])

    def test_sanitized_material_name_collision_reports_shared_material_instance(self):
        report = create_material_texture_bindings(
            {
                "materials": [{"name": "B a"}, {"name": "B-a"}],
                "material_texture_sets": [
                    {"status": "bound", "material_name": "B a", "texture_set": "Set_A", "textures": []},
                    {"status": "bound", "material_name": "B-a", "texture_set": "Set_B", "textures": []},
                ],
            },
            "/Game/Props",
        )

        risks = dict((item["id"], item) for item in report["risks"])
        self.assertEqual(report["bindings"][0]["ue_material_instance_name"], "MI_B_a")
        self.assertEqual(report["bindings"][1]["ue_material_instance_name"], "MI_B_a")
        self.assertIn("shared_material_instance", risks)
        self.assertEqual(risks["shared_material_instance"]["materials"], ["B a", "B-a"])

    def test_duplicate_explicit_slot_index_reports_risk(self):
        report = create_material_texture_bindings(
            {
                "material_slots": [
                    {"name": "B_a1", "index": 0},
                    {"name": "B_b1", "index": 0},
                ],
                "material_texture_sets": [
                    {"status": "bound", "material_name": "B_a1", "texture_set": "Set_A", "textures": []},
                    {"status": "bound", "material_name": "B_b1", "texture_set": "Set_B", "textures": []},
                ],
            },
            "/Game/Props",
        )

        risks = dict((item["id"], item) for item in report["risks"])
        self.assertEqual(report["bindings"][0]["slot_index"], 0)
        self.assertEqual(report["bindings"][1]["slot_index"], 0)
        self.assertIn("shared_slot_index", risks)
        self.assertEqual(risks["shared_slot_index"]["materials"], ["B_a1", "B_b1"])


if __name__ == "__main__":
    unittest.main()
