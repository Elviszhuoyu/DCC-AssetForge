from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.interface_contract import validate_manifest_contract, validate_package_contract
from asset_forge.shared.manifest_schema import ASSET_FORGE_SCHEMA_VERSION, create_manifest, write_manifest
from asset_forge.shared.report_schema import create_export_report
from asset_forge.unreal.manifest_reader import UnrealManifestReader


class InterfaceContractTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fbx_path = os.path.join(self.temp_dir, "SM_Crate.fbx")
        with open(self.fbx_path, "wb") as stream:
            stream.write(b"fake fbx")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_new_manifest_passes_contract_with_schema_version(self):
        manifest = self._manifest()

        report = validate_manifest_contract(manifest)

        self.assertEqual(manifest["schema_version"], ASSET_FORGE_SCHEMA_VERSION)
        self.assertEqual(report["schema_version"], ASSET_FORGE_SCHEMA_VERSION)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["can_accept"])

    def test_legacy_manifest_missing_schema_version_warns_without_blocking(self):
        manifest = self._manifest()
        manifest.pop("schema_version")
        manifest.pop("asset_forge_schema_version")
        manifest["version"] = "0.1"

        report = validate_manifest_contract(manifest)

        self.assertEqual(report["status"], "warning")
        self.assertTrue(report["can_accept"])
        self.assertTrue(any(item["id"] == "schema_version" and item["status"] == "warning" for item in report["checks"]))
        self.assertIn("next_action", report)

    def test_empty_textures_warn_without_blocking_old_package(self):
        manifest = self._manifest()
        manifest["textures"] = []

        report = validate_manifest_contract(manifest)

        self.assertEqual(report["status"], "warning")
        self.assertTrue(report["can_accept"])
        self.assertTrue(any(item["id"] == "textures" and item["status"] == "warning" for item in report["checks"]))
        self.assertIn("next_action", report)

    def test_missing_key_fields_are_errors(self):
        manifest = self._manifest()
        manifest.pop("fbx_path")
        manifest.pop("material_profile")

        report = validate_manifest_contract(manifest)

        self.assertEqual(report["status"], "error")
        self.assertFalse(report["can_accept"])
        ids = [item["id"] for item in report["checks"] if item["status"] == "error"]
        self.assertIn("field_fbx_path", ids)
        self.assertIn("field_material_profile", ids)

    def test_unreal_path_and_windows_fbx_path_are_normalized_with_warning(self):
        manifest = self._manifest()
        manifest["target_path"] = "/Game/Props/Test01\n"
        manifest["fbx_path"] = self.fbx_path.replace("/", "\\")

        report = validate_manifest_contract(manifest)
        reader_report = UnrealManifestReader().load(self._write_manifest(manifest), require_fbx_exists=False)

        self.assertEqual(reader_report["manifest"]["target_path"], "/Game/Props/Test01")
        self.assertTrue(any(item["id"] == "target_path" and item["status"] == "warning" for item in report["checks"]))
        self.assertTrue(any(item["id"] == "fbx_path" and item["status"] == "warning" for item in report["checks"]))

    def test_export_report_uses_unified_schema_fields(self):
        manifest = self._manifest()

        report = create_export_report(
            {"asset_name": "SM_Crate", "textures": [], "materials": []},
            {"status": "pass", "score": 100, "can_export": True, "checks": []},
            manifest,
            {"package_dir": self.temp_dir, "fbx_path": self.fbx_path, "manifest_path": self._write_manifest(manifest)},
        )

        self.assertEqual(report["version"], "0.1")
        self.assertEqual(report["schema_version"], ASSET_FORGE_SCHEMA_VERSION)
        self.assertIn("status", report)
        self.assertIn("can_accept", report)
        self.assertIn("warnings", report)
        self.assertIn("errors", report)
        self.assertIn("next_action", report)
        self.assertIn("material_texture_bindings", report)
        self.assertIn("material_texture_binding_risks", report)

    def test_package_contract_reads_manifest_file(self):
        manifest_path = self._write_manifest(self._manifest())

        report = validate_package_contract(manifest_path)

        self.assertEqual(report["stage"], "maya_ue_interface_contract")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["import_policy_summary"]["status"], "manual_validation_required")
        self.assertIn("manual_validation_required", report)

    def test_contract_report_declares_dcc_support_roadmap(self):
        report = validate_manifest_contract(self._manifest())

        self.assertEqual(report["dcc_support"]["maya"]["support"], "implemented")
        self.assertTrue(report["dcc_support"]["maya"]["real_exporter"])
        self.assertEqual(report["dcc_support"]["blender"]["support"], "roadmap")
        self.assertFalse(report["dcc_support"]["blender"]["real_exporter"])
        self.assertEqual(report["dcc_support"]["3ds_max"]["adapter_status"], "contract_only")
        self.assertFalse(report["dcc_support"]["3ds_max"]["portfolio_mvp"])
        self.assertEqual(report["dcc_support_summary"]["implemented"], ["Maya"])
        self.assertIn("Blender", report["dcc_support_summary"]["roadmap"])
        self.assertIn("3ds Max", report["dcc_support_summary"]["roadmap"])

    def _manifest(self):
        return create_manifest(
            "SM_Crate",
            self.fbx_path.replace("\\", "/"),
            "/Game/Props",
            material_profile="Props_Opaque_PainterUE_ARM",
            textures=[{"usage": "base_color", "package_path": os.path.join(self.temp_dir, "T_Crate_BaseColor.png")}],
        )

    def _write_manifest(self, manifest):
        path = os.path.join(self.temp_dir, "SM_Crate_manifest.json")
        write_manifest(path, manifest)
        return path


if __name__ == "__main__":
    unittest.main()
