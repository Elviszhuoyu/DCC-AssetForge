from __future__ import absolute_import

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from scripts import unreal_import_manifest


class UnrealImportScriptArgsTest(unittest.TestCase):
    def _run_script_in_temp(self, args):
        script_path = os.path.abspath("scripts/unreal_import_manifest.py")
        return subprocess.run(
            [sys.executable, script_path] + args,
            cwd=os.getcwd(),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_print_json_normalizes_unreal_enum_like_values(self):
        class FakeTextureGroup(object):
            name = "TEXTUREGROUP_WORLD"

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            unreal_import_manifest._print_json({"actual_policy": {"texture_group": FakeTextureGroup()}})

        report = json.loads(stdout.getvalue())
        self.assertEqual(report["actual_policy"]["texture_group"], "TEXTUREGROUP_WORLD")

    def test_cli_guidance_prints_to_stderr_without_polluting_json_stdout(self):
        stderr = io.StringIO()
        report = {
            "summary": {
                "decision_label": "可以导入/验收",
                "decision": "ready",
                "can_import": True,
                "next_action": "继续执行真实导入",
                "why": ["没有阻断项"],
                "next_steps": [{"label": "继续", "detail": "打开 UE Gate 执行导入"}],
            }
        }

        with contextlib.redirect_stderr(stderr):
            unreal_import_manifest._print_cli_report_guidance(report, unreal_import_manifest._mode_flags([]))

        text = stderr.getvalue()
        self.assertIn("DCC AssetForge guidance:", text)
        self.assertIn("decision_label: 可以导入/验收", text)
        self.assertIn("decision: ready", text)
        self.assertIn("can_import: true", text)
        self.assertIn("next_action: 继续执行真实导入", text)

    def test_help_prints_usage_without_manifest_path(self):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/unreal_import_manifest.py",
                "--help",
            ],
            cwd=os.getcwd(),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertIn("Usage:", result.stdout)
        self.assertIn("--contract-check", result.stdout)
        self.assertIn("--latest", result.stdout)
        self.assertIn("--all", result.stdout)
        self.assertIn("--validate-all-packages", result.stdout)
        self.assertIn("--accept-flow-all", result.stdout)
        self.assertIn("--require-import", result.stdout)
        self.assertIn("--pretest-check", result.stdout)
        self.assertIn("--offline-evidence-bundle", result.stdout)
        self.assertIn("[offline_evidence_report]", result.stdout)
        self.assertIn("--portfolio-demo-pack", result.stdout)
        self.assertIn("--portfolio-evidence-manifest", result.stdout)
        self.assertIn("--offline-evidence-bundle -> --portfolio-demo-pack -> --portfolio-evidence-manifest", result.stdout)
        self.assertIn("需要第一步生成的 offline evidence bundle report", result.stdout)
        self.assertIn("需要第二步生成的 portfolio demo pack report", result.stdout)
        self.assertIn("--gate-ui", result.stdout)
        self.assertIn("--import-options-json", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_portfolio_demo_pack_without_evidence_input_warns_with_next_action(self):
        import tempfile

        script_path = os.path.abspath("scripts/unreal_import_manifest.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    script_path,
                    "--portfolio-demo-pack",
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            report = json.loads(result.stdout)
            self.assertEqual(report["stage"], "portfolio_demo_pack")
            self.assertEqual(report["status"], "warning")
            self.assertEqual(report["warnings"][0]["id"], "missing_offline_evidence_bundle")
            self.assertIn("--offline-evidence-bundle", report["next_action"])
            self.assertIn("--portfolio-demo-pack", report["next_action"])
            self.assertEqual(result.stderr, "")

    def test_portfolio_evidence_manifest_without_demo_pack_warns_with_chain_next_action(self):
        import tempfile

        script_path = os.path.abspath("scripts/unreal_import_manifest.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    script_path,
                    "--portfolio-evidence-manifest",
                ],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            report = json.loads(result.stdout)
            self.assertEqual(report["stage"], "portfolio_evidence_manifest")
            self.assertEqual(report["status"], "warning")
            self.assertEqual(report["warnings"][0]["id"], "missing_portfolio_demo_pack")
            self.assertIn("--offline-evidence-bundle -> --portfolio-demo-pack -> --portfolio-evidence-manifest", report["next_action"])
            self.assertEqual(result.stderr, "")

    def test_portfolio_readiness_cli_outputs_review_sheet(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = os.path.join(temp_dir, "offline_evidence.json")
            with open(evidence_path, "w", encoding="utf-8") as stream:
                json.dump(
                    {
                        "stage": "offline_evidence_bundle",
                        "portfolio_evidence_manifest": {
                            "stage": "portfolio_evidence_manifest",
                            "capture_summary": {
                                "total_capture_count": 3,
                                "captured_capture_count": 1,
                                "missing_capture_count": 2,
                                "next_capture": "ue_gate_click_capture",
                            },
                        },
                    },
                    stream,
                    ensure_ascii=False,
                )

            result = self._run_script_in_temp(["--portfolio-readiness", evidence_path])
            report = json.loads(result.stdout)

        self.assertEqual(report["stage"], "portfolio_readiness")
        review_sheet = report["portfolio_review_sheet"]
        self.assertIn("{0}/100".format(report["score"]), review_sheet["summary_line"])
        self.assertIn("1/3", review_sheet["capture_line"])
        self.assertIn("ue_gate_click_capture", review_sheet["capture_line"])
        self.assertLessEqual(len(review_sheet["first_actions"]), 3)
        self.assertIn("UBT", review_sheet["proof_boundary"])
        self.assertEqual(result.stderr, "")

    def test_portfolio_cli_report_path_preserves_artifact_args_and_clean_stderr_on_missing_upstream(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_evidence_path = os.path.join(temp_dir, "missing_offline_evidence.json")
            demo_report_path = os.path.join(temp_dir, "portfolio_demo_pack.json")
            demo_result = self._run_script_in_temp(
                [
                    "--portfolio-demo-pack",
                    missing_evidence_path,
                    demo_report_path,
                ]
            )

            demo_report = json.loads(demo_result.stdout)
            with open(demo_report_path, encoding="utf-8") as stream:
                written_demo_report = json.load(stream)
            self.assertEqual(demo_report["status"], "warning")
            self.assertEqual(demo_report["warnings"][0]["id"], "missing_offline_evidence_bundle")
            self.assertEqual(demo_result.stderr, "")
            self.assertEqual(demo_report["report_artifact"]["file_name"], "portfolio_demo_pack.json")
            self.assertEqual(written_demo_report["report_artifact"], demo_report["report_artifact"])
            self.assertIn("--portfolio-demo-pack", demo_report["command_args"])
            self.assertIn(missing_evidence_path, demo_report["command_args"])

            missing_demo_pack_path = os.path.join(temp_dir, "missing_demo_pack.json")
            capture_root = os.path.join(temp_dir, "captures")
            manifest_report_path = os.path.join(temp_dir, "portfolio_evidence_manifest.json")
            manifest_result = self._run_script_in_temp(
                [
                    "--portfolio-evidence-manifest",
                    missing_demo_pack_path,
                    capture_root,
                    manifest_report_path,
                ]
            )

            manifest_report = json.loads(manifest_result.stdout)
            with open(manifest_report_path, encoding="utf-8") as stream:
                written_manifest_report = json.load(stream)
            self.assertEqual(manifest_report["status"], "warning")
            self.assertEqual(manifest_report["warnings"][0]["id"], "missing_portfolio_demo_pack")
            self.assertEqual(manifest_result.stderr, "")
            self.assertEqual(manifest_report["report_artifact"]["file_name"], "portfolio_evidence_manifest.json")
            self.assertEqual(written_manifest_report["report_artifact"], manifest_report["report_artifact"])
            self.assertIn("--portfolio-evidence-manifest", manifest_report["command_args"])
            self.assertIn(missing_demo_pack_path, manifest_report["command_args"])

    def test_bad_usage_prints_usage_and_next_action_without_traceback(self):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/unreal_import_manifest.py",
                "--contract-check",
            ],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("Usage:", result.stderr)
        self.assertIn("Next action:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_pretest_check_with_explicit_repo_root_does_not_run_contract_on_repo(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = os.path.join(temp_dir, "pretest.json")
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/unreal_import_manifest.py",
                    "--pretest-check",
                    os.getcwd(),
                    report_path,
                ],
                cwd=os.getcwd(),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            report = json.loads(result.stdout)
            self.assertEqual(report["stage"], "asset_forge_doctor")
            self.assertNotEqual(report["status"], "error")
            self.assertTrue(report["can_accept"])
            self.assertFalse(any(item["id"] == "interface_contract" for item in report["checks"]))
            self.assertTrue(os.path.exists(report_path))

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
                encoding="utf-8",
                env=self._env(temp_dir),
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "skipped")
            self.assertEqual(report["asset_name"], "SM_Crate_01")
            self.assertIn("DCC AssetForge guidance:", result.stderr)
            self.assertIn("decision_label:", result.stderr)
            self.assertIn("can_import:", result.stderr)
            self.assertIn("next_action:", result.stderr)
            self.assertIn("预检查", result.stdout)
        finally:
            self._remove_tree(temp_dir)

    def test_package_dry_run_accepts_import_options_json(self):
        temp_dir = self._make_package()

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/unreal_import_manifest.py",
                    "--package",
                    "--dry-run",
                    "--import-options-json",
                    json.dumps(
                        {
                            "combine_meshes": True,
                            "auto_generate_collision": True,
                            "import_mesh_lods": False,
                            "vertex_color_import_option": "OVERRIDE",
                        }
                    ),
                    temp_dir,
                ],
                cwd=os.getcwd(),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=self._env(temp_dir),
            )
            report = json.loads(result.stdout)
            options = report["fbx_import_options_report"]["options"]
            self.assertTrue(options["combine_meshes"])
            self.assertTrue(options["auto_generate_collision"])
            self.assertFalse(options["import_mesh_lods"])
            self.assertEqual(options["vertex_color_import_option"], "override")
        finally:
            self._remove_tree(temp_dir)

    def test_import_options_json_error_prints_usage_without_traceback(self):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/unreal_import_manifest.py",
                "--package",
                "--import-options-json",
                "[1, 2, 3]",
                "E:/MissingPackage",
            ],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("--import-options-json", result.stderr)
        self.assertIn("Usage:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

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
                encoding="utf-8",
                env=self._env(temp_dir),
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["stage"], "package_acceptance")
            self.assertTrue(os.path.exists(report_path))
        finally:
            self._remove_tree(temp_dir)

    def test_validate_all_packages_flag_writes_batch_acceptance_report(self):
        temp_dir = self._make_package()
        report_path = os.path.join(temp_dir, "batch_acceptance_report.json")

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/unreal_import_manifest.py",
                    "--validate-all-packages",
                    temp_dir,
                    report_path,
                ],
                cwd=os.getcwd(),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=self._env(temp_dir),
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["stage"], "batch_package_acceptance")
            self.assertEqual(report["total"], 1)
            self.assertTrue(os.path.exists(report_path))
        finally:
            self._remove_tree(temp_dir)

    def test_accept_flow_flag_writes_unified_flow_report_without_real_import(self):
        temp_dir = self._make_package()
        report_path = os.path.join(temp_dir, "acceptance_flow_report.json")

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/unreal_import_manifest.py",
                    "--accept-flow",
                    temp_dir,
                    report_path,
                ],
                cwd=os.getcwd(),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=self._env(temp_dir),
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["stage"], "package_acceptance_flow")
            self.assertEqual(report["dry_run"]["status"], "skipped")
            self.assertEqual(report["import"]["stage"], "import")
            self.assertTrue(os.path.exists(report_path))
            self.assertIn("next_action", report)
            self.assertIn("DCC AssetForge guidance:", result.stderr)
            self.assertIn("decision:", result.stderr)
            self.assertIn("next_steps:", result.stderr)
        finally:
            self._remove_tree(temp_dir)

    def test_accept_flow_all_flag_writes_batch_unified_flow_report(self):
        temp_dir = self._make_package()
        report_path = os.path.join(temp_dir, "batch_acceptance_flow_report.json")

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/unreal_import_manifest.py",
                    "--accept-flow-all",
                    temp_dir,
                    report_path,
                ],
                cwd=os.getcwd(),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=self._env(temp_dir),
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["stage"], "batch_package_acceptance_flow")
            self.assertEqual(report["total"], 1)
            self.assertIn("warning_packages", report["summary"])
            self.assertTrue(os.path.exists(report_path))
            self.assertIn("DCC AssetForge guidance:", result.stderr)
            self.assertIn("decision_label:", result.stderr)
        finally:
            self._remove_tree(temp_dir)

    def _make_package(self):
        temp_dir = tempfile.mkdtemp()
        create_offline_static_prop_package(temp_dir, asset_name="SM_Crate_01")
        return temp_dir

    def _remove_tree(self, path):
        import shutil

        shutil.rmtree(path)

    def _env(self, log_root):
        env = os.environ.copy()
        env["ASSET_FORGE_LOG_ROOT"] = log_root
        return env


if __name__ == "__main__":
    unittest.main()
