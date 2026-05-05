from __future__ import absolute_import

import os
import shutil
import tempfile
import time
import unittest

from asset_forge.maya.export_package import build_export_package, build_skeletal_export_package
from asset_forge.shared.manifest_schema import create_manifest, write_manifest
from asset_forge.shared.report_schema import create_skeletal_package_report, write_report, read_report
from asset_forge.shared.skeletal_rule_validator import SkeletalMeshRuleValidator
from asset_forge.shared.skeletal_scan_schema import create_skeletal_scan_result
from asset_forge.unreal.manifest_finder import find_latest_manifest, find_manifest_files
from asset_forge.unreal.pipeline import import_all_manifests, import_latest_manifest, UnrealBatchImportPipeline


class FakeLatestImporter(object):
    def import_static_mesh(self, manifest, preset):
        return [manifest["target_path"] + "/" + manifest["asset_name"]]


class ExportPackageAndLatestManifestTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_export_package_paths_use_asset_folder(self):
        package = build_export_package(self.temp_dir, "SM_Crate_01")

        self.assertTrue(package["package_dir"].endswith("/SM_Crate_01"))
        self.assertTrue(package["fbx_path"].endswith("/SM_Crate_01/SM_Crate_01.fbx"))
        self.assertTrue(package["manifest_path"].endswith("/SM_Crate_01/SM_Crate_01_manifest.json"))
        self.assertTrue(package["export_report_path"].endswith("/SM_Crate_01/SM_Crate_01_export_report.json"))
        self.assertTrue(package["end_to_end_report_path"].endswith("/SM_Crate_01/SM_Crate_01_end_to_end_report.json"))
        self.assertTrue(package["material_profiles_snapshot_path"].endswith("/SM_Crate_01/material_profiles_snapshot.json"))
        self.assertNotIn("\\", package["fbx_path"])

    def test_skeletal_export_package_adds_planned_subdirectories(self):
        package = build_skeletal_export_package(self.temp_dir, "SK_Mannequin")

        self.assertEqual(package["asset_type"], "skeletal_mesh")
        self.assertTrue(package["package_dir"].endswith("/SK_Mannequin"))
        self.assertTrue(package["skeleton_dir"].endswith("/SK_Mannequin/Skeleton"))
        self.assertTrue(package["animations_dir"].endswith("/SK_Mannequin/Animations"))
        self.assertTrue(package["morph_targets_dir"].endswith("/SK_Mannequin/MorphTargets"))
        self.assertTrue(package["skeleton_manifest_path"].endswith("/Skeleton/SK_Mannequin_skeleton.json"))
        self.assertTrue(package["package_report_path"].endswith("/SK_Mannequin/SK_Mannequin_package_report.json"))
        self.assertTrue(os.path.isdir(package["skeleton_dir"]))
        self.assertTrue(os.path.isdir(package["animations_dir"]))
        self.assertTrue(os.path.isdir(package["morph_targets_dir"]))
        self.assertNotIn("\\", package["skeleton_manifest_path"])

    def test_skeletal_package_report_summarizes_reserved_paths_and_validation(self):
        package = build_skeletal_export_package(self.temp_dir, "SK_Mannequin")
        scan = create_skeletal_scan_result(
            "SK_Mannequin",
            root_joint="root",
            joints=["root", "pelvis"],
            skin_clusters=[{"name": "skinCluster1", "max_influences": 4}],
            lods=[{"name": "LOD0"}],
            materials=[{"name": "M_Body"}],
        )
        validation = SkeletalMeshRuleValidator().validate(scan)
        manifest = create_manifest(
            "SK_Mannequin",
            package["fbx_path"],
            "/Game/Characters",
            asset_type="skeletal_mesh",
            package_dir=package["package_dir"],
        )

        report = create_skeletal_package_report(scan, validation, manifest, package)
        write_report(package["package_report_path"], report)
        loaded = read_report(package["package_report_path"])

        self.assertEqual(loaded["stage"], "skeletal_package")
        self.assertEqual(loaded["validation"]["status"], "pass")
        self.assertEqual(loaded["root_joint"], "root")
        self.assertEqual(loaded["joint_count"], 2)
        self.assertTrue(loaded["skeleton_dir"].endswith("/SK_Mannequin/Skeleton"))
        self.assertNotIn("\\", loaded["skeleton_manifest_path"])

    def test_find_latest_manifest_recurses_package_dirs(self):
        old_dir = build_export_package(self.temp_dir, "SM_Old")
        new_dir = build_export_package(self.temp_dir, "SM_New")

        old_manifest = create_manifest(
            "SM_Old",
            old_dir["fbx_path"],
            "/Game/Props",
            package_dir=old_dir["package_dir"],
        )
        new_manifest = create_manifest(
            "SM_New",
            new_dir["fbx_path"],
            "/Game/Props",
            package_dir=new_dir["package_dir"],
        )

        with open(old_dir["fbx_path"], "wb") as stream:
            stream.write(b"old")
        with open(new_dir["fbx_path"], "wb") as stream:
            stream.write(b"new")
        write_manifest(old_dir["manifest_path"], old_manifest)
        time.sleep(0.01)
        write_manifest(new_dir["manifest_path"], new_manifest)

        manifests = find_manifest_files(self.temp_dir)
        latest = find_latest_manifest(self.temp_dir)

        self.assertEqual(len(manifests), 2)
        self.assertTrue(latest.endswith("/SM_New/SM_New_manifest.json"))

    def test_batch_dry_run_writes_batch_report(self):
        first = self._write_package("SM_A")
        second = self._write_package("SM_B")

        report = import_all_manifests(self.temp_dir, dry_run=True)

        self.assertEqual(report["stage"], "batch_import")
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["total"], 2)
        self.assertEqual(report["counts"]["skipped"], 2)
        self.assertTrue(report["summary"]["can_accept"])
        self.assertEqual(report["summary"]["error_count"], 0)
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "batch_dry_run_report.json")))
        self.assertTrue(os.path.exists(os.path.join(first["package_dir"], "SM_A_import_report.json")))
        self.assertTrue(os.path.exists(os.path.join(second["package_dir"], "SM_B_import_report.json")))

    def test_batch_import_uses_injected_item_pipeline(self):
        self._write_package("SM_A")
        self._write_package("SM_B")
        item_pipeline = FakeItemPipeline()

        report = UnrealBatchImportPipeline(item_pipeline=item_pipeline).run(self.temp_dir, dry_run=False)

        self.assertEqual(report["counts"]["success"], 2)
        self.assertEqual(len(item_pipeline.imported), 2)

    def test_batch_report_aggregates_warning_and_error_counts(self):
        self._write_package("SM_A")
        self._write_package("SM_B")
        item_pipeline = MixedResultItemPipeline()

        report = UnrealBatchImportPipeline(item_pipeline=item_pipeline).run(self.temp_dir, dry_run=False)

        self.assertFalse(report["summary"]["can_accept"])
        self.assertEqual(report["summary"]["warning_count"], 1)
        self.assertEqual(report["summary"]["error_count"], 1)
        self.assertEqual(report["summary"]["blocked_assets"], ["SM_B_manifest.json"])
        self.assertEqual(report["summary"]["warning_assets"], ["SM_A_manifest.json"])

    def _write_package(self, asset_name):
        package = build_export_package(self.temp_dir, asset_name)
        with open(package["fbx_path"], "wb") as stream:
            stream.write(b"fake")
        manifest = create_manifest(
            asset_name,
            package["fbx_path"],
            "/Game/Props",
            package_dir=package["package_dir"],
        )
        write_manifest(package["manifest_path"], manifest)
        return package


class FakeItemPipeline(object):
    def __init__(self):
        self.imported = []

    def import_from_manifest(self, manifest_path):
        self.imported.append(manifest_path)
        return {"status": "success", "asset_name": os.path.basename(manifest_path), "issues": []}

    def dry_run_manifest(self, manifest_path):
        return {"status": "skipped", "asset_name": os.path.basename(manifest_path), "issues": []}


class MixedResultItemPipeline(object):
    def import_from_manifest(self, manifest_path):
        asset_name = os.path.basename(manifest_path)
        if asset_name.startswith("SM_B"):
            return {
                "status": "failed",
                "asset_name": asset_name,
                "post_import_validation": {
                    "checks": [
                        {"id": "target_path", "status": "error", "message": "导入路径不符合 Manifest"}
                    ]
                },
            }
        return {
            "status": "success",
            "asset_name": asset_name,
            "material_assignment_report": {"issues": ["材质槽未完全绑定"]},
        }

    def dry_run_manifest(self, manifest_path):
        return self.import_from_manifest(manifest_path)


if __name__ == "__main__":
    unittest.main()
