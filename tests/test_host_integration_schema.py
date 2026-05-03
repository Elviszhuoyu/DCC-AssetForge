from __future__ import absolute_import

import unittest

from asset_forge.shared.constants import SOURCE_DCC_BLENDER, SOURCE_DCC_MAYA, TARGET_ENGINE_UNREAL
from asset_forge.shared.host_integration_schema import (
    get_host_integration_contract,
    get_host_integration_contracts,
    validate_host_integration_contracts,
)


class HostIntegrationSchemaTest(unittest.TestCase):
    def test_default_host_contracts_are_valid(self):
        contracts = get_host_integration_contracts()

        self.assertEqual(validate_host_integration_contracts(contracts), [])

    def test_maya_adapter_is_not_the_maya_module_package(self):
        maya = get_host_integration_contract(SOURCE_DCC_MAYA)

        self.assertEqual(maya["package_type"], "maya_module")
        self.assertEqual(maya["official_descriptor"], ".mod")
        self.assertEqual(maya["descriptor_path"], "integrations/maya/AssetForge.mod")
        self.assertIn("integrations/maya/scripts", maya["expected_package_roots"])
        self.assertIn("maya.cmds", maya["runtime_api"])
        self.assertFalse(maya["adapter_is_package"])

    def test_blender_requires_extension_gate_before_adapter_work(self):
        blender = get_host_integration_contract(SOURCE_DCC_BLENDER)

        self.assertEqual(blender["package_type"], "blender_extension")
        self.assertEqual(blender["official_descriptor"], "blender_manifest.toml")
        self.assertEqual(blender["descriptor_path"], "integrations/blender/asset_forge_extension/blender_manifest.toml")
        self.assertEqual(blender["status"], "planned")
        self.assertFalse(blender["adapter_is_package"])

    def test_unreal_plugin_contract_owns_assetforge_mount(self):
        unreal = get_host_integration_contract(TARGET_ENGINE_UNREAL)

        self.assertEqual(unreal["package_type"], "unreal_plugin")
        self.assertEqual(unreal["official_descriptor"], "Plugins/AssetForge/AssetForge.uplugin")
        self.assertEqual(unreal["content_mount"], "/AssetForge")
        self.assertFalse(unreal["adapter_is_package"])


if __name__ == "__main__":
    unittest.main()
