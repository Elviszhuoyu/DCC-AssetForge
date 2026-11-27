from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.manifest_schema import read_manifest
from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.acceptance_runner import UnrealPackageAcceptanceFlow, run_all_asset_forge_package_acceptance, run_asset_forge_package_acceptance
from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline


class OfflineStaticPropPackageTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_creates_minimal_static_prop_package_with_texture_dimensions(self):
        package = create_offline_static_prop_package(self.temp_dir)
        manifest = read_manifest(package["manifest_path"])

        self.assertTrue(os.path.exists(package["fbx_path"]))
        with open(package["fbx_path"], "rb") as stream:
            fbx_header = stream.read(96)
        self.assertIn(b"FBX 7.4.0", fbx_header)
        self.assertGreater(os.path.getsize(package["fbx_path"]), 1000)
        self.assertGreater(os.path.getsize(package["textures"][0]["path"]), 100)
        self.assertEqual(os.path.getsize(package["textures"][1]["path"]), 18 + 64 * 64 * 4)
        self.assertEqual(manifest["asset_name"], "SM_AF_Offline_Crate")
        self.assertEqual(manifest["textures"][0]["width"], 64)
        self.assertEqual(manifest["textures"][1]["height"], 64)
        self.assertEqual(manifest["textures"][0]["texture_metadata_status"], "pass")

    def test_offline_package_runs_acceptance_flow_and_dry_run(self):
        package = create_offline_static_prop_package(self.temp_dir)

        report = run_asset_forge_package_acceptance(package["package_dir"])

        self.assertEqual(report["stage"], "package_acceptance_flow")
        self.assertEqual(report["asset_name"], "SM_AF_Offline_Crate")
        self.assertEqual(report["dry_run"]["status"], "skipped")
        self.assertIn("texture_quality_validation", report["package_acceptance"])
        self.assertIn("在目标 UE 工程中使用 --run-import", report["next_action"])

    def test_auto_materials_records_before_after_without_faking_ue_success(self):
        package = create_offline_static_prop_package(self.temp_dir)

        report = run_asset_forge_package_acceptance(package["package_dir"], auto_bootstrap_material_assets=True)

        self.assertTrue(report["auto_materials"]["enabled"])
        self.assertEqual(report["auto_materials"]["bootstrap_report"]["status"], "failed")
        self.assertEqual(report["auto_materials"]["bootstrap_report"]["material_network_status"], "generated_pbr")
        self.assertNotEqual(report["auto_materials"]["bootstrap_report"]["material_network_status"], "placeholder")
        self.assertIn("目标 UE 工程", report["next_action"])
        self.assertIn("before", report["auto_materials"])
        self.assertIn("after", report["auto_materials"])

    def test_batch_acceptance_flow_summarizes_warning_packages(self):
        create_offline_static_prop_package(self.temp_dir, "SM_AF_Offline_A")
        create_offline_static_prop_package(self.temp_dir, "SM_AF_Offline_B")

        report = run_all_asset_forge_package_acceptance(self.temp_dir)

        self.assertEqual(report["stage"], "batch_package_acceptance_flow")
        self.assertEqual(report["total"], 2)
        self.assertEqual(report["summary"]["blocked_packages"], [])
        self.assertEqual(len(report["summary"]["warning_packages"]), 2)

    def test_offline_package_can_use_pipeline_dry_run_directly(self):
        package = create_offline_static_prop_package(self.temp_dir)

        report = UnrealStaticMeshImportPipeline().dry_run_manifest(package["manifest_path"])

        self.assertEqual(report["status"], "skipped")
        self.assertEqual(report["asset_name"], "SM_AF_Offline_Crate")
        self.assertEqual(report["texture_import_plan"]["count"], 2)

    def test_acceptance_flow_exposes_real_import_result_summary(self):
        package = create_offline_static_prop_package(self.temp_dir)
        report = UnrealPackageAcceptanceFlow(
            acceptance_validator=FakePassAcceptanceValidator(package["manifest_path"]),
            import_pipeline=FakeImportPipeline(),
        ).run(package["package_dir"], run_import=True)

        self.assertEqual(report["import_result_summary"]["status"], "success")
        self.assertEqual(report["import_result_summary"]["report_path"], "C:/Reports/import.json")
        self.assertEqual(report["import_result_summary"]["imported_asset_count"], 2)
        self.assertEqual(report["import_result_summary"]["imported_texture_count"], 5)
        self.assertEqual(report["import_result_summary"]["created_material_instance_count"], 3)
        self.assertEqual(report["import_result_summary"]["material_assignment_count"], 5)
        self.assertEqual(report["import_result_summary"]["expected_static_mesh_count"], 5)
        self.assertEqual(report["import_result_summary"]["imported_static_mesh_count"], 5)

class FakePassAcceptanceValidator(object):
    def __init__(self, manifest_path):
        self.manifest_path = manifest_path

    def validate(self, package_dir):
        return {
            "status": "pass",
            "asset_name": "SM_AF_Offline_Crate",
            "manifest_path": self.manifest_path,
            "summary": {"can_accept": True, "warnings": [], "errors": [], "warning_count": 0, "error_count": 0},
        }


class FakeImportPipeline(object):
    def dry_run_manifest(self, manifest_path):
        return {"status": "skipped", "summary": {"can_accept": True, "warnings": [], "errors": []}}

    def import_from_manifest(self, manifest_path):
        return {
            "status": "success",
            "report_path": "C:/Reports/import.json",
            "imported_assets": ["/Game/Props/SM_A.SM_A", "/Game/Props/SM_B.SM_B"],
            "summary": {
                "status": "success",
                "imported_texture_count": 5,
                "created_material_instance_count": 3,
                "material_assignment_count": 5,
            },
            "post_import_validation": {
                "status": "pass",
                "expected_static_mesh_count": 5,
                "imported_static_mesh_count": 5,
            },
        }


if __name__ == "__main__":
    unittest.main()
