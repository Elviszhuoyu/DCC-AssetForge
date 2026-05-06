from __future__ import absolute_import

import ast
import os
import subprocess
import sys
import unittest

from asset_forge.shared.constants import IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE, TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.manifest_schema import create_manifest, write_manifest


class UnrealImportScriptArgsTest(unittest.TestCase):
    def test_package_flag_can_appear_before_path(self):
        temp_dir = self._make_package()

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/unreal_import_manifest.py",
                    "--package",
                    "--dry-run",
                    temp_dir,
                ],
                cwd=os.getcwd(),
                check=True,
                capture_output=True,
                text=True,
            )
            report = ast.literal_eval(result.stdout.strip())
            self.assertEqual(report["status"], "skipped")
            self.assertEqual(report["asset_name"], "SM_Crate_01")
        finally:
            self._remove_tree(temp_dir)

    def test_validate_package_flag_writes_acceptance_report(self):
        temp_dir = self._make_package()
        report_path = os.path.join(temp_dir, "acceptance_report.json")

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/unreal_import_manifest.py",
                    "--validate-package",
                    temp_dir,
                    report_path,
                ],
                cwd=os.getcwd(),
                check=True,
                capture_output=True,
                text=True,
            )
            report = ast.literal_eval(result.stdout.strip())
            self.assertEqual(report["stage"], "package_acceptance")
            self.assertTrue(os.path.exists(report_path))
        finally:
            self._remove_tree(temp_dir)

    def _make_package(self):
        import tempfile

        temp_dir = tempfile.mkdtemp()
        fbx_path = os.path.join(temp_dir, "SM_Crate_01.fbx")
        with open(fbx_path, "wb") as stream:
            stream.write(b"fake fbx")
        manifest = create_manifest(
            "SM_Crate_01",
            fbx_path,
            "/Game/Props",
            checks={},
            score=100,
            target_platform=TARGET_PLATFORM_HIGH_END_MOBILE,
            import_preset=IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
        )
        write_manifest(os.path.join(temp_dir, "SM_Crate_01_manifest.json"), manifest)
        return temp_dir

    def _remove_tree(self, path):
        import shutil

        shutil.rmtree(path)


if __name__ == "__main__":
    unittest.main()
