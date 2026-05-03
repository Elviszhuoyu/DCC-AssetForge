from __future__ import absolute_import

import importlib.util
import unittest

from asset_forge.maya.module_package_schema import (
    get_maya_module_package_plan,
    read_maya_module_descriptor,
    validate_maya_module_package,
)


class MayaModulePackageTest(unittest.TestCase):
    def test_maya_module_package_is_valid(self):
        self.assertEqual(validate_maya_module_package(), [])

    def test_descriptor_maps_repo_root_and_maya_package_dirs(self):
        lines = read_maya_module_descriptor()

        self.assertIn("+ AssetForge 0.1 ../..", lines)
        self.assertIn("scripts: integrations/maya/scripts", lines)
        self.assertIn("icons: integrations/maya/icons", lines)
        self.assertIn("plug-ins: integrations/maya/plug-ins", lines)
        self.assertIn("PYTHONPATH +:= .", lines)

    def test_entry_script_exports_expected_functions(self):
        plan = get_maya_module_package_plan()
        spec = importlib.util.spec_from_file_location("asset_forge_maya", plan["entry_script"])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for function_name in plan["entry_functions"]:
            self.assertTrue(callable(getattr(module, function_name)))


if __name__ == "__main__":
    unittest.main()
