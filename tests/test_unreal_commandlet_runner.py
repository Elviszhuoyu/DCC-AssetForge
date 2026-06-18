from __future__ import absolute_import

import json
import os
import shutil
import tempfile
import unittest

from asset_forge.unreal.commandlet_runner import (
    build_accept_flow_command,
    build_material_evidence_command,
    run_accept_flow_commandlet,
    run_accept_flow_with_material_evidence_commandlet,
)
from scripts.unreal_run_accept_flow_commandlet import parse_args


class UnrealCommandletRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_build_accept_flow_command_uses_forward_slashes_and_ddc_fallback(self):
        command = build_accept_flow_command(
            r"<UNREAL_ENGINE_DRIVE>/UE_5.6\Engine\Binaries\Win64\UnrealEditor-Cmd.exe",
            r"<LOCAL_WORK_DRIVE>/UE_Pj\UE5\AssetForgeAutomation\AssetForgeAutomation.uproject",
            r"E:\Repo\scripts\ue_cleanup_accept_flow.py",
            r"E:\Repo\Package\SM_B",
            r"E:\Repo\Reports\flow.json",
            "/Game/Props/Test",
        )

        script_arg = [item for item in command if item.startswith("-script=")][0]
        self.assertIn("E:/Repo/scripts/ue_cleanup_accept_flow.py", script_arg)
        self.assertIn("E:/Repo/Package/SM_B", script_arg)
        self.assertIn("E:/Repo/Reports/flow.json", script_arg)
        self.assertNotIn("\\u", script_arg.lower())
        self.assertIn("-ddc=InstalledNoZenLocalFallback", command)
        self.assertIn("-NullRHI", command)

    def test_build_material_evidence_command_uses_cold_start_readback(self):
        command = build_material_evidence_command(
            r"<UNREAL_ENGINE_DRIVE>/UE_5.6\Engine\Binaries\Win64\UnrealEditor-Cmd.exe",
            r"<LOCAL_WORK_DRIVE>/UE_Pj\UE5\AssetForgeAutomation\AssetForgeAutomation.uproject",
            r"E:\Repo\scripts\unreal_collect_material_evidence.py",
            r"E:\Repo\Reports\flow.json",
            r"E:\Repo\Reports\flow_material.json",
        )

        script_arg = [item for item in command if item.startswith("-script=")][0]
        self.assertIn("E:/Repo/scripts/unreal_collect_material_evidence.py", script_arg)
        self.assertIn("E:/Repo/Reports/flow.json", script_arg)
        self.assertIn("E:/Repo/Reports/flow_material.json", script_arg)
        self.assertIn("--cold-start-readback", script_arg)
        self.assertNotIn("\\u", script_arg.lower())
        self.assertIn("-ddc=InstalledNoZenLocalFallback", command)

    def test_run_accept_flow_commandlet_returns_success_from_json_report(self):
        report_path = os.path.join(self.temp_dir, "flow.json")
        log_path = os.path.join(self.temp_dir, "flow.log")

        def fake_runner(command, **kwargs):
            with open(report_path, "w", encoding="utf-8") as stream:
                json.dump(
                    {
                        "status": "warning",
                        "gate_status": "pass",
                        "gate_passed": True,
                        "can_accept": True,
                        "can_import": True,
                        "report_path": report_path,
                        "warnings": [{"source": "test", "message": "warning is non-blocking"}],
                        "errors": [],
                        "import": {"status": "success", "post_import_validation": {"status": "pass"}},
                    },
                    stream,
                )
            return FakeCompleted(returncode=0, stdout="Python script executed successfully", stderr="")

        report = run_accept_flow_commandlet(
            "UECmd.exe",
            "Project.uproject",
            "Package",
            report_path,
            log_path=log_path,
            repo_root=self.temp_dir,
            runner=fake_runner,
        )

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["process_exit_code"], 0)
        self.assertTrue(report["gate_passed"])
        self.assertEqual(report["post_import_validation"], "pass")
        self.assertTrue(os.path.exists(log_path))

    def test_run_accept_flow_commandlet_flags_missing_report_as_error(self):
        report_path = os.path.join(self.temp_dir, "missing.json")

        report = run_accept_flow_commandlet(
            "UECmd.exe",
            "Project.uproject",
            "Package",
            report_path,
            repo_root=self.temp_dir,
            runner=lambda command, **kwargs: FakeCompleted(returncode=1, stdout="", stderr="failed"),
        )

        self.assertEqual(report["status"], "error")
        self.assertEqual(report["process_exit_code"], 1)
        self.assertFalse(report["gate_passed"])

    def test_run_accept_flow_with_material_evidence_runs_second_fresh_commandlet(self):
        report_path = os.path.join(self.temp_dir, "flow.json")
        log_path = os.path.join(self.temp_dir, "flow.log")
        material_report_path = os.path.join(self.temp_dir, "flow_material.json")
        material_log_path = os.path.join(self.temp_dir, "flow_material.log")
        commands = []

        def fake_runner(command, **kwargs):
            commands.append(command)
            script_arg = [item for item in command if item.startswith("-script=")][0]
            if "ue_cleanup_accept_flow.py" in script_arg:
                with open(report_path, "w", encoding="utf-8") as stream:
                    json.dump(
                        {
                            "status": "success",
                            "gate_status": "pass",
                            "gate_passed": True,
                            "can_accept": True,
                            "can_import": True,
                            "warnings": [],
                            "errors": [],
                            "import": {"status": "success", "post_import_validation": {"status": "pass"}},
                        },
                        stream,
                    )
            elif "unreal_collect_material_evidence.py" in script_arg:
                with open(material_report_path, "w", encoding="utf-8") as stream:
                    json.dump(_material_report(), stream)
            else:
                raise AssertionError("unexpected command: {0}".format(script_arg))
            return FakeCompleted(returncode=0, stdout="ok", stderr="")

        report = run_accept_flow_with_material_evidence_commandlet(
            "UECmd.exe",
            "Project.uproject",
            "Package",
            report_path,
            log_path=log_path,
            material_report_path=material_report_path,
            material_log_path=material_log_path,
            repo_root=self.temp_dir,
            runner=fake_runner,
        )

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["stage"], "ue_accept_flow_with_material_evidence_commandlet")
        self.assertEqual(report["accept_flow_status"], "success")
        self.assertEqual(report["material_status"], "success")
        self.assertEqual(report["real_graph_status"], "pass")
        self.assertEqual(report["comment_blocks_status"], "pass")
        self.assertEqual(report["cold_start_readback_status"], "pass")
        self.assertEqual(report["material_report_path"], material_report_path.replace("\\", "/"))
        self.assertTrue(os.path.exists(log_path))
        self.assertTrue(os.path.exists(material_log_path))
        self.assertEqual(len(commands), 2)

    def test_parse_args_keeps_legacy_positionals_and_material_flags(self):
        args = parse_args(
            [
                "UECmd.exe",
                "Project.uproject",
                "Package",
                "flow.json",
                "/Game/Props/Test",
                "flow.log",
                "--with-material-evidence",
                "--material-report",
                "flow_material.json",
                "--material-log",
                "flow_material.log",
            ]
        )

        self.assertEqual(args.unreal_editor_cmd, "UECmd.exe")
        self.assertEqual(args.target_path, "/Game/Props/Test")
        self.assertEqual(args.log_path, "flow.log")
        self.assertTrue(args.with_material_evidence)
        self.assertEqual(args.material_report, "flow_material.json")
        self.assertEqual(args.material_log, "flow_material.log")


class FakeCompleted(object):
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _material_report():
    return {
        "status": "success",
        "can_accept": True,
        "import": {
            "status": "success",
            "ta_visual_review_status": "manual_validation_required",
            "screenshot_evidence_status": "not_provided",
            "ta_visual_review_next_action": "capture a real UE material graph screenshot",
            "material_graph_evidence_report": {"status": "warning"},
            "real_ue_material_graph": {
                "status": "pass",
                "materials": [
                    {
                        "material_path": "/AssetForge/Materials/M_AF_Props_Master",
                        "comment_blocks": {
                            "status": "pass",
                            "expected_af_comments": 7,
                            "linked_graph_comments": 7,
                            "visible_graph_comments_with_size": 7,
                            "invalid_graph_comment_dimensions": 0,
                            "cold_start_readback_status": "pass",
                        },
                    }
                ],
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
