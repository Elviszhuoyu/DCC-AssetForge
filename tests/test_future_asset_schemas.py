from __future__ import absolute_import

import unittest

from asset_forge.blender.adapter import BlenderAdapter
from asset_forge.shared.asset_type_schema import get_asset_type_schema, get_default_import_preset
from asset_forge.shared.constants import (
    ASSET_TYPE_ANIMATION,
    ASSET_TYPE_MORPH_TARGET,
    ASSET_TYPE_SKELETAL_MESH,
    ASSET_TYPE_STATIC_PROP,
    IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
    SOURCE_DCC_MAYA,
    TARGET_ENGINE_UNREAL,
    TARGET_PLATFORM_HIGH_END_MOBILE,
)
from asset_forge.shared.manifest_schema import create_manifest, create_skeletal_mesh_manifest, validate_manifest
from asset_forge.shared.skeletal_mesh_rule_baseline import get_skeletal_mesh_rule_baseline
from asset_forge.unreal.import_presets import UnrealImportPresetManager


class FutureAssetSchemaTest(unittest.TestCase):
    def test_static_prop_schema_is_implemented(self):
        schema = get_asset_type_schema(ASSET_TYPE_STATIC_PROP)

        self.assertEqual(schema["status"], "implemented")
        self.assertIn(SOURCE_DCC_MAYA, schema["source_dcc"])
        self.assertEqual(schema["target_engine"], TARGET_ENGINE_UNREAL)
        self.assertIn("lightmap_uv", schema["planned_checks"])
        self.assertEqual(
            get_default_import_preset(ASSET_TYPE_STATIC_PROP, TARGET_PLATFORM_HIGH_END_MOBILE),
            IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
        )

    def test_future_asset_types_have_manifest_fields(self):
        for asset_type in [ASSET_TYPE_SKELETAL_MESH, ASSET_TYPE_ANIMATION, ASSET_TYPE_MORPH_TARGET]:
            schema = get_asset_type_schema(asset_type)
            self.assertEqual(schema["status"], "planned")
            self.assertTrue(schema["manifest_fields"])
            self.assertTrue(schema["planned_checks"])
            self.assertIn("default_import_presets", schema)

    def test_unreal_import_preset_manager_uses_asset_type_registry(self):
        manager = UnrealImportPresetManager()
        manifest = {
            "asset_type": ASSET_TYPE_STATIC_PROP,
            "target_platform": TARGET_PLATFORM_HIGH_END_MOBILE,
            "import_preset": "",
        }

        self.assertEqual(manager.preset_name_for_manifest(manifest), IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE)

    def test_skeletal_mesh_manifest_adds_planned_fields_without_changing_static_prop(self):
        static_manifest = create_manifest("SM_Crate_01", "C:/Exports/SM_Crate_01.fbx", "/Game/Props")
        skeletal_manifest = create_skeletal_mesh_manifest(
            "SK_Mannequin",
            "C:/Exports/SK_Mannequin.fbx",
            "/Game/Characters",
            root_joint="root",
            joint_count=86,
            skin_cluster_count=1,
            max_influences=4,
            lods=[{"name": "LOD0"}],
        )

        self.assertEqual(static_manifest["asset_type"], ASSET_TYPE_STATIC_PROP)
        self.assertNotIn("root_joint", static_manifest)
        self.assertEqual(skeletal_manifest["asset_type"], ASSET_TYPE_SKELETAL_MESH)
        self.assertEqual(skeletal_manifest["root_joint"], "root")
        self.assertEqual(skeletal_manifest["joint_count"], 86)
        self.assertEqual(skeletal_manifest["max_influences"], 4)
        self.assertEqual(skeletal_manifest["lods"], [{"name": "LOD0"}])
        self.assertEqual(validate_manifest(skeletal_manifest), [])

    def test_skeletal_mesh_rule_baseline_is_official_source_driven(self):
        baseline = get_skeletal_mesh_rule_baseline()

        self.assertEqual(baseline["status"], "planned")
        self.assertEqual(baseline["fbx_version"], "2020.2")
        self.assertIn("morph_targets", baseline["supported_fbx_features"])
        self.assertIn("max_influences", baseline["planned_checks"])
        self.assertTrue(baseline["maya_export_baseline"]["skins"])
        self.assertTrue(baseline["unreal_import_baseline"]["import_as_skeletal"])
        self.assertTrue(all(source.startswith("https://") for source in baseline["official_sources"]))

    def test_blender_adapter_is_explicitly_planned(self):
        adapter = BlenderAdapter()

        self.assertFalse(adapter.is_available())
        with self.assertRaises(NotImplementedError):
            adapter.get_current_selection()


if __name__ == "__main__":
    unittest.main()
