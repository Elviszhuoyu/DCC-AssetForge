from __future__ import absolute_import

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.acceptance_runner import run_asset_forge_package_acceptance


class PathNormalizationReportsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.package = create_offline_static_prop_package(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_accept_flow_normalizes_windows_backslash_input_paths(self):
        package_dir = self.package["package_dir"].replace("/", "\\")

        report = run_asset_forge_package_acceptance(package_dir)

        self.assertNotIn("\\", report["package_dir"])
        self.assertNotIn("\\", report["manifest_path"])
        self.assertEqual(report["package_acceptance"]["target_path"], "/Game/AssetForgeOffline")
        self.assertFalse(report["package_acceptance"]["target_path"].startswith("E:"))

    def test_default_accept_flow_report_path_is_in_package_dir(self):
        report = run_asset_forge_package_acceptance(self.package["package_dir"])
        default_path = os.path.join(self.package["package_dir"], "AssetForgeReports", "package_acceptance_flow_report.json")

        self.assertTrue(os.path.exists(default_path))
        self.assertEqual(report["stage"], "package_acceptance_flow")

    def test_powershell_style_cli_stdout_is_utf8_json(self):
        env = os.environ.copy()
        env["ASSET_FORGE_LOG_ROOT"] = self.temp_dir
        result = subprocess.run(
            [sys.executable, "scripts/unreal_import_manifest.py", "--accept-flow", self.package["package_dir"]],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )

        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertIn("在真实 UE 5.6", report["next_action"])


if __name__ == "__main__":
    unittest.main()
