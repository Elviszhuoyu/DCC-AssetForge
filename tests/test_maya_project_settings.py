from __future__ import absolute_import

import json
import os
import shutil
import tempfile
import unittest

from asset_forge.maya.project_settings import default_project_settings, load_project_settings, normalize_project_settings, save_project_settings


class MayaProjectSettingsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_defaults_include_mvp_fields(self):
        settings = default_project_settings()

        for key in [
            "export_root",
            "texture_root",
            "triangle_budget",
            "mesh_prefix",
            "texture_prefix",
            "texture_set_token",
            "package_version_mode",
            "package_version_padding",
            "ue_target_path",
            "target_platform",
            "material_profile",
            "virtual_texture_policy",
            "texture_streaming_policy",
            "texture_group",
            "nanite_policy",
            "static_mesh_lod_group",
            "static_mesh_lod_import_policy",
            "generate_lightmap_uvs",
            "collision_complexity",
            "build_reversed_index_buffer",
        ]:
            self.assertIn(key, settings)

    def test_missing_fields_use_defaults_and_sanitize_target_path(self):
        settings = normalize_project_settings({"ue_target_path": "/Game/Props/Test01\n", "triangle_budget": "30000"})

        self.assertEqual(settings["ue_target_path"], "/Game/Props/Test01")
        self.assertEqual(settings["triangle_budget"], 30000)
        self.assertEqual(settings["mesh_prefix"], "SM_")
        self.assertEqual(settings["texture_set_token"], "")
        self.assertEqual(settings["package_version_mode"], "overwrite")
        self.assertEqual(settings["target_platform"], "pc")

    def test_version_mode_aliases_and_invalid_padding_fall_back(self):
        settings = normalize_project_settings({"package_version_mode": "versioned", "package_version_padding": "bad"})

        self.assertEqual(settings["version"], "0.3")
        self.assertEqual(settings["package_version_mode"], "auto_increment")
        self.assertEqual(settings["package_version_padding"], 3)

    def test_load_save_roundtrip_utf8_json_and_import_policies(self):
        path = os.path.join(self.temp_dir, "project_settings.json")

        saved_path = save_project_settings(
            path,
            {
                "export_root": "D:/Exports",
                "texture_root": "D:/贴图",
                "texture_set_token": "a1,d1",
                "ue_target_path": "/Game/Props",
                "virtual_texture_policy": "force_off",
                "texture_streaming_policy": "never_stream",
                "texture_group": "TEXTUREGROUP_World",
                "package_version_mode": "auto_increment",
                "package_version_padding": 4,
                "nanite_policy": "enable",
                "static_mesh_lod_group": "SmallProp",
                "static_mesh_lod_import_policy": "report_only",
            },
        )
        loaded = load_project_settings(saved_path)

        self.assertEqual(loaded["export_root"], "D:/Exports")
        self.assertEqual(loaded["texture_root"], "D:/贴图")
        self.assertEqual(loaded["texture_set_token"], "a1,d1")
        self.assertEqual(loaded["virtual_texture_policy"], "force_off")
        self.assertEqual(loaded["texture_streaming_policy"], "never_stream")
        self.assertEqual(loaded["texture_group"], "TEXTUREGROUP_World")
        self.assertEqual(loaded["package_version_mode"], "auto_increment")
        self.assertEqual(loaded["package_version_padding"], 4)
        self.assertEqual(loaded["nanite_policy"], "enable")
        self.assertEqual(loaded["static_mesh_lod_group"], "SmallProp")
        self.assertEqual(loaded["static_mesh_lod_import_policy"], "report_only")
        with open(saved_path, "r", encoding="utf-8") as stream:
            raw = json.load(stream)
        self.assertEqual(raw["texture_prefix"], "T_")
        self.assertEqual(raw["version"], "0.3")

    def test_non_json_extension_is_normalized_to_json(self):
        self.assertEqual(save_project_settings(os.path.join(self.temp_dir, "project_settings"), {})[-5:], ".json")


if __name__ == "__main__":
    unittest.main()
