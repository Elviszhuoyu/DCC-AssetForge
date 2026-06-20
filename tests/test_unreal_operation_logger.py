from __future__ import absolute_import

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.operation_logger import UnrealOperationLogger, latest_log_path, latest_log_summary, read_latest_log_tail, repair_mojibake


def mojibake_from_text(text):
    return text.encode("utf-8").decode("gbk", "ignore")


def mojibake_markers():
    return [
        chr(0x3F) * 4,
        mojibake_from_text("测试"),
        mojibake_from_text("正式"),
        mojibake_from_text("日志"),
        mojibake_from_text("路径"),
        mojibake_from_text("可生成"),
        mojibake_from_text("材质"),
    ]


class UnrealOperationLoggerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_logger_writes_daily_jsonl_and_latest_log(self):
        logger = UnrealOperationLogger(root=self.temp_dir)
        manifest_path = "E:/测试/manifest.json"

        entry = logger.log("unreal_dry_run", "success", inputs={"manifest_path": manifest_path}, outputs={"status": "skipped"})

        self.assertTrue(entry["log_path"].endswith("latest_unreal.log"))
        self.assertTrue(os.path.exists(latest_log_path(self.temp_dir)))
        with open(latest_log_path(self.temp_dir), "r", encoding="utf-8") as stream:
            raw = stream.read()
        data = json.loads(raw.splitlines()[-1])
        self.assertEqual(data["operation"], "unreal_dry_run")
        self.assertEqual(data["source_app"], "unreal")
        self.assertEqual(data["source_dcc"], "unreal")
        self.assertEqual(data["inputs"]["manifest_path"], manifest_path)
        self.assertIn("测试", raw)
        for marker in mojibake_markers():
            self.assertNotIn(marker, raw)

    def test_latest_unreal_log_keeps_normal_chinese_text(self):
        logger = UnrealOperationLogger(root=self.temp_dir)
        note = "正式 UE 日志路径生成验证，不代表真实 UE 导入验收"
        logger.log("unreal_operation_log_smoke", "success", outputs={"note": note})

        with open(latest_log_path(self.temp_dir), "r", encoding="utf-8") as stream:
            raw = stream.read()

        self.assertIn(note, raw)
        for marker in mojibake_markers():
            self.assertNotIn(marker, raw)

    def test_config_material_profiles_have_readable_chinese_network_message(self):
        with open(os.path.join("config", "material_profiles.json"), "r", encoding="utf-8") as stream:
            raw = stream.read()
            data = json.loads(raw)

        self.assertIn("UE Python bootstrap 可生成参数化 PBR 母材质网络", raw)
        for marker in mojibake_markers():
            self.assertNotIn(marker, raw)
        for profile in data["profiles"]:
            self.assertIn("材质", profile.get("material_network_message", ""))

    def test_repair_mojibake_handles_unreal_smoke_note(self):
        good = "正式"
        mojibake = mojibake_from_text(good)
        self.assertEqual(repair_mojibake(mojibake), good)

    def test_cli_package_dry_run_writes_unreal_operation_log(self):
        package = create_offline_static_prop_package(self.temp_dir)

        result = self._run_cli(["--package", "--dry-run", package["package_dir"]])

        self.assertEqual(result.returncode, 0, result.stderr)
        operations = self._latest_operations()
        self.assertIn("unreal_cli_start", operations)
        self.assertIn("unreal_dry_run", operations)
        self.assertIn("unreal_cli_success", operations)

    def test_cli_accept_flow_writes_accept_flow_log(self):
        package = create_offline_static_prop_package(self.temp_dir)
        report_path = os.path.join(self.temp_dir, "acceptance_flow_report.json")

        result = self._run_cli(["--accept-flow", package["package_dir"], report_path])

        self.assertEqual(result.returncode, 0, result.stderr)
        entries = self._latest_entries()
        operations = [entry["operation"] for entry in entries]
        self.assertIn("unreal_accept_flow", operations)
        accept_flow = [entry for entry in entries if entry["operation"] == "unreal_accept_flow"][-1]
        self.assertEqual(accept_flow["outputs"]["package_dir"], package["package_dir"])
        self.assertEqual(accept_flow["report_path"], report_path.replace("\\", "/"))

    def test_cli_failure_writes_failed_log(self):
        result = self._run_cli([])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Usage:", result.stderr)
        self.assertIn("Next action:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        entries = self._latest_entries()
        self.assertEqual(entries[-1]["operation"], "unreal_cli_failed")
        self.assertTrue(entries[-1]["errors"])

    def test_latest_tail_reads_recent_entries_without_large_log_wall(self):
        logger = UnrealOperationLogger(root=self.temp_dir)
        logger.log("unreal_dry_run", "success", outputs={"manifest_path": "E:/测试/A_manifest.json"})
        logger.log("unreal_import", "warning", errors=["需要真实 UE 验证"])

        entries = read_latest_log_tail(self.temp_dir, 1)
        summary = latest_log_summary(self.temp_dir, 1)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["operation"], "unreal_import")
        self.assertEqual(summary[0]["operation"], "unreal_import")
        self.assertIn("error=需要真实 UE 验证", summary[0]["details"])

    def _run_cli(self, args):
        env = os.environ.copy()
        env["ASSET_FORGE_LOG_ROOT"] = self.temp_dir
        return subprocess.run(
            [sys.executable, "scripts/unreal_import_manifest.py"] + args,
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )

    def _latest_entries(self):
        with open(latest_log_path(self.temp_dir), "r", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def _latest_operations(self):
        return [entry["operation"] for entry in self._latest_entries()]


if __name__ == "__main__":
    unittest.main()
