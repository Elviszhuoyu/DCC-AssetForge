from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest

from asset_forge.shared.manifest_lint import lint_static_prop_manifest
from asset_forge.shared.manifest_schema import read_manifest, write_manifest
from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.package_acceptance import validate_asset_forge_package


class ManifestLintTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.package = create_offline_static_prop_package(self.temp_dir)
        self.manifest = read_manifest(self.package["manifest_path"])

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_manifest_lint_warns_missing_strategy_snapshot_and_bad_texture_metadata(self):
        self.manifest["textures"][0].pop("width")
        self.manifest["textures"][0]["srgb"] = "yes"
        self.manifest["textures"][0]["usage"] = "mystery"
        self.manifest.pop("existing_mesh_strategy")

        report = lint_static_prop_manifest(self.manifest)

        self.assertEqual(report["status"], "warning")
        messages = [item["message"] for item in report["warnings"]]
        self.assertTrue(any("未知贴图 usage" in message for message in messages))
        self.assertTrue(any("width" in message for message in messages))
        self.assertTrue(any("srgb" in message for message in messages))
        self.assertTrue(any("existing_mesh_strategy" in message for message in messages))

    def test_package_acceptance_includes_manifest_lint_report(self):
        report = validate_asset_forge_package(self.package["package_dir"])

        self.assertIn("manifest_lint", report)
        self.assertIn("manifest_lint", report)
        self.assertEqual(report["manifest_lint"]["status"], "pass")

    def test_manifest_lint_passes_explicit_vnext_fields(self):
        snapshot_path = os.path.join(self.package["package_dir"], "material_profiles_snapshot.json")
        with open(snapshot_path, "w", encoding="utf-8") as stream:
            stream.write('{"version":"0.1","profiles":[]}\n')
        self.manifest["material_profiles_snapshot_path"] = snapshot_path
        self.manifest["existing_mesh_strategy"] = "overwrite"
        self.manifest["existing_texture_strategy"] = "overwrite"
        self.manifest["existing_material_strategy"] = "reuse"
        write_manifest(self.package["manifest_path"], self.manifest)

        lint_report = lint_static_prop_manifest(self.manifest)

        self.assertEqual(lint_report["status"], "pass")


if __name__ == "__main__":
    unittest.main()
