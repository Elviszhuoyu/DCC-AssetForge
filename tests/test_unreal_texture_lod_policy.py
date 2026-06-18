import os
import shutil
import tempfile
import unittest

from asset_forge.maya.project_settings import normalize_project_settings
from asset_forge.maya.manifest_writer import MayaManifestWriter
from asset_forge.shared.manifest_lint import lint_static_prop_manifest
from asset_forge.shared.manifest_schema import create_manifest
from asset_forge.shared.material_profile_contract import validate_material_profile_contract
from asset_forge.unreal.material_binding_planner import UnrealMaterialBindingPlanner
from asset_forge.unreal.texture_import_planner import UnrealTextureImportPlanner
from asset_forge.unreal.texture_importer import UnrealTextureImporter, preview_texture_import_policy_report


class UnrealTextureLodPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.texture_path = os.path.join(self.temp_dir, "T_Crate_BaseColor.png")
        with open(self.texture_path, "wb") as stream:
            stream.write(b"fake")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_project_settings_normalizes_ue_texture_and_lod_policy(self):
        settings = normalize_project_settings(
            {
                "virtual_texture_policy": "force_off",
                "texture_streaming_policy": "never_stream",
                "texture_group": "TEXTUREGROUP_World",
                "nanite_policy": "enable",
                "static_mesh_lod_group": "SmallProp",
                "static_mesh_lod_import_policy": "report_only",
            }
        )

        self.assertEqual(settings["virtual_texture_policy"], "force_off")
        self.assertEqual(settings["texture_streaming_policy"], "never_stream")
        self.assertEqual(settings["texture_group"], "TEXTUREGROUP_World")
        self.assertEqual(settings["nanite_policy"], "enable")
        self.assertEqual(settings["static_mesh_lod_group"], "SmallProp")
        self.assertEqual(settings["static_mesh_lod_import_policy"], "report_only")

    def test_texture_import_planner_carries_manifest_policy_to_each_texture(self):
        manifest = self._manifest(
            texture_import_policy={
                "virtual_texture_policy": "force_on",
                "texture_streaming_policy": "never_stream",
                "texture_group": "TEXTUREGROUP_World",
            }
        )

        plan = UnrealTextureImportPlanner().plan(manifest)

        self.assertEqual(plan["texture_import_policy"]["virtual_texture_policy"], "force_on")
        texture = plan["textures"][0]
        self.assertEqual(texture["virtual_texture_policy"], "force_on")
        self.assertEqual(texture["texture_streaming_policy"], "never_stream")
        self.assertEqual(texture["texture_group"], "TEXTUREGROUP_World")

    def test_texture_import_planner_marks_4k_auto_vt_as_sampler_contract(self):
        manifest = self._manifest(
            texture_import_policy={
                "virtual_texture_policy": "auto",
                "texture_streaming_policy": "streaming",
                "texture_group": "TEXTUREGROUP_World",
            }
        )
        manifest["textures"][0]["width"] = 4096
        manifest["textures"][0]["height"] = 4096

        plan = UnrealTextureImportPlanner().plan(manifest)
        texture = plan["textures"][0]

        self.assertTrue(texture["virtual_texture_streaming"])
        self.assertTrue(texture["requires_virtual_texture_sampling"])
        self.assertIn("4K", texture["virtual_texture_reason"])
        self.assertEqual(texture["format_contract"]["parameter"], "BaseColor")
        self.assertTrue(texture["format_contract"]["srgb"])

    def test_texture_import_planner_records_data_texture_format_contract(self):
        manifest = self._manifest()
        manifest["textures"][0]["usage"] = "packed_arm"
        manifest["materials"][0]["textures"][0]["usage"] = "packed_arm"

        plan = UnrealTextureImportPlanner().plan(manifest)
        texture = plan["textures"][0]

        self.assertEqual(texture["parameter"], "ARM")
        self.assertFalse(texture["format_contract"]["srgb"])
        self.assertTrue(texture["format_contract"]["is_data_texture"])
        self.assertEqual(texture["format_contract"]["compression"], "masks")

    def test_maya_manifest_writer_preserves_texture_and_lod_policy(self):
        manifest = MayaManifestWriter().build(
            {"asset_name": "SM_Crate", "materials": [], "textures": []},
            {"target_platform": "high_end_mobile", "checks": {}, "score": 100},
            os.path.join(self.temp_dir, "SM_Crate.fbx"),
            "/Game/Props",
            texture_import_policy={"virtual_texture_policy": "auto", "texture_streaming_policy": "streaming", "texture_group": "TEXTUREGROUP_World"},
            static_mesh_import_policy={"nanite_policy": "enable", "lod_group": "SmallProp", "import_lod_policy": "report_only"},
        )

        self.assertEqual(manifest["texture_import_policy"]["virtual_texture_policy"], "auto")
        self.assertEqual(manifest["static_mesh_import_policy"]["nanite_policy"], "enable")
        self.assertEqual(manifest["static_mesh_import_policy"]["lod_group"], "SmallProp")

    def test_maya_manifest_writer_preserves_texture_folder_scan_summary(self):
        manifest = MayaManifestWriter().build(
            {
                "asset_name": "SM_Crate",
                "materials": [],
                "textures": [],
                "texture_folder_scan": {
                    "texture_set_token": "a1,d1",
                    "selected_texture_sets": ["HK416_D_B_a1", "HK416_D_B_d1"],
                    "matched_count": 6,
                },
            },
            {"target_platform": "high_end_mobile", "checks": {}, "score": 100},
            os.path.join(self.temp_dir, "SM_Crate.fbx"),
            "/Game/Props",
        )

        self.assertEqual(manifest["texture_folder_scan"]["texture_set_token"], "a1,d1")
        self.assertEqual(manifest["texture_folder_scan"]["matched_count"], 6)

    def test_manifest_lint_reports_texture_and_static_mesh_policy(self):
        manifest = self._manifest(
            texture_import_policy={"virtual_texture_policy": "force_off", "texture_streaming_policy": "streaming", "texture_group": "project_default"},
            static_mesh_import_policy={"nanite_policy": "enable", "lod_group": "SmallProp", "import_lod_policy": "report_only"},
        )

        report = lint_static_prop_manifest(manifest)
        ids = [item["id"] for item in report["checks"]]

        self.assertIn("virtual_texture_policy", ids)
        self.assertIn("texture_streaming_policy", ids)
        self.assertIn("nanite_policy", ids)
        self.assertIn("static_mesh_lod_group", ids)
        self.assertIn("static_mesh_import_lod_policy", ids)

    def test_texture_importer_records_applied_virtual_texture_streaming_and_group_policy(self):
        fake_unreal = FakeUnreal()
        importer = UnrealTextureImporter(fake_unreal)
        plan = {
            "existing_texture_strategy": "overwrite",
            "textures": [
                {
                    "source_path": self.texture_path,
                    "target_dir": "/Game/Props/Textures",
                    "target_asset_path": "/Game/Props/Textures/T_Crate_BaseColor",
                    "asset_name": "T_Crate_BaseColor",
                    "usage": "base_color",
                    "srgb": True,
                    "compression": "default",
                    "virtual_texture_policy": "force_on",
                    "texture_streaming_policy": "never_stream",
                    "texture_group": "TEXTUREGROUP_World",
                }
            ],
        }

        importer.import_textures(plan)
        configured = importer.last_configuration_report["configured"][0]
        applied = configured["policy_report"]["applied"]

        self.assertIn({"property": "virtual_texture_streaming", "value": True}, applied)
        self.assertIn({"property": "never_stream", "value": True}, applied)
        self.assertIn({"property": "lod_group", "value": "TEXTUREGROUP_World"}, applied)

    def test_texture_importer_normalizes_short_texture_group_name(self):
        fake_unreal = FakeUnreal()
        importer = UnrealTextureImporter(fake_unreal)
        plan = {
            "existing_texture_strategy": "overwrite",
            "textures": [
                {
                    "source_path": self.texture_path,
                    "target_dir": "/Game/Props/Textures",
                    "target_asset_path": "/Game/Props/Textures/T_Crate_BaseColor_ShortGroup",
                    "asset_name": "T_Crate_BaseColor_ShortGroup",
                    "usage": "base_color",
                    "srgb": True,
                    "compression": "default",
                    "virtual_texture_policy": "force_off",
                    "texture_streaming_policy": "streaming",
                    "texture_group": "World",
                }
            ],
        }

        importer.import_textures(plan)
        policy_report = importer.last_configuration_report["configured"][0]["policy_report"]

        self.assertIn({"property": "lod_group", "value": "TEXTUREGROUP_World"}, policy_report["applied"])
        self.assertEqual(policy_report["actual_policy"]["texture_group"], "TEXTUREGROUP_World")
        self.assertEqual(policy_report["warnings"], [])

    def test_texture_importer_applies_usage_default_group_to_arm_texture(self):
        fake_unreal = FakeUnreal()
        importer = UnrealTextureImporter(fake_unreal)
        plan = {
            "existing_texture_strategy": "overwrite",
            "textures": [
                {
                    "source_path": self.texture_path,
                    "target_dir": "/Game/Props/Textures",
                    "target_asset_path": "/Game/Props/Textures/T_Crate_ARM",
                    "asset_name": "T_Crate_ARM",
                    "usage": "packed_arm",
                    "srgb": False,
                    "compression": "masks",
                    "virtual_texture_policy": "force_off",
                    "texture_streaming_policy": "project_default",
                    "texture_group": "project_default",
                }
            ],
        }

        importer.import_textures(plan)
        texture = fake_unreal.EditorAssetLibrary.assets["/Game/Props/Textures/T_Crate_ARM"]
        policy_report = importer.last_configuration_report["configured"][0]["policy_report"]

        self.assertEqual(texture.LODGroup, "TEXTUREGROUP_World")
        self.assertEqual(texture.compression_settings, "TC_MASKS")
        self.assertFalse(texture.srgb)
        self.assertIn({"property": "lod_group", "value": "TEXTUREGROUP_World"}, policy_report["applied"])
        self.assertEqual(policy_report["resolved_texture_group_policy"], "usage_default")

    def test_texture_importer_applies_usage_default_group_to_normal_texture(self):
        fake_unreal = FakeUnreal()
        importer = UnrealTextureImporter(fake_unreal)
        plan = {
            "existing_texture_strategy": "overwrite",
            "textures": [
                {
                    "source_path": self.texture_path,
                    "target_dir": "/Game/Props/Textures",
                    "target_asset_path": "/Game/Props/Textures/T_Crate_Normal",
                    "asset_name": "T_Crate_Normal",
                    "usage": "normal",
                    "srgb": False,
                    "compression": "normalmap",
                    "virtual_texture_policy": "force_off",
                    "texture_streaming_policy": "project_default",
                    "texture_group": "project_default",
                }
            ],
        }

        importer.import_textures(plan)
        texture = fake_unreal.EditorAssetLibrary.assets["/Game/Props/Textures/T_Crate_Normal"]

        self.assertEqual(texture.LODGroup, "TEXTUREGROUP_WorldNormalMap")
        self.assertEqual(texture.compression_settings, "TC_NORMALMAP")

    def test_texture_importer_resolves_auto_vt_never_stream_to_force_off(self):
        fake_unreal = FakeUnreal()
        importer = UnrealTextureImporter(fake_unreal)
        plan = {
            "existing_texture_strategy": "overwrite",
            "textures": [
                {
                    "source_path": self.texture_path,
                    "target_dir": "/Game/Props/Textures",
                    "target_asset_path": "/Game/Props/Textures/T_Crate_BaseColor",
                    "asset_name": "T_Crate_BaseColor",
                    "usage": "base_color",
                    "srgb": True,
                    "compression": "default",
                    "virtual_texture_policy": "auto",
                    "texture_streaming_policy": "never_stream",
                    "texture_group": "project_default",
                }
            ],
        }

        importer.import_textures(plan)
        policy_report = importer.last_configuration_report["configured"][0]["policy_report"]

        self.assertEqual(policy_report["resolved_virtual_texture_policy"], "auto_resolved_force_off")
        self.assertIn({"property": "virtual_texture_streaming", "value": False}, policy_report["applied"])
        self.assertFalse(policy_report["actual_policy"]["effective_virtual_texture"])
        self.assertIn("never_stream", policy_report["resolution_reason"])
        self.assertIn("VT=auto", policy_report["user_message"])

    def test_texture_policy_preview_resolves_auto_vt_never_stream_without_unreal(self):
        plan = UnrealTextureImportPlanner().plan(
            self._manifest(
                texture_import_policy={
                    "virtual_texture_policy": "auto",
                    "texture_streaming_policy": "never_stream",
                    "texture_group": "project_default",
                }
            )
        )

        report = preview_texture_import_policy_report(plan)
        policy_report = report["actions"][0]["policy_report"]

        self.assertEqual(report["mode"], "offline_preview")
        self.assertEqual(policy_report["resolved_virtual_texture_policy"], "auto_resolved_force_off")
        self.assertIn({"property": "virtual_texture_streaming", "value": False}, policy_report["applied"])
        self.assertIn({"property": "never_stream", "value": True}, policy_report["applied"])
        self.assertFalse(policy_report["actual_policy"]["effective_virtual_texture"])
        self.assertTrue(policy_report["actual_policy"]["never_stream"])
        self.assertEqual(policy_report["actual_policy_source"], "offline_expected_from_requested_policy")
        self.assertIn("VT=auto", policy_report["user_message"])

    def test_texture_importer_resolves_project_default_vt_to_force_off(self):
        fake_unreal = FakeUnreal()
        importer = UnrealTextureImporter(fake_unreal)
        plan = {
            "existing_texture_strategy": "overwrite",
            "textures": [
                {
                    "source_path": self.texture_path,
                    "target_dir": "/Game/Props/Textures",
                    "target_asset_path": "/Game/Props/Textures/T_Crate_BaseColor",
                    "asset_name": "T_Crate_BaseColor",
                    "usage": "base_color",
                    "srgb": True,
                    "compression": "default",
                    "virtual_texture_policy": "project_default",
                    "texture_streaming_policy": "streaming",
                    "texture_group": "project_default",
                }
            ],
        }

        importer.import_textures(plan)
        policy_report = importer.last_configuration_report["configured"][0]["policy_report"]

        self.assertEqual(policy_report["resolved_virtual_texture_policy"], "project_default_resolved_force_off")
        self.assertIn({"property": "virtual_texture_streaming", "value": False}, policy_report["applied"])
        self.assertFalse(policy_report["actual_policy"]["effective_virtual_texture"])

    def test_material_binding_plan_reports_maya_to_mi_mapping(self):
        manifest = self._manifest()
        texture_plan = UnrealTextureImportPlanner().plan(manifest)

        plan = UnrealMaterialBindingPlanner().plan(manifest, texture_plan)
        material = plan["materials"][0]

        self.assertEqual(material["maya_material_name"], "B_A1")
        self.assertEqual(material["material_instance_name"], "MI_B_A1")
        self.assertEqual(material["material_instance_path"], "/Game/Props/Materials/MI_B_A1")
        self.assertEqual(material["parent_material_path"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertEqual(material["selected_master_family"], "MM_Surface_PBR")
        self.assertEqual(material["selected_material_variant"], "/AssetForge/Materials/M_AF_Props_Master")
        self.assertIn("base_color", material["detected_features"])
        self.assertEqual(material["parameter_api_mapping"]["BaseColor"], "Base Color")
        self.assertEqual(material["parameter_api_mapping"]["Normal"], "Normal Map")
        self.assertEqual(material["parameter_api_mapping"]["ARM"], "Pack Map")

    def test_material_profile_contract_reports_generated_pbr_requires_ue_verification(self):
        report = validate_material_profile_contract("Props_Opaque_PainterUE_ARM")
        checks = [item for item in report["checks"] if item["id"] == "parent_material_network"]

        self.assertEqual(checks[0]["status"], "warning")
        self.assertIn("generated_pbr", checks[0]["message"])

    def _manifest(self, texture_import_policy=None, static_mesh_import_policy=None):
        return create_manifest(
            "SM_Crate",
            os.path.join(self.temp_dir, "SM_Crate.fbx"),
            "/Game/Props",
            material_profile="Props_Opaque_PainterUE_ARM",
            materials=[
                {
                    "name": "B_A1",
                    "textures": [
                        {"usage": "base_color", "package_path": self.texture_path, "copied": True},
                    ],
                }
            ],
            textures=[{"usage": "base_color", "package_path": self.texture_path, "copied": True, "srgb": True, "compression": "default", "width": 4, "height": 4}],
            texture_import_policy=texture_import_policy or {},
            static_mesh_import_policy=static_mesh_import_policy or {},
        )


class FakeAsset(object):
    pass


class FakeTask(object):
    def __init__(self):
        self.imported_object_paths = []

    def set_editor_property(self, name, value):
        setattr(self, name, value)

    def get_editor_property(self, name):
        return getattr(self, name)


class FakeAssetTools(object):
    def import_asset_tasks(self, tasks):
        for task in tasks:
            task.imported_object_paths = [task.destination_path + "/" + task.destination_name + "." + task.destination_name]


class FakeAssetToolsHelpers(object):
    @staticmethod
    def get_asset_tools():
        return FakeAssetTools()


class FakeEditorAssetLibrary(object):
    assets = {}

    @classmethod
    def does_asset_exist(cls, asset_path):
        return False

    @classmethod
    def load_asset(cls, asset_path):
        cls.assets.setdefault(asset_path, FakeAsset())
        return cls.assets[asset_path]

    @staticmethod
    def save_asset(asset_path):
        return True


class FakeCompressionSettings(object):
    TC_DEFAULT = "TC_DEFAULT"
    TC_NORMALMAP = "TC_NORMALMAP"
    TC_MASKS = "TC_MASKS"


class FakeTextureGroup(object):
    TEXTUREGROUP_World = "TEXTUREGROUP_World"
    TEXTUREGROUP_WorldNormalMap = "TEXTUREGROUP_WorldNormalMap"


class FakeUnreal(object):
    AssetImportTask = FakeTask
    AssetToolsHelpers = FakeAssetToolsHelpers
    EditorAssetLibrary = FakeEditorAssetLibrary
    TextureCompressionSettings = FakeCompressionSettings
    TextureGroup = FakeTextureGroup


if __name__ == "__main__":
    unittest.main()
