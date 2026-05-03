from __future__ import absolute_import

import unittest

from asset_forge.blender.adapter import BlenderAdapter
from asset_forge.shared.asset_type_schema import get_asset_type_schema
from asset_forge.shared.constants import (
    ASSET_TYPE_ANIMATION,
    ASSET_TYPE_MORPH_TARGET,
    ASSET_TYPE_SKELETAL_MESH,
    ASSET_TYPE_STATIC_PROP,
)


class FutureAssetSchemaTest(unittest.TestCase):
    def test_static_prop_schema_is_implemented(self):
        schema = get_asset_type_schema(ASSET_TYPE_STATIC_PROP)

        self.assertEqual(schema["status"], "implemented")
        self.assertIn("lightmap_uv", schema["planned_checks"])

    def test_future_asset_types_have_manifest_fields(self):
        for asset_type in [ASSET_TYPE_SKELETAL_MESH, ASSET_TYPE_ANIMATION, ASSET_TYPE_MORPH_TARGET]:
            schema = get_asset_type_schema(asset_type)
            self.assertEqual(schema["status"], "planned")
            self.assertTrue(schema["manifest_fields"])
            self.assertTrue(schema["planned_checks"])

    def test_blender_adapter_is_explicitly_planned(self):
        adapter = BlenderAdapter()

        self.assertFalse(adapter.is_available())
        with self.assertRaises(NotImplementedError):
            adapter.get_current_selection()


if __name__ == "__main__":
    unittest.main()
