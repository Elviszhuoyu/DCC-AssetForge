from __future__ import absolute_import

import json
import os
import shutil
import tempfile
import unittest

from asset_forge.unreal.engine_version_preflight import UnrealEngineVersionPreflight, parse_major_minor


class UnrealEngineVersionPreflightTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.uproject_path = os.path.join(self.temp_dir, "AssetForgeBuildProxy.uproject")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_parse_major_minor_accepts_release_strings(self):
        self.assertEqual(parse_major_minor("5.5.4-Release"), (5, 5))
        self.assertEqual(parse_major_minor("UE_5.6"), (5, 6))
        self.assertIsNone(parse_major_minor("custom-guid"))

    def test_matching_manifest_runtime_and_project_passes(self):
        self._write_uproject("5.5")

        report = UnrealEngineVersionPreflight(
            unreal_module=FakeUnreal("5.5.4-Release", self.uproject_path)
        ).check({"target_engine_version": "5.5"})

        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["can_write_assets"])

    def test_manifest_runtime_mismatch_blocks_writes(self):
        self._write_uproject("5.5")

        report = UnrealEngineVersionPreflight(
            unreal_module=FakeUnreal("5.5.4-Release", self.uproject_path)
        ).check({"target_engine_version": "5.6"})

        self.assertEqual(report["status"], "error")
        self.assertFalse(report["can_write_assets"])
        self.assertIn("5.6", report["errors"][0]["message"])

    def test_project_release_lines_are_checked_before_writing(self):
        for runtime in ("5.3.2", "5.6.1", "5.8.4"):
            project_version = ".".join(runtime.split(".")[:2])
            self._write_uproject(project_version)
            guard = UnrealEngineVersionPreflight(unreal_module=FakeUnreal(runtime, self.uproject_path))
            for target in ("5.3", "5.6", "5.8", "not-a-version"):
                with self.subTest(runtime=runtime, target=target):
                    self.assertEqual(guard.check({"target_engine_version": target})["can_write_assets"], target == project_version)

    def test_unreadable_runtime_cannot_report_a_version_match(self):
        guard = UnrealEngineVersionPreflight(unreal_module=FakeUnreal("custom-build", ""))
        self.assertEqual(guard.check({"target_engine_version": "5.8"})["status"], "warning")

    def test_missing_runtime_reports_warning_not_block(self):
        report = UnrealEngineVersionPreflight(unreal_module=FakeUnreal("", "")).check({"target_engine_version": "5.5"})

        self.assertEqual(report["status"], "warning")
        self.assertTrue(report["can_write_assets"])

    def _write_uproject(self, engine_association):
        with open(self.uproject_path, "w", encoding="utf-8") as stream:
            json.dump({"EngineAssociation": engine_association}, stream)


class FakeUnreal(object):
    def __init__(self, engine_version, project_file_path):
        self.SystemLibrary = FakeSystemLibrary(engine_version)
        self.Paths = FakePaths(project_file_path)


class FakeSystemLibrary(object):
    def __init__(self, engine_version):
        self.engine_version = engine_version

    def get_engine_version(self):
        return self.engine_version


class FakePaths(object):
    def __init__(self, project_file_path):
        self.project_file_path = project_file_path

    def get_project_file_path(self):
        return self.project_file_path


if __name__ == "__main__":
    unittest.main()
