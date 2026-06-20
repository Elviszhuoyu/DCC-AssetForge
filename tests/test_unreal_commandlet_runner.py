from __future__ import absolute_import

import json
import os
import shutil
import tempfile
import unittest

from asset_forge.unreal.commandlet_runner import (
    build_editor_launch_command,
    build_accept_flow_command,
    build_material_evidence_command,
    close_unreal_crash_reporters,
    find_running_unreal_editors,
    launch_unreal_editor_safe,
    run_accept_flow_commandlet,
    run_accept_flow_with_material_evidence_commandlet,
)
from scripts.unreal_launch_editor_safe import parse_args as parse_editor_launch_args
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

    def test_build_editor_launch_command_uses_ddc_fallback(self):
        command = build_editor_launch_command(
            r"<UNREAL_ENGINE_DRIVE>/UE_5.6\Engine\Binaries\Win64\UnrealEditor.exe",
            r"<LOCAL_WORK_DRIVE>/UE_Pj\UE5\AssetForgeAutomation\AssetForgeAutomation.uproject",
        )

        self.assertEqual(command[0], r"<UNREAL_ENGINE_DRIVE>/UE_5.6\Engine\Binaries\Win64\UnrealEditor.exe")
        self.assertEqual(command[1], "<LOCAL_WORK_DRIVE>/UE_Pj/UE5/AssetForgeAutomation/AssetForgeAutomation.uproject")
        self.assertIn("-ddc=InstalledNoZenLocalFallback", command)
        self.assertIn("-nop4", command)
        self.assertIn("-nosplash", command)

    def test_close_unreal_crash_reporters_targets_only_ue_reporter(self):
        calls = []

        def fake_runner(command, **kwargs):
            calls.append(command)
            return FakeCompleted(returncode=0, stdout="SUCCESS", stderr="")

        report = close_unreal_crash_reporters(runner=fake_runner)

        self.assertEqual(report["status"], "closed")
        self.assertEqual(calls[0], ["taskkill", "/IM", "CrashReportClientEditor.exe", "/F"])

    def test_launch_unreal_editor_safe_cleans_reporter_and_keeps_process_running(self):
        calls = []

        def fake_runner(command, **kwargs):
            calls.append(command)
            return FakeCompleted(returncode=0, stdout="SUCCESS", stderr="")

        report = launch_unreal_editor_safe(
            "UE.exe",
            r"<LOCAL_WORK_DRIVE>/Project\Project.uproject",
            wait_seconds=0,
            popen=lambda command: FakePopen(command, pid=42, returncode=None),
            crash_reporter_runner=fake_runner,
            process_list_runner=lambda command, **kwargs: FakeCompleted(returncode=0, stdout='INFO: No tasks are running which match the specified criteria.', stderr=""),
        )

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["pid"], 42)
        self.assertEqual(report["ddc_mode"], "InstalledNoZenLocalFallback")
        self.assertTrue(report["crash_reporter_cleanup"]["closed"])
        self.assertTrue(report["post_launch_crash_reporter_cleanup"]["closed"])
        self.assertIn("-ddc=InstalledNoZenLocalFallback", report["command"])

    def test_launch_unreal_editor_safe_reuses_existing_editor_by_default(self):
        report = launch_unreal_editor_safe(
            "UE.exe",
            r"<LOCAL_WORK_DRIVE>/Project\Project.uproject",
            wait_seconds=0,
            popen=lambda command: (_ for _ in ()).throw(AssertionError("should not launch a second editor")),
            crash_reporter_runner=lambda command, **kwargs: FakeCompleted(returncode=0, stdout="SUCCESS", stderr=""),
            process_list_runner=lambda command, **kwargs: FakeCompleted(returncode=0, stdout='"UnrealEditor.exe","64776","Console","1","1,024 K"\n', stderr=""),
        )

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["launch_state"], "already_running")
        self.assertFalse(report["did_launch"])
        self.assertEqual(report["pid"], 64776)
        self.assertTrue(report["post_launch_crash_reporter_cleanup"]["closed"])

    def test_find_running_unreal_editors_parses_tasklist_csv(self):
        rows = find_running_unreal_editors(
            runner=lambda command, **kwargs: FakeCompleted(
                returncode=0,
                stdout='"UnrealEditor.exe","64776","Console","1","1,024 K"\n',
                stderr="",
            )
        )

        self.assertEqual(rows, [{"image_name": "UnrealEditor.exe", "pid": 64776}])

    def test_parse_editor_launch_args_defaults_to_crash_reporter_cleanup(self):
        args = parse_editor_launch_args(["UE.exe", "Project.uproject"])

        self.assertEqual(args.ddc_mode, "InstalledNoZenLocalFallback")
        self.assertFalse(args.keep_crash_reporters)
        self.assertFalse(args.force_new)

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

    def test_run_accept_flow_commandlet_absolutizes_report_and_log_paths(self):
        local_temp_dir = tempfile.mkdtemp(dir=os.getcwd())
        self.addCleanup(lambda: os.path.isdir(local_temp_dir) and shutil.rmtree(local_temp_dir))
        abs_report_path = os.path.join(local_temp_dir, "relative_flow.json")
        rel_report_path = os.path.relpath(abs_report_path, os.getcwd())
        rel_package_dir = os.path.relpath(os.path.join(local_temp_dir, "Package"), os.getcwd())
        rel_log_path = os.path.relpath(os.path.join(local_temp_dir, "relative_flow.log"), os.getcwd())
        os.makedirs(os.path.join(local_temp_dir, "Package"))

        def fake_runner(command, **kwargs):
            script_arg = [item for item in command if item.startswith("-script=")][0]
            self.assertIn(abs_report_path.replace("\\", "/"), script_arg)
            self.assertIn(os.path.abspath(rel_package_dir).replace("\\", "/"), script_arg)
            with open(abs_report_path, "w", encoding="utf-8") as stream:
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
            return FakeCompleted(returncode=0, stdout="Python script executed successfully", stderr="")

        report = run_accept_flow_commandlet(
            "UECmd.exe",
            "Project.uproject",
            rel_package_dir,
            rel_report_path,
            log_path=rel_log_path,
            repo_root=self.temp_dir,
            runner=fake_runner,
        )

        self.assertEqual(report["status"], "success")
        self.assertTrue(os.path.exists(abs_report_path))
        self.assertTrue(os.path.exists(os.path.abspath(rel_log_path)))

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


class FakePopen(object):
    def __init__(self, command, pid=1, returncode=None):
        self.command = list(command or [])
        self.pid = pid
        self._returncode = returncode

    def poll(self):
        return self._returncode


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
