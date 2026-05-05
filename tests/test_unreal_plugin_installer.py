from __future__ import absolute_import

import json
import os
import shutil
import tempfile
import unittest

from asset_forge.unreal.plugin_installer import install_assetforge_plugin, plan_assetforge_plugin_install


class UnrealPluginInstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_plugin = os.path.join(self.temp_dir, "SourceAssetForge")
        os.makedirs(os.path.join(self.source_plugin, "Content", "Python"))
        self._write_json(
            os.path.join(self.source_plugin, "AssetForge.uplugin"),
            {
                "FileVersion": 3,
                "FriendlyName": "Asset Forge",
                "CanContainContent": True,
                "Modules": [],
            },
        )
        with open(os.path.join(self.source_plugin, "Content", "Python", "init_unreal.py"), "w", encoding="utf-8") as stream:
            stream.write("BOOTSTRAP_REPORT = {}\n")

        self.project_dir = os.path.join(self.temp_dir, "UEProject")
        os.makedirs(self.project_dir)
        self.project_file = os.path.join(self.project_dir, "UEProject.uproject")
        self._write_json(self.project_file, {"FileVersion": 3, "Plugins": []})

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_plan_resolves_project_plugin_target(self):
        plan = plan_assetforge_plugin_install(self.project_file, self.source_plugin)

        self.assertEqual(plan["status"], "ready")
        self.assertTrue(plan["can_install"])
        self.assertEqual(plan["content_mount"], "/AssetForge")
        self.assertTrue(plan["target_plugin_dir"].endswith("UEProject/Plugins/AssetForge"))
        self.assertTrue(plan["requires_editor_restart"])

    def test_install_copies_plugin_and_enables_uproject(self):
        report = install_assetforge_plugin(self.project_dir, self.source_plugin)

        target_descriptor = os.path.join(self.project_dir, "Plugins", "AssetForge", "AssetForge.uplugin")
        target_python = os.path.join(self.project_dir, "Plugins", "AssetForge", "Content", "Python", "init_unreal.py")
        project_data = self._read_json(self.project_file)
        self.assertEqual(report["status"], "success")
        self.assertTrue(os.path.exists(target_descriptor))
        self.assertTrue(os.path.exists(target_python))
        self.assertIn(target_descriptor.replace("\\", "/"), report["copied_files"])
        self.assertEqual(project_data["Plugins"][0], {"Name": "AssetForge", "Enabled": True})

    def test_dry_run_does_not_write_project(self):
        report = install_assetforge_plugin(self.project_dir, self.source_plugin, dry_run=True)

        target_descriptor = os.path.join(self.project_dir, "Plugins", "AssetForge", "AssetForge.uplugin")
        self.assertEqual(report["status"], "skipped")
        self.assertFalse(os.path.exists(target_descriptor))
        self.assertEqual(self._read_json(self.project_file)["Plugins"], [])

    def _write_json(self, path, data):
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")

    def _read_json(self, path):
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)


if __name__ == "__main__":
    unittest.main()
