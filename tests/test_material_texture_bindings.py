from __future__ import absolute_import

import unittest

from asset_forge.shared.material_texture_bindings import create_material_texture_bindings


class MaterialTextureBindingsTest(unittest.TestCase):
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
