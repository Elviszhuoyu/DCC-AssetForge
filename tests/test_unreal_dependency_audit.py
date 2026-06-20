from __future__ import absolute_import

import unittest

from asset_forge.unreal.dependency_audit import (
    STATUS_BLOCKED_PLUGIN_DEPENDENCY,
    STATUS_PASS,
    STATUS_PROJECT_MATERIAL_PROFILE_READY,
    STATUS_WARNING,
    audit_unreal_dependencies,
)


class UnrealDependencyAuditTest(unittest.TestCase):
    def test_no_plugin_dependency_passes(self):
        report = {
            "static_mesh": {"target_asset_path": "/Game/Props/SM_Crate_01"},
            "material_binding_plan": {
                "materials": [
                    {
                        "target_asset_path": "/Game/Props/Materials/MI_Crate",
                        "parent_material": "/Game/Materials/M_Project_Props_Master",
                        "texture_parameters": {"BaseColor": "/Game/Props/Textures/T_Crate_BaseColor"},
                    }
                ]
            },
        }

        audit = audit_unreal_dependencies(report)

        self.assertEqual(audit["status"], STATUS_PASS)
        self.assertTrue(audit["can_release"])
        self.assertEqual(audit["asset_forge_dependency_count"], 0)
        self.assertEqual(audit["reparent_plan"]["status"], "not_required")

    def test_material_instance_parent_without_mapping_blocks_release(self):
        report = _report_with_asset_forge_parent()

        audit = audit_unreal_dependencies(report)

        self.assertEqual(audit["status"], STATUS_BLOCKED_PLUGIN_DEPENDENCY)
        self.assertFalse(audit["can_release"])
        self.assertEqual(audit["asset_forge_dependency_count"], 1)
        self.assertEqual(audit["plugin_dependencies"][0]["asset_type"], "material")
        self.assertEqual(audit["plugin_dependencies"][0]["reference_role"], "parent_material")
        self.assertEqual(audit["reparent_plan"]["missing_mappings"], ["/AssetForge/Materials/M_AF_Props_Master"])

    def test_material_parent_mapping_creates_dry_run_reparent_plan(self):
        report = _report_with_asset_forge_parent()
        mapping = {
            "/AssetForge/Materials/M_AF_Props_Master": "/Game/Materials/M_Project_Props_Master",
        }

        audit = audit_unreal_dependencies(report, project_material_parent_mapping=mapping)

        self.assertEqual(audit["status"], STATUS_PROJECT_MATERIAL_PROFILE_READY)
        self.assertTrue(audit["can_release"])
        self.assertEqual(audit["reparent_plan"]["status"], "ready")
        self.assertEqual(audit["reparent_plan"]["action_count"], 1)
        self.assertTrue(audit["reparent_plan"]["dry_run"])
        action = audit["reparent_plan"]["actions"][0]
        self.assertEqual(action["action"], "reparent_material_instance")
        self.assertEqual(action["source_parent_material"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertEqual(action["target_parent_material"], "/Game/Materials/M_Project_Props_Master")

    def test_explicitly_allowed_plugin_dependency_is_warning(self):
        report = {
            "texture_import_plan": {
                "textures": [
                    {
                        "target_asset_path": "/Game/Props/Textures/T_Crate_BaseColor",
                        "source_asset_path": "/AssetForge/Textures/T_AF_Default_BaseColor",
                    }
                ]
            }
        }

        audit = audit_unreal_dependencies(report, allow_plugin_dependencies=True)

        self.assertEqual(audit["status"], STATUS_WARNING)
        self.assertTrue(audit["can_release"])
        self.assertEqual(audit["plugin_dependencies"][0]["asset_type"], "texture")
        self.assertEqual(audit["blocked_dependencies"], [])

    def test_scans_material_functions_mpc_and_static_mesh_paths(self):
        report = {
            "static_mesh_path": "/AssetForge/Meshes/SM_Debug",
            "material_function": "/AssetForge/MaterialFunctions/MF_AF_UnpackARM",
            "mpc": "/AssetForge/ParameterCollections/MPC_AF_Global",
        }

        audit = audit_unreal_dependencies(report)

        self.assertEqual(audit["status"], STATUS_BLOCKED_PLUGIN_DEPENDENCY)
        self.assertEqual(
            sorted(item["asset_type"] for item in audit["plugin_dependencies"]),
            ["material_function", "material_parameter_collection", "static_mesh"],
        )


def _report_with_asset_forge_parent():
    return {
        "material_binding_plan": {
            "materials": [
                {
                    "material_name": "M_Crate",
                    "target_asset_path": "/Game/Props/Materials/MI_Crate",
                    "parent_material": "/AssetForge/Materials/M_AF_Props_Master",
                }
            ]
        }
    }


if __name__ == "__main__":
    unittest.main()
